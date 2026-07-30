# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Application composition root for the account manager."""

from __future__ import annotations

from dataclasses import dataclass

from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.facade import AccountManagerFacade
from warestore.application.account_manager.presenter import AccountManagerPresenter


@dataclass(slots=True)
class AccountManagerApp:
    facade: AccountManagerFacade
    controller: AccountManagerController
    presenter: AccountManagerPresenter


def create_account_manager_app(vault_key: bytes | None = None) -> AccountManagerApp:
    facade = AccountManagerFacade(vault_key=vault_key)
    controller = AccountManagerController(facade)
    presenter = AccountManagerPresenter(controller)
    return AccountManagerApp(facade=facade, controller=controller, presenter=presenter)
