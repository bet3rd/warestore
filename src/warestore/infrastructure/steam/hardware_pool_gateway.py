# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging
import os
import shutil
import urllib.request

logger = logging.getLogger(__name__)

_URL = (
    "https://raw.githubusercontent.com/bet3rd/steam_hwid_spoofer"
    "/main/tools/hardware_pool.json"
)
_FILENAME = "hardware_pool.json"


def _persistent_dir() -> str:
    """Directory where hardware_pool.json is cached between runs — the same
    persistent dir the injector is staged into, so the pool lands right next to
    it (dest == cache, no extra copy). In dev that's the repo root.
    """
    from warestore.infrastructure.steam.injector_stage import data_dir

    return data_dir()


def ensure(injector_path: str) -> bool:
    """Ensure hardware_pool.json exists next to injector_path.

    1. If the file is already there → nothing to do.
    2. If a cached copy lives in the persistent dir → copy it across.
    3. Otherwise download from the upstream raw URL, cache it, then copy.

    Returns True when the file is ready, False on unrecoverable failure.
    """
    injector_dir = os.path.dirname(injector_path)
    dest = os.path.join(injector_dir, _FILENAME)

    if os.path.exists(dest):
        return True

    cache_dir = _persistent_dir()
    cache = os.path.join(cache_dir, _FILENAME)

    if not os.path.exists(cache):
        logger.info("hardware_pool.json not found — downloading from remote")
        try:
            urllib.request.urlretrieve(_URL, cache)
            logger.info("hardware_pool.json downloaded and cached")
        except Exception as exc:
            logger.warning(f"Failed to download hardware_pool.json: {exc}")
            return False

    if dest != cache:
        try:
            shutil.copy2(cache, dest)
        except Exception as exc:
            logger.warning(f"Failed to copy hardware_pool.json to injector dir: {exc}")
            return False

    return True
