# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os

import vdf

from warestore.config.settings import STEAMID64_BASE
from warestore.infrastructure.steam.persona_gateway import PersonaGateway

SRC = str(STEAMID64_BASE + 1000)  # id32 = 1000
DST = str(STEAMID64_BASE + 2000)  # id32 = 2000
OPTS = "-novid -tickrate 128 -high"


def _localconfig(steam_dir: str, sid: str) -> str:
    id32 = int(sid) - STEAMID64_BASE
    return os.path.join(steam_dir, "userdata", str(id32), "config", "localconfig.vdf")


def _seed_source(steam_dir: str, options: str) -> None:
    """Write a source localconfig.vdf with launch options at Steam's real path."""
    path = _localconfig(steam_dir, SRC)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    data = {
        "UserLocalConfigStore": {
            "Software": {"Valve": {"Steam": {"apps": {"730": {"LaunchOptions": options}}}}}
        }
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(vdf.dumps(data, pretty=True))


def test_get_reads_real_steam_path(tmp_path):
    steam = str(tmp_path)
    _seed_source(steam, OPTS)
    assert PersonaGateway().get_cs2_launch_options(steam, SRC) == OPTS


def test_get_missing_returns_empty(tmp_path):
    assert PersonaGateway().get_cs2_launch_options(str(tmp_path), SRC) == ""


def test_set_writes_to_real_steam_path(tmp_path):
    steam = str(tmp_path)
    PersonaGateway().set_cs2_launch_options(steam, DST, OPTS)
    # Read the raw file and confirm the value sits under the correct nested key.
    data = vdf.loads(open(_localconfig(steam, DST), encoding="utf-8").read())
    node = data["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]["730"]
    assert node["LaunchOptions"] == OPTS
    # And that there is NO shallow (wrong) apps/730 key that Steam would ignore.
    assert "apps" not in data["UserLocalConfigStore"]


def test_copy_transfers_options(tmp_path):
    steam = str(tmp_path)
    _seed_source(steam, OPTS)
    assert PersonaGateway().copy_launch_options(steam, SRC, DST) is True
    assert PersonaGateway().get_cs2_launch_options(steam, DST) == OPTS


def test_copy_noop_when_source_has_none(tmp_path):
    steam = str(tmp_path)
    _seed_source(steam, "")  # empty options
    assert PersonaGateway().copy_launch_options(steam, SRC, DST) is False


def test_copy_noop_same_account(tmp_path):
    steam = str(tmp_path)
    _seed_source(steam, OPTS)
    assert PersonaGateway().copy_launch_options(steam, SRC, SRC) is False


def test_set_preserves_existing_localconfig_keys(tmp_path):
    """Setting launch options must not clobber other UserLocalConfigStore data."""
    steam = str(tmp_path)
    path = _localconfig(steam, DST)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(vdf.dumps({"UserLocalConfigStore": {"friends": {"SignIntoFriends": "1"}}}, pretty=True))
    PersonaGateway().set_cs2_launch_options(steam, DST, OPTS)
    data = vdf.loads(open(path, encoding="utf-8").read())
    assert data["UserLocalConfigStore"]["friends"]["SignIntoFriends"] == "1"
    assert (
        data["UserLocalConfigStore"]["Software"]["Valve"]["Steam"]["apps"]["730"]["LaunchOptions"]
        == OPTS
    )
