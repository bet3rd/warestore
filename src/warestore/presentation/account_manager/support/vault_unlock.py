# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Master-password vault: first-launch setup, per-launch unlock, and recovery.

Uses envelope encryption (see vault_crypto): a random DEK encrypts the tokens
and is wrapped by both the password and a one-time recovery code. Returns the
DEK for the session (or None for DPAPI mode). Run after the QApplication exists
but before the app/facade is built.
"""

from __future__ import annotations

import logging
import sys

from PyQt5.QtWidgets import QApplication, QInputDialog, QLineEdit, QMessageBox

from warestore.infrastructure.persistence import vault_crypto

logger = logging.getLogger(__name__)

_MIN_LEN = 8


# --- settings <-> crypto glue (no Qt) ---


def set_password(settings: dict, dek: bytes, password: str) -> None:
    salt = vault_crypto.new_salt()
    settings["vault_pw_salt"] = salt.hex()
    settings["vault_pw_wrap"] = vault_crypto.wrap_dek(vault_crypto.derive_key(password, salt), dek)


def set_recovery(settings: dict, dek: bytes, code: str) -> None:
    salt = vault_crypto.new_salt()
    kek = vault_crypto.derive_key(vault_crypto.normalize_recovery_code(code), salt)
    settings["vault_rc_salt"] = salt.hex()
    settings["vault_rc_wrap"] = vault_crypto.wrap_dek(kek, dek)


def unlock_password(settings: dict, password: str) -> bytes:
    salt = bytes.fromhex(settings["vault_pw_salt"])
    return vault_crypto.unwrap_dek(vault_crypto.derive_key(password, salt), settings["vault_pw_wrap"])


def unlock_recovery(settings: dict, code: str) -> bytes:
    salt = bytes.fromhex(settings["vault_rc_salt"])
    kek = vault_crypto.derive_key(vault_crypto.normalize_recovery_code(code), salt)
    return vault_crypto.unwrap_dek(kek, settings["vault_rc_wrap"])


# --- dialogs ---


def _prompt_password(title: str, label: str) -> str | None:
    text, ok = QInputDialog.getText(None, title, label, QLineEdit.Password)
    return text if ok else None


def _prompt_text(title: str, label: str) -> str | None:
    text, ok = QInputDialog.getText(None, title, label)
    return text if ok else None


def prompt_new_password() -> str | None:
    while True:
        pw1 = _prompt_password("Set master password", f"New master password (min {_MIN_LEN} chars):")
        if pw1 is None:
            return None
        if len(pw1) < _MIN_LEN:
            QMessageBox.warning(None, "Too short", f"Use at least {_MIN_LEN} characters.")
            continue
        pw2 = _prompt_password("Confirm master password", "Re-enter the password:")
        if pw2 is None:
            return None
        if pw1 != pw2:
            QMessageBox.warning(None, "Mismatch", "Passwords did not match — try again.")
            continue
        return pw1


def show_recovery_code(code: str, *, parent=None) -> None:
    QApplication.clipboard().setText(code)
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Warning)
    box.setWindowTitle("Save your recovery code")
    box.setText(
        f"Recovery code (copied to clipboard):\n\n{code}\n\n"
        "Store this somewhere safe (password manager / printed). It's the ONLY "
        "way back in if you forget your master password. It is not shown again."
    )
    box.setTextInteractionFlags(box.textInteractionFlags() | 0x1)  # TextSelectableByMouse
    box.exec_()


# --- startup flow ---


def setup_or_unlock_vault(settings_repo) -> bytes | None:
    settings = settings_repo.load()
    if not settings.get("vault_setup_done"):
        return _first_launch(settings_repo, settings)
    if settings.get("vault_mode") == "password":
        return _unlock(settings_repo, settings)
    return None  # DPAPI mode — no prompt


def _first_launch(settings_repo, settings: dict) -> bytes | None:
    resp = QMessageBox.question(
        None,
        "Secure WareStore",
        "Protect your saved tokens with a master password?\n\n"
        "Yes — you'll enter it on every launch; the vault is unreadable without\n"
        "it (even to software running as you). You'll get a one-time recovery code.\n\n"
        "No — tokens stay encrypted to this Windows account only (no prompt).\n\n"
        "You can change this later in Settings → Security.",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.No,
    )
    if resp == QMessageBox.Yes:
        password = prompt_new_password()
        if password is not None:
            dek = vault_crypto.new_dek()
            code = vault_crypto.generate_recovery_code()
            set_password(settings, dek, password)
            set_recovery(settings, dek, code)
            settings["vault_mode"] = "password"
            settings["vault_setup_done"] = True
            settings_repo.save(settings)
            show_recovery_code(code)
            return dek

    settings["vault_mode"] = "dpapi"
    settings["vault_setup_done"] = True
    for k in ("vault_pw_salt", "vault_pw_wrap", "vault_rc_salt", "vault_rc_wrap"):
        settings[k] = ""
    settings_repo.save(settings)
    return None


def _unlock(settings_repo, settings: dict) -> bytes | None:
    if not settings.get("vault_pw_wrap"):
        logger.error("Vault is in password mode but is missing its wrapped key.")
        QMessageBox.critical(None, "Vault error", "Vault settings are corrupt; cannot unlock.")
        sys.exit(1)

    while True:
        box = QMessageBox(None)
        box.setWindowTitle("Unlock WareStore")
        box.setText("Enter your master password to unlock the token vault.")
        enter_btn = box.addButton("Enter password", QMessageBox.AcceptRole)
        recover_btn = box.addButton("Use recovery code", QMessageBox.ActionRole)
        box.addButton("Quit", QMessageBox.RejectRole)
        box.exec_()
        clicked = box.clickedButton()

        if clicked == enter_btn:
            password = _prompt_password("Unlock WareStore", "Master password:")
            if password is None:
                continue
            try:
                return unlock_password(settings, password)
            except Exception:
                QMessageBox.warning(None, "Wrong password", "Incorrect master password — try again.")
        elif clicked == recover_btn:
            dek = _recover(settings_repo, settings)
            if dek is not None:
                return dek
        else:
            sys.exit(0)


def _recover(settings_repo, settings: dict) -> bytes | None:
    code = _prompt_text("Recover vault", "Enter your recovery code:")
    if code is None:
        return None
    try:
        dek = unlock_recovery(settings, code)
    except Exception:
        QMessageBox.warning(None, "Invalid code", "That recovery code didn't work.")
        return None

    QMessageBox.information(None, "Recovered", "Recovery succeeded — please set a new master password.")
    new_password = prompt_new_password()
    if new_password is not None:
        set_password(settings, dek, new_password)
        settings_repo.save(settings)
    return dek
