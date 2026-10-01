import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from warestore.application.account_manager.account_check import CheckResult, SourceLoadout
from warestore.presentation.account_manager.features.login.switch_worker import SwitchWorker


@pytest.fixture(scope="module", autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


class FakeCtrl:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def seed_cs2_config_if_new(self, sid):
        return False

    def apply_source_launch_options(self, sid):
        return False

    def steam_id_for_entry(self, raw):
        self.calls.append("steam_id_for_entry")
        return "76561198000000002"

    def read_source_loadout(self):
        self.calls.append("read_source_loadout")
        return SourceLoadout(reason="no CS2 config source set")

    def check_account(self, steam_id, *, source, steps=None, deadline=None):
        self.calls.append("check_account")
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
