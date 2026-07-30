# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Login, switch, and relogin worker orchestration."""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtWidgets import QLineEdit, QWidget

from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.presenter import AccountManagerPresenter
from warestore.presentation.account_manager.features.login.switch_worker import (
    SwitchWorker,
)


class LoginCoordinator:
    def __init__(
        self,
        parent: QWidget,
        controller: AccountManagerController,
        presenter: AccountManagerPresenter,
        *,
        entry: QLineEdit,
        token_err,
        set_login_enabled: Callable[[bool], None],
        set_busy: Callable[[bool, str], None],
        set_status: Callable[[str], None],
        sync_layout: Callable[[], None],
        refresh_log: Callable[[], None],
        reload_accounts: Callable[[], None],
        get_selected_account: Callable[[], dict | None],
        set_selected_account: Callable[[dict], None],
    ) -> None:
        self._parent = parent
        self._ctrl = controller
        self._presenter = presenter
        self._entry = entry
        self._token_err = token_err
        self._set_login_enabled = set_login_enabled
        self._set_busy = set_busy
        self._set_status = set_status
        self._sync_layout = sync_layout
        self._refresh_log = refresh_log
        self._reload_accounts = reload_accounts
        self._get_selected = get_selected_account
        self._set_selected = set_selected_account
        self._worker: SwitchWorker | None = None

    def is_busy(self) -> bool:
        return bool(self._worker and self._worker.isRunning())

    def _set_token_error(
        self,
        text: str,
        *,
        sync_layout: Callable[[], None] | None = None,
    ) -> None:
        if text:
            self._token_err.setText(text)
            self._token_err.setVisible(True)
        else:
            self._token_err.clear()
            self._token_err.setVisible(False)
        if sync_layout:
            sync_layout()

    def validate_token_text(self, text: str, *, sync_layout: Callable[[], None]) -> None:
        raw = text.strip()
        ready = False
        if not raw:
            self._set_token_error("", sync_layout=sync_layout)
        else:
            entry = self._ctrl.sanitize_entry(raw)
            if entry:
                if not self._ctrl.is_entry_importable(entry):
                    self._set_token_error(
                        "Token expired — paste a fresh refresh token",
                        sync_layout=sync_layout,
                    )
                else:
                    self._set_token_error("", sync_layout=sync_layout)
                    ready = True
            else:
                self._set_token_error(
                    "Invalid token — use username----eyJ… or a bare JWT",
                    sync_layout=sync_layout,
                )
        self._set_login_enabled(ready)

    def login(self) -> None:
        raw = self._entry.text().strip()
        if not raw or self.is_busy():
            return
        token_str = self._ctrl.sanitize_entry(raw)
        if not token_str:
            self._set_token_error("Invalid token format", sync_layout=self._sync_layout)
            return
        if not self._ctrl.is_entry_importable(token_str):
            self._set_token_error(
                "Token expired — paste a fresh refresh token",
                sync_layout=self._sync_layout,
            )
            return
        self._set_token_error("")
        self.start_switch(mode="token", token=token_str)

    def switch_selected(self) -> None:
        acc = self._get_selected()
        if not acc or self.is_busy():
            return
        self.start_switch(mode="native", acc=acc)

    def relogin(self, acc: dict) -> None:
        entry_str = self._presenter.relogin_entry_for(acc)
        if not entry_str:
            self._set_status("No saved token for this account.")
            return
        self.start_switch(mode="token", token=entry_str, acc=acc)

    def switch_account(self, acc: dict) -> None:
        self._set_selected(acc)
        self.switch_selected()

    def start_switch(
        self,
        mode: str,
        token: str = "",
        acc: dict | None = None,
    ) -> None:
        target = acc or self._get_selected()
        opts = self._presenter.switch_worker_options(mode=mode, acc=target, token=token)
        label = self._presenter.switch_label(mode, target)
        self._worker = SwitchWorker(**opts, ctrl=self._ctrl)
        self._worker.status.connect(lambda msg: self._set_busy(True, msg))
        self._worker.finished.connect(self._on_worker_done)
        self._set_busy(True, f"Switching — {label}…")
        self._worker.start()

    def _on_worker_done(self, ok: bool) -> None:
        self._set_busy(False)
        if ok:
            self._reload_accounts()
            if self._entry.text().strip():
                self._entry.clear()
            self._set_login_enabled(False)
        else:
            self._set_status("Switch/login failed — see log.")
        self._refresh_log()
