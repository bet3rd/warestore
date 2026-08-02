# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os
from typing import Any

from warestore.config.settings import ACCOUNT_MANAGER_DATA_DIR
from warestore.infrastructure.persistence.json_store import JsonStore


class SettingsRepository:
    _DEFAULTS = {
        "open_cs2": False,
        "cs2_launch_options": "",
        "show_log_panel": False,
        "close_to_tray": False,
        "auto_remove_expired_tokens": False,
        "gcpd_check_on_launch": False,
        "disable_workshop": False,
        "disable_remote_play": True,
        "add_account_only": False,
        "spoof_on_login": False,
        "cs2_config_source_sid": "",
        "exclude_from_capture": True,
        "dpi_scale": 100,
        "steam_api_key": "",
        "vault_setup_done": False,
        "vault_mode": "dpapi",
        "vault_pw_salt": "",
        "vault_pw_wrap": "",
        "vault_rc_salt": "",
        "vault_rc_wrap": "",
        "window_x": None,
        "window_y": None,
    }

    def __init__(self, path: str | None = None) -> None:
        self._store = JsonStore(path or os.path.join(ACCOUNT_MANAGER_DATA_DIR, "settings.json"))

    def load(self) -> dict[str, Any]:
        return {**self._DEFAULTS, **self._store.read()}

    def save(self, settings: dict[str, Any]) -> None:
        self._store.write(settings)
