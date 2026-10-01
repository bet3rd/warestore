# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account grid loading, selection, and online status."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QFileDialog, QWidget

from warestore.application.account_manager.account_check import CheckSteps
from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.presenter import AccountManagerPresenter
from warestore.presentation.account_manager.features.accounts.account_check_worker import (
    AccountCheckWorker,
)
from warestore.presentation.account_manager.features.accounts.status_worker import (
    StatusFetchWorker,
)
from warestore.presentation.account_manager.support.account_targets import (
    normalize_account_targets,
)


# Override Config's follow-up: just the weapon picks from the source.
LOADOUT_ONLY = CheckSteps(loadout=True, stats=False, workshop=False)


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
        # Last fetched status per SteamID (online state, bans, level, persona,
        # avatar). A reload re-applies it to the rebuilt cards and only fetches
        # accounts missing from it; a full fetch happens on launch and when the
        # user hits Refresh.
        self._status_cache: dict[str, dict] = {}

        self._check_worker: AccountCheckWorker | None = None
        self._check_names: dict[str, str] = {}
        self._check_stats = {"done": 0, "pending": 0, "dead": 0, "failed": 0}
        self._check_dead: list[dict] = []
        # SteamIDs currently queued or being checked (not yet reported idle) —
        # used both to know which cards are *newly* queued (enqueue only
        # returns a count) and to drive the status bar's N/total progress.
        self._check_pending_ids: set[str] = set()
        self._check_batch_total = 0
        self._check_batch_done = 0

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

    def load_accounts(self, refresh_status: bool = False) -> None:
        """Rebuild the grid. ``refresh_status`` re-fetches every account's
        status from Steam (launch / Refresh); otherwise only accounts that
        have never been fetched are, and the rest keep their cached status."""
        self._selected = None
        if not self._is_switch_busy():
            self._info.setText("")

        result = self._presenter.load_accounts()
        if not result.steam_dir:
            self._info.setText(result.status_message)
            return

        source_cleared = self._forget_deleted_source(
            {acc.get("steamid", "") for acc in result.accounts}
        )
        self._grid.populate(result.accounts, result.steam_dir)
        self._apply_statuses(self._status_cache)
        self._filter(self._get_search())
        self.apply_card_metadata()
        self._sync_layout()

        if source_cleared:
            self._info.setText("CS2 config source cleared — its account was removed.")
        elif result.accounts:
            self._info.setText(result.status_message)

        self._on_accounts_loaded()
        self.start_status_fetch(full=refresh_status)
        self._refresh_log()

    def _forget_deleted_source(self, listed_sids: set[str]) -> bool:
        """Back to "no source set" once the CS2 config source account is gone
        from the manager (not in Steam's login list and no saved token). Its
        userdata folder is left alone. True when the source was cleared."""
        sid = self._settings.get("cs2_config_source_sid", "")
        if not sid or sid in listed_sids or self._ctrl.saved_token_entry(sid).get("token"):
            return False
        self._save_cs2_source("")
        return True

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
        """Right-click "Override Config": copy the source's CS2 config, then
        queue a loadout-only check so its weapon picks follow too."""
        targets = normalize_account_targets(accounts)
        if not targets:
            return
        source = self._ctrl.cs2_config_source()
        if not source:
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
        loadout_targets = [
            acc for acc in targets
            if acc.get("steamid") and acc["steamid"] != source
            and self._ctrl.saved_token_entry(acc["steamid"]).get("token")
        ]
        if loadout_targets:
            self.check_accounts(loadout_targets, steps=LOADOUT_ONLY)

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


    def _status_targets(self, *, full: bool) -> list[str]:
        sids = self._grid.steam_ids()
        return sids if full else [sid for sid in sids if sid not in self._status_cache]

    def start_status_fetch(self, *, full: bool = True) -> None:
        if self._status_worker and self._status_worker.isRunning():
            return
        sids = self._status_targets(full=full)
        if not sids:
            return
        if not self._is_switch_busy():
            self._info.setText("Fetching status…")
        self._status_worker = StatusFetchWorker(sids, ctrl=self._ctrl)
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

        self._status_cache.update(statuses)
        self._apply_statuses(statuses)

        # Cache the fresh persona names + avatar hashes so the next launch shows
        # them immediately (one batched write).
        profiles = {
            sid: {"persona": s.get("persona", ""), "avatar_hash": s.get("avatar_hash", "")}
            for sid, s in statuses.items()
            if s.get("persona") or s.get("avatar_hash")
        }
        if profiles:
            self._ctrl.persist_profiles(profiles)

        # Bans arrive after the initial render, so the "no bans" filter must be
        # re-evaluated once they're known.
        if self._grid.has_active_filters():
            self._grid.reapply_filters()
            self._sync_layout()

    def _apply_statuses(self, statuses: dict) -> None:
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
            if status.get("persona"):
                card.set_persona(status["persona"])
            if status.get("avatar_path"):
                card.set_avatar_from_file(status["avatar_path"])

    def _prompt_dead_accounts(self, dead: list[dict]) -> None:
        """Offer to remove accounts flagged dead during a sweep (expired token
        or a logon Steam rejected). Removal purges the login entry + token."""
        from warestore.presentation.account_manager.ui.dialogs import DeadAccountsDialog

        dialog = DeadAccountsDialog(
            self._parent,
            dead,
            exclude_from_capture=bool(self._settings.get("exclude_from_capture", True)),
        )
        if not dialog.exec_():
            return
        selected = dialog.selected_accounts()
        if selected:
            self.remove_accounts(selected)

    def remove_accounts(self, accounts: list[dict]) -> None:
        removed = 0
        for acc in accounts:
            if self._presenter.delete_account(acc.get("steamid", "")):
                removed += 1
        if removed:
            self.load_accounts()
            self._info.setText(f"Removed {removed} dead account(s).")

    # --- account check ---------------------------------------------------------

    def check_accounts(self, accounts, steps: CheckSteps | None = None) -> None:
        """Right-click "Check account" / "Refresh stats": queue one CS2 server
        session per account. ``steps=None`` runs whatever the user's settings
        say (today's "Check account" behaviour)."""
        targets = [
            acc for acc in normalize_account_targets(accounts)
            if acc.get("steamid") and self._ctrl.saved_token_entry(acc["steamid"]).get("token")
        ]
        if not targets:
            self._info.setText("No saved tokens for the selected account(s) — can't check.")
            return
        if self._check_worker is None:
            self._check_worker = AccountCheckWorker(self._ctrl)
            self._check_worker.started_account.connect(self._on_check_started)
            self._check_worker.finished_account.connect(self._on_check_finished)
            self._check_worker.drained.connect(self._on_checks_drained)
        for acc in targets:
            self._check_names[acc["steamid"]] = acc.get("account_name", "") or acc["steamid"]
        new_ids = [acc["steamid"] for acc in targets if acc["steamid"] not in self._check_pending_ids]
        added = self._check_worker.enqueue([acc["steamid"] for acc in targets], steps)
        if not added:
            self._info.setText("Already checking those account(s)…")
            return
        self._check_batch_total += len(new_ids)
        for sid in new_ids:
            self._check_pending_ids.add(sid)
            card = self._card_for(sid)
            if card:
                card.set_check_state("queued")

    def check_account_menu(self, accounts) -> None:
        """Right-click "Check account": the user's Stats/Workshop settings, but
        never the loadout — that's copied only on token add and Override Config."""
        settings = self._ctrl.account_check_steps()
        steps = CheckSteps(loadout=False, stats=settings.stats, workshop=settings.workshop)
        if not (steps.stats or steps.workshop):
            self._info.setText("Nothing to check — Stats and Workshop are both off in Settings.")
            return
        self.check_accounts(accounts, steps=steps)

    def refresh_stats(self, accounts) -> None:
        """Right-click "Refresh stats" / the main-panel button: a stats-only
        check (profile + cooldown + GCPD) — no Workshop clear, no loadout
        write."""
        self.check_accounts(accounts, steps=CheckSteps(loadout=False, workshop=False, stats=True))

    def refresh_all_stats(self) -> None:
        """Stats-only check for every account on the grid (sequentially)."""
        self.refresh_stats(self.accounts_on_grid())

    def _card_for(self, steam_id: str):
        return next((c for c in self._grid.cards() if c.acc.get("steamid", "") == steam_id), None)

    def _on_check_started(self, steam_id: str) -> None:
        card = self._card_for(steam_id)
        if card:
            card.set_check_state("checking")
        name = self._check_names.get(steam_id, steam_id)
        if self._check_batch_total > 1:
            self._info.setText(
                f"Checking {self._check_batch_done + 1}/{self._check_batch_total} — {name}…"
            )
        else:
            self._info.setText(f"Checking {name}…")

    def _on_check_finished(self, steam_id: str, result) -> None:
        card = self._card_for(steam_id)
        if card:
            card.set_check_state("idle")
        self._check_pending_ids.discard(steam_id)
        self._check_batch_done += 1
        name = self._check_names.get(steam_id, steam_id)
        if result is None:
            self._check_stats["failed"] += 1
        elif result.token_dead:
            self._check_stats["dead"] += 1
            self._check_dead.append({"steamid": steam_id, "name": name, "reason": "Logon rejected"})
        elif result.in_use and not result.web_only:
            self._check_stats["pending"] += 1
        else:
            # A web-only fallback (account in use) still counts as pending —
            # Prime and the loadout wait for a full check — but its stats are
            # fresh, so the card is updated like any other check.
            self._check_stats["pending" if result.in_use else "done"] += 1
            if card:
                # A partial stats reply (e.g. the cooldown step timed out) must
                # never overwrite another, still-good saved value — Premier,
                # Wingman, and the cooldown are each updated independently,
                # only when that step actually answered this check.
                premier_arrived = result.profile_ok or result.gcpd_ok
                if premier_arrived or result.cooldown_ok:
                    card.set_check_update(
                        premier_rating=result.premier_rating if premier_arrived else None,
                        premier_wins=result.premier_wins if premier_arrived else None,
                        wingman_rank=result.wingman_rank if result.gcpd_ok else None,
                        wingman_wins=result.wingman_wins if result.gcpd_ok else None,
                        cooldown_expires=result.cooldown_expires if result.cooldown_ok else None,
                    )
                if premier_arrived:
                    card.acc["premier_rating"] = result.premier_rating
                    card.acc["premier_wins"] = result.premier_wins
                if result.gcpd_ok:
                    card.acc["wingman_rank"] = result.wingman_rank
                    card.acc["wingman_wins"] = result.wingman_wins
                if result.cooldown_ok:
                    card.acc["cs2_cooldown_expires"] = result.cooldown_expires
        if result is not None:
            self._info.setText(f"{name}: {result.summary()}")
        self.apply_card_metadata()

    def _on_checks_drained(self) -> None:
        # Any card still "queued" shouldn't happen (every enqueued id is
        # expected to reach _on_check_finished first) — but a check that
        # raised before started_account fired would leave one behind, so
        # make sure nothing is left spinning/dimmed once the queue is empty.
        for sid in getattr(self, "_check_pending_ids", ()):
            card = self._card_for(sid)
            if card:
                card.set_check_state("idle")
        self._check_pending_ids = set()
        self._check_batch_total = 0
        self._check_batch_done = 0
        s = self._check_stats
        total = sum(s.values())
        if total > 1:
            parts = [f"{s['done']} checked"]
            if s["pending"]:
                parts.append(f"{s['pending']} pending (in use)")
            if s["dead"]:
                parts.append(f"{s['dead']} not working")
            if s["failed"]:
                parts.append(f"{s['failed']} failed")
            self._info.setText("Account check: " + ", ".join(parts) + ".")
        self._check_stats = {"done": 0, "pending": 0, "dead": 0, "failed": 0}
        if self._check_dead:
            dead, self._check_dead = self._check_dead, []
            self._prompt_dead_accounts(dead)
