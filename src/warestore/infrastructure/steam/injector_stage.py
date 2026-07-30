# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Discovery + on-demand download of the HWID spoofer injector.

The injector is deliberately NOT bundled with the app — the base install stays a
plain account manager (cleaner AV profile). The user installs the spoofer on
demand from Settings, which downloads injector.exe from the steam_hwid_spoofer
GitHub releases into a persistent per-user dir. Its data files
(hardware_pool.json, profiles.json) live beside it there.
"""

import logging
import os
import sys
import urllib.request
from pathlib import Path

from warestore.config.settings import ACCOUNT_MANAGER_DATA_DIR

logger = logging.getLogger(__name__)

# Latest release asset on the spoofer repo. Attach an asset named injector.exe.
INJECTOR_URL = (
    "https://github.com/bet3rd/steam_hwid_spoofer/releases/latest/download/injector.exe"
)


def data_dir() -> str:
    """Persistent dir holding the injector and its data files.

    Frozen: ``%APPDATA%\\SteamLoginTool_CLI\\bin``. Dev: the repo root, where a
    locally built injector.exe / hardware_pool.json already live.
    """
    if getattr(sys, "frozen", False):
        return os.path.join(ACCOUNT_MANAGER_DATA_DIR, "bin")
    return str(Path(__file__).resolve().parents[4])


def injector_path() -> str:
    return os.path.join(data_dir(), "injector.exe")


def is_installed() -> bool:
    return os.path.exists(injector_path())


def download_injector() -> None:
    """Download injector.exe into :func:`data_dir`. Raises on failure."""
    target_dir = data_dir()
    os.makedirs(target_dir, exist_ok=True)
    dest = injector_path()
    tmp = dest + ".part"
    logger.info(f"Downloading HWID spoofer from {INJECTOR_URL}")
    try:
        urllib.request.urlretrieve(INJECTOR_URL, tmp)
        os.replace(tmp, dest)
        logger.info("HWID spoofer installed")
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        raise
