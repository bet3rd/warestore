import base64
import json
import time
from types import SimpleNamespace

from warestore.domain.auth.jwt_service import SteamJwtService
from warestore.domain.accounts.services.token_parser import TokenParser
from warestore.domain.steam.services.login_service import SteamLoginService

SAMPLE_JWT = "ey.payload.sig"


def _jwt(iat: int) -> str:
    """A minimal Steam-shaped refresh-token JWT carrying a given `iat`."""
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    header = b64({"typ": "JWT", "alg": "EdDSA"})
    payload = b64({"iss": "steam", "sub": "1", "aud": ["client", "web"],
                   "iat": iat, "exp": iat + 99_999_999})
    return f"{header}.{payload}.sig"


def _jwt_exp(exp: int) -> str:
    """A Steam-shaped JWT with an explicit `exp`."""
    def b64(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")

    header = b64({"typ": "JWT", "alg": "EdDSA"})
    payload = b64({"iss": "steam", "sub": "1", "aud": ["client", "web"], "iat": 1, "exp": exp})
    return f"{header}.{payload}.sig"


class FakeProcess:
    def install_path(self):
        return "C:/Steam"

    def local_vdf_path(self):
        return "C:/local.vdf"

    def kill(self):
        pass

    def launch(self, *, open_cs2=False):
        pass

    def launch_with_spoofer(self, injector_path, *, open_cs2=False):
        pass


class FakeFiles:
    def __init__(self, loginusers: dict, local_vdf: dict):
        self._loginusers = loginusers
        self._local_vdf = local_vdf

    def read_vdf(self, path: str):
        if "loginusers" in path:
            return self._loginusers
        return self._local_vdf

    def write_vdf(self, path, data):
        pass

    def read_text(self, path):
        return ""

    def write_text(self, path, text):
        pass


class FakeCrypto:
    """Mirrors the real crc32-key scheme but with a controllable decrypt."""

    def __init__(self, decrypt_map: dict, raise_for: set[str] | None = None):
        self._decrypt_map = decrypt_map
        self._raise_for = raise_for or set()

    def crc32_key(self, username: str) -> str:
        return f"key_{username}"

    def encrypt(self, token: str, username: str) -> str:
        return f"enc:{token}"

    def decrypt(self, encrypted: str, username: str) -> str:
        if username in self._raise_for:
            raise OSError("(87, 'CryptUnprotectData', 'The parameter is incorrect.')")
        return self._decrypt_map[username]


class FakeRegistry:
    def set_autologin_with_remember(self, username):
        pass


class FakePersona:
    def set_state(self, steam_dir, steam_id, state):
        pass

    def set_cs2_launch_options(self, steam_dir, steam_id, options):
        pass


class FakeTokens:
    def __init__(self):
        self.saved: dict = {}

    def load_all(self):
        return dict(self.saved)

    def save_all(self, tokens):
        self.saved = tokens

    def store(self, steam_id, username, token):
        self.saved[steam_id] = {"username": username, "token": token}

    def remove(self, steam_id):
        return self.saved.pop(steam_id, None) is not None


def _loginusers(accounts: list[tuple[str, str]]) -> dict:
    return {
        "users": {
            steamid: {"AccountName": name, "PersonaName": name, "Timestamp": "1", "MostRecent": "0"}
            for steamid, name in accounts
        }
    }


def _connect_cache(entries: dict) -> dict:
    return {
        "MachineUserConfigStore": {
            "Software": {"Valve": {"Steam": {"ConnectCache": entries}}}
        }
    }


def _make_service(files: FakeFiles, crypto: FakeCrypto, tokens: FakeTokens) -> SteamLoginService:
    return SteamLoginService(
        process=FakeProcess(),
        files=files,
        crypto=crypto,
        registry=FakeRegistry(),
        persona=FakePersona(),
        tokens=tokens,
        jwt=SteamJwtService(),
        parser=TokenParser(),
    )


def test_account_missing_from_connect_cache_is_skipped_not_crashed(monkeypatch):
    # Regression: an account with no cached refresh token yet (fresh login,
    # never fully cached) must not crash extraction for everyone else — this
    # used to raise pywintypes.error(87) from decrypting an empty string.
    monkeypatch.setattr("os.path.exists", lambda path: True)
    files = FakeFiles(
        loginusers=_loginusers([("76500000000000001", "freshacct")]),
        local_vdf=_connect_cache({}),  # no entry for freshacct
    )
    crypto = FakeCrypto(decrypt_map={})
    tokens = FakeTokens()
    service = _make_service(files, crypto, tokens)

    count = service.extract_tokens_from_steam()

    assert count == 0
    assert tokens.saved == {}


def test_corrupted_blob_for_one_account_does_not_block_others(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda path: True)
    files = FakeFiles(
        loginusers=_loginusers(
            [("76500000000000001", "badacct"), ("76500000000000002", "goodacct")]
        ),
        local_vdf=_connect_cache({"key_badacct": "deadbeef", "key_goodacct": "cafebabe"}),
    )
    crypto = FakeCrypto(
        decrypt_map={"goodacct": SAMPLE_JWT},
        raise_for={"badacct"},
    )
    tokens = FakeTokens()
    service = _make_service(files, crypto, tokens)

    count = service.extract_tokens_from_steam()

    assert count == 1
    assert tokens.saved["76500000000000002"]["token"] == SAMPLE_JWT
    assert "76500000000000001" not in tokens.saved


def test_reextracts_newer_token_for_existing_account(monkeypatch):
    # The bug: a re-login rotates the refresh token, but extraction used to skip
    # any account it already had a token for, keeping the stale one forever.
    monkeypatch.setattr("os.path.exists", lambda path: True)
    old, new = _jwt(1000), _jwt(2000)
    files = FakeFiles(
        loginusers=_loginusers([("76500000000000001", "acct")]),
        local_vdf=_connect_cache({"key_acct": "enc"}),
    )
    crypto = FakeCrypto(decrypt_map={"acct": new})  # ConnectCache holds the NEWER token
    tokens = FakeTokens()
    tokens.saved = {"76500000000000001": {"username": "acct", "token": old}}  # stale stored
    service = _make_service(files, crypto, tokens)

    count = service.extract_tokens_from_steam()

    assert count == 1
    assert tokens.saved["76500000000000001"]["token"] == new  # refreshed to the newer one


def test_does_not_downgrade_to_older_cached_token(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda path: True)
    old, new = _jwt(1000), _jwt(2000)
    files = FakeFiles(
        loginusers=_loginusers([("76500000000000001", "acct")]),
        local_vdf=_connect_cache({"key_acct": "enc"}),
    )
    crypto = FakeCrypto(decrypt_map={"acct": old})  # ConnectCache has an OLDER token
    tokens = FakeTokens()
    tokens.saved = {"76500000000000001": {"username": "acct", "token": new}}  # newer stored
    service = _make_service(files, crypto, tokens)

    count = service.extract_tokens_from_steam()

    assert count == 0
    assert tokens.saved["76500000000000001"]["token"] == new  # kept the newer one


def test_skip_expired_avoids_reextracting_dead_tokens(monkeypatch):
    # 'Remove expired on refresh': an expired ConnectCache token must NOT be
    # re-extracted, or it churns (re-added every refresh, then purged again).
    monkeypatch.setattr("os.path.exists", lambda path: True)
    expired = _jwt_exp(int(time.time()) - 86400)  # expired yesterday
    files = FakeFiles(
        loginusers=_loginusers([("76500000000000001", "acct")]),
        local_vdf=_connect_cache({"key_acct": "enc"}),
    )
    tokens = FakeTokens()
    service = _make_service(files, FakeCrypto(decrypt_map={"acct": expired}), tokens)

    # Default (setting off): still extracted — unchanged behaviour.
    assert service.extract_tokens_from_steam() == 1
    tokens.saved.clear()

    # Setting on: the dead token is not re-extracted.
    assert service.extract_tokens_from_steam(skip_expired=True) == 0
    assert tokens.saved == {}


def test_valid_token_still_extracted_with_skip_expired(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda path: True)
    valid = _jwt_exp(int(time.time()) + 90 * 86400)
    files = FakeFiles(
        loginusers=_loginusers([("76500000000000001", "acct")]),
        local_vdf=_connect_cache({"key_acct": "enc"}),
    )
    tokens = FakeTokens()
    service = _make_service(files, FakeCrypto(decrypt_map={"acct": valid}), tokens)

    assert service.extract_tokens_from_steam(skip_expired=True) == 1
    assert tokens.saved["76500000000000001"]["token"] == valid


def test_identical_token_is_not_rewritten(monkeypatch):
    monkeypatch.setattr("os.path.exists", lambda path: True)
    same = _jwt(1500)
    files = FakeFiles(
        loginusers=_loginusers([("76500000000000001", "acct")]),
        local_vdf=_connect_cache({"key_acct": "enc"}),
    )
    crypto = FakeCrypto(decrypt_map={"acct": same})
    tokens = FakeTokens()
    tokens.saved = {"76500000000000001": {"username": "acct", "token": same}}
    service = _make_service(files, crypto, tokens)

    assert service.extract_tokens_from_steam() == 0
