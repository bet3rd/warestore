# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""In-process, non-destructive Steam web-session cookie mint (replaces server.js).

Given a refresh token, do a CM logon (WebSocket) and mint a web access token via
``Authentication.GenerateAccessTokenForApp`` over that AUTHENTICATED session, then
build the ``steamLoginSecure`` cookie. Pure Python via ValvePython/steam — no Node.

SAFETY: renewal is never requested (ValvePython's bundled proto has no
``renewal_type`` field, so the CM defaults to None) — the refresh token is never
rotated/consumed. This NEVER calls ``/jwt/finalizelogin`` or the token-killing
HTTP endpoints. See the ``safe-cs2-cookie-mint`` memory for the full rationale.

MUST run off the Qt thread (the caller ``Cs2RankWorker`` is a ``QThread``):
ValvePython uses gevent, whose hub is thread-local, and we never monkey-patch, so
the Qt event loop is untouched. ``steam`` is imported lazily for the same reason.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import secrets
import urllib.parse

logger = logging.getLogger(__name__)

_UM_METHOD = "Authentication.GenerateAccessTokenForApp#1"
_PROTOCOL_VERSION = 65580
_CM_ATTEMPTS = 3

# CM logon EResults that mean the refresh token itself is bad/revoked — safe to
# treat the account as dead. Everything else (TryAnotherCM, ServiceUnavailable,
# timeouts, "no response") is transient and must NEVER flag an account.
_REJECTED_ERESULTS = frozenset({"InvalidPassword", "Expired", "Revoked", "AccessDenied"})


class TokenRejectedError(Exception):
    """The CM logon rejected the refresh token (e.g. InvalidPassword / Revoked).

    Distinct from a transient failure (returned as None): this means the token is
    dead, so the caller can offer to remove the account.
    """

    def __init__(self, eresult: str):
        super().__init__(eresult)
        self.eresult = eresult


class CmLogonError(Exception):
    """Transient CM failure (no CM reachable / no logon response). Never means
    the token is bad."""


def _clean_token(raw: str) -> str:
    """Bare JWT from the app's ``username----<JWT>`` format (or a plain JWT).
    Without this the prefix rides along and the CM rejects it (InvalidPassword)."""
    raw = (raw or "").strip()
    if "----" in raw:
        raw = raw.rsplit("----", 1)[-1]
    return raw.strip()


def _jwt_sub(token: str) -> int:
    payload = token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    return int(json.loads(base64.urlsafe_b64decode(payload))["sub"])


def _machine_id(seed: str) -> bytes:
    """Steam machine-id KV MessageObject with 3 sha1 hashes (values arbitrary)."""
    def cstr(s: str) -> bytes:
        return s.encode("utf-8") + b"\x00"

    def sha(tag: str) -> bytes:
        return cstr(hashlib.sha1((tag + seed).encode()).hexdigest())

    return (
        b"\x00" + cstr("MessageObject")
        + b"\x01" + cstr("BB3") + sha("BB3")
        + b"\x01" + cstr("FF2") + sha("FF2")
        + b"\x01" + cstr("3B3") + sha("3B3")
        + b"\x08\x08"
    )


def _token_logon(client, refresh_token: str, steamid: int):
    """Secure the channel, send a ClientLogon carrying the refresh token in
    access_token (field 108). Returns the ClientLogOnResponse or None."""
    from steam.core.msg import MsgProto
    from steam.enums import EResult
    from steam.enums.emsg import EMsg
    from steam.steamid import SteamID

    if client._pre_login() != EResult.OK:  # waits for EVENT_CHANNEL_SECURED
        return None
    msg = MsgProto(EMsg.ClientLogon)
    msg.header.steamid = SteamID(steamid).as_64
    b = msg.body
    b.protocol_version = _PROTOCOL_VERSION
    b.client_os_type = 20  # Windows10
    b.client_language = "english"
    b.should_remember_password = True
    b.supports_rate_limit_response = True
    b.chat_mode = 2
    b.machine_name = ""
    try:
        b.obfuscated_private_ip.v4 = 0
    except Exception:  # noqa: BLE001 - field shape varies by proto build
        pass
    b.machine_id = _machine_id(str(steamid))
    b.access_token = refresh_token
    client.send(msg)
    return client.wait_msg(EMsg.ClientLogOnResponse, timeout=30)


