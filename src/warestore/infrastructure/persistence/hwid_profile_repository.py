# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class HwidProfileRepository:
    """Reads and writes profiles.json next to injector.exe."""

    def _path(self, injector_dir: str) -> Path:
        return Path(injector_dir) / "profiles.json"

    def _load(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception as exc:
            logger.warning(f"profiles.json read error: {exc}")
            return {}

    def _save(self, path: Path, data: dict) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4)
        except Exception as exc:
            logger.error(f"profiles.json write error: {exc}")

    def get(self, account_name: str, injector_dir: str) -> dict | None:
        return self._load(self._path(injector_dir)).get(account_name)

    def delete(self, account_name: str, injector_dir: str) -> bool:
        path = self._path(injector_dir)
        data = self._load(path)
        if account_name not in data:
            return False
        del data[account_name]
        self._save(path, data)
        logger.info(f"Deleted HWID profile for {account_name!r}")
        return True

    def all_profiles(self, injector_dir: str) -> dict:
        return self._load(self._path(injector_dir))
