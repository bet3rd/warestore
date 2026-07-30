# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Finds and removes leftover Steam `userdata/<id32>` folders.

Steam never cleans these up when an account leaves the login list, so they
accumulate (game configs, screenshots, cloud saves, CS2 configs).

Two tiers of candidate, because "not in loginusers.vdf" alone is unsafe:
WareStore logs accounts in from saved tokens, so a managed account is
routinely absent from Steam's login list while still very much in use --
deleting its folder would destroy its per-account CS2 config.
"""

from __future__ import annotations

import logging
import os
import shutil
from dataclasses import dataclass

from warestore.config.settings import STEAMID64_BASE

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class UserdataFolder:
    account_id32: str
    path: str
    size_bytes: int
    token_managed: bool  # WareStore still holds a login token for it
    has_cs2_config: bool
    account_name: str = ""  # resolved for display; "" when unknown


class UserdataGateway:
    def userdata_dir(self, steam_dir: str) -> str:
        return os.path.join(steam_dir, "userdata")

    def _to_id32(self, steam_id64: str) -> str | None:
        try:
            return str(int(steam_id64) - STEAMID64_BASE)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dir_size(path: str) -> int:
        total = 0
        for root, _dirs, files in os.walk(path):
            for name in files:
                try:
                    total += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass  # file vanished or locked mid-walk; not worth failing over
        return total

    def scan(
        self,
        steam_dir: str,
        login_ids64: set[str],
        token_ids64: set[str],
        names_by_id32: dict[str, str] | None = None,
    ) -> list[UserdataFolder]:
        """Return userdata folders with no matching entry in loginusers.vdf.

        `token_managed` marks the ones WareStore can still log into, so callers
        can keep them out of a delete by default. `names_by_id32` supplies a
        display name per folder id when available.
        """
        base = self.userdata_dir(steam_dir)
        if not os.path.isdir(base):
            return []

        login32 = {v for v in (self._to_id32(s) for s in login_ids64) if v}
        token32 = {v for v in (self._to_id32(s) for s in token_ids64) if v}
        names = names_by_id32 or {}

        found: list[UserdataFolder] = []
        for name in os.listdir(base):
            path = os.path.join(base, name)
            # Steam uses "0" for anonymous/shared data -- never a real account.
            if not name.isdigit() or name == "0" or not os.path.isdir(path):
                continue
            if name in login32:
                continue
            found.append(
                UserdataFolder(
                    account_id32=name,
                    path=path,
                    size_bytes=self._dir_size(path),
                    token_managed=name in token32,
                    has_cs2_config=os.path.isdir(os.path.join(path, "730")),
                    account_name=names.get(name, ""),
                )
            )
        found.sort(key=lambda f: f.size_bytes, reverse=True)
        return found

    def delete(self, folders: list[UserdataFolder]) -> tuple[int, int, list[str]]:
        """Delete the given folders. Returns (count, bytes_freed, errors)."""
        deleted = 0
        freed = 0
        errors: list[str] = []
        for folder in folders:
            try:
                shutil.rmtree(folder.path)
                deleted += 1
                freed += folder.size_bytes
                logger.info(f"Removed userdata/{folder.account_id32}")
            except Exception as exc:
                errors.append(f"{folder.account_id32}: {exc}")
                logger.warning(f"userdata/{folder.account_id32} delete failed: {exc}")
        return deleted, freed, errors
