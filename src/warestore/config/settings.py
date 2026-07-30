# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os

from warestore import __version__

CURRENT_VERSION = __version__
VERSION_CHECK_URL = "https://raw.githubusercontent.com/bet3rd/warestore/refs/heads/main/version.json"

ACCOUNT_MANAGER_DATA_DIR = os.path.join(
    os.environ.get("APPDATA", ""),
    "SteamLoginTool_CLI",
)
STEAMID64_BASE = 76561197960265728
CS2_APP_ID = "730"
