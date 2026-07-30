# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import requests

from warestore.config.settings import CURRENT_VERSION, VERSION_CHECK_URL


class UpdateGateway:
    def check(self) -> dict:
        response = requests.get(VERSION_CHECK_URL, timeout=15)
        response.raise_for_status()
        info = response.json()
        latest = info["latest_version"]
        force_below = info["force_update_below_version"]
        return {
            "latest_version": latest,
            "change_log": info["change_log"],
            "download_url": info["download_url"],
            "force_update": CURRENT_VERSION <= force_below,
            "update_available": latest != CURRENT_VERSION,
        }
