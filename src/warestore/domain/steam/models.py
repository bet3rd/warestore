# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LoginUser:
    steam_id: str
    account_name: str
    persona_name: str
    timestamp: int
    most_recent: str

    def to_dict(self) -> dict:
        return {
            "steamid": self.steam_id,
            "account_name": self.account_name,
            "persona_name": self.persona_name,
            "timestamp": self.timestamp,
            "most_recent": self.most_recent,
        }
