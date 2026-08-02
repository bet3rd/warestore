# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""On-demand CS2 rank/cooldown scrape via an in-process CM-logon cookie mint.

SAFE PATH ONLY. The ``steamLoginSecure`` cookie is minted in-process by a **CM
logon** (ValvePython/steam, see :mod:`cs2_cm_mint`) — the same non-destructive
logon the desktop client does — then this gateway does a **read-only** GCPD GET
and parses it. It NEVER calls ``finalizelogin`` or requests a token renewal (the
endpoints/flags that rotate/kill refresh tokens). No Node, no external service.

Every step logs at INFO so the dev console shows exactly what happened.
"""

from __future__ import annotations

import logging
import urllib.error
import urllib.request

from warestore.infrastructure.steam.cs2_cm_mint import mint_web_cookies
from warestore.infrastructure.steam.gcpd_parser import (
    Cs2Rank,
    looks_like_gcpd_page,
    looks_like_login_page,
    parse_matchmaking,
)

logger = logging.getLogger(__name__)


class Cs2RankScrapeGateway:
    def __init__(self, timeout: int = 20) -> None:
        self._timeout = timeout

    def fetch(self, steam_id64: int, refresh_token: str) -> Cs2Rank | None:
        if not steam_id64 or not refresh_token:
            return None
        cookies = self._mint_cookies(refresh_token)
        if cookies is None:
            return None
        html = self._scrape(steam_id64, cookies)
        if html is None:
            return None
        rank = parse_matchmaking(html)
        logger.info(
            "cs2-rank: %s parsed -> premier=%s wingman=%s cooldown_unix=%s",
            steam_id64, rank.premier_rating, rank.wingman_rank, rank.cooldown_expires_unix,
        )
        return rank

    def _mint_cookies(self, refresh_token: str) -> dict | None:
        logger.info("cs2-rank: minting web cookie via in-process CM logon")
        cookies = mint_web_cookies(refresh_token)
        if not cookies or not cookies.get("steamLoginSecure"):
            logger.warning("cs2-rank: CM cookie mint failed (see cs2-mint logs above)")
            return None
        logger.info(
            "cs2-rank: CM logon OK — cookie minted (%d chars)",
            len(cookies["steamLoginSecure"]),
        )
        return cookies

    def _scrape(self, steam_id64: int, cookies: dict) -> str | None:
        url = (
            f"https://steamcommunity.com/profiles/{steam_id64}"
            "/gcpd/730?tab=matchmaking&l=english"
        )
        header = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req = urllib.request.Request(
            url, headers={"Cookie": header, "User-Agent": "Mozilla/5.0"}
        )
        logger.info("cs2-rank: scraping GCPD for %s (read-only)", steam_id64)
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
        logger.info("cs2-rank: GCPD page fetched (%d bytes)", len(html))
        return html
