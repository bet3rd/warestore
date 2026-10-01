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


def account_in_use(steamid64: int) -> tuple[bool, bool]:
    """(Steam here is logged into this account, cs2.exe is running)."""
    import psutil

    names = {(p.info.get("name") or "").lower() for p in psutil.process_iter(["name"])}
    steam_up = "steam.exe" in names
    cs2_up = "cs2.exe" in names
    active = 0
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam\ActiveProcess") as key:
            active = int(winreg.QueryValueEx(key, "ActiveUser")[0] or 0)
    except OSError:
        pass
    logged_in_here = steam_up and active == (steamid64 & 0xFFFFFFFF)
    return logged_in_here, cs2_up


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
        read_only: bool = False,
        logon=open_cm_client,
        gc_factory=None,
        in_use_probe=account_in_use,
        workshop_factory=WorkshopWebClient,
    ) -> None:
        self._token = _clean_token(refresh_token)
        self._read_only = read_only
        self._logon = logon
        self._gc_factory = gc_factory or _default_gc_factory
        self._in_use_probe = in_use_probe
        self._workshop_factory = workshop_factory
        self._client = None
        self._gc = None
        self._welcome = b""
        self._equip_replies: list[int] = []
        self.steamid = 0
        self.account_id = 0

    # --- lifecycle -----------------------------------------------------------

    def __enter__(self) -> "Cs2Session":
        steamid = _jwt_sub(self._token)
        logged_in_here, cs2_running = self._in_use_probe(steamid)
        if logged_in_here and (cs2_running or not self._read_only):
            raise AccountInUseError("account is in use on this PC")
        self._client, self.steamid, self._token = self._logon(self._token)
        self.account_id = self.steamid & 0xFFFFFFFF
        try:
            self._gc = self._gc_factory(self._client)
            for emsg in gp.EQUIP_REPLY_MSGS:
                self._gc.on(emsg, lambda _hdr, _body, _e=emsg: self._equip_replies.append(_e))
            self._client.games_played([gp.CS2_APP_ID])
            self._welcome = self._hello(self.HELLO_TIMEOUT)
        except BaseException:
            self._close()
            raise
        return self

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
            if time.monotonic() >= deadline:
                raise GcUnavailableError(
                    f"CS2 GC sent no welcome (GC_CLIENT_VERSION={gp.GC_CLIENT_VERSION})"
                )

    # --- steps -----------------------------------------------------------------

    def read_loadout(self) -> gp.Loadout:
        return gp.resolve_loadout(gp.parse_loadout(self._welcome, self.account_id))

    def write_loadout(self, want: gp.Loadout) -> tuple[int, int]:
        before = self.read_loadout()
        to_send = [(team, slot, itemdef) for (team, slot), itemdef in want.items()
                   if before.get((team, slot)) != itemdef]
        if to_send:
            self._equip_replies.clear()
            change_num = gp.so_cache_version(self._welcome) + 1
            self._send(gp.MSG_ADJUST_EQUIP_SLOTS, gp.encode_adjust_equip_slots(to_send, change_num))
            deadline = time.monotonic() + self.EQUIP_REPLY_TIMEOUT
            while not self._equip_replies and time.monotonic() < deadline:
                self._client.sleep(0.2)
            self._client.sleep(1.2)  # trailing SO updates arrive in the same burst
            self._welcome = self._hello(self.HELLO_TIMEOUT)  # authoritative re-read
        after = self.read_loadout()
        matched = sum(1 for key, itemdef in want.items() if after.get(key) == itemdef)
        if matched < len(want):
            logger.info("loadout: %d/%d slots matched after write", matched, len(want))
        return matched, len(want)

    def profile(self) -> gp.GcProfile | None:
        self._send(gp.MSG_PROFILE_REQUEST, gp.encode_profile_request(self.account_id))
        body = self._wait(gp.MSG_PROFILE, self.REPLY_TIMEOUT)
        return gp.decode_players_profile(body, self.account_id) if body is not None else None

    def cooldown_seconds(self) -> int | None:
        self._send(gp.MSG_MM_HELLO, b"")
        body = self._wait(gp.MSG_MM_HELLO_REPLY, self.REPLY_TIMEOUT)
        return gp.decode_account_profile(body).cooldown_seconds if body is not None else None

    def clear_workshop(self) -> tuple[int, int]:
        access_token = mint_access_token(self._client, self._token, self.steamid)
        if not access_token:
            raise ConnectionError("could not mint a web session for Workshop")
        return self._workshop_factory(self.steamid, access_token).clear_all()
