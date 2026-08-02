# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account-manager use cases — UI-agnostic orchestration."""

from __future__ import annotations

from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.features.accounts import (
    AccountLoadResult,
    AccountsPresenter,
)
from warestore.application.account_manager.features.cooldown import CooldownPresenter
from warestore.application.account_manager.features.login import LoginPresenter
from warestore.application.account_manager.view_models import (
    AccountCardMenuState,
    AccountCardViewState,
)


class AccountManagerPresenter:
    def __init__(self, ctrl: AccountManagerController) -> None:
        self._ctrl = ctrl
        self._accounts = AccountsPresenter(ctrl)
        self._cooldown = CooldownPresenter(ctrl, self._accounts)
        self._login = LoginPresenter(ctrl)

    def load_accounts(self) -> AccountLoadResult:
        return self._accounts.load_accounts()

    def jwt_expiry_for(self, steam_id: str) -> int:
        return self._accounts.jwt_expiry_for(steam_id)

    def cooldown_label_for(self, steam_id: str) -> str:
        return self._cooldown.cooldown_label_for(steam_id)

    def card_menu_for(self, acc: dict) -> AccountCardMenuState:
        return self._accounts.card_menu_for(
            acc,
            has_cooldown=bool(self._cooldown.cooldown_label_for(acc.get("steamid", ""))),
        )

    def card_view_state_for(
        self,
        acc: dict,
        *,
        hwid_profile_names: frozenset[str] = frozenset(),
    ) -> AccountCardViewState:
        steam_id = acc.get("steamid", "")
        return self._accounts.card_view_state_for(
            acc,
            cooldown_label=self._cooldown.cooldown_label_for(steam_id),
            hwid_profile_names=hwid_profile_names,
        )

    def set_account_cooldown(self, steam_id: str, duration_seconds: int) -> None:
        self._cooldown.set_account_cooldown(steam_id, duration_seconds)

    def account_display_name(self, acc: dict) -> str:
        return self._accounts.account_display_name(acc)

    def build_cooldown_watch(self, accounts: list[dict]) -> dict[str, int]:
        return self._cooldown.build_cooldown_watch(accounts)

    def pop_expired_cooldowns(
        self,
        watch: dict[str, int],
        accounts: list[dict],
    ) -> list[str]:
        return self._cooldown.pop_expired_cooldowns(watch, accounts)

    def delete_account(self, steam_id: str) -> bool:
        return self._accounts.delete_account(steam_id)

    def relogin_entry_for(self, acc: dict) -> str | None:
        return self._login.relogin_entry_for(acc)

    def export_entries_for(self, accounts: list[dict]) -> list[str]:
        return self._login.export_entries_for(accounts)

    def switch_worker_options(
        self,
        *,
        mode: str,
        acc: dict | None = None,
        token: str = "",
    ) -> dict:
        return self._login.switch_worker_options(mode=mode, acc=acc, token=token)

    def switch_label(self, mode: str, acc: dict | None) -> str:
        return self._login.switch_label(mode, acc)
