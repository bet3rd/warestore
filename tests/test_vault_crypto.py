import pytest

from warestore.infrastructure.persistence import vault_crypto

# Low iteration count keeps PBKDF2 fast in tests.
ITERS = 1000


def test_derive_key_deterministic_and_32_bytes():
    salt = b"0" * 16
    assert vault_crypto.derive_key("pw", salt, ITERS) == vault_crypto.derive_key("pw", salt, ITERS)
    assert len(vault_crypto.derive_key("pw", salt, ITERS)) == 32


def test_derive_key_varies_by_password_and_salt():
    assert vault_crypto.derive_key("a", b"0" * 16, ITERS) != vault_crypto.derive_key("b", b"0" * 16, ITERS)
    assert vault_crypto.derive_key("a", b"0" * 16, ITERS) != vault_crypto.derive_key("a", b"1" * 16, ITERS)


def test_new_dek_is_random_32_bytes():
    a, b = vault_crypto.new_dek(), vault_crypto.new_dek()
    assert len(a) == 32 and a != b


def test_wrap_unwrap_roundtrip():
    dek = vault_crypto.new_dek()
    kek = vault_crypto.derive_key("pw", vault_crypto.new_salt(), ITERS)
    assert vault_crypto.unwrap_dek(kek, vault_crypto.wrap_dek(kek, dek)) == dek


def test_unwrap_wrong_kek_fails():
    dek, salt = vault_crypto.new_dek(), vault_crypto.new_salt()
    wrapped = vault_crypto.wrap_dek(vault_crypto.derive_key("right", salt, ITERS), dek)
    with pytest.raises(Exception):
        vault_crypto.unwrap_dek(vault_crypto.derive_key("wrong", salt, ITERS), wrapped)


def test_recovery_code_format_and_normalization():
    code = vault_crypto.generate_recovery_code()
    assert "-" in code
    norm = vault_crypto.normalize_recovery_code(code)
    assert norm.isalnum() and norm == norm.upper()
    # formatting/case is ignored on input
    assert vault_crypto.normalize_recovery_code(code.lower().replace("-", " ")) == norm
