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
