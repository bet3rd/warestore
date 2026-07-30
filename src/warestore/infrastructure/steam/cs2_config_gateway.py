# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging
import os
import shutil

from warestore.config.settings import CS2_APP_ID, STEAMID64_BASE

logger = logging.getLogger(__name__)


class Cs2ConfigGateway:
    """Copy an account's per-user CS2 (app 730) config folder to another account.

    CS2 keeps per-account settings (video, cfg, etc.) under
    ``<steam>/userdata/<accountid32>/730/``. Seeding a target account means
    copying that whole folder from a chosen *source* account, after backing up
    whatever the target already had.
    """

    def account_id32(self, steam_id64: str) -> int:
        return int(steam_id64) - STEAMID64_BASE

    def config_dir(self, steam_dir: str, steam_id64: str) -> str:
        return os.path.join(
            steam_dir, "userdata", str(self.account_id32(steam_id64)), CS2_APP_ID
        )

    @staticmethod
    def _non_empty_dir(path: str) -> bool:
        if not os.path.isdir(path):
            return False
        with os.scandir(path) as it:
            return any(it)

    def has_config(self, steam_dir: str, steam_id64: str) -> bool:
        return self._non_empty_dir(self.config_dir(steam_dir, steam_id64))

    def copy_config(self, steam_dir: str, src_sid: str, dst_sid: str) -> bool:
        """Copy the source 730 folder into the target, backing up any existing one.

        Returns True only when a copy actually happened. No-op (False) when the
        two SteamIDs match or the source has no CS2 config to copy.
        """
        if src_sid == dst_sid:
            logger.info("CS2 config: source and target are the same account — skipping.")
            return False

        src = self.config_dir(steam_dir, src_sid)
        if not self._non_empty_dir(src):
            logger.warning(f"CS2 config: source has no 730 config at {src} — skipping.")
            return False

        dst = self.config_dir(steam_dir, dst_sid)
        try:
            if os.path.exists(dst):
                backup = self._backup_path(dst)
                os.replace(dst, backup)  # same-filesystem rename of the dir
                logger.info(f"CS2 config: backed up existing target → {backup}")
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copytree(src, dst)
            logger.info(f"CS2 config: copied {src} → {dst}")
            return True
        except OSError as exc:
            logger.warning(f"CS2 config copy failed: {exc}")
            return False

    @staticmethod
    def _backup_path(dst: str) -> str:
        base = f"{dst}.bak"
        candidate = base
        n = 1
        while os.path.exists(candidate):
            candidate = f"{base}{n}"
            n += 1
        return candidate
