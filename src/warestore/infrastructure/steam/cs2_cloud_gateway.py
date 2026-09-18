# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Toggle Steam Cloud sync for CS2 on a single account.

Steam stores the per-app cloud switch per account in
``userdata/<id32>/7/remote/sharedconfig.vdf`` under
``UserRoamingConfigStore/Software/Valve/Steam/apps/<appid>/cloudenabled``.

Turning it off for 730 makes the on-disk config authoritative: Steam stops
reconciling that account's CS2 files against the cloud, so a config seeded from
a source account can't be silently overwritten on the next launch. Steam must be
closed when this is written (it is during seeding), or Steam will rewrite the
file from memory on exit.
"""

from __future__ import annotations

import logging
import os

import vdf

from warestore.config.settings import CS2_APP_ID, STEAMID64_BASE
from warestore.infrastructure.persistence.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)

_ROOT_KEY = "UserRoamingConfigStore"


class Cs2CloudGateway:
    def sharedconfig_path(self, steam_dir: str, steam_id64: str) -> str:
        steamid32 = int(steam_id64) - STEAMID64_BASE
        return os.path.join(
            steam_dir, "userdata", str(steamid32), "7", "remote", "sharedconfig.vdf"
        )

    def set_cloud_enabled(
        self, steam_dir: str, steam_id64: str, enabled: bool, app_id: str = CS2_APP_ID
    ) -> bool:
        """Set ``cloudenabled`` for one app on one account. True if written."""
        path = self.sharedconfig_path(steam_dir, steam_id64)

        data: dict = {}
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8", errors="replace") as f:
                    data = vdf.loads(f.read())
            except Exception as exc:  # noqa: BLE001
                # Don't clobber a config we couldn't parse -- leave it alone.
                logger.warning(f"sharedconfig.vdf unreadable, CS2 cloud toggle skipped: {exc}")
                return False

        # Steam's root key casing has varied across versions; reuse whatever the
        # file already has rather than adding a second, divergent root block.
        root_key = next(
            (k for k in data if k.lower() == _ROOT_KEY.lower()), _ROOT_KEY
        )
        store = data.setdefault(root_key, {})
        apps = (
            store.setdefault("Software", {})
            .setdefault("Valve", {})
            .setdefault("Steam", {})
            .setdefault("apps", {})
        )
        apps.setdefault(app_id, {})["cloudenabled"] = "0" if not enabled else "1"

        try:
            atomic_write_text(path, vdf.dumps(data, pretty=True))
        except OSError as exc:
            logger.warning(f"Could not write sharedconfig.vdf: {exc}")
            return False
        logger.info(
            "CS2 cloud sync %s for %s", "enabled" if enabled else "disabled", steam_id64
        )
        return True

    def is_cloud_enabled(
        self, steam_dir: str, steam_id64: str, app_id: str = CS2_APP_ID
    ) -> bool:
        """True unless the account explicitly has cloud disabled for the app."""
        path = self.sharedconfig_path(steam_dir, steam_id64)
        if not os.path.exists(path):
            return True
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                data = vdf.loads(f.read())
        except Exception:  # noqa: BLE001
            return True
        for key, store in data.items():
            if key.lower() != _ROOT_KEY.lower():
                continue
            apps = (
                store.get("Software", {})
                .get("Valve", {})
                .get("Steam", {})
                .get("apps", {})
            )
            value = apps.get(app_id, {}).get("cloudenabled")
            if value is not None:
                return value != "0"
        return True
