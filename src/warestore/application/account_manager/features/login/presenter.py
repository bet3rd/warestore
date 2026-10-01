# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Login and switch use cases."""

from __future__ import annotations

from warestore.application.account_manager.controller import AccountManagerController


class LoginPresenter:
    def __init__(self, ctrl: AccountManagerController) -> None:
        self._ctrl = ctrl

    def relogin_entry_for(self, acc: dict) -> str | None:
        sid = acc.get("steamid", "")
        entry = self._ctrl.saved_token_entry(sid)
        token = entry.get("token", "")
        if not token:
            return None
        username = entry.get("username") or acc.get("account_name", "")
        return f"{username}----{token}" if username else token

    def export_entries_for(self, accounts: list[dict]) -> list[str]:
        lines: list[str] = []
        for acc in accounts:
            entry = self.relogin_entry_for(acc)
            if entry:
                lines.append(entry)
        return lines

    def switch_worker_options(
        self,
        *,
        mode: str,
        acc: dict | None = None,
        token: str = "",
        is_add: bool = False,
    ) -> dict:
        cfg = self._ctrl.load_settings()
        return {
            "mode": mode,
            "acc": acc,
            "token": token,
            "persona_state": 7,
            "open_cs2": cfg.get("open_cs2", False),
            "cs2_options": cfg.get("cs2_launch_options", ""),
            "disable_remote_play": True,  # always: streaming never starts up
            "add_account_only": cfg.get("add_account_only", False),
            "spoof_on_login": cfg.get("spoof_on_login", False),
            # Only a pasted NEW token runs the account check; re-login reuses
            # token mode and must not.
            "check_account": bool(is_add and cfg.get("account_check_on_add", True)),
        }

    @staticmethod
    def switch_label(mode: str, acc: dict | None) -> str:
        if mode == "native" and acc:
            return acc.get("account_name", "account")
        return "token login"
