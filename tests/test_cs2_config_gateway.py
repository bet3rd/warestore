import os

from warestore.config.settings import CS2_APP_ID, STEAMID64_BASE
from warestore.infrastructure.steam.cs2_config_gateway import Cs2ConfigGateway

SRC_SID = "76561198000000001"
DST_SID = "76561198000000002"


def _seed_config(steam_dir, sid, files):
    gw = Cs2ConfigGateway()
    cfg = gw.config_dir(steam_dir, sid)
    os.makedirs(os.path.join(cfg, "local", "cfg"), exist_ok=True)
    for name, content in files.items():
        with open(os.path.join(cfg, name), "w", encoding="utf-8") as f:
            f.write(content)
    return cfg


def test_account_id32_and_path(tmp_path):
    gw = Cs2ConfigGateway()
    assert gw.account_id32(SRC_SID) == int(SRC_SID) - STEAMID64_BASE
    path = gw.config_dir(str(tmp_path), SRC_SID)
    assert path.endswith(os.path.join("userdata", str(gw.account_id32(SRC_SID)), CS2_APP_ID))


def test_has_config(tmp_path):
    gw = Cs2ConfigGateway()
    assert not gw.has_config(str(tmp_path), SRC_SID)
    _seed_config(str(tmp_path), SRC_SID, {"video.txt": "x"})
    assert gw.has_config(str(tmp_path), SRC_SID)


def test_copy_creates_target(tmp_path):
    gw = Cs2ConfigGateway()
    _seed_config(str(tmp_path), SRC_SID, {"video.txt": "fps=300"})
    assert gw.copy_config(str(tmp_path), SRC_SID, DST_SID) is True
    dst = gw.config_dir(str(tmp_path), DST_SID)
    with open(os.path.join(dst, "video.txt"), encoding="utf-8") as f:
        assert f.read() == "fps=300"
    # nested structure is copied too
    assert os.path.isdir(os.path.join(dst, "local", "cfg"))


def test_copy_backs_up_existing_target(tmp_path):
    gw = Cs2ConfigGateway()
    _seed_config(str(tmp_path), SRC_SID, {"video.txt": "from-source"})
    _seed_config(str(tmp_path), DST_SID, {"video.txt": "from-target"})
    assert gw.copy_config(str(tmp_path), SRC_SID, DST_SID) is True
    dst = gw.config_dir(str(tmp_path), DST_SID)
    with open(os.path.join(dst, "video.txt"), encoding="utf-8") as f:
        assert f.read() == "from-source"
    with open(os.path.join(dst + ".bak", "video.txt"), encoding="utf-8") as f:
        assert f.read() == "from-target"


def test_copy_skips_when_source_empty(tmp_path):
    gw = Cs2ConfigGateway()
    assert gw.copy_config(str(tmp_path), SRC_SID, DST_SID) is False
    assert not gw.has_config(str(tmp_path), DST_SID)


def test_copy_skips_same_account(tmp_path):
    gw = Cs2ConfigGateway()
    _seed_config(str(tmp_path), SRC_SID, {"video.txt": "x"})
    assert gw.copy_config(str(tmp_path), SRC_SID, SRC_SID) is False
