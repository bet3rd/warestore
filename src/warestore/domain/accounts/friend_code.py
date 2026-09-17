# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Compute a CS2 friend code from a SteamID64.

Pure, offline, deterministic. The friend code is the ``SUCVS-FADA`` style
string CS2 shows under "Add a Friend" — it encodes the 32-bit account id with a
4-bit-interleaved MD5 checksum, base-32 encoded over Valve's alphabet. The
leading constant ``AAAA-`` group is dropped, matching what the client displays.
"""

from __future__ import annotations

import hashlib
import struct

_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def cs2_friend_code(steam64: int) -> str:
    """Return the CS2 friend code (e.g. ``SUCVS-FADA``) for a SteamID64."""
    account_id = steam64 & 0xFFFFFFFF

    # MD5 of the little-endian bytes of 0x4353474F ("CSGO") | account_id.
    data = (b"CSGO" + struct.pack(">L", account_id))[::-1]
    (h,) = struct.unpack("<L", hashlib.md5(data).digest()[:4])

    result = 0
    for i in range(8):
        id_nib = (steam64 >> (i * 4)) & 0xF
        hash_bit = (h >> i) & 0x1
        a = (result << 4) | id_nib
        result = ((result >> 28) << 32) | a
        result = ((result >> 31) << 32) | ((a << 1) | hash_bit)

    result = struct.unpack("<Q", struct.pack(">Q", result))[0]

    code = ""
    for i in range(13):
        if i in (4, 9):
            code += "-"
        code += _ALPHABET[result & 31]
        result >>= 5
    return code[5:]  # drop the constant "AAAA-" prefix


def friend_code_for_steamid(steamid: str) -> str:
    """Friend code for a SteamID64 given as a string; "" if it isn't a valid id.

    Steam account ids are 76561197960265728 + account_id, so a real id is a
    17-digit number at or above that base. Anything else yields "".
    """
    try:
        s = int(steamid)
    except (TypeError, ValueError):
        return ""
    if s < 76561197960265728:
        return ""
    return cs2_friend_code(s)
