# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account grid loading, selection, and online status."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QFileDialog, QWidget

from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.presenter import AccountManagerPresenter
from warestore.presentation.account_manager.features.accounts.status_worker import (
    StatusFetchWorker,
)
from warestore.presentation.account_manager.support.account_targets import (
    normalize_account_targets,
)


class AccountCoordinator:
    def __init__(
        self,
        parent: QWidget,
        presenter: AccountManagerPresenter,
        controller: AccountManagerController,
        settings: dict,
        *,
        account_grid,
        info_label,
        sync_layout: Callable[[], None],
        refresh_log: Callable[[], None],
        is_switch_busy: Callable[[], bool],
        on_accounts_loaded: Callable[[], None],
        get_search_text: Callable[[], str],
        filter_accounts: Callable[[str], None],
    ) -> None:
        self._parent = parent
        self._presenter = presenter
        self._ctrl = controller
        self._settings = settings
        self._grid = account_grid
        self._info = info_label
        self._sync_layout = sync_layout
        self._refresh_log = refresh_log
        self._is_switch_busy = is_switch_busy
        self._on_accounts_loaded = on_accounts_loaded
        self._get_search = get_search_text
        self._filter = filter_accounts
        self._selected: dict | None = None
        self._status_worker: StatusFetchWorker | None = None

    @property
    def selected_account(self) -> dict | None:
        return self._selected

    @selected_account.setter
    def selected_account(self, acc: dict | None) -> None:
        self._selected = acc

    def accounts_on_grid(self) -> list[dict]:
        return self._grid.accounts()

    def apply_card_metadata(self) -> None:
        hwid_names = self._ctrl.hwid_profile_names()
        self._grid.apply_view_states(
            lambda acc, **kw: self._presenter.card_view_state_for(
                acc, hwid_profile_names=hwid_names, **kw
            )
        )
        # Colour/cooldown filters depend on the state just applied above, so
        # re-evaluate visibility once the cards are up to date.
        if self._grid.has_active_filters():
            self._grid.reapply_filters()
            self._sync_layout()

    def load_accounts(self) -> None:
        self._selected = None
        if not self._is_switch_busy():
            self._info.setText("")

        result = self._presenter.load_accounts()
        if not result.steam_dir:
            self._info.setText(result.status_message)
            return

        self._grid.populate(result.accounts, result.steam_dir)
        self._filter(self._get_search())
        self.apply_card_metadata()
        self._sync_layout()

        if result.accounts:
            self._info.setText(result.status_message)

        self._on_accounts_loaded()
        self.start_status_fetch()
        self._refresh_log()

    def select_accounts(self, accounts: list[dict]) -> None:
        self._selected = accounts[0] if accounts else None
        if len(accounts) > 1 and not self._is_switch_busy():
            self._info.setText(f"{len(accounts)} accounts selected")

    def delete_accounts(self, accounts) -> None:
        targets = normalize_account_targets(accounts)
        if not targets:
            return

        deleted = 0
        for acc in targets:
            if self._presenter.delete_account(acc.get("steamid", "")):
                deleted += 1

        if deleted:
            self.load_accounts()
            self._info.setText(f"Deleted {deleted} account(s).")

    def set_color(self, accounts, color: str) -> None:
        targets = normalize_account_targets(accounts)
        changed = False
        for acc in targets:
            sid = acc.get("steamid", "")
            if sid:
                self._ctrl.set_account_color(sid, color)
                changed = True
        if changed:
            self.apply_card_metadata()

    def reset_hwid(self, account) -> None:
        acc = account[0] if isinstance(account, list) else account
        name = acc.get("account_name", "")
        if name and self._ctrl.reset_hwid_profile(name):
            self._info.setText(f"HWID profile reset for {name} — new values generated on next login.")
            self.apply_card_metadata()

    def set_cs2_source(self, account) -> None:
        acc = account[0] if isinstance(account, list) else account
        sid = acc.get("steamid", "")
        if not sid:
            return
        if self._settings.get("cs2_config_source_sid") == sid:
            self._save_cs2_source("")
            self._info.setText("CS2 config source cleared.")
        else:
            self._save_cs2_source(sid)
            name = acc.get("account_name", "") or sid
            self._info.setText(
                f"CS2 config source set to {name}. "
                "New accounts copy its CS2 config on first login."
            )
        self.apply_card_metadata()

    def _save_cs2_source(self, sid: str) -> None:
        # Write through the shared settings dict so a later settings-panel save
        # (which persists that same dict) can't clobber the source back to "".
        self._settings["cs2_config_source_sid"] = sid
        self._ctrl.save_settings(self._settings)

    def apply_cs2_source(self, accounts) -> None:
        targets = normalize_account_targets(accounts)
        if not targets:
            return
        if not self._ctrl.cs2_config_source():
            self._info.setText("No CS2 config source set.")
            return
        applied = 0
        for acc in targets:
            sid = acc.get("steamid", "")
            if sid and self._ctrl.apply_cs2_config(sid):
                applied += 1
        if applied:
            self._info.setText(
                f"Overrode CS2 config from source on {applied} account(s)."
            )
        else:
            self._info.setText("No CS2 config applied (source has no 730 config?).")
        self.apply_card_metadata()

    def copy_export_tokens(self, accounts) -> None:
        self._export_tokens(accounts, clipboard=True, save_file=False)

    def export_tokens_to_file(self, accounts) -> None:
        self._export_tokens(accounts, clipboard=False, save_file=True)

    def _export_tokens(
        self,
        accounts,
        *,
        clipboard: bool,
        save_file: bool,
    ) -> None:
        targets = normalize_account_targets(accounts)
        lines = self._presenter.export_entries_for(targets)
        if not lines:
            self._info.setText("No saved tokens to export.")
            return

        skipped = len(targets) - len(lines)
        suffix = f" ({skipped} missing token(s) skipped.)" if skipped else ""

        if clipboard:
            QApplication.clipboard().setText("\n".join(lines))
            self._info.setText(f"Copied {len(lines)} token(s) to clipboard.{suffix}")

        if save_file:
            path, _ = QFileDialog.getSaveFileName(
                self._parent,
                "Export tokens",
                "tokens.txt",
                "Text files (*.txt);;All files (*)",
            )
            if not path:
                return
            Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")
            self._info.setText(f"Exported {len(lines)} token(s) to {path}.{suffix}")


    def start_status_fetch(self) -> None:
        if self._status_worker and self._status_worker.isRunning():
            return
        all_sids = self._grid.steam_ids()
        if not all_sids:
            return
        if not self._is_switch_busy():
            self._info.setText("Fetching status…")
        self._status_worker = StatusFetchWorker(all_sids, ctrl=self._ctrl)
        self._status_worker.progress.connect(self._on_status_progress)
        self._status_worker.done.connect(self._on_status_done)
        self._status_worker.start()

    def _on_status_progress(self, msg: str) -> None:
        if not self._is_switch_busy():
            self._info.setText(msg)

    def _on_status_done(self, statuses: dict) -> None:
        if not self._is_switch_busy() and not self._selected:
            n = self._grid.card_count()
            if n:
                self._info.setText(f"Loaded {n} account(s).")

        for card in self._grid.cards():
            sid = card.acc.get("steamid", "")
            if sid not in statuses:
                continue
            status = statuses[sid]
            card.set_status(
                status.get("state", 0),
                status.get("game", ""),
                stale=status.get("stale", False),
            )
            card.set_ban_info(status.get("ban"))
            card.set_level(status.get("level"))

        # Bans arrive after the initial render, so the "no bans" filter must be
        # re-evaluated once they're known.
        if self._grid.has_active_filters():
            self._grid.reapply_filters()
            self._sync_layout()
