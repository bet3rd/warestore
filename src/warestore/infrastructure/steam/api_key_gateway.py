# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Validates a Steam Web API key via a lightweight authenticated endpoint."""

import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# GetSupportedAPIList needs no steamid and returns 200 for a valid key, 403 for
# a bad one — a clean, cheap key check.
_ENDPOINT = "https://api.steampowered.com/ISteamWebAPIUtil/GetSupportedAPIList/v1/"


class SteamApiKeyGateway:
    def __init__(self, timeout: int = 8) -> None:
        self._timeout = timeout

    def validate(self, api_key: str) -> str:
        """Return "valid", "invalid", or "error" for the given key."""
        key = api_key.strip()
        if not key:
            return "invalid"
        query = urllib.parse.urlencode({"key": key})
        try:
            with urllib.request.urlopen(f"{_ENDPOINT}?{query}", timeout=self._timeout) as resp:
                resp.read()
            return "valid"
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                return "invalid"
            logger.warning(f"API key check HTTP {exc.code}")
            return "error"
        except Exception as exc:
            logger.warning(f"API key check failed: {exc}")
            return "error"
