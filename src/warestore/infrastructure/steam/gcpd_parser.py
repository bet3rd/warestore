# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Parse CS2 Premier/Wingman rank + competitive cooldown from GCPD HTML.

Pure, offline, read-only: takes the HTML of /gcpd/730?tab=matchmaking and returns
the scraped values. It does NOT fetch anything and never touches a token — the
cookie must be obtained safely (a CM logon, never an auth HTTP endpoint) and the
page fetched separately, then handed here. Kept as a standalone module so the
lethal token-minting gateway could be deleted without losing the parser.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

# A permanent cooldown has no real expiry; use a far-future unix so "expires >
# now" logic still reads it as active. Well under 2**31 to avoid overflow.
COOLDOWN_PERMANENT = 2_000_000_000


@dataclass
class Cs2Rank:
    premier_rating: int = -1   # -1 = unknown/unranked, else CS Rating
    premier_wins: int = -1
    wingman_rank: int = -1     # -1 = unknown/unranked, else 1-18
    wingman_wins: int = -1
    cooldown_expires_unix: int = 0  # 0 = none, else unix expiry (or COOLDOWN_PERMANENT)
    cooldown_reason: str = ""


_TABLE_RE = re.compile(
    r'<table[^>]*class\s*=\s*"[^"]*generic_kv_table[^"]*"[^>]*>(.*?)</table>', re.I | re.S
)
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
_CELL_RE = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
_TAG_RE = re.compile(r"<[^>]*>")
_ENTITIES = [("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
             ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")]


def _strip_tags(s: str) -> str:
    s = _TAG_RE.sub("", s)
    for ch in "\n\r\t":
        s = s.replace(ch, "")
    for frm, to in _ENTITIES:
        s = s.replace(frm, to)
    return s.strip()


def _ci(hay: str, needle: str) -> bool:
    return needle.lower() in hay.lower()


def _to_int(s: str, dflt: int = -1) -> int:
    s = s.replace(",", "").replace(" ", "")
    m = re.match(r"[+-]?\d+", s)
    return int(m.group()) if m else dflt


def _tables(html: str) -> list[list[list[str]]]:
    out = []
    for tm in _TABLE_RE.finditer(html):
        rows = []
        for rm in _ROW_RE.finditer(tm.group(1)):
            cells = [_strip_tags(cm.group(1)) for cm in _CELL_RE.finditer(rm.group(1))]
            if cells:
                rows.append(cells)
        out.append(rows)
    return out


def _parse_timestamp(s: str) -> int:
    m = re.match(r"\s*(\d+)-(\d+)-(\d+)\s+(\d+):(\d+):(\d+)", s)
    if not m:
        return 0
    import calendar

    y, mo, d, h, mi, se = map(int, m.groups())
    try:
        return calendar.timegm((y, mo, d, h, mi, se, 0, 0, 0))
    except (ValueError, OverflowError):
        return 0


def looks_like_login_page(html: str) -> bool:
    return _ci(html, "g_steamID = false") or _ci(html, "<title>Sign In")


def looks_like_gcpd_page(html: str) -> bool:
    return _ci(html, "generic_kv_table") or _ci(html, "Personal Game Data")


def parse_matchmaking(html: str, now: int | None = None) -> Cs2Rank:
    """Scrape Premier/Wingman + cooldown from the matchmaking-tab HTML."""
    out = Cs2Rank()
    now = int(time.time()) if now is None else now
    for tbl in _tables(html):
        if len(tbl) < 2:
            continue
        header = tbl[0]
        if not header:
            continue

        if _ci(header[0], "Cooldown"):
            for row in tbl[1:]:
                if not row:
                    continue
                ts = _parse_timestamp(row[0])
                if ts == 0:
                    if row[0] and len(row) > 1 and _to_int(row[1], 0) >= 1:
                        out.cooldown_expires_unix = COOLDOWN_PERMANENT
                        out.cooldown_reason = "Competitive cooldown"
                    continue
                if out.cooldown_expires_unix == COOLDOWN_PERMANENT:
                    continue
                if ts > now and (out.cooldown_expires_unix == 0
                                 or ts < out.cooldown_expires_unix):
                    out.cooldown_expires_unix = ts
                    out.cooldown_reason = "Competitive cooldown"
            continue

        if _ci(header[0], "Matchmaking Mode"):
            if any(_ci(c, n) for c in header
                   for n in ("Map", "Mappa", "Mapa", "Carte", "Karte")):
                continue  # per-map variant table
            skill_col = wins_col = -1
            for c, cell in enumerate(header):
                if skill_col < 0 and _ci(cell, "Skill"):
                    skill_col = c
                if wins_col < 0 and _ci(cell, "Wins"):
                    wins_col = c
            if skill_col < 0:
                skill_col = 4
            if wins_col < 0:
                wins_col = 1
            for row in tbl[1:]:
                if not row:
                    continue
                skill = _to_int(row[skill_col], -1) if len(row) > skill_col else -1
                wins = _to_int(row[wins_col], -1) if len(row) > wins_col else -1
                if skill < 0 and wins < 0:
                    continue
                if _ci(row[0], "Premier"):
                    if skill > 0:
                        out.premier_rating = skill
                    if wins >= 0:
                        out.premier_wins = wins
                elif _ci(row[0], "Wingman"):
                    if skill > 0:
                        out.wingman_rank = skill
                    if wins >= 0:
                        out.wingman_wins = wins
            continue
    return out
