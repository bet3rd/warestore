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

    def __init__(self):
        self.persona_state = EPersonaState.Online  # ValvePython's default
        self.connected = False
        self.disconnected = False
        FakeClient.instances.append(self)

    def connect(self):
        self.connected = True
        return True

    def disconnect(self):
        self.disconnected = True


@pytest.fixture(autouse=True)
def _fake_steam(monkeypatch):
    FakeClient.instances = []
    monkeypatch.setattr(steam.client, "SteamClient", FakeClient)


def test_logon_is_offline_before_the_logon_message(monkeypatch):
    seen = {}

    def fake_logon(client, token, steamid):
        seen["persona"] = client.persona_state
        return SimpleNamespace(body=SimpleNamespace(eresult=EResult.OK))

    monkeypatch.setattr(mint, "_token_logon", fake_logon)
    client, steamid, token = mint.open_cm_client("alice----" + _token())
    assert seen["persona"] == EPersonaState.Offline
    assert steamid == SID and token == _token() and client is FakeClient.instances[0]


def test_rejected_token_raises_and_disconnects(monkeypatch):
    monkeypatch.setattr(
        mint, "_token_logon",
        lambda c, t, s: SimpleNamespace(body=SimpleNamespace(eresult=EResult.InvalidPassword)),
    )
    with pytest.raises(mint.TokenRejectedError):
        mint.open_cm_client(_token())
    assert FakeClient.instances[-1].disconnected


def test_no_response_is_transient(monkeypatch):
    monkeypatch.setattr(mint, "_token_logon", lambda c, t, s: None)
    with pytest.raises(mint.CmLogonError):
        mint.open_cm_client(_token())
