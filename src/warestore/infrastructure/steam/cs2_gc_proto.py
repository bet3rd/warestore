# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd
# Approach ported from fakearchie/nfatool (MIT) — https://github.com/fakearchie/nfatool

"""CS2 Game Coordinator wire format: pure functions, no network.

Only the handful of messages the account check needs: the GC hello/welcome
(whose SO cache holds the weapon loadout), the batch equip message, and the
players-profile / matchmaking-hello replies (level, Premier, cooldown).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

CS2_APP_ID = 730
GC_CLIENT_VERSION = 2_000_244  # may need bumping when CS2 updates

MSG_CLIENT_HELLO = 4006
MSG_CLIENT_WELCOME = 4004
MSG_ADJUST_EQUIP_SLOTS = 2531
MSG_MM_HELLO = 9109
MSG_MM_HELLO_REPLY = 9110
MSG_PROFILE_REQUEST = 9127
MSG_PROFILE = 9128
# The GC answers an equip with an ACK of the same id plus SO create/update/destroy/
# cache-subscribed/update-multiple messages.
EQUIP_REPLY_MSGS = (MSG_ADJUST_EQUIP_SLOTS, 21, 22, 23, 24, 26)

SO_TYPE_EQUIP_SLOT = 3
SO_TYPE_DEFAULT_EQUIPPED = 43
RANK_TYPE_PREMIER = 11
DEFAULT_ITEM_MASK = 0xF000000000000000

TEAM_T = 2
TEAM_CT = 3

Loadout = dict[tuple[int, int], int]

# The game's built-in weapon for each (team, slot); a slot with no SO entry holds
# this. Slots: 2-6 pistols, 8-12 mid-tier, 14-18 rifles.
DEFAULT_LOADOUT: Loadout = {
    (TEAM_T, 2): 4, (TEAM_T, 3): 2, (TEAM_T, 4): 36, (TEAM_T, 5): 30, (TEAM_T, 6): 1,
    (TEAM_T, 8): 35, (TEAM_T, 9): 25, (TEAM_T, 10): 23, (TEAM_T, 11): 19, (TEAM_T, 12): 17,
    (TEAM_T, 14): 13, (TEAM_T, 15): 7, (TEAM_T, 16): 40, (TEAM_T, 17): 39, (TEAM_T, 18): 9,
    (TEAM_CT, 2): 32, (TEAM_CT, 3): 2, (TEAM_CT, 4): 36, (TEAM_CT, 5): 3, (TEAM_CT, 6): 1,
    (TEAM_CT, 8): 35, (TEAM_CT, 9): 25, (TEAM_CT, 10): 23, (TEAM_CT, 11): 19, (TEAM_CT, 12): 34,
    (TEAM_CT, 14): 10, (TEAM_CT, 15): 60, (TEAM_CT, 16): 40, (TEAM_CT, 17): 8, (TEAM_CT, 18): 9,
}


# --- wire format -------------------------------------------------------------

def encode_varint(n: int) -> bytes:
    if n < 0:
        n &= (1 << 64) - 1  # protobuf encodes negative int32/int64 as 10-byte varints
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        out.append(b | (0x80 if n else 0))
        if not n:
            return bytes(out)


def _read_varint(buf: bytes, i: int) -> tuple[int, int]:
    shift = result = 0
    while True:
        if i >= len(buf) or shift > 63:
            raise ValueError("truncated varint")
        b = buf[i]
        i += 1
        result |= (b & 0x7F) << shift
        if not b & 0x80:
            return result, i
        shift += 7


def iter_fields(buf: bytes) -> Iterator[tuple[int, int, int | bytes]]:
    """Yield (field_number, wire_type, value). Raises ValueError on bad input."""
    i = 0
    while i < len(buf):
        key, i = _read_varint(buf, i)
        num, wt = key >> 3, key & 7
        if wt == 0:
            value, i = _read_varint(buf, i)
        elif wt == 1:
            if i + 8 > len(buf):
                raise ValueError("truncated fixed64")
            value, i = int.from_bytes(buf[i:i + 8], "little"), i + 8
        elif wt == 2:
            length, i = _read_varint(buf, i)
            if i + length > len(buf):
                raise ValueError("truncated length-delimited field")
            value, i = buf[i:i + length], i + length
        elif wt == 5:
            if i + 4 > len(buf):
                raise ValueError("truncated fixed32")
            value, i = int.from_bytes(buf[i:i + 4], "little"), i + 4
        else:
            raise ValueError(f"unsupported wire type {wt}")
        yield num, wt, value


def _vfield(num: int, value: int) -> bytes:
    return encode_varint(num << 3) + encode_varint(value)


def _bfield(num: int, payload: bytes) -> bytes:
    return encode_varint((num << 3) | 2) + encode_varint(len(payload)) + payload


def _int32(value: int) -> int:
    value &= 0xFFFFFFFF
    return value - (1 << 32) if value >= 1 << 31 else value


# --- requests ----------------------------------------------------------------

def encode_client_hello() -> bytes:
    return _vfield(1, GC_CLIENT_VERSION) + _vfield(3, 0) + _vfield(4, 0) + _vfield(9, 0)


def encode_profile_request(account_id: int) -> bytes:
    return _vfield(3, account_id) + _vfield(4, 32)


def encode_adjust_equip_slots(slots: list[tuple[int, int, int]], change_num: int) -> bytes:
    """One batch equip: (team, slot, itemdef) per slot, stock weapons only."""
    out = b""
    for team, slot, itemdef in slots:
        out += _bfield(1, _vfield(1, team) + _vfield(2, slot) + _vfield(3, DEFAULT_ITEM_MASK | itemdef))
    return out + _vfield(2, change_num & 0xFFFFFFFF)


# --- welcome / loadout -------------------------------------------------------

def _decode_slot_object(type_id: int, data: bytes) -> tuple[int, int, int, int] | None:
    """(account_id, team, slot, itemdef) or None when not a loadout object."""
    f = {num: v for num, _wt, v in iter_fields(data)}
    if type_id == SO_TYPE_DEFAULT_EQUIPPED:
        return f.get(1, 0), f.get(3, 0), f.get(4, 0), f.get(2, 0)
    if type_id == SO_TYPE_EQUIP_SLOT:
        itemdef = f.get(5, 0)
        item_id = f.get(4, 0)
        if not itemdef and (item_id & DEFAULT_ITEM_MASK) == DEFAULT_ITEM_MASK:
            itemdef = item_id & ~DEFAULT_ITEM_MASK & 0xFFFFFFFFFFFFFFFF
        return f.get(1, 0), f.get(2, 0), f.get(3, 0), itemdef
    return None


def parse_loadout(welcome: bytes, account_id: int) -> Loadout:
    """Explicit weapon-slot entries from a ClientWelcome (welcome field 3 = SO caches)."""
    explicit: Loadout = {}
    for num, wt, cache in iter_fields(welcome):
        if num != 3 or wt != 2:
            continue
        for n2, wt2, typed in iter_fields(cache):
            if n2 != 2 or wt2 != 2:
                continue
            type_id = 0
            objects: list[bytes] = []
            for n3, wt3, v in iter_fields(typed):
                if n3 == 1:
                    type_id = v
                elif n3 == 2 and wt3 == 2:
                    objects.append(v)
            for data in objects:
                try:
                    decoded = _decode_slot_object(type_id, data)
                except ValueError:
                    continue  # one bad object never spoils the rest
                if decoded is None:
                    continue
                acct, team, slot, itemdef = decoded
                if type_id == SO_TYPE_DEFAULT_EQUIPPED and acct != account_id:
                    continue
                if acct and acct != account_id:
                    continue
                if (team, slot) in DEFAULT_LOADOUT and 0 < itemdef <= 10_000:
                    explicit[(team, slot)] = itemdef
    return explicit


def resolve_loadout(explicit: Loadout) -> Loadout:
    """All 30 weapon slots: the explicit entry if any, else the built-in default."""
    return {key: explicit.get(key, default) for key, default in DEFAULT_LOADOUT.items()}


def so_cache_version(welcome: bytes) -> int:
    for num, wt, cache in iter_fields(welcome):
        if num == 3 and wt == 2:
            for n2, _wt2, v in iter_fields(cache):
                if n2 == 3:
                    return int(v)
    return 0


# --- stats -------------------------------------------------------------------

@dataclass(frozen=True)
class GcProfile:
    account_id: int = 0
    level: int = -1           # CS2 profile level, -1 unknown
    premier_rating: int = -1  # -1 = unranked / unknown
    premier_wins: int = -1
    cooldown_seconds: int = 0  # 0 = none


def decode_account_profile(buf: bytes) -> GcProfile:
    account_id = level = 0
    has_level = False
    premier_rating, premier_wins = -1, -1
    cooldown = 0
    for num, wt, v in iter_fields(buf):
        if num == 1:
            account_id = v
        elif num == 4:
            cooldown = max(0, _int32(v))
        elif num == 17:
            level, has_level = v, True
        elif num in (7, 20) and wt == 2:
            r = {n: x for n, _w, x in iter_fields(v)}
            if r.get(6, 0) == RANK_TYPE_PREMIER:
                rating, wins = r.get(2, 0), r.get(3, 0)
                premier_rating = rating if rating > 0 else -1
                premier_wins = wins if rating > 0 else -1
    return GcProfile(
        account_id=account_id,
        level=level if has_level else -1,
        premier_rating=premier_rating,
        premier_wins=premier_wins,
        cooldown_seconds=cooldown,
    )


def decode_players_profile(buf: bytes, account_id: int) -> GcProfile | None:
    profiles = [decode_account_profile(v) for num, wt, v in iter_fields(buf) if num == 2 and wt == 2]
    if not profiles:
        return None
    return next((p for p in profiles if p.account_id == account_id), profiles[0])


# --- synthetic encoders (tests build fake GC replies with these) --------------

def encode_equip_slot_object(account_id: int, team: int, slot: int, itemdef: int) -> bytes:
    return _vfield(1, account_id) + _vfield(2, team) + _vfield(3, slot) + _vfield(4, DEFAULT_ITEM_MASK | itemdef)


def encode_default_equipped_object(account_id: int, team: int, slot: int, itemdef: int) -> bytes:
    return _vfield(1, account_id) + _vfield(2, itemdef) + _vfield(3, team) + _vfield(4, slot)


def encode_welcome(objects: list[tuple[int, bytes]], version: int = 0) -> bytes:
    by_type: dict[int, list[bytes]] = {}
    for type_id, data in objects:
        by_type.setdefault(type_id, []).append(data)
    cache = b"".join(
        _bfield(2, _vfield(1, type_id) + b"".join(_bfield(2, d) for d in datas))
        for type_id, datas in by_type.items()
    ) + _vfield(3, version)
    return _bfield(3, cache)


def encode_account_profile(
    account_id: int,
    *,
    level: int | None = None,
    premier_rating: int | None = None,
    premier_wins: int | None = None,
    cooldown_seconds: int | None = None,
) -> bytes:
    out = _vfield(1, account_id)
    if cooldown_seconds is not None:
        out += _vfield(4, cooldown_seconds)
    if premier_rating is not None:
        out += _bfield(7, _vfield(2, premier_rating) + _vfield(3, premier_wins or 0) + _vfield(6, RANK_TYPE_PREMIER))
    if level is not None:
        out += _vfield(17, level)
    return out


def encode_players_profile(profiles: list[bytes]) -> bytes:
    return b"".join(_bfield(2, p) for p in profiles)
