# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Cooldown watch timer and account cooldown actions."""

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget

from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.presenter import AccountManagerPresenter
from warestore.presentation.account_manager.features.cooldown.dialog import (
    CooldownCustomDialog,
)
from warestore.presentation.account_manager.support.account_targets import (
    normalize_account_targets,
)
from warestore.presentation.account_manager.ui.tray import notify_cooldown_finished


class CooldownCoordinator:
    def __init__(
        self,
        parent: QWidget,
        presenter: AccountManagerPresenter,
        controller: AccountManagerController,
        *,
        accounts_on_grid: Callable[[], list[dict]],
        refresh_cards: Callable[[], None],
        set_status: Callable[[str], None],
    ) -> None:
        self._parent = parent
        self._presenter = presenter
        self._controller = controller
        self._accounts_on_grid = accounts_on_grid
        self._refresh_cards = refresh_cards
        self._set_status = set_status
        self._watch: dict[str, int] = {}
        self._tray = None
        self._window: QWidget | None = None

        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._on_tick)
        self._timer.start(15_000)

    def set_notify_targets(self, tray, window: QWidget) -> None:
        self._tray = tray
        self._window = window

    def sync_watch(self, accounts: list[dict]) -> None:
        self._watch = self._presenter.build_cooldown_watch(accounts)
        self._sync_timer()

    def set_cooldown(self, accounts, duration_seconds: int) -> None:
        targets = normalize_account_targets(accounts)
        if not targets:
            return

        for acc in targets:
            steam_id = acc.get("steamid", "")
            if not steam_id:
                continue

            self._presenter.set_account_cooldown(steam_id, duration_seconds)
            if duration_seconds <= 0:
                self._watch.pop(steam_id, None)
            else:
                until = self._controller.get_metadata(steam_id).cooldown_until
                if until:
                    self._watch[steam_id] = until

        self._sync_timer()
        self._refresh_cards()

        if len(targets) == 1:
            acc = targets[0]
            name = self._presenter.account_display_name(acc)
            if duration_seconds <= 0:
                self._set_status(f"Cooldown cleared for {name}")
                return
            steam_id = acc.get("steamid", "")
            label = self._presenter.cooldown_label_for(steam_id)
            suffix = f" — {label}" if label else ""
            self._set_status(f"Cooldown set for {name}{suffix}")
            return

        if duration_seconds <= 0:
            self._set_status(f"Cooldown cleared for {len(targets)} accounts")
        else:
            self._set_status(f"Cooldown set for {len(targets)} accounts")

    def open_custom_dialog(self, accounts) -> None:
        targets = normalize_account_targets(accounts)
        if not targets:
            return

        dialog = CooldownCustomDialog(
            self._parent,
            exclude_from_capture=self._controller.load_settings().get(
                "exclude_from_capture", True
            ),
        )
        if dialog.exec_() != dialog.Accepted:
            return
        self.set_cooldown(targets, dialog.duration_seconds())

    def _sync_timer(self) -> None:
        interval = 1000 if self._watch else 15_000
        if self._timer.interval() != interval:
            self._timer.setInterval(interval)

    def _on_tick(self) -> None:
        if not self._watch:
            self._sync_timer()
            return

        accounts = self._accounts_on_grid()
        if not accounts:
            return

        expired = self._presenter.pop_expired_cooldowns(self._watch, accounts)
        self._refresh_cards()
        if expired and self._window is not None:
            notify_cooldown_finished(self._tray, self._window, expired)
        self._sync_timer()
