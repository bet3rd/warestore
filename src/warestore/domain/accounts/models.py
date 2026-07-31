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
        }
