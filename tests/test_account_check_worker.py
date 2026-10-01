import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from warestore.application.account_manager.account_check import CheckResult, SourceLoadout
from warestore.presentation.account_manager.features.accounts.account_check_worker import (
    AccountCheckQueue,
    AccountCheckWorker,
)


def test_queue_drops_duplicates_and_the_running_account():
    q = AccountCheckQueue()
    assert q.add(["a", "b", "a"]) == 2
    q.set_current(q.pop())  # "a" is running
    assert q.add(["a", "b", "c"]) == 1  # only "c" is new
    assert [q.pop(), q.pop(), q.pop()] == ["b", "c", None]


class FakeCtrl:
    def __init__(self):
        self.source_reads = 0
        self.checked = []
        self.source_sid = "src"

    def cs2_config_source(self):
        return self.source_sid

    def read_source_loadout(self):
        self.source_reads += 1
        return SourceLoadout(steam_id=self.source_sid, name="src", loadout={})

    def check_account(self, steam_id, *, source, steps=None, deadline=None):
        self.checked.append((steam_id, source.steam_id))
        return CheckResult(steam_id=steam_id)


@pytest.fixture(scope="module", autouse=True)
def _app():
    return QApplication.instance() or QApplication([])


def test_worker_reads_the_source_once_per_drain():
    ctrl = FakeCtrl()
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["a", "b"])
    worker.run()  # run synchronously; no thread needed for the logic
    assert ctrl.checked == [("a", "src"), ("b", "src")]
    assert ctrl.source_reads == 1


def test_worker_rereads_when_the_source_setting_changes():
    ctrl = FakeCtrl()
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["a"])
    worker.run()
    ctrl.source_sid = "src2"
    worker._queue.add(["b"])
    worker.run()
    assert ctrl.source_reads == 2 and ctrl.checked[-1] == ("b", "src2")