def open_cm_client(refresh_token: str):
    """Connect and log on with the refresh token, appearing OFFLINE.

    Returns ``(client, steamid64, clean_token)``; the caller must disconnect.
    ValvePython's ``SteamClient`` defaults to ``persona_state = Online`` and
    sends it automatically on logon (builtins/user.py), so it is set to Offline
    first: no status is sent and friends never see the account come online.
    Raises ``TokenRejectedError`` for a dead token, ``CmLogonError`` otherwise.
    """
    from steam.client import SteamClient
    from steam.enums import EPersonaState, EResult

    token = _clean_token(refresh_token)
    if not token:
        raise CmLogonError("empty token")
    try:
        steamid = _jwt_sub(token)
    except Exception as exc:  # noqa: BLE001
        raise CmLogonError("could not decode steamid from token") from exc

    client = SteamClient()
    client.persona_state = EPersonaState.Offline
    for attempt in range(1, _CM_ATTEMPTS + 1):
        if not client.connected and client.connect() is None:
            logger.info("cm-logon: attempt %d could not connect to a CM", attempt)
            continue
        resp = _token_logon(client, token, steamid)
        if resp is not None and resp.body.eresult == EResult.OK:
            return client, steamid, token
        reason = (EResult(resp.body.eresult).name if resp is not None
                  and resp.body.eresult in EResult._value2member_map_ else "no response")
        logger.info("cm-logon: attempt %d failed (%s)", attempt, reason)
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
        if reason in _REJECTED_ERESULTS:
            raise TokenRejectedError(reason)
    raise CmLogonError(f"CM logon failed after {_CM_ATTEMPTS} attempts")


def mint_access_token(client, token: str, steamid: int) -> str | None:
    """Web access token over an authenticated session. Renewal is never requested,
    so the refresh token is never rotated."""
    from steam.enums import EResult

    um = client.send_um_and_wait(_UM_METHOD, {"refresh_token": token, "steamid": steamid}, timeout=15)
    if um is None or um.header.eresult != EResult.OK:
        reason = (EResult(um.header.eresult).name if um is not None
                  and um.header.eresult in EResult._value2member_map_ else "no response")
        logger.warning("cs2-mint: GenerateAccessTokenForApp failed (%s)", reason)
        return None
    if getattr(um.body, "refresh_token", ""):  # must never happen (renewal not requested)
        logger.error("cs2-mint: CM returned a rotated refresh token — aborting to be safe")
        return None
    return getattr(um.body, "access_token", "") or None


def mint_web_cookies(refresh_token: str) -> dict | None:
    """Return ``{"steamLoginSecure": ..., "sessionid": ...}`` or None on failure.

    Non-destructive: the refresh token is used only for a CM logon and to mint an
    access token with renewal disabled; it is never rotated.
    """
    try:
        client, steamid, token = open_cm_client(refresh_token)
    except TokenRejectedError:
        raise
    except CmLogonError as exc:
        logger.warning("cs2-mint: %s", exc)
        return None
    except Exception as e:  # noqa: BLE001 - dependency missing / import error
        logger.warning("cs2-mint: ValvePython 'steam' unavailable: %s", e)
        return None
    try:
        access_token = mint_access_token(client, token, steamid)
        if not access_token:
            return None
        logger.info("cs2-mint: web cookie minted for %s (non-destructive)", steamid)
        return {
            "steamLoginSecure": urllib.parse.quote(f"{steamid}||{access_token}", safe=""),
            "sessionid": secrets.token_hex(12),
        }
    except Exception:  # noqa: BLE001 - never propagate into the worker
        logger.exception("cs2-mint: unexpected error during mint")
        return None
    finally:
        try:
            client.disconnect()
        except Exception:  # noqa: BLE001
            pass
