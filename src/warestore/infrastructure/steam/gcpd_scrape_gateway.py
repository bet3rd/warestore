# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Read-only CS2 Premier/Wingman rank + competitive cooldown via a GCPD scrape.

The caller supplies an already-minted ``steamLoginSecure``/``sessionid`` cookie
pair (see ``Cs2Session._access_token``/``gcpd_rank`` — the cookie rides the
same CM-logon web access token the account check already minted for Workshop,
so this never logs on again on its own). This gateway only does the read-only
GCPD GET and parses it — it never touches a token or calls any auth endpoint.

Each step logs at DEBUG; failures log as warnings.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

from warestore.infrastructure.steam.gcpd_parser import (
    Cs2Rank,
    looks_like_gcpd_page,
    looks_like_login_page,
    parse_matchmaking,
    parse_profile_rank,
    parse_service_medal,
)

logger = logging.getLogger(__name__)


class Cs2RankScrapeGateway:
    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    def fetch_with_cookies(self, steam_id64: int, cookies: dict) -> Cs2Rank | None:
        if not steam_id64 or not cookies.get("steamLoginSecure"):
            return None
        html = self._scrape(steam_id64, cookies)
        if html is None:
            return None
        rank = parse_matchmaking(html)
        logger.debug(
            "cs2-rank: %s parsed -> premier=%s wingman=%s cooldown_unix=%s",
            steam_id64, rank.premier_rating, rank.wingman_rank, rank.cooldown_expires_unix,
        )
        return rank

    def fetch_account_with_cookies(self, steam_id64: int, cookies: dict) -> tuple[int, int]:
        """(CS2 level, service medal) from the account tab; -1 for unknown.
        Service medal: 1 earned one, 0 not."""
        if not steam_id64 or not cookies.get("steamLoginSecure"):
            return -1, -1
        html = self._scrape(steam_id64, cookies, tab="accountmain")
        if html is None:
            return -1, -1
        level, medal = parse_profile_rank(html), parse_service_medal(html)
        logger.debug("cs2-rank: %s parsed -> level=%s service_medal=%s", steam_id64, level, medal)
        return level, medal

    def _scrape(self, steam_id64: int, cookies: dict, tab: str = "matchmaking") -> str | None:
        url = (
            f"https://steamcommunity.com/profiles/{steam_id64}"
            f"/gcpd/730?tab={tab}&l=english"
        )
        header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req = urllib.request.Request(
            url, headers={"Cookie": header, "User-Agent": "Mozilla/5.0"}
        )
        logger.debug("cs2-rank: scraping GCPD for %s (read-only)", steam_id64)
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as r:
                html = r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            logger.warning("cs2-rank: GCPD fetch failed: %s", e)
            return None
        if looks_like_login_page(html) or not looks_like_gcpd_page(html):
            logger.warning(
                "cs2-rank: GCPD page did not authenticate (login_page=%s, gcpd_page=%s)",
                looks_like_login_page(html), looks_like_gcpd_page(html),
            )
            return None
        logger.debug("cs2-rank: GCPD page fetched (%d bytes)", len(html))
        return html
