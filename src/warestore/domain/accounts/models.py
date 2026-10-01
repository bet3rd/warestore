# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from dataclasses import dataclass


@dataclass
class AccountRecord:
    eya: str = ""
    last_played: int = 0
    cooldown_until: int = 0
    cooldown_duration: int = 0
    color: str = ""
    cs2_seeded: bool = False
    # Cached from the last status refresh so the card shows the current name +
    # avatar on launch, before the next refresh completes.
    persona: str = ""
    avatar_hash: str = ""
    # Cached from the last on-demand CS2 rank fetch so it survives a grid reload
    # / relaunch. -1 = unknown/unranked; cooldown expiry is unix (0 = none).
    premier_rating: int = -1
    premier_wins: int = -1
    wingman_rank: int = -1
    wingman_wins: int = -1
    cs2_cooldown_expires: int = 0
    # Last account check (one CM/GC session): CS2 level, when, what it did, and
    # whether the last attempt was skipped because the account was in use.
    cs2_level: int = -1
    last_check: int = 0
    last_check_summary: str = ""
    check_pending: bool = False
    # From the CS2 Game Coordinator only: 1 Prime, 0 non-Prime, -1 never read.
    prime: int = -1

    @classmethod
    def from_raw(cls, raw: object) -> "AccountRecord":
        if isinstance(raw, str):
            return cls(eya=raw)
        if isinstance(raw, dict):
            return cls(
                eya=str(raw.get("eya", "")),
                last_played=int(raw.get("last_played", 0)),
                cooldown_until=int(raw.get("cooldown_until", 0)),
                cooldown_duration=int(raw.get("cooldown_duration", 0)),
                color=str(raw.get("color", "")),
                cs2_seeded=bool(raw.get("cs2_seeded", False)),
                persona=str(raw.get("persona", "")),
                avatar_hash=str(raw.get("avatar_hash", "")),
                premier_rating=int(raw.get("premier_rating", -1)),
                premier_wins=int(raw.get("premier_wins", -1)),
                wingman_rank=int(raw.get("wingman_rank", -1)),
                wingman_wins=int(raw.get("wingman_wins", -1)),
                cs2_cooldown_expires=int(raw.get("cs2_cooldown_expires", 0)),
                cs2_level=int(raw.get("cs2_level", -1)),
                last_check=int(raw.get("last_check", 0)),
                last_check_summary=str(raw.get("last_check_summary", "")),
                check_pending=bool(raw.get("check_pending", False)),
                prime=int(raw.get("prime", -1)),
            )
        return cls()

    def to_dict(self) -> dict:
        return {
            "eya": self.eya,
            "last_played": self.last_played,
            "cooldown_until": self.cooldown_until,
            "cooldown_duration": self.cooldown_duration,
            "color": self.color,
            "cs2_seeded": self.cs2_seeded,
            "persona": self.persona,
            "avatar_hash": self.avatar_hash,
            "premier_rating": self.premier_rating,
            "premier_wins": self.premier_wins,
            "wingman_rank": self.wingman_rank,
            "wingman_wins": self.wingman_wins,
            "cs2_cooldown_expires": self.cs2_cooldown_expires,
            "cs2_level": self.cs2_level,
            "last_check": self.last_check,
            "last_check_summary": self.last_check_summary,
            "check_pending": self.check_pending,
            "prime": self.prime,
        }
