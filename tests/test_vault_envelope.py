"""Envelope glue: password + recovery both unwrap the same DEK (no Qt app needed)."""

import pytest

from warestore.infrastructure.persistence import vault_crypto
from warestore.presentation.account_manager.support import vault_unlock


def test_password_and_recovery_unlock_same_dek():
    dek = vault_crypto.new_dek()
    code = vault_crypto.generate_recovery_code()
    settings: dict = {}
    vault_unlock.set_password(settings, dek, "hunter2pass")
    vault_unlock.set_recovery(settings, dek, code)

    assert vault_unlock.unlock_password(settings, "hunter2pass") == dek
    assert vault_unlock.unlock_recovery(settings, code) == dek
    # recovery code is format/case-insensitive
    assert vault_unlock.unlock_recovery(settings, code.lower().replace("-", " ")) == dek


def test_wrong_password_raises():
    settings: dict = {}
    vault_unlock.set_password(settings, vault_crypto.new_dek(), "right-password")
    with pytest.raises(Exception):
        vault_unlock.unlock_password(settings, "wrong-password")


def test_change_password_keeps_dek_and_recovery_still_works():
    dek = vault_crypto.new_dek()
    code = vault_crypto.generate_recovery_code()
    settings: dict = {}
    vault_unlock.set_password(settings, dek, "old-password")
    vault_unlock.set_recovery(settings, dek, code)

    vault_unlock.set_password(settings, dek, "new-password")  # re-wrap same DEK
    assert vault_unlock.unlock_password(settings, "new-password") == dek
    with pytest.raises(Exception):
        vault_unlock.unlock_password(settings, "old-password")
    assert vault_unlock.unlock_recovery(settings, code) == dek  # recovery unchanged
