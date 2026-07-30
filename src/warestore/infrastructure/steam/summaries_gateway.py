# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Fetches account status via the Steam Web API (GetPlayerSummaries).

Returns the same {sid: {"state", "game"}} shape as the profile-XML gateway so
it's a drop-in status source, but batched (100 ids/call) and more reliable.
"""

import json
import logging
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable

logger = logging.getLogger(__name__)

_ENDPOINT = "https://api.steampowered.com/ISteamUser/GetPlayerSummaries/v2/"
_BATCH = 100


class SteamSummariesGateway:
    def __init__(self, timeout: int = 10) -> None:
        self._timeout = timeout

    def fetch_statuses(
        self,
        api_key: str,
        steam_ids: list[str],
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, dict]:
        if not api_key or not steam_ids:
            return {}
        result: dict[str, dict] = {}
        total = len(steam_ids)
        for start in range(0, total, _BATCH):
            chunk = steam_ids[start : start + _BATCH]
            if on_progress:
                on_progress(f"Fetching status ({min(start + len(chunk), total)}/{total})…")
            result.update(self._fetch_chunk(api_key, chunk))
        return result

    def _fetch_chunk(self, api_key: str, chunk: list[str]) -> dict[str, dict]:
        query = urllib.parse.urlencode({"key": api_key, "steamids": ",".join(chunk)})
        try:
            with urllib.request.urlopen(f"{_ENDPOINT}?{query}", timeout=self._timeout) as resp:
                payload = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            logger.warning(f"Summaries HTTP {exc.code} (check Steam API key)")
            return {sid: {"state": -1, "game": "", "stale": True} for sid in chunk}
        except Exception as exc:
            logger.warning(f"Summaries fetch failed: {exc}")
            return {sid: {"state": -1, "game": "", "stale": True} for sid in chunk}

        out: dict[str, dict] = {}
        for player in payload.get("response", {}).get("players", []):
            sid = player.get("steamid", "")
            if not sid:
                continue
            game = player.get("gameextrainfo", "")
            if game:
                state = 6  # in-game; the card paints blue whenever a game is set
            else:
                # personastate: 0 offline,1 online,2 busy,3 away,4 snooze,
                # 5 looking-to-trade,6 looking-to-play. Cards color 0-4; map 5/6
                # to online.
                persona = int(player.get("personastate", 0))
                state = persona if persona <= 4 else 1
            out[sid] = {"state": state, "game": game}
        return out
