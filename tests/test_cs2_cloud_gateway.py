"""Per-account Steam Cloud toggle for CS2 (sharedconfig.vdf)."""

import os

import vdf

from warestore.infrastructure.steam.cs2_cloud_gateway import Cs2CloudGateway

SID = "76561198000000002"


def _read(path):
    with open(path, encoding="utf-8") as f:
        return vdf.loads(f.read())


def _apps(data):
    root = next(iter(data))
    return data[root]["Software"]["Valve"]["Steam"]["apps"]


def test_creates_file_when_missing(tmp_path):
    gw = Cs2CloudGateway()
    assert gw.set_cloud_enabled(str(tmp_path), SID, False) is True
    path = gw.sharedconfig_path(str(tmp_path), SID)
    assert os.path.exists(path)
    assert _apps(_read(path))["730"]["cloudenabled"] == "0"
    assert gw.is_cloud_enabled(str(tmp_path), SID) is False


def test_preserves_unrelated_keys(tmp_path):
    gw = Cs2CloudGateway()
    path = gw.sharedconfig_path(str(tmp_path), SID)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    existing = {
        "UserRoamingConfigStore": {
            "Software": {"Valve": {"Steam": {
                "SurveyDate": "2024-02-24",
                "apps": {"440": {"cloudenabled": "1"}},
            }}},
            "JSClientStorage": {"spotlight": {"x": "1"}},
        }
    }
    with open(path, "w", encoding="utf-8") as f:
        f.write(vdf.dumps(existing, pretty=True))

    assert gw.set_cloud_enabled(str(tmp_path), SID, False) is True
    data = _read(path)
    steam = data["UserRoamingConfigStore"]["Software"]["Valve"]["Steam"]
    assert steam["SurveyDate"] == "2024-02-24"           # untouched
    assert steam["apps"]["440"]["cloudenabled"] == "1"   # other app untouched
    assert steam["apps"]["730"]["cloudenabled"] == "0"   # ours set
    assert data["UserRoamingConfigStore"]["JSClientStorage"]["spotlight"]["x"] == "1"


def test_idempotent(tmp_path):
    gw = Cs2CloudGateway()
    gw.set_cloud_enabled(str(tmp_path), SID, False)
    first = open(gw.sharedconfig_path(str(tmp_path), SID), encoding="utf-8").read()
    gw.set_cloud_enabled(str(tmp_path), SID, False)
    second = open(gw.sharedconfig_path(str(tmp_path), SID), encoding="utf-8").read()
    assert first == second


def test_can_re_enable(tmp_path):
    gw = Cs2CloudGateway()
    gw.set_cloud_enabled(str(tmp_path), SID, False)
    assert gw.is_cloud_enabled(str(tmp_path), SID) is False
    gw.set_cloud_enabled(str(tmp_path), SID, True)
    assert gw.is_cloud_enabled(str(tmp_path), SID) is True


def test_unparseable_file_is_left_alone(tmp_path):
    gw = Cs2CloudGateway()
    path = gw.sharedconfig_path(str(tmp_path), SID)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write('"broken" { unclosed')
    before = open(path, encoding="utf-8").read()
    assert gw.set_cloud_enabled(str(tmp_path), SID, False) is False
    assert open(path, encoding="utf-8").read() == before  # not clobbered


def test_defaults_to_enabled_when_no_file(tmp_path):
    assert Cs2CloudGateway().is_cloud_enabled(str(tmp_path), SID) is True
