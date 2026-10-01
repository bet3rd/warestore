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
RAW_TOKEN = "alice----eyJ"


@pytest.fixture(scope="module", autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


class FakeCtrl:
    def __init__(self, fail=False, loadout_on=True, source_sid="76561198000000001", result=None):
        self.calls = []
        self.fail = fail
        self.loadout_on = loadout_on
        self.source_sid = source_sid
        self.result = result
        self.deadlines: dict[str, float | None] = {}
        self.checked_token = None

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

    def check_account(self, steam_id, *, source, steps=None, deadline=None, token=None):
        self.calls.append("check_account")
        self.deadlines["check_account"] = deadline
        self.checked_token = token
        if self.fail:
            raise RuntimeError("boom")
        return self.result or CheckResult(steam_id=steam_id)

    def kill_steam(self):
        self.calls.append("kill_steam")

    def steam_install_path(self):
        return r"C:\Steam"

    def perform_token_login(self, token, disable_remote_play=False):
        self.calls.append("perform_token_login")
        return True

    def launch_steam(self, *, open_cs2=False):
        self.calls.append("launch_steam")


def _run(ctrl, check=True):
    worker = SwitchWorker(mode="token", token=RAW_TOKEN, check_account=check, ctrl=ctrl)
    out = {"finished": None, "status": []}
    worker.finished.connect(lambda ok: out.__setitem__("finished", ok))
    worker.status.connect(out["status"].append)
    worker.run()  # synchronously; the logic doesn't need the thread
    return out


def test_the_token_is_checked_before_anything_is_written_to_steam():
    ctrl = FakeCtrl()
    out = _run(ctrl)
    assert ctrl.calls == [
        "steam_id_for_entry", "read_source_loadout", "check_account",
        "kill_steam", "perform_token_login", "launch_steam",
    ]
    assert out["finished"] is True


def test_the_check_uses_the_pasted_token_not_the_vault():
    ctrl = FakeCtrl()
    _run(ctrl)
    assert ctrl.checked_token == RAW_TOKEN


def test_a_rejected_token_is_never_added():
    ctrl = FakeCtrl(result=CheckResult(steam_id=TARGET_SID, token_dead=True))
    out = _run(ctrl)
    assert "perform_token_login" not in ctrl.calls
    assert "kill_steam" not in ctrl.calls and "launch_steam" not in ctrl.calls
    assert out["finished"] is False
    assert any("rejected" in s.lower() for s in out["status"])


def test_a_check_that_cannot_reach_steam_still_adds_the_account():
    ctrl = FakeCtrl(fail=True)
    out = _run(ctrl)
    assert "perform_token_login" in ctrl.calls and out["finished"] is True


def test_no_check_when_disabled():
    ctrl = FakeCtrl()
    _run(ctrl, check=False)
    assert ctrl.calls == ["kill_steam", "perform_token_login", "launch_steam"]


# --- the add-flow deadline is computed once, before the source read ---------


def test_deadline_is_the_same_for_the_source_read_and_the_check():
    ctrl = FakeCtrl()
    _run(ctrl)
    assert ctrl.deadlines["read_source_loadout"] is not None
    assert ctrl.deadlines["read_source_loadout"] == ctrl.deadlines["check_account"]


# --- never log into the source account when it can't matter -----------------


def test_no_source_read_when_the_loadout_step_is_off():
    ctrl = FakeCtrl(loadout_on=False)
    _run(ctrl)
    assert "read_source_loadout" not in ctrl.calls
    assert ctrl.calls[:2] == ["steam_id_for_entry", "check_account"]


def test_no_source_read_when_no_source_is_set():
    ctrl = FakeCtrl(source_sid="")
    _run(ctrl)
    assert "read_source_loadout" not in ctrl.calls


def test_no_source_read_when_the_target_is_the_source():
    ctrl = FakeCtrl(source_sid=TARGET_SID)
    _run(ctrl)
    assert "read_source_loadout" not in ctrl.calls


def test_a_rejected_token_is_flagged_for_the_prompt():
    ctrl = FakeCtrl(result=CheckResult(steam_id=TARGET_SID, token_dead=True))
    worker = SwitchWorker(mode="token", token=RAW_TOKEN, check_account=True, ctrl=ctrl)
    worker.run()
    assert worker.token_rejected is True


# --- the "keep it anyway?" prompt --------------------------------------------


def _login_coord(keep: bool):
    from types import SimpleNamespace

    from warestore.presentation.account_manager.features.login.coordinator import LoginCoordinator

    coord = LoginCoordinator.__new__(LoginCoordinator)
    coord._worker = SimpleNamespace(token_rejected=True, token=RAW_TOKEN,
                                    failure_message="Steam rejected this token — account not added.")
    coord.started = []
    coord.statuses = []
    coord._set_busy = lambda busy, msg="": None
    coord._set_status = coord.statuses.append
    coord._refresh_log = lambda: None
    coord._confirm_keep_rejected = lambda: keep
    coord.start_switch = lambda **kw: coord.started.append(kw)
    return coord


def test_keeping_a_rejected_token_adds_it_without_checking_again():
    coord = _login_coord(keep=True)
    coord._on_worker_done(False)
    assert coord.started == [{"mode": "token", "token": RAW_TOKEN, "is_add": True, "skip_check": True}]


def test_not_keeping_a_rejected_token_adds_nothing():
    coord = _login_coord(keep=False)
    coord._on_worker_done(False)
    assert coord.started == []
    assert "not added" in coord.statuses[-1].lower()
