# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import zlib

import win32crypt

_OBFUSCATE_ENTROPY = (
    b"B\x00O\x00b\x00f\x00u\x00s\x00c\x00a\x00t\x00e\x00B\x00u\x00f\x00f\x00e\x00r\x00\x00\x00"
)


class SteamCryptoGateway:
    def crc32_key(self, username: str) -> str:
        value = zlib.crc32(username.encode("utf-8"))
        hex_value = f"{value:08x}".lstrip("0") or "0"
        return f"{hex_value}1"

    def encrypt(self, token: str, account_name: str) -> str:
        encrypted = win32crypt.CryptProtectData(
            token.encode("utf-8"),
            _OBFUSCATE_ENTROPY.decode("utf-8"),
            account_name.encode("utf-8"),
            None,
            None,
            17,
        )
        blob = encrypted[0] if isinstance(encrypted, (tuple, list)) else encrypted
        return blob.hex()

    def decrypt(self, encrypted_hex: str, account_name: str) -> str:
        data = bytes.fromhex(encrypted_hex)
        _desc, plaintext = win32crypt.CryptUnprotectData(
            data,
            account_name.encode("utf-8"),
            None,
            None,
            0,
        )
        return plaintext.decode("utf-8").strip("\x00")
