# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import base64
import json
import time

import jwt


class SteamJwtService:
    @staticmethod
    def is_valid_format(token: str) -> bool:
        """True when `token` is structurally a JWT (three dot-separated parts)."""
        return bool(token) and token.count(".") == 2

    @staticmethod
    def looks_like_jwt(token: str) -> bool:
        """Heuristic for a Steam refresh-token JWT (base64 payload starts 'ey')."""
        return bool(token) and token.lower().startswith("ey") and token.count(".") == 2

    def decode_steam_id(self, token: str) -> str | None:
        payload = self._parse_payload(token)
        if not payload:
            return None
        try:
            return json.loads(payload).get("sub")
        except json.JSONDecodeError:
            return None

    def verify_expiry(self, refresh_token: str) -> int:
        try:
            decoded = jwt.decode(refresh_token, options={"verify_signature": False})
            if decoded.get("iss") != "steam":
                return -1
            if "client" not in decoded.get("aud", ""):
                return -1
            expires_in = int(decoded.get("exp", 0) - time.time())
            return expires_in if expires_in > 0 else -1
        except Exception:
            return -1

    @staticmethod
    def _parse_payload(token: str) -> str | None:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = parts[1]
        padding = len(payload) % 4
        if padding:
            payload += "=" * (4 - padding)
        try:
            return base64.b64decode(payload).decode("utf-8")
        except Exception:
            return None
