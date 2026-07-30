import json

import warestore.infrastructure.steam.bans_gateway as bans_module
from warestore.infrastructure.steam.bans_gateway import SteamBansGateway


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_no_key_or_ids_skips_network():
    gw = SteamBansGateway()
    assert gw.fetch_bans("", ["7656"]) == {}
    assert gw.fetch_bans("key", []) == {}


def test_parses_player_bans(monkeypatch):
    payload = {
        "players": [
            {
                "SteamId": "76561198000000001",
                "VACBanned": True,
                "NumberOfVACBans": 2,
                "NumberOfGameBans": 1,
                "CommunityBanned": False,
                "EconomyBan": "none",
                "DaysSinceLastBan": 30,
            }
        ]
    }
    monkeypatch.setattr(
        bans_module.urllib.request, "urlopen", lambda url, timeout=0: _FakeResp(payload)
    )
    out = SteamBansGateway().fetch_bans("key", ["76561198000000001"])
    rec = out["76561198000000001"]
    assert rec["vac"] is True
    assert rec["vac_count"] == 2
    assert rec["game_bans"] == 1
    assert rec["community"] is False
    assert rec["trade"] == "none"


def test_network_error_returns_empty(monkeypatch):
    def boom(url, timeout=0):
        raise OSError("network down")

    monkeypatch.setattr(bans_module.urllib.request, "urlopen", boom)
    assert SteamBansGateway().fetch_bans("key", ["1"]) == {}
