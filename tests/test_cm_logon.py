import base64
import json
from types import SimpleNamespace

import pytest
import steam.client
from steam.enums import EPersonaState, EResult

from warestore.infrastructure.steam import cs2_cm_mint as mint

SID = 76561198000000001


def _token(sid=SID):
    def b64(d):
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{b64({'alg': 'none'})}.{b64({'sub': str(sid)})}.sig"


class FakeClient:
    instances: list["FakeClient"] = []
    connect_result = True

    def __init__(self):
        self.persona_state = EPersonaState.Online  # ValvePython's default
        self.connected = False
        self.disconnected = False
        self.connect_calls: list[dict] = []
        FakeClient.instances.append(self)

    def connect(self, retry=0, delay=0):
        self.connect_calls.append({"retry": retry, "delay": delay})
        if not FakeClient.connect_result:
            return False
        self.connected = True
        return True

    def disconnect(self):
        self.disconnected = True


@pytest.fixture(autouse=True)
def _fake_steam(monkeypatch):
    FakeClient.instances = []
    FakeClient.connect_result = True
    monkeypatch.setattr(steam.client, "SteamClient", FakeClient)


def test_logon_is_offline_before_the_logon_message(monkeypatch):
    seen = {}

    def fake_logon(client, token, steamid, timeout=30):
        seen["persona"] = client.persona_state
        return SimpleNamespace(body=SimpleNamespace(eresult=EResult.OK))

    monkeypatch.setattr(mint, "_token_logon", fake_logon)
    client, steamid, token = mint.open_cm_client("alice----" + _token())
    assert seen["persona"] == EPersonaState.Offline
    assert steamid == SID and token == _token() and client is FakeClient.instances[0]


def test_rejected_token_raises_and_disconnects(monkeypatch):
    monkeypatch.setattr(
        mint, "_token_logon",
        lambda c, t, s, timeout=30: SimpleNamespace(body=SimpleNamespace(eresult=EResult.InvalidPassword)),
    )
    with pytest.raises(mint.TokenRejectedError):
        mint.open_cm_client(_token())
    assert FakeClient.instances[-1].disconnected


def test_no_response_is_transient(monkeypatch):
    monkeypatch.setattr(mint, "_token_logon", lambda c, t, s, timeout=30: None)
    with pytest.raises(mint.CmLogonError):
        mint.open_cm_client(_token())


def test_connect_failure_raises_without_hanging_and_uses_finite_retry():
    """C1: client.connect() must never be called with ValvePython's default
    retry=0 (unlimited retries — steam/core/cm.py loops forever when CM ports
    are blocked or there's no network), and a connect() False must not be
    confused with the None "already connecting" case."""
    FakeClient.connect_result = False
    with pytest.raises(mint.CmLogonError):
        mint.open_cm_client(_token())
    assert len(FakeClient.instances) == 1
    client = FakeClient.instances[0]
    assert client.connect_calls, "connect() was never called"
    for call in client.connect_calls:
        assert call["retry"] not in (0, None), "connect() must use a finite retry"


def test_rate_limit_stops_at_once_without_retrying(monkeypatch):
    calls = []

    def fake_logon(c, t, s, timeout=30):
        calls.append(1)
        return SimpleNamespace(body=SimpleNamespace(eresult=EResult.RateLimitExceeded))

    monkeypatch.setattr(mint, "_token_logon", fake_logon)
    with pytest.raises(mint.RateLimitedError):
        mint.open_cm_client(_token())
    assert len(calls) == 1  # retrying would only dig the hole deeper
    assert FakeClient.instances[-1].disconnected


def test_rate_limit_is_still_a_transient_cm_error():
    assert issubclass(mint.RateLimitedError, mint.CmLogonError)
