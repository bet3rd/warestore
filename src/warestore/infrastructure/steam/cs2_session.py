# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd
# Approach ported from fakearchie/nfatool (MIT) — https://github.com/fakearchie/nfatool

"""One CM logon as an account, talking to the CS2 Game Coordinator.

Logs on with persona Offline, marks the account as playing CS2 only for the
lifetime of the ``with`` block, and always stops "playing" and disconnects on
exit. ``web_only=True`` is a plain logon that never starts CS2 — for an account
that is playing elsewhere — so only the web steps (GCPD, Workshop) work.
MUST run off the Qt thread (ValvePython/gevent).
"""

from __future__ import annotations

import logging
import secrets
import time
from urllib.parse import quote

from warestore.infrastructure.steam import cs2_gc_proto as gp
from warestore.infrastructure.steam.cs2_cm_mint import (
    _clean_token,
    _jwt_sub,
    mint_access_token,
    open_cm_client,
)
from warestore.infrastructure.steam.cs2_workshop_web import WorkshopWebClient
from warestore.infrastructure.steam.gcpd_parser import Cs2Rank
from warestore.infrastructure.steam.gcpd_scrape_gateway import Cs2RankScrapeGateway

logger = logging.getLogger(__name__)

# Sentinel: the web access token hasn't been minted yet this session (as
# opposed to a mint that was tried and failed, which caches None).
_UNSET = object()


class AccountInUseError(Exception):
    """Steam on this PC is using the account (or CS2 is running on it)."""


class GcUnavailableError(Exception):
    """The CS2 Game Coordinator didn't answer (no CS2 license, outage, or an
    outdated GC_CLIENT_VERSION)."""


def _steam_registry() -> tuple[int, int]:
    """(active_user_id32, running_app_id), each 0 when missing/unreadable."""
    import winreg

    active = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as key:
            active = int(winreg.QueryValueEx(key, "ActiveUser")[0] or 0)
    except OSError:
        pass
    running = 0
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            running = int(winreg.QueryValueEx(key, "RunningAppID")[0] or 0)
    except OSError:
        pass
    return active, running


def _process_names() -> set[str]:
    import psutil

    return {(p.info.get("name") or "").lower() for p in psutil.process_iter(["name"])}


def account_in_use(steamid64: int) -> str | None:
    """Human reason the account must be skipped, else None.

    Steam on this PC may be LOGGED INTO the account as long as it isn't
    PLAYING anything here (another device's play session is caught separately,
    via the GC's ``ClientPlayingSessionState`` notice during the hello)."""
    active, running_app = _steam_registry()
    names = _process_names()
    logged_in_here = "steam.exe" in names and active == (steamid64 & 0xFFFFFFFF)
    if logged_in_here and (running_app != 0 or "cs2.exe" in names):
        return "playing a game on this PC"
    return None


def _default_gc_factory(client):
    from steam.client.gc import GameCoordinator

    return GameCoordinator(client, gp.CS2_APP_ID)


