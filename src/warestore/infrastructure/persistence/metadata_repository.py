# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os
from datetime import datetime

from warestore.config.settings import ACCOUNT_MANAGER_DATA_DIR
from warestore.domain.accounts.models import AccountRecord
from warestore.infrastructure.persistence.json_store import JsonStore


class AccountMetadataRepository:
    def __init__(self, path: str | None = None) -> None:
        self._store = JsonStore(
            path or os.path.join(ACCOUNT_MANAGER_DATA_DIR, "account_metadata.json")
        )

    def get(self, steam_id: str) -> AccountRecord:
        return AccountRecord.from_raw(self._load().get(steam_id, {}))

    def all(self) -> dict[str, AccountRecord]:
        """Every stored record in one read (avoids N file reads on load)."""
        return {sid: AccountRecord.from_raw(raw) for sid, raw in self._load().items()}

    def set_profiles(self, profiles: dict[str, dict]) -> None:
        """Batch-store persona/avatar_hash for many accounts in a single write.

        Each value is a dict with optional 'persona' and 'avatar_hash'. Empty
        values are ignored so a failed fetch never wipes a good cached value.
        """
        if not profiles:
            return
        data = self._load()
        for steam_id, prof in profiles.items():
            record = AccountRecord.from_raw(data.get(steam_id, {}))
            if prof.get("persona"):
                record.persona = prof["persona"]
            if prof.get("avatar_hash"):
                record.avatar_hash = prof["avatar_hash"]
            data[steam_id] = record.to_dict()
        self._save(data)

    def set_last_played(self, steam_id: str, played: bool = True) -> None:
        data = self._load()
        record = AccountRecord.from_raw(data.get(steam_id, {}))
        record.last_played = int(datetime.now().timestamp()) if played else 0
        data[steam_id] = record.to_dict()
        self._save(data)

    def set_cooldown(self, steam_id: str, duration_seconds: int) -> None:
        data = self._load()
        record = AccountRecord.from_raw(data.get(steam_id, {}))
        record.cooldown_until = int(datetime.now().timestamp()) + max(0, duration_seconds)
        record.cooldown_duration = max(0, duration_seconds)
        data[steam_id] = record.to_dict()
        self._save(data)

    def set_color(self, steam_id: str, color: str) -> None:
        data = self._load()
        record = AccountRecord.from_raw(data.get(steam_id, {}))
        record.color = color.strip()
        data[steam_id] = record.to_dict()
        self._save(data)

    def set_cs2_rank(
        self,
        steam_id: str,
        premier_rating: int,
        wingman_rank: int,
        cooldown_expires: int,
        premier_wins: int = -1,
        wingman_wins: int = -1,
    ) -> None:
        """Cache the last on-demand CS2 rank fetch so it survives a reload."""
        data = self._load()
        record = AccountRecord.from_raw(data.get(steam_id, {}))
        record.premier_rating = int(premier_rating)
        record.premier_wins = int(premier_wins)
        record.wingman_rank = int(wingman_rank)
        record.wingman_wins = int(wingman_wins)
        record.cs2_cooldown_expires = int(cooldown_expires)
        data[steam_id] = record.to_dict()
        self._save(data)

    def set_cs2_seeded(self, steam_id: str, seeded: bool = True) -> None:
        data = self._load()
        record = AccountRecord.from_raw(data.get(steam_id, {}))
        record.cs2_seeded = seeded
        data[steam_id] = record.to_dict()
        self._save(data)

    def clear_cooldown(self, steam_id: str) -> None:
        data = self._load()
        record = AccountRecord.from_raw(data.get(steam_id, {}))
        record.cooldown_until = 0
        record.cooldown_duration = 0
        data[steam_id] = record.to_dict()
        self._save(data)

    def delete(self, steam_id: str) -> None:
        data = self._load()
        if steam_id in data:
            del data[steam_id]
            self._save(data)

    def _load(self) -> dict[str, dict]:
        return self._store.read()

    def _save(self, data: dict[str, dict]) -> None:
        self._store.write(data)
