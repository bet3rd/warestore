# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Fetches VAC/game/community/trade ban status via the Steam Web API."""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.steampowered.com/ISteamUser/GetPlayerBans/v1/"
_BATCH = 100  # GetPlayerBans accepts up to 100 steamids per call


class SteamBansGateway:
    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def fetch_bans(self, api_key: str, steam_ids: list[str]) -> dict[str, dict]:
        """Return {steam_id: ban_dict} for the given ids, or {} if no key/error.

        ban_dict keys: vac (bool), vac_count (int), game_bans (int),
        community (bool), trade ("none"|"probation"|"banned"), days_since (int).
        """
        if not api_key or not steam_ids:
            return {}
        result: dict[str, dict] = {}
        for start in range(0, len(steam_ids), _BATCH):
            chunk = steam_ids[start : start + _BATCH]
            result.update(self._fetch_chunk(api_key, chunk))
        return result

    def _fetch_chunk(self, api_key: str, chunk: list[str]) -> dict[str, dict]:
        query = urllib.parse.urlencode({"key": api_key, "steamids": ",".join(chunk)})
        try:
            with urllib.request.urlopen(f"{_ENDPOINT}?{query}", timeout=self._timeout) as resp:
                payload = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            # 401/403 → bad/forbidden key; log once per call, return empty.
            logger.warning(f"Ban fetch HTTP {exc.code} (check Steam API key)")
            return {}
        except Exception as exc:
            logger.warning(f"Ban fetch failed: {exc}")
            return {}

        out: dict[str, dict] = {}
        for entry in payload.get("players", []):
            sid = entry.get("SteamId", "")
            if not sid:
                continue
            out[sid] = {
                "vac": bool(entry.get("VACBanned", False)),
                "vac_count": int(entry.get("NumberOfVACBans", 0)),
                "game_bans": int(entry.get("NumberOfGameBans", 0)),
                "community": bool(entry.get("CommunityBanned", False)),
                "trade": str(entry.get("EconomyBan", "none")),
                "days_since": int(entry.get("DaysSinceLastBan", 0)),
            }
        return out