class Cs2Session:
    HELLO_TIMEOUT = 25.0     # whole welcome budget
    HELLO_RETRY = 4.0        # resend hello this often
    EQUIP_REPLY_TIMEOUT = 8.0
    REPLY_TIMEOUT = 12.0

    def __init__(
        self,
        refresh_token: str,
        *,
        read_only: bool = False,  # kept for compatibility; no longer affects the in-use rule
        web_only: bool = False,
        logon=open_cm_client,
        gc_factory=None,
        in_use_probe=account_in_use,
        workshop_factory=WorkshopWebClient,
        gcpd_factory=Cs2RankScrapeGateway,
        deadline: float | None = None,
    ) -> None:
        self._token = _clean_token(refresh_token)
        self._read_only = read_only
        self._web_only = web_only
        self._logon = logon
        self._gc_factory = gc_factory or _default_gc_factory
        self._in_use_probe = in_use_probe
        self._workshop_factory = workshop_factory
        self._gcpd_factory = gcpd_factory
        self._deadline = deadline
        self._client = None
        self._gc = None
        self._welcome = b""
        self._mm_hello: bytes | None = None
        self._equip_replies: list[int] = []
        self._playing_blocked = False
        self._access_token_cache = _UNSET
        self._gcpd_account: tuple[int, int] | None = None
        self.steamid = 0
        self.account_id = 0

    # --- lifecycle -----------------------------------------------------------

    def _budget(self, want: float) -> float:
        """``want`` capped by the time left before ``self._deadline``.

        Raises ``GcUnavailableError`` once there's no time left, rather than
        letting a wait run with a non-positive/negative timeout."""
        if self._deadline is None:
            return want
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            raise GcUnavailableError("time limit")
        return min(want, remaining)

    def __enter__(self) -> "Cs2Session":
        if self._web_only:
            # The caller already knows the account is in use; this logon never
            # starts CS2, so it can't disturb the session that's playing.
            self._client, self.steamid, self._token = self._logon(self._token, deadline=self._deadline)
            self.account_id = self.steamid & 0xFFFFFFFF
            return self
        steamid = _jwt_sub(self._token)
        reason = self._in_use_probe(steamid)
        if reason:
            raise AccountInUseError(reason)
        self._client, self.steamid, self._token = self._logon(self._token, deadline=self._deadline)
        self.account_id = self.steamid & 0xFFFFFFFF
        try:
            self._gc = self._gc_factory(self._client)
            for emsg in gp.EQUIP_REPLY_MSGS:
                self._gc.on(emsg, lambda _hdr, _body, _e=emsg: self._equip_replies.append(_e))
            # Registered before games_played: 9110 (the cooldown answer) can
            # arrive unprompted, bundled with any ClientWelcome — including
            # this first one — so a late cooldown_seconds() call might already
            # have it and skip the leave/re-enter cycle entirely.
            self._gc.on(gp.MSG_MM_HELLO_REPLY, self._on_mm_hello_reply)
            self._playing_blocked = False
            self._client.on(gp.MSG_CLIENT_PLAYING_SESSION_STATE, self._on_playing_session_state)
            self._client.games_played([gp.CS2_APP_ID])
            self._welcome = self._hello(self._budget(self.HELLO_TIMEOUT))
        except BaseException:
            self._close()
            raise
        return self

    def _on_mm_hello_reply(self, _hdr, body) -> None:
        self._mm_hello = body

    def _on_playing_session_state(self, msg) -> None:
        """Steam (not the GC) telling us this account is playing somewhere.

        ValvePython has no body class for ``ClientPlayingSessionState``, so the
        raw payload bytes are decoded directly."""
        blocked, _app = gp.decode_playing_session_state(getattr(msg, "payload", None) or b"")
        if blocked:
            self._playing_blocked = True

    def __exit__(self, *exc) -> None:
        self._close()

    def _close(self) -> None:
        if self._client is None:
            return
        if not self._web_only:
            try:
                self._client.games_played([])
            except Exception:  # noqa: BLE001
                pass
        try:
            self._client.disconnect()
        except Exception:  # noqa: BLE001
            pass

    # --- GC plumbing ---------------------------------------------------------

    def _send(self, emsg: int, body: bytes) -> None:
        from steam.core.msg import GCMsgHdrProto

        self._gc.send(GCMsgHdrProto(emsg), body)

    def _wait(self, emsg: int, timeout: float) -> bytes | None:
        got = self._gc.wait_event(emsg, timeout=timeout)
        return got[1] if got else None

    def _hello(self, budget: float) -> bytes:
        deadline = time.monotonic() + budget
        while True:
            self._send(gp.MSG_CLIENT_HELLO, gp.encode_client_hello())
            welcome = self._wait(gp.MSG_CLIENT_WELCOME, min(self.HELLO_RETRY, budget))
            if welcome is not None:
                return welcome
            if self._playing_blocked:
                raise AccountInUseError("playing on another device")
            if time.monotonic() >= deadline:
                raise GcUnavailableError(
                    f"CS2 GC sent no welcome (GC_CLIENT_VERSION={gp.GC_CLIENT_VERSION})"
                )

    # --- steps -----------------------------------------------------------------

    def prime(self) -> bool | None:
        """Prime status from the GC's welcome; None when unknown (web-only)."""
        return gp.decode_prime(self._welcome) if self._welcome else None

    def read_loadout(self) -> gp.Loadout:
        return gp.resolve_loadout(gp.parse_loadout(self._welcome, self.account_id))

    def write_loadout(self, want: gp.Loadout) -> tuple[int, int, int]:
        before = self.read_loadout()
        to_send = [(team, slot, itemdef) for (team, slot), itemdef in want.items()
                   if before.get((team, slot)) != itemdef]
        changed = len(to_send)
        if to_send:
            self._equip_replies.clear()
            change_num = gp.so_cache_version(self._welcome) + 1
            self._send(gp.MSG_ADJUST_EQUIP_SLOTS, gp.encode_adjust_equip_slots(to_send, change_num))
            wait_deadline = time.monotonic() + self._budget(self.EQUIP_REPLY_TIMEOUT)
            while not self._equip_replies and time.monotonic() < wait_deadline:
                self._client.sleep(0.2)
            self._client.sleep(1.2)  # trailing SO updates arrive in the same burst
            self._welcome = self._hello(self._budget(self.HELLO_TIMEOUT))  # authoritative re-read
        after = self.read_loadout()
        matched = sum(1 for key, itemdef in want.items() if after.get(key) == itemdef)
        if matched < len(want):
            logger.info("loadout: %d/%d slots matched after write", matched, len(want))
        return matched, len(want), changed

    def profile(self) -> gp.GcProfile | None:
        self._send(gp.MSG_PROFILE_REQUEST, gp.encode_profile_request(self.account_id))
        body = self._wait(gp.MSG_PROFILE, self._budget(self.REPLY_TIMEOUT))
        return gp.decode_players_profile(body, self.account_id) if body is not None else None

    def cooldown_seconds(self) -> int | None:
        """Competitive-cooldown seconds, or None if it couldn't be learned.

        Steam never answers an on-demand MSG_MM_HELLO (9109) — live probes
        showed 9110 only ever arrives unprompted, bundled with a fresh
        ClientWelcome, right after the account leaves and re-enters CS2
        (games_played([]) -> brief pause -> games_played([730]) -> ClientHello
        -> welcome + 9110 together). __enter__ already captures any 9110 that
        shows up on its own; this only drives the leave/re-enter cycle when
        nothing arrived yet, up to twice.
        """
        for _ in range(2):
            if self._mm_hello is not None:
                break
            self._reenter_for_mm_hello()
        if self._mm_hello is None:
            return None
        return gp.decode_account_profile(self._mm_hello).cooldown_seconds

    def cooldown_reason(self) -> int:
        """The GC's penalty_reason for the cooldown (0 if none/unknown)."""
        if self._mm_hello is None:
            return 0
        return gp.decode_account_profile(self._mm_hello).penalty_reason

    def _reenter_for_mm_hello(self) -> None:
        self._client.games_played([])
        self._client.sleep(self._budget(2.5))
        self._client.games_played([gp.CS2_APP_ID])
        self._send(gp.MSG_CLIENT_HELLO, gp.encode_client_hello())
        deadline = time.monotonic() + self._budget(self.REPLY_TIMEOUT)
        welcome = self._wait(gp.MSG_CLIENT_WELCOME, max(0.0, deadline - time.monotonic()))
        if welcome is not None:
            self._welcome = welcome
        if self._playing_blocked:
            raise AccountInUseError("playing on another device")
        while self._mm_hello is None and time.monotonic() < deadline:
            self._client.sleep(0.2)
        if self._playing_blocked:
            raise AccountInUseError("playing on another device")

    def _access_token(self) -> str | None:
        """The web access token for this session, minted at most once.

        Workshop clearing and the GCPD scrape both need a web session for the
        same account, so the mint (an extra UM round-trip to the CM) happens
        at most once per session and the result — success or failure — is
        reused by whichever of them runs.
        """
        if self._access_token_cache is _UNSET:
            self._access_token_cache = mint_access_token(self._client, self._token, self.steamid)
        return self._access_token_cache

    def clear_workshop(self) -> tuple[int, int]:
        access_token = self._access_token()
        if not access_token:
            raise ConnectionError("could not mint a web session for Workshop")
        return self._workshop_factory(self.steamid, access_token).clear_all()

    def gcpd_rank(self) -> Cs2Rank | None:
        """Premier/Wingman rank + competitive cooldown, scraped from GCPD.

        Reuses the same minted web access token as ``clear_workshop`` (no
        extra CM logon). Returns None on any failure — this is best-effort:
        the GC's own profile()/cooldown_seconds() data must still save even
        when GCPD can't be reached.
        """
        cookies = self._web_cookies()
        if cookies is None:
            return None
        return self._gcpd_factory().fetch_with_cookies(self.steamid, cookies)

    def gcpd_level(self) -> int:
        """CS2 level from GCPD's account page (-1 if unknown) — for web-only
        checks, or when the GC's profile carries no level."""
        return self._gcpd_account_page()[0]

    def gcpd_service_medal(self) -> int:
        """1 if GCPD says the account earned a service medal, 0 if not, -1 unknown."""
        return self._gcpd_account_page()[1]

    def _gcpd_account_page(self) -> tuple[int, int]:
        """(level, service medal) from GCPD's account page, fetched at most once."""
        if self._gcpd_account is None:
            cookies = self._web_cookies()
            self._gcpd_account = (
                (-1, -1) if cookies is None
                else self._gcpd_factory().fetch_account_with_cookies(self.steamid, cookies)
            )
        return self._gcpd_account

    def _web_cookies(self) -> dict | None:
        access_token = self._access_token()
        if not access_token:
            return None
        return {
            "steamLoginSecure": quote(f"{self.steamid}||{access_token}", safe=""),
            "sessionid": secrets.token_hex(12),
        }
