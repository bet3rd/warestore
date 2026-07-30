import os

import vdf

from warestore.config.settings import STEAMID64_BASE
from warestore.infrastructure.steam.persona_gateway import PersonaGateway

STEAM_ID64 = "76561198000000001"
STEAM_ID32 = str(int(STEAM_ID64) - STEAMID64_BASE)


def _localconfig(steam_dir) -> str:
    return os.path.join(steam_dir, "userdata", STEAM_ID32, "config", "localconfig.vdf")


def _write(path: str, data: dict) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(vdf.dumps(data, pretty=True))


def _read(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return vdf.loads(f.read())


def test_disables_remote_play_in_existing_block(tmp_path):
    steam_dir = str(tmp_path)
    path = _localconfig(steam_dir)
    _write(path, {"UserLocalConfigStore": {"streaming_v2": {"EnableStreaming": "1"}}})

    PersonaGateway().set_remote_play(steam_dir, STEAM_ID64, False)

    store = _read(path)["UserLocalConfigStore"]
    assert store["streaming_v2"]["EnableStreaming"] == "0"


def test_creates_streaming_block_when_missing(tmp_path):
    # Steam only writes streaming_v2 after the account has run once, so a
    # fresh account's localconfig has no such block to edit.
    steam_dir = str(tmp_path)
    path = _localconfig(steam_dir)
    _write(path, {"UserLocalConfigStore": {"friends": {"SignIntoFriends": "1"}}})

    PersonaGateway().set_remote_play(steam_dir, STEAM_ID64, False)

    store = _read(path)["UserLocalConfigStore"]
    assert store["streaming_v2"]["EnableStreaming"] == "0"
    # Unrelated sections must survive the rewrite.
    assert store["friends"]["SignIntoFriends"] == "1"


def test_preserves_other_streaming_keys(tmp_path):
    steam_dir = str(tmp_path)
    path = _localconfig(steam_dir)
    _write(
        path,
        {
            "UserLocalConfigStore": {
                "streaming_v2": {
                    "EnableStreaming": "1",
                    "DefaultAudioDeviceName": "Some Headset",
                }
            }
        },
    )

    PersonaGateway().set_remote_play(steam_dir, STEAM_ID64, False)

    streaming = _read(path)["UserLocalConfigStore"]["streaming_v2"]
    assert streaming["EnableStreaming"] == "0"
    assert streaming["DefaultAudioDeviceName"] == "Some Headset"


def test_enabling_writes_one(tmp_path):
    steam_dir = str(tmp_path)
    path = _localconfig(steam_dir)
    _write(path, {"UserLocalConfigStore": {"streaming_v2": {"EnableStreaming": "0"}}})

    PersonaGateway().set_remote_play(steam_dir, STEAM_ID64, True)

    assert _read(path)["UserLocalConfigStore"]["streaming_v2"]["EnableStreaming"] == "1"


def test_unparseable_config_is_left_untouched(tmp_path):
    # Better to skip the toggle than clobber a config we couldn't read.
    steam_dir = str(tmp_path)
    path = _localconfig(steam_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    garbage = '"UserLocalConfigStore" { "unclosed'
    with open(path, "w", encoding="utf-8") as f:
        f.write(garbage)

    PersonaGateway().set_remote_play(steam_dir, STEAM_ID64, False)

    with open(path, encoding="utf-8") as f:
        assert f.read() == garbage
