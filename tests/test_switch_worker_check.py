import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from warestore.application.account_manager.account_check import (
    CheckResult,
    CheckSteps,
    SourceLoadout,
)
from warestore.presentation.account_manager.features.login.switch_worker import SwitchWorker

TARGET_SID = "76561198000000002"


@pytest.fixture(scope="module", autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


class FakeCtrl:
    def __init__(self, fail=False, loadout_on=True, source_sid="76561198000000001"):
        self.calls = []
        self.fail = fail
        self.loadout_on = loadout_on
        self.source_sid = source_sid
        self.deadlines: dict[str, float | None] = {}

    def seed_cs2_config_if_new(self, sid):
        return False

    def apply_source_launch_options(self, sid):
        return False

    def steam_id_for_entry(self, raw):
        self.calls.append("steam_id_for_entry")
        return TARGET_SID

    def account_check_steps(self):
        return CheckSteps(loadout=self.loadout_on)

    def cs2_config_source(self):
        return self.source_sid

    def read_source_loadout(self, deadline=None):
        self.calls.append("read_source_loadout")
        self.deadlines["read_source_loadout"] = deadline
        return SourceLoadout(steam_id=self.source_sid, name="src", loadout={})

    def check_account(self, steam_id, *, source, steps=None, deadline=None):
        self.calls.append("check_account")
        self.deadlines["check_account"] = deadline
        if self.fail:
            raise RuntimeError("boom")
        return CheckResult(steam_id=steam_id)

    def launch_steam(self, *, open_cs2=False):
        self.calls.append("launch_steam")


def _worker(ctrl, check=True):
    return SwitchWorker(mode="token", token="alice----eyJ", check_account=check, ctrl=ctrl)


def test_check_runs_before_steam_launches():
    ctrl = FakeCtrl()
    _worker(ctrl)._post_login(r"C:\Steam")
    assert ctrl.calls == ["steam_id_for_entry", "read_source_loadout", "check_account", "launch_steam"]


def test_a_failing_check_still_launches_steam():
    ctrl = FakeCtrl(fail=True)
    _worker(ctrl)._post_login(r"C:\Steam")
    assert ctrl.calls[-1] == "launch_steam"


def test_no_check_when_disabled():
    ctrl = FakeCtrl()
    _worker(ctrl, check=False)._post_login(r"C:\Steam")
    assert ctrl.calls == ["launch_steam"]


# --- I1: the add-flow deadline is computed once, before the source read -----


def test_deadline_is_the_same_for_the_source_read_and_the_check():
    ctrl = FakeCtrl()
    _worker(ctrl)._post_login(r"C:\Steam")
    assert ctrl.deadlines["read_source_loadout"] is not None
    assert ctrl.deadlines["read_source_loadout"] == ctrl.deadlines["check_account"]


# --- I2: never log into the source account when it can't matter ------------


def test_no_source_read_when_the_loadout_step_is_off():
    ctrl = FakeCtrl(loadout_on=False)
    _worker(ctrl)._post_login(r"C:\Steam")
    assert "read_source_loadout" not in ctrl.calls
    assert ctrl.calls == ["steam_id_for_entry", "check_account", "launch_steam"]


def test_no_source_read_when_no_source_is_set():
    ctrl = FakeCtrl(source_sid="")
    _worker(ctrl)._post_login(r"C:\Steam")
    assert "read_source_loadout" not in ctrl.calls


def test_no_source_read_when_the_target_is_the_source():
    ctrl = FakeCtrl(source_sid=TARGET_SID)
    _worker(ctrl)._post_login(r"C:\Steam")
    assert "read_source_loadout" not in ctrl.calls
