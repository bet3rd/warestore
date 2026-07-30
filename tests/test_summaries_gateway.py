import json

import warestore.infrastructure.steam.level_gateway as level_module
import warestore.infrastructure.steam.summaries_gateway as sum_module
from warestore.infrastructure.steam.level_gateway import SteamLevelGateway
from warestore.infrastructure.steam.summaries_gateway import SteamSummariesGateway


class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_summaries_no_key_skips_network():
    assert SteamSummariesGateway().fetch_statuses("", ["1"]) == {}
    assert SteamSummariesGateway().fetch_statuses("k", []) == {}


def test_summaries_maps_state_and_game(monkeypatch):
    payload = {
        "response": {
            "players": [
                {"steamid": "1", "personastate": 1},  # online
                {"steamid": "2", "personastate": 1, "gameextrainfo": "CS2"},  # in-game
                {"steamid": "3", "personastate": 3},  # away
                {"steamid": "4", "personastate": 6},  # looking-to-play -> online
            ]
        }
    }
    monkeypatch.setattr(
        sum_module.urllib.request, "urlopen", lambda url, timeout=0: _FakeResp(payload)
    )
    out = SteamSummariesGateway().fetch_statuses("key", ["1", "2", "3", "4"])
    assert out["1"] == {"state": 1, "game": ""}
    assert out["2"] == {"state": 6, "game": "CS2"}
    assert out["3"] == {"state": 3, "game": ""}
    assert out["4"] == {"state": 1, "game": ""}


def test_summaries_http_error_marks_stale(monkeypatch):
    import urllib.error

    def boom(url, timeout=0):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(sum_module.urllib.request, "urlopen", boom)
    out = SteamSummariesGateway().fetch_statuses("key", ["1"])
    assert out["1"]["stale"] is True


def test_levels_parse_and_skip(monkeypatch):
    calls = {"n": 0}

    def fake(url, timeout=0):
        calls["n"] += 1
        # second id has no level in response
        if "steamid=2" in url:
            return _FakeResp({"response": {}})
        return _FakeResp({"response": {"player_level": 42}})

    monkeypatch.setattr(level_module.urllib.request, "urlopen", fake)
    out = SteamLevelGateway().fetch_levels("key", ["1", "2"])
    assert out == {"1": 42}
    assert calls["n"] == 2


def test_levels_no_key_skips_network():
    assert SteamLevelGateway().fetch_levels("", ["1"]) == {}
