"""Controller orchestration for CS2 config seeding (seed-once semantics)."""

import os
from types import SimpleNamespace

from warestore.application.account_manager.controller import AccountManagerController
from warestore.domain.accounts.models import AccountRecord
from warestore.infrastructure.steam.cs2_config_gateway import Cs2ConfigGateway
from warestore.infrastructure.steam.persona_gateway import PersonaGateway

SRC_SID = "76561198000000001"
DST_SID = "76561198000000002"


class _FakeSettings:
    def __init__(self, data):
        self._data = data

    def load(self):
        return dict(self._data)

    def save(self, data):
        self._data = dict(data)


class _FakeMetadata:
    def __init__(self):
        self.records: dict[str, AccountRecord] = {}
        self.seeded: dict[str, bool] = {}

    def get(self, sid):
        return self.records.get(sid, AccountRecord())

    def set_cs2_seeded(self, sid, seeded=True):
        self.seeded[sid] = seeded
        rec = self.records.setdefault(sid, AccountRecord())
        rec.cs2_seeded = seeded


def _make_controller(tmp_path, source_sid):
    cs2 = Cs2ConfigGateway()
    facade = SimpleNamespace(
        settings=_FakeSettings({"cs2_config_source_sid": source_sid}),
        metadata=_FakeMetadata(),
        cs2_config=cs2,
        steam_login=SimpleNamespace(
            process=SimpleNamespace(install_path=lambda: str(tmp_path)),
            copy_cs2_launch_options=PersonaGateway().copy_launch_options,
        ),
    )
    return AccountManagerController(facade=facade), facade


def _seed_source(tmp_path):
    cfg = Cs2ConfigGateway().config_dir(str(tmp_path), SRC_SID)
    os.makedirs(cfg, exist_ok=True)
    with open(os.path.join(cfg, "video.txt"), "w", encoding="utf-8") as f:
        f.write("fps=300")


def test_seed_copies_and_marks_once(tmp_path):
    _seed_source(tmp_path)
    ctrl, facade = _make_controller(tmp_path, SRC_SID)

    assert ctrl.seed_cs2_config_if_new(DST_SID) is True
    assert facade.metadata.seeded[DST_SID] is True
    assert facade.cs2_config.has_config(str(tmp_path), DST_SID)

    # already seeded → no second copy
    assert ctrl.seed_cs2_config_if_new(DST_SID) is False


def test_skip_when_no_source(tmp_path):
    _seed_source(tmp_path)
    ctrl, _ = _make_controller(tmp_path, "")
    assert ctrl.seed_cs2_config_if_new(DST_SID) is False


def test_skip_target_is_source(tmp_path):
    _seed_source(tmp_path)
    ctrl, _ = _make_controller(tmp_path, SRC_SID)
    assert ctrl.seed_cs2_config_if_new(SRC_SID) is False


def test_not_marked_when_source_has_no_config(tmp_path):
    # source folder never created → nothing to copy, so target stays unseeded
    ctrl, facade = _make_controller(tmp_path, SRC_SID)
    assert ctrl.seed_cs2_config_if_new(DST_SID) is False
    assert DST_SID not in facade.metadata.seeded


def test_source_getter_setter_roundtrip(tmp_path):
    ctrl, _ = _make_controller(tmp_path, "")
    ctrl.set_cs2_config_source(SRC_SID)
    assert ctrl.cs2_config_source() == SRC_SID


def test_apply_overrides_already_seeded(tmp_path):
    _seed_source(tmp_path)
    ctrl, facade = _make_controller(tmp_path, SRC_SID)
    # mark target as already seeded — seed path would now skip it...
    facade.metadata.set_cs2_seeded(DST_SID, True)
    assert ctrl.seed_cs2_config_if_new(DST_SID) is False
    # ...but the manual override applies regardless and copies the config.
    assert ctrl.apply_cs2_config(DST_SID) is True
    assert facade.cs2_config.has_config(str(tmp_path), DST_SID)


def test_apply_skips_without_source(tmp_path):
    _seed_source(tmp_path)
    ctrl, _ = _make_controller(tmp_path, "")
    assert ctrl.apply_cs2_config(DST_SID) is False


def test_apply_source_launch_options_copies_every_time(tmp_path):
    # source has launch options; target starts with none
    persona = PersonaGateway()
    persona.set_cs2_launch_options(str(tmp_path), SRC_SID, "-novid -high")
    ctrl, _ = _make_controller(tmp_path, SRC_SID)

    # not gated on seeding — works even for an already-seeded / arbitrary target
    assert ctrl.apply_source_launch_options(DST_SID) is True
    assert persona.get_cs2_launch_options(str(tmp_path), DST_SID) == "-novid -high"
    # and again on the next switch (no seed-once gate)
    assert ctrl.apply_source_launch_options(DST_SID) is True


def test_apply_source_launch_options_noop_without_source(tmp_path):
    persona = PersonaGateway()
    persona.set_cs2_launch_options(str(tmp_path), SRC_SID, "-novid")
    ctrl, _ = _make_controller(tmp_path, "")
    assert ctrl.apply_source_launch_options(DST_SID) is False
