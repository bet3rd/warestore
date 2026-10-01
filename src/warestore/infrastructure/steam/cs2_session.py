# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd
# Approach ported from fakearchie/nfatool (MIT) — https://github.com/fakearchie/nfatool

"""One CM logon as an account, talking to the CS2 Game Coordinator.

Logs on with persona Offline, marks the account as playing CS2 only for the
lifetime of the ``with`` block, and always stops "playing" and disconnects on
exit. MUST run off the Qt thread (ValvePython/gevent).
"""

from __future__ import annotations

import logging
import time

from warestore.infrastructure.steam import cs2_gc_proto as gp
from warestore.infrastructure.steam.cs2_cm_mint import (
    _clean_token,
    _jwt_sub,
    mint_access_token,
    open_cm_client,
)
from warestore.infrastructure.steam.cs2_workshop_web import WorkshopWebClient

logger = logging.getLogger(__name__)


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
        logon=open_cm_client,
        gc_factory=None,
        in_use_probe=account_in_use,
        workshop_factory=WorkshopWebClient,
        deadline: float | None = None,
    ) -> None:
        self._token = _clean_token(refresh_token)
        self._read_only = read_only
        self._logon = logon
        self._gc_factory = gc_factory or _default_gc_factory
        self._in_use_probe = in_use_probe
        self._workshop_factory = workshop_factory
        self._deadline = deadline
        self._client = None
        self._gc = None
        self._welcome = b""
        self._equip_replies: list[int] = []
        self._playing_blocked = False
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
            self._playing_blocked = False
            self._client.on(gp.MSG_CLIENT_PLAYING_SESSION_STATE, self._on_playing_session_state)
            self._client.games_played([gp.CS2_APP_ID])
            self._welcome = self._hello(self._budget(self.HELLO_TIMEOUT))
        except BaseException:
            self._close()
            raise
        return self

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
        self._send(gp.MSG_MM_HELLO, b"")
        body = self._wait(gp.MSG_MM_HELLO_REPLY, self._budget(self.REPLY_TIMEOUT))
        return gp.decode_account_profile(body).cooldown_seconds if body is not None else None

    def clear_workshop(self) -> tuple[int, int]:
        access_token = mint_access_token(self._client, self._token, self.steamid)
        if not access_token:
            raise ConnectionError("could not mint a web session for Workshop")
        return self._workshop_factory(self.steamid, access_token).clear_all()
