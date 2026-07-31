from warestore.infrastructure.steam.profile_gateway import SteamProfileGateway


def test_parse_in_game_status(monkeypatch):
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
<profile>
  <privacyState>public</privacyState>
  <onlineState>in-game</onlineState>
  <stateMessage><![CDATA[In-Game<br/>Counter-Strike 2]]></stateMessage>
</profile>"""

    class FakeResp:
        def read(self):
            return xml

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: FakeResp(),
    )

    gw = SteamProfileGateway(throttle_seconds=0)
    status = gw._fetch_one("76561198000000001")
    assert status["state"] == 6
    assert "Counter-Strike" in status["game"]


def _mock_xml(monkeypatch, xml: bytes):
    class FakeResp:
        def read(self):
            return xml

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: FakeResp())


def test_parse_online_status(monkeypatch):
    _mock_xml(
        monkeypatch,
        b"""<profile>
  <privacyState>public</privacyState>
  <onlineState>online</onlineState>
</profile>""",
    )
    status = SteamProfileGateway(throttle_seconds=0)._fetch_one("76561198000000001")
    assert (status["state"], status["game"]) == (1, "")


def test_parse_persona_and_avatar(monkeypatch):
    _mock_xml(
        monkeypatch,
        b"""<profile>
  <privacyState>public</privacyState>
  <onlineState>online</onlineState>
  <steamID>CoolGuy</steamID>
  <avatarFull>https://avatars.example/abcdef_full.jpg</avatarFull>
</profile>""",
    )
    status = SteamProfileGateway(throttle_seconds=0)._fetch_one("76561198000000001")
    assert status["persona"] == "CoolGuy"
    assert status["avatar"] == "https://avatars.example/abcdef_full.jpg"
    assert status["avatar_hash"] == "abcdef"


def test_parse_private_profile(monkeypatch):
    _mock_xml(
        monkeypatch,
        b"""<profile>
  <privacyState>private</privacyState>
</profile>""",
    )
    status = SteamProfileGateway(throttle_seconds=0)._fetch_one("76561198000000001")
    assert status["private"] is True
    assert status["state"] == 0
