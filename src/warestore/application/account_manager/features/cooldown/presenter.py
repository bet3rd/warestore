# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account cooldown use cases."""

from __future__ import annotations

import time

from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.features.accounts.presenter import (
    AccountsPresenter,
)
from warestore.domain.accounts.cooldown import is_cooldown_active


class CooldownPresenter:
    def __init__(
        self,
        ctrl: AccountManagerController,
        accounts: AccountsPresenter,
    ) -> None:
        self._ctrl = ctrl
        self._accounts = accounts

    def cooldown_label_for(self, steam_id: str) -> str:
        if not steam_id:
            return ""
        record = self._ctrl.get_metadata(steam_id)
        return self._ctrl.format_cooldown(record.cooldown_until)

    def set_account_cooldown(self, steam_id: str, duration_seconds: int) -> None:
        if not steam_id:
            return
        if duration_seconds <= 0:
            self._ctrl.clear_cooldown(steam_id)
        else:
            self._ctrl.set_cooldown(steam_id, duration_seconds)

    def build_cooldown_watch(self, accounts: list[dict]) -> dict[str, int]:
        watch: dict[str, int] = {}
        for acc in accounts:
            steam_id = acc.get("steamid", "")
            if not steam_id:
                continue
            until = self._ctrl.get_metadata(steam_id).cooldown_until
            if is_cooldown_active(until):
                watch[steam_id] = until
        return watch

    def pop_expired_cooldowns(
        self,
        watch: dict[str, int],
        accounts: list[dict],
    ) -> list[str]:
        if not watch:
            return []
        now = int(time.time())
        by_id = {acc.get("steamid", ""): acc for acc in accounts}
        expired_names: list[str] = []
        for steam_id, until in list(watch.items()):
            if until > now:
                continue
            watch.pop(steam_id, None)
            self._ctrl.clear_cooldown(steam_id)
            acc = by_id.get(steam_id)
            if acc:
                expired_names.append(self._accounts.account_display_name(acc))
        return expired_names
