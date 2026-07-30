# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Settings panel, bulk import, master password, and update checks."""

from __future__ import annotations

import logging
from collections.abc import Callable

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox, QWidget

from warestore.application.account_manager.controller import AccountManagerController
from warestore.infrastructure.persistence import vault_crypto
from warestore.presentation.account_manager.support import vault_unlock
from warestore.presentation.account_manager.support.vault_unlock import prompt_new_password
from warestore.presentation.account_manager.ui.dialogs import (
    UpdateDialog,
    UserdataCleanupDialog,
)
from warestore.presentation.account_manager.features.settings.api_key_worker import (
    ApiKeyValidateWorker,
)
from warestore.presentation.account_manager.features.settings.bulk_import_worker import (
    BulkImportWorker,
)
from warestore.presentation.account_manager.features.settings.userdata_worker import (
    UserdataDeleteWorker,
    UserdataScanWorker,
)
from warestore.presentation.account_manager.features.settings.spoofer_worker import (
    SpooferInstallWorker,
)

logger = logging.getLogger(__name__)

_STEAM_KEY_LEN = 32


class SettingsCoordinator:
    def __init__(
        self,
        parent: QWidget,
        controller: AccountManagerController,
        settings: dict,
        settings_ui,
        *,
        set_busy: Callable[[bool, str], None],
        set_status: Callable[[str], None],
        sync_layout: Callable[[], None],
        refresh_log: Callable[[], None],
        reload_accounts: Callable[[], None],
        set_log_visible: Callable[[bool], None],
        toggle_settings_open: Callable[[], None],
        apply_capture_exclusion: Callable[[], None],
    ) -> None:
        self._parent = parent
        self._ctrl = controller
        self._settings = settings
        self._ui = settings_ui
        self._set_busy = set_busy
        self._set_status = set_status
        self._sync_layout = sync_layout
        self._refresh_log = refresh_log
        self._reload_accounts = reload_accounts
        self._set_log_visible = set_log_visible
        self._toggle_settings = toggle_settings_open
        self._apply_capture_exclusion = apply_capture_exclusion
        self._bulk_worker: BulkImportWorker | None = None
        self._bulk_rejected_count = 0
        self._update_notice_shown = False
        self._userdata_scan: UserdataScanWorker | None = None
        self._userdata_delete: UserdataDeleteWorker | None = None
        self._spoofer_worker: SpooferInstallWorker | None = None
        self.refresh_spoofer_state()

        # Debounced background validation for the Steam Web API key.
        self._api_worker: ApiKeyValidateWorker | None = None
        self._api_timer = QTimer(parent)
        self._api_timer.setSingleShot(True)
        self._api_timer.timeout.connect(self._run_api_validation)
        self._schedule_api_validation(self._settings.get("steam_api_key", "").strip())

    def toggle_panel(self) -> None:
        self.refresh_spoofer_state()
        self._ui.scroll_to_top()
        self._toggle_settings()

    def on_log_toggle(self, checked: bool) -> None:
        self._settings["show_log_panel"] = checked
        self._ctrl.save_settings(self._settings)
        self._set_log_visible(checked)
        if checked:
            self._refresh_log()
        self._sync_layout()

    def on_close_to_tray_toggle(self, checked: bool) -> None:
        self._settings["close_to_tray"] = checked
        self._ctrl.save_settings(self._settings)

    def on_auto_remove_expired_toggle(self, checked: bool) -> None:
        self._settings["auto_remove_expired_tokens"] = checked
        self._ctrl.save_settings(self._settings)
        if checked and self._ctrl.purge_expired_tokens():
            self._reload_accounts()

    def on_exclude_from_capture_toggle(self, checked: bool) -> None:
        self._settings["exclude_from_capture"] = checked
        self._ctrl.save_settings(self._settings)
        self._apply_capture_exclusion()

    def on_cs2_toggle(self, checked: bool) -> None:
        self._settings["open_cs2"] = checked
        self._ui.le_opts.setVisible(checked)
        self._ctrl.save_settings(self._settings)

    def on_opts_change(self, text: str) -> None:
        self._settings["cs2_launch_options"] = text
        self._ctrl.save_settings(self._settings)

    def on_workshop_toggle(self, checked: bool) -> None:
        self._settings["disable_workshop"] = checked
        self._ctrl.save_settings(self._settings)

    def on_remote_play_toggle(self, checked: bool) -> None:
        self._settings["disable_remote_play"] = checked
        self._ctrl.save_settings(self._settings)

    def on_add_only_toggle(self, checked: bool) -> None:
        self._settings["add_account_only"] = checked
        self._ctrl.save_settings(self._settings)

    def on_spoof_toggle(self, checked: bool) -> None:
        self._settings["spoof_on_login"] = checked
        self._ctrl.save_settings(self._settings)

    def refresh_spoofer_state(self) -> None:
        self._ui.set_spoofer_installed(self._ctrl.spoofer_installed())

    def on_install_spoofer(self) -> None:
        if self._spoofer_worker is not None and self._spoofer_worker.isRunning():
            return
        self._ui.btn_install_spoofer.setEnabled(False)
        self._set_busy(True, "Downloading HWID spoofer…")
        self._spoofer_worker = SpooferInstallWorker(self._ctrl)
        self._spoofer_worker.done.connect(self._on_spoofer_installed)
        self._spoofer_worker.start()

    def _on_spoofer_installed(self, success: bool, error: str) -> None:
        self._set_busy(False, "")
        if success:
            self._set_status("HWID spoofer installed.")
            self.refresh_spoofer_state()
        else:
            self._ui.btn_install_spoofer.setEnabled(True)
            QMessageBox.warning(
                self._parent,
                "Install failed",
                "Couldn't download the HWID spoofer.\n\n"
                f"{error}\n\nCheck your connection and try again.",
            )

    def on_api_key_change(self, text: str) -> None:
        key = text.strip()
        self._settings["steam_api_key"] = key
        self._ctrl.save_settings(self._settings)
        self._schedule_api_validation(key)

    # --- live API-key validation ---

    def _schedule_api_validation(self, key: str) -> None:
        # Status sits next to the section title, so keep it short and only show
        # it once there's a full-length key to check.
        if len(key) != _STEAM_KEY_LEN:
            self._api_timer.stop()
            self._set_api_status("", "")
            return
        self._set_api_status("Checking…", "#888888")
        self._api_timer.start(600)  # wait for typing/paste to settle

    def _run_api_validation(self) -> None:
        key = self._settings.get("steam_api_key", "").strip()
        if len(key) != _STEAM_KEY_LEN:
            return
        if self._api_worker and self._api_worker.isRunning():
            self._api_timer.start(300)  # retry once the in-flight check finishes
            return
        self._api_worker = ApiKeyValidateWorker(key, ctrl=self._ctrl)
        self._api_worker.done.connect(
            lambda result, checked=key: self._on_api_validated(checked, result)
        )
        self._api_worker.start()

    def _on_api_validated(self, checked_key: str, result: str) -> None:
        # Drop stale results if the key changed while the check was in flight.
        if checked_key != self._settings.get("steam_api_key", "").strip():
            return
        if result == "valid":
            self._set_api_status("✓ Valid", "#5ba85e")
        elif result == "invalid":
            self._set_api_status("✗ Invalid", "#cc4444")
        else:
            self._set_api_status("⚠ Error", "#c97820")

    def _set_api_status(self, text: str, color: str) -> None:
        self._ui.lbl_api_status.setText(text)
        self._ui.lbl_api_status.setStyleSheet(
            f"color: {color}; font-size: 11px;" if text else ""
        )

    # --- leftover userdata cleanup ---

    def on_clean_userdata(self) -> None:
        if self._userdata_scan and self._userdata_scan.isRunning():
            return
        self._ui.btn_clean_userdata.setEnabled(False)
        self._set_busy(True, "Scanning Steam userdata…")
        self._userdata_scan = UserdataScanWorker(ctrl=self._ctrl)
        self._userdata_scan.done.connect(self._on_userdata_scanned)
        self._userdata_scan.start()

    def _on_userdata_scanned(self, folders: list | None, error: str | None) -> None:
        self._set_busy(False)
        self._ui.btn_clean_userdata.setEnabled(True)
        if error:
            # Fail closed: the safety set couldn't be established, so we refuse to
            # offer any deletion rather than risk removing an in-use account.
            warn = QMessageBox(self._parent)
            warn.setWindowTitle("Can't clean safely")
            warn.setIcon(QMessageBox.Warning)
            warn.setText("Steam userdata cleanup was cancelled to protect your data.")
            warn.setInformativeText(error)
            warn.setStandardButtons(QMessageBox.Ok)
            warn.exec_()
            self._set_status("Userdata cleanup cancelled — couldn't verify what's safe to remove.")
            return
        if not folders:
            self._set_status("No leftover userdata folders found.")
            return

        dialog = UserdataCleanupDialog(
            self._parent,
            folders,
            exclude_from_capture=self._settings.get("exclude_from_capture", True),
        )
        if not dialog.exec_():
            return
        selected = dialog.selected_folders()
        if not selected:
            return

        total = sum(f.size_bytes for f in selected)
        confirm = QMessageBox(self._parent)
        confirm.setWindowTitle("Delete userdata folders")
        confirm.setIcon(QMessageBox.Warning)
        confirm.setText(
            f"Permanently delete {len(selected)} folder"
            f"{'s' if len(selected) != 1 else ''} "
            f"({total / 1024 / 1024:.0f} MB)?"
        )
        confirm.setInformativeText("This cannot be undone.")
        confirm.setStandardButtons(QMessageBox.Cancel | QMessageBox.Yes)
        confirm.setDefaultButton(QMessageBox.Cancel)
        if confirm.exec_() != QMessageBox.Yes:
            return

        self._ui.btn_clean_userdata.setEnabled(False)
        self._set_busy(True, f"Deleting {len(selected)} folders…")
        self._userdata_delete = UserdataDeleteWorker(selected, ctrl=self._ctrl)
        self._userdata_delete.done.connect(self._on_userdata_deleted)
        self._userdata_delete.start()

    def _on_userdata_deleted(self, count: int, freed: int, errors: list) -> None:
        self._set_busy(False)
        self._ui.btn_clean_userdata.setEnabled(True)
        msg = f"Removed {count} folder{'s' if count != 1 else ''} · {freed / 1024 / 1024:.0f} MB freed"
        if errors:
            msg += f" · {len(errors)} failed"
            logger.warning(f"userdata cleanup errors: {errors}")
        self._set_status(msg)

    # --- master password ---

    def on_master_password(self) -> None:
        if self._settings.get("vault_mode") == "password":
            self._manage_password()
        else:
            self._enable_password()

    def _enable_password(self) -> None:
        password = prompt_new_password()
        if password is None:
            return
        dek = vault_crypto.new_dek()
        code = vault_crypto.generate_recovery_code()
        self._ctrl.rekey_vault(dek)  # re-encrypt tokens with the new DEK
        vault_unlock.set_password(self._settings, dek, password)
        vault_unlock.set_recovery(self._settings, dek, code)
        self._settings["vault_mode"] = "password"
        self._ctrl.save_settings(self._settings)
        self._ui.refresh_master_state()
        vault_unlock.show_recovery_code(code, parent=self._parent)
        self._set_status("Master password set.")

    def _unlock_current(self) -> bytes | None:
        """Prompt for the current password and return the DEK, or None."""
        pw, ok = QInputDialog.getText(
            self._parent, "Confirm master password",
            "Enter your current master password:", QLineEdit.Password,
        )
        if not ok:
            return None
        try:
            return vault_unlock.unlock_password(self._settings, pw)
        except Exception:
            QMessageBox.warning(self._parent, "Wrong password", "Incorrect master password.")
            return None

    def _manage_password(self) -> None:
        box = QMessageBox(self._parent)
        box.setWindowTitle("Master password")
        box.setText("A master password is currently set.")
        change_btn = box.addButton("Change password…", QMessageBox.AcceptRole)
        regen_btn = box.addButton("New recovery code…", QMessageBox.ActionRole)
        remove_btn = box.addButton("Remove", QMessageBox.DestructiveRole)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()

        if clicked == change_btn:
            dek = self._unlock_current()
            if dek is None:
                return
            password = prompt_new_password()
            if password is None:
                return
            vault_unlock.set_password(self._settings, dek, password)  # DEK unchanged
            self._ctrl.save_settings(self._settings)
            self._set_status("Master password changed.")
        elif clicked == regen_btn:
            dek = self._unlock_current()
            if dek is None:
                return
            code = vault_crypto.generate_recovery_code()
            vault_unlock.set_recovery(self._settings, dek, code)
            self._ctrl.save_settings(self._settings)
            vault_unlock.show_recovery_code(code, parent=self._parent)
            self._set_status("New recovery code generated.")
        elif clicked == remove_btn:
            dek = self._unlock_current()
            if dek is None:
                return
            self._ctrl.rekey_vault(None)  # re-encrypt tokens back to DPAPI
            self._settings["vault_mode"] = "dpapi"
            for k in ("vault_pw_salt", "vault_pw_wrap", "vault_rc_salt", "vault_rc_wrap"):
                self._settings[k] = ""
            self._ctrl.save_settings(self._settings)
            self._ui.refresh_master_state()
            self._set_status("Master password removed.")

    def on_bulk_text_change(self) -> None:
        busy = bool(self._bulk_worker and self._bulk_worker.isRunning())
        if busy:
            return

        importable, expired = self._ctrl.classify_bulk_tokens(
            self._ui.txt_bulk.toPlainText()
        )
        count = len(importable)
        self._ui.btn_import.setEnabled(count > 0)
        self._ui.btn_import.setText(
            f'Import  {count} token{"s" if count != 1 else ""}' if count else "Import"
        )

        if expired and importable:
            self._set_bulk_status(
                f"{count} importable · {len(expired)} expired (skipped)",
                warning=True,
            )
        elif expired:
            self._set_bulk_status(
                f"{len(expired)} expired token{'s' if len(expired) != 1 else ''} — nothing to import",
                warning=True,
            )
        elif count:
            self._set_bulk_status("")
        else:
            self._set_bulk_status("")

    def on_import(self) -> None:
        importable, expired = self._ctrl.classify_bulk_tokens(
            self._ui.txt_bulk.toPlainText()
        )
        if not importable:
            if expired:
                self._set_bulk_status(
                    f"{len(expired)} expired token{'s' if len(expired) != 1 else ''} — nothing to import",
                    warning=True,
                )
            return

        self._bulk_rejected_count = len(expired)
        self._ui.btn_import.setEnabled(False)
        self._ui.txt_bulk.setEnabled(False)
        self._set_bulk_status("")
        self._set_busy(True, f"Bulk import 0 / {len(importable)}…")
        self._ui.lbl_status.setObjectName("info")
        self._ui.lbl_status.setText(f"0 / {len(importable)}")
        self._bulk_worker = BulkImportWorker(importable, ctrl=self._ctrl)
        self._bulk_worker.progress.connect(
            lambda current, total: self._ui.lbl_status.setText(f"{current} / {total}")
        )
        self._bulk_worker.status.connect(lambda msg: self._set_busy(True, msg))
        self._bulk_worker.done.connect(self._on_import_done)
        self._bulk_worker.start()

    def _on_import_done(self, success: int, total: int) -> None:
        self._ui.txt_bulk.setEnabled(True)
        self._set_busy(False)
        skipped = self._bulk_rejected_count
        msg = f"Imported {success} / {total}"
        if skipped:
            msg += f" · {skipped} expired skipped"
        self._set_bulk_status(msg, warning=bool(skipped and not success))
        self._bulk_rejected_count = 0
        self.on_bulk_text_change()
        if success:
            self._reload_accounts()

    def _set_bulk_status(self, text: str, *, warning: bool = False) -> None:
        name = "warning" if warning and text else "info"
        if self._ui.lbl_status.objectName() != name:
            self._ui.lbl_status.setObjectName(name)
            self._ui.lbl_status.style().unpolish(self._ui.lbl_status)
            self._ui.lbl_status.style().polish(self._ui.lbl_status)
        self._ui.lbl_status.setText(text)

    def on_browse_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self._parent,
            "Open Token File",
            "",
            "Text Files (*.txt);;All Files (*)",
        )
        if not path:
            return
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                self._ui.txt_bulk.setPlainText(f.read())
            self.on_bulk_text_change()
        except Exception as exc:
            logger.warning(f"Browse file read error: {exc}")

    def check_updates(self) -> None:
        try:
            info = self._ctrl.check_updates()
            if info["force_update"] or info["update_available"]:
                dialog = UpdateDialog(
                    self._parent,
                    info["download_url"],
                    info["latest_version"],
                    info["force_update"],
                    change_log=info.get("change_log", ""),
                    exclude_from_capture=self._settings.get("exclude_from_capture", True),
                )
                dialog.exec_()
                if (
                    info["update_available"]
                    and not info["force_update"]
                    and not self._update_notice_shown
                ):
                    self._set_status("You are not using the latest version.")
                    self._update_notice_shown = True
            elif not self._update_notice_shown:
                self._set_status("You are using the latest version.")
                self._update_notice_shown = True
        except Exception:
            if not self._update_notice_shown:
                self._set_status("Failed to check for updates.")
                self._update_notice_shown = True
