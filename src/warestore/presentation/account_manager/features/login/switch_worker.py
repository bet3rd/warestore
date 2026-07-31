# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from warestore.application.account_manager.controller import AccountManagerController

logger = logging.getLogger(__name__)


class SwitchWorker(QThread):
    finished = pyqtSignal(bool)
    status = pyqtSignal(str)

    def __init__(
        self,
        mode: str,
        acc: dict | None = None,
        token: str = "",
        persona_state: int = 7,
        open_cs2: bool = False,
        cs2_options: str = "",
        disable_workshop: bool = False,
        disable_remote_play: bool = False,
        add_account_only: bool = False,
        spoof_on_login: bool = False,
        *,
        ctrl: AccountManagerController,
    ):
        super().__init__()
        self._ctrl = ctrl
        self.mode = mode
        self.acc = acc
        self.token = token
        self.persona_state = persona_state
        self.open_cs2 = open_cs2
        self.cs2_options = cs2_options
        self.disable_workshop = disable_workshop
        self.disable_remote_play = disable_remote_play
        self.add_account_only = add_account_only
        self.spoof_on_login = spoof_on_login

    def run(self):
        try:
            verb = "Adding" if self.add_account_only else "Switching"
            self.status.emit(f"{verb} — {self._label()}…")
            self._ctrl.kill_steam()
            steam_dir = self._ctrl.steam_install_path()
            ok = self._perform_login()
            if ok:
                self._post_login(steam_dir)
            self.finished.emit(ok)
        except Exception as exc:
            logger.exception(f"Worker error: {exc}")
            self.finished.emit(False)

    def _label(self) -> str:
        if self.mode == "native" and self.acc:
            return self.acc.get("account_name", "account")
        return "token login"

    def _perform_login(self) -> bool:
        if self.mode == "token":
            return self._ctrl.perform_token_login(self.token, self.disable_remote_play)
        return self._ctrl.switch_account(
            self.acc, self.persona_state, self.disable_remote_play
        )

    def _post_login(self, steam_dir: str | None) -> None:
        # Workshop downloads are per-account (driven by the account's subscription
        # list), so we need the SteamID we just logged into. On a native switch
        # that's acc["steamid"]; a token-add account has no local subscription
        # file yet (nothing to download), so there's nothing to disable there.
        if self.disable_workshop and steam_dir and self.acc:
            steam_id = self.acc.get("steamid")
            if steam_id:
                disabled = self._ctrl.disable_cs2_workshop(steam_dir, steam_id)
                if disabled:
                    self.status.emit(f"Disabled {disabled} Workshop item(s).")
        # Seed this account's CS2 config from the chosen source account the first
        # time we log into it natively (Steam is closed here, so the folder is in
        # place before CS2 next launches). Token-login adds are seeded later, on
        # their first native switch.
        if self.mode == "native" and self.acc:
            try:
                if self._ctrl.seed_cs2_config_if_new(self.acc["steamid"]):
                    self.status.emit("Copied CS2 config from source account.")
            except Exception as exc:  # never let seeding break a login
                logger.warning(f"CS2 config seeding skipped: {exc}")
            # Launch options track the source on EVERY switch (not seed-once), so
            # every account keeps the source's launch options. Steam is closed
            # here, so the value is in place before the next launch.
            try:
                if self._ctrl.apply_source_launch_options(self.acc["steamid"]):
                    self.status.emit("Applied CS2 launch options from source.")
            except Exception as exc:
                logger.warning(f"CS2 launch options copy skipped: {exc}")
        if self.add_account_only:
            logger.info("Account added — leaving Steam closed (add-only mode).")
            return
        launch_cs2 = self.open_cs2 and self.mode == "native"
        # Only apply the configured launch options when the user actually set
        # some — an empty field must not overwrite options seeded from the CS2
        # source account (or ones the account already had).
        if (
            self.mode == "native"
            and self.open_cs2
            and self.acc
            and steam_dir
            and self.cs2_options.strip()
        ):
            self._ctrl.set_cs2_launch_options(
                steam_dir, self.acc["steamid"], self.cs2_options
            )
        self._launch_steam(launch_cs2)

    def _launch_steam(self, open_cs2: bool) -> None:
        if not self.spoof_on_login:
            self._ctrl.launch_steam(open_cs2=open_cs2)
            return
        injector_path = self._ctrl.find_injector_exe()
        if injector_path:
            logger.info("Spoofer enabled — launching Steam via injector.")
            self._ctrl.ensure_hardware_pool(injector_path)
            self._ctrl.launch_steam_with_spoofer(injector_path, open_cs2=open_cs2)
        else:
            logger.warning(
                "spoof_on_login is set but injector.exe was not found"
                " — falling back to normal Steam launch."
            )
            self._ctrl.launch_steam(open_cs2=open_cs2)
