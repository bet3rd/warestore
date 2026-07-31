# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging
import os

import vdf

from warestore.config.settings import STEAMID64_BASE

logger = logging.getLogger(__name__)


class PersonaGateway:
    def set_state(self, steam_dir: str, steam_id64: str, state: int = 7) -> None:
        steamid32 = int(steam_id64) - STEAMID64_BASE
        config_dir = os.path.join(steam_dir, "userdata", str(steamid32), "config")
        localconfig = os.path.join(config_dir, "localconfig.vdf")
        os.makedirs(config_dir, exist_ok=True)

        prefs_key = f"FriendStoreLocalPrefs_{steamid32}"
        prefs_val = f'{{"ePersonaState":{state},"strNonFriendsAllowedToMsg":""}}'

        data: dict = {}
        if os.path.exists(localconfig):
            try:
                with open(localconfig, encoding="utf-8", errors="replace") as f:
                    data = vdf.loads(f.read())
            except Exception as exc:
                logger.warning(f"localconfig.vdf unreadable, recreating: {exc}")
                data = {}

        store = data.setdefault("UserLocalConfigStore", {})
        friends = store.setdefault("friends", {})
        friends["SignIntoFriends"] = "1"
        friends["PersonaStateDesired"] = str(state)
        store.setdefault("WebStorage", {})[prefs_key] = prefs_val

        with open(localconfig, "w", encoding="utf-8") as f:
            f.write(vdf.dumps(data, pretty=True))

    def set_remote_play(self, steam_dir: str, steam_id64: str, enabled: bool) -> None:
        """Toggle Steam Settings → Remote Play → "Enable Remote Play".

        Per-account setting, stored in the same localconfig.vdf as the persona
        state under UserLocalConfigStore → streaming_v2 → EnableStreaming.
        """
        steamid32 = int(steam_id64) - STEAMID64_BASE
        config_dir = os.path.join(steam_dir, "userdata", str(steamid32), "config")
        localconfig = os.path.join(config_dir, "localconfig.vdf")
        os.makedirs(config_dir, exist_ok=True)

        data: dict = {}
        if os.path.exists(localconfig):
            try:
                with open(localconfig, encoding="utf-8", errors="replace") as f:
                    data = vdf.loads(f.read())
            except Exception as exc:
                # Don't overwrite a config we failed to parse — leave it alone.
                logger.warning(f"localconfig.vdf unreadable, Remote Play skipped: {exc}")
                return

        # Steam only writes streaming_v2 once the account has run at least
        # once, so create the block when it's missing.
        (data.setdefault("UserLocalConfigStore", {}).setdefault("streaming_v2", {}))[
            "EnableStreaming"
        ] = "1" if enabled else "0"

        try:
            with open(localconfig, "w", encoding="utf-8") as f:
                f.write(vdf.dumps(data, pretty=True))
            logger.info(f'Remote Play {"enabled" if enabled else "disabled"}.')
        except Exception as exc:
            logger.warning(f"Remote Play write failed: {exc}")

    # CS2 launch options live under a deeply-nested key in localconfig.vdf:
    # UserLocalConfigStore → Software → Valve → Steam → apps → 730 →
    # LaunchOptions. This is exactly where Steam itself reads/writes them; a
    # shallower path (e.g. UserLocalConfigStore → apps → 730) is silently ignored.
    _LAUNCH_OPTS_PATH = ("Software", "Valve", "Steam", "apps", "730")

    def _localconfig_path(self, steam_id64: str, steam_dir: str) -> str:
        steamid32 = int(steam_id64) - STEAMID64_BASE
        return os.path.join(
            steam_dir, "userdata", str(steamid32), "config", "localconfig.vdf"
        )

    def get_cs2_launch_options(self, steam_dir: str, steam_id64: str) -> str:
        localconfig = self._localconfig_path(steam_id64, steam_dir)
        if not os.path.exists(localconfig):
            return ""
        try:
            with open(localconfig, encoding="utf-8", errors="replace") as f:
                node = vdf.loads(f.read()).get("UserLocalConfigStore", {})
        except Exception:
            return ""
        for key in self._LAUNCH_OPTS_PATH:
            node = node.get(key, {}) if isinstance(node, dict) else {}
        return node.get("LaunchOptions", "") if isinstance(node, dict) else ""

    def set_cs2_launch_options(self, steam_dir: str, steam_id64: str, options: str) -> None:
        localconfig = self._localconfig_path(steam_id64, steam_dir)
        os.makedirs(os.path.dirname(localconfig), exist_ok=True)
        data: dict = {}
        if os.path.exists(localconfig):
            try:
                with open(localconfig, encoding="utf-8", errors="replace") as f:
                    data = vdf.loads(f.read())
            except Exception as exc:
                logger.warning(f"localconfig.vdf unreadable, CS2 launch options skipped: {exc}")
                return
        node = data.setdefault("UserLocalConfigStore", {})
        for key in self._LAUNCH_OPTS_PATH:
            node = node.setdefault(key, {})
        node["LaunchOptions"] = options
        try:
            with open(localconfig, "w", encoding="utf-8") as f:
                f.write(vdf.dumps(data, pretty=True))
            logger.info(f'CS2 launch options set: "{options}"')
        except Exception as exc:
            logger.warning(f"CS2 launch options write failed: {exc}")

    def copy_launch_options(self, steam_dir: str, src_sid: str, dst_sid: str) -> bool:
        """Copy the source account's CS2 launch options to the target.

        No-op (False) when the accounts match or the source has none set.
        """
        if src_sid == dst_sid:
            return False
        options = self.get_cs2_launch_options(steam_dir, src_sid)
        if not options:
            return False
        self.set_cs2_launch_options(steam_dir, dst_sid, options)
        logger.info(f"CS2 launch options copied → {dst_sid}")
        return True
