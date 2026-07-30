# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging
import re
import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections.abc import Callable

logger = logging.getLogger(__name__)


class SteamProfileGateway:
    """Fetches online/in-game state from Steam Community profile XML."""

    def __init__(self, throttle_seconds: float = 0.4, timeout: int = 10) -> None:
        self._throttle = throttle_seconds
        self._timeout = timeout

    def fetch_statuses(
        self,
        steam_ids: list[str],
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, dict]:
        result: dict[str, dict] = {}
        total = len(steam_ids)
        for i, sid in enumerate(steam_ids):
            if on_progress:
                on_progress(f"Fetching status ({i + 1}/{total})…")
            result[sid] = self._fetch_one(sid)
            if i < total - 1:
                time.sleep(self._throttle)
        return result

    def _fetch_one(self, steam_id: str) -> dict:
        try:
            req = urllib.request.Request(
                f"https://steamcommunity.com/profiles/{steam_id}/?xml=1&_={int(time.time())}",
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                },
            )
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                tree = ET.fromstring(resp.read())

            if tree.findtext("privacyState", "") != "public":
                return {"state": 0, "game": "", "private": True}

            online_state = tree.findtext("onlineState", "offline")
            state_msg = tree.findtext("stateMessage", "")
            cleaned = re.sub(r"<[^>]+>", " ", state_msg).strip()

            if online_state == "in-game":
                state = 6
                game = re.sub(
                    r"(?i)(currently\s+)?in-game\s*", "", cleaned
                ).strip(" :/\\\n")
            elif online_state == "online":
                state, game = 1, ""
            else:
                state, game = 0, ""

            return {"state": state, "game": game}
        except urllib.error.HTTPError as exc:
            if exc.code == 429:
                logger.debug(f"Rate limited — retry later ({steam_id})")
            else:
                logger.warning(f"Profile fetch HTTP {exc.code} ({steam_id})")
            return {"state": -1, "game": "", "stale": True}
        except Exception as exc:
            logger.warning(f"Profile fetch failed ({steam_id}): {exc}")
            return {"state": -1, "game": "", "stale": True}
