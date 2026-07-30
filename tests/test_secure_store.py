import json
import os

from warestore.infrastructure.persistence import vault_crypto
from warestore.infrastructure.persistence.secure_store import SecureJsonStore
from warestore.infrastructure.persistence.token_repository import TokenRepository

_KEY = vault_crypto.derive_key("test-pw", b"0" * 16, 1000)
_KEY2 = vault_crypto.derive_key("other-pw", b"0" * 16, 1000)


def test_roundtrip_encrypts_on_disk(tmp_path):
    path = str(tmp_path / "tokens.json")
    store = SecureJsonStore(path)
    store.write({"76561": {"username": "alice", "token": "eyHEADER.body.sig"}})

    raw = (tmp_path / "tokens.json").read_bytes()
    assert b"eyHEADER.body.sig" not in raw  # not stored in plaintext
    assert raw[:4] == b"\x01\x00\x00\x00"  # DPAPI blob header

    assert store.read()["76561"]["token"] == "eyHEADER.body.sig"


def test_missing_file_returns_default(tmp_path):
    store = SecureJsonStore(str(tmp_path / "nope.json"))
    assert store.read() == {}
    assert store.read({"a": 1}) == {"a": 1}


def test_legacy_plaintext_is_migrated(tmp_path):
    path = tmp_path / "tokens.json"
    path.write_text(json.dumps({"111": {"token": "plain.jwt.value"}}), encoding="utf-8")

    store = SecureJsonStore(str(path))
    assert store.read()["111"]["token"] == "plain.jwt.value"

    raw = path.read_bytes()
    assert b"plain.jwt.value" not in raw  # re-saved encrypted
    assert store.read()["111"]["token"] == "plain.jwt.value"  # still readable


def test_empty_file_returns_default(tmp_path):
    path = tmp_path / "tokens.json"
    path.write_bytes(b"")
    assert SecureJsonStore(str(path)).read() == {}


# --- master-password (AES) mode ---


def test_password_mode_roundtrip_and_format(tmp_path):
    path = tmp_path / "tokens.json"
    store = SecureJsonStore(str(path), key=_KEY)
    store.write({"a": {"token": "eyX.y.z"}})
    raw = path.read_bytes()
    assert raw[:4] == b"WSV1"  # AES vault header
    assert b"eyX.y.z" not in raw
    assert store.read()["a"]["token"] == "eyX.y.z"


def test_locked_vault_without_key_returns_default(tmp_path):
    path = tmp_path / "tokens.json"
    SecureJsonStore(str(path), key=_KEY).write({"a": 1})
    assert SecureJsonStore(str(path)).read() == {}  # no key -> locked
    assert SecureJsonStore(str(path), key=_KEY2).read() == {}  # wrong key -> fails closed


def test_dpapi_upgrades_to_password_on_read(tmp_path):
    path = tmp_path / "tokens.json"
    SecureJsonStore(str(path)).write({"a": {"token": "t"}})  # DPAPI
    assert path.read_bytes()[:4] != b"WSV1"
    store = SecureJsonStore(str(path), key=_KEY)
    assert store.read()["a"]["token"] == "t"  # reads DPAPI, re-saves AES
    assert path.read_bytes()[:4] == b"WSV1"


def test_repo_rekey_both_directions(tmp_path):
    repo = TokenRepository(path=str(tmp_path / "tok.json"))
    repo.store("s", "u", "eyA.b.c")  # DPAPI
    repo.rekey(_KEY)  # -> AES
    assert (tmp_path / "tok.json").read_bytes()[:4] == b"WSV1"
    assert repo.load_all()["s"]["token"] == "eyA.b.c"
    repo.rekey(None)  # -> DPAPI
    assert (tmp_path / "tok.json").read_bytes()[:4] != b"WSV1"
    assert repo.load_all()["s"]["token"] == "eyA.b.c"
