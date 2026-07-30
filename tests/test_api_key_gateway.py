import urllib.error

import warestore.infrastructure.steam.api_key_gateway as mod
from warestore.infrastructure.steam.api_key_gateway import SteamApiKeyGateway

KEY = "A" * 32


class _OkResp:
    def read(self):
        return b"{}"

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_empty_key_is_invalid():
    assert SteamApiKeyGateway().validate("   ") == "invalid"


def test_valid_key(monkeypatch):
    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda url, timeout=0: _OkResp())
    assert SteamApiKeyGateway().validate(KEY) == "valid"


def test_forbidden_is_invalid(monkeypatch):
    def boom(url, timeout=0):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    assert SteamApiKeyGateway().validate(KEY) == "invalid"


def test_other_http_status_is_error(monkeypatch):
    def boom(url, timeout=0):
        raise urllib.error.HTTPError(url, 500, "Server Error", {}, None)

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    assert SteamApiKeyGateway().validate(KEY) == "error"


def test_network_failure_is_error(monkeypatch):
    def boom(url, timeout=0):
        raise OSError("network down")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    assert SteamApiKeyGateway().validate(KEY) == "error"
