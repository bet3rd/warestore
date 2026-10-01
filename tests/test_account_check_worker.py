import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication

from warestore.application.account_manager.account_check import (
    CheckResult,
    CheckSteps,
    SourceLoadout,
)
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
        self.loadout_on = True

    def cs2_config_source(self):
        return self.source_sid

    def account_check_steps(self):
        return CheckSteps(loadout=self.loadout_on)

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


# --- I4: the cached source loadout lasts one drain only ---------------------


def test_source_is_reread_on_a_later_drain_even_with_the_same_source():
    ctrl = FakeCtrl()
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["a"])
    worker.run()
    worker._queue.add(["b"])
    worker.run()
    assert ctrl.source_reads == 2
    assert ctrl.checked == [("a", "src"), ("b", "src")]


# --- I2: never log into the source when it can't matter ---------------------


def test_no_source_read_when_the_loadout_step_is_off():
    ctrl = FakeCtrl()
    ctrl.loadout_on = False
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["a"])
    worker.run()
    assert ctrl.source_reads == 0
    assert ctrl.checked == [("a", "")]


def test_no_source_read_when_no_source_is_set():
    ctrl = FakeCtrl()
    ctrl.source_sid = ""
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["a"])
    worker.run()
    assert ctrl.source_reads == 0


def test_no_source_read_when_the_target_is_the_source():
    ctrl = FakeCtrl()
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["src"])  # target steam_id == the configured source
    worker.run()
    assert ctrl.source_reads == 0
    assert ctrl.checked == [("src", "src")]


def test_check_and_rank_sweep_dead_lists_stay_separate():
    """Verify that when both check and rank sweeps are in flight, dead accounts
    from each are handled separately and not lost."""
    from warestore.presentation.account_manager.features.accounts.coordinator import (
        AccountCoordinator,
    )

    # Build a minimal coordinator without full init
    coord = AccountCoordinator.__new__(AccountCoordinator)
    coord._check_stats = {"done": 0, "pending": 0, "dead": 1, "failed": 0}
    coord._check_dead = [{"steamid": "check_dead", "name": "Check Dead"}]
    coord._cs2_dead = [{"steamid": "rank_dead", "name": "Rank Dead"}]

    # Fake info label
    class FakeInfo:
        def setText(self, text):
            self.text = text

    coord._info = FakeInfo()

    # Record what _prompt_dead_accounts was called with
    prompted_dead = []

    def fake_prompt(dead: list[dict]):
        prompted_dead.append(dead[:])  # copy the list

    coord._prompt_dead_accounts = fake_prompt

    # Drain the check queue
    coord._on_checks_drained()

    # Verify: the prompt got only the check's dead account
    assert len(prompted_dead) == 1
    assert prompted_dead[0] == [{"steamid": "check_dead", "name": "Check Dead"}]
    # And the rank sweep's dead account is still in _cs2_dead
    assert coord._cs2_dead == [{"steamid": "rank_dead", "name": "Rank Dead"}]
    # And check_dead was cleared
    assert coord._check_dead == []


def test_check_accounts_queues_cards_and_tracks_batch_progress():
    """check_accounts marks newly-enqueued cards "queued" and tracks batch
    progress; _on_check_started/_on_check_finished/_on_checks_drained drive the
    per-card state and the status-bar text."""
    from warestore.presentation.account_manager.features.accounts.coordinator import (
        AccountCoordinator,
    )

    class FakeCard:
        def __init__(self, acc):
            self.acc = acc
            self.state = "idle"

        def set_check_state(self, state):
            self.state = state

    accounts = [
        {"steamid": "a", "account_name": "Alice"},
        {"steamid": "b", "account_name": "Bob"},
    ]
    cards = {acc["steamid"]: FakeCard(acc) for acc in accounts}

    class FakeGrid:
        def cards(self):
            return list(cards.values())

    class FakeCtrl:
        def saved_token_entry(self, sid):
            return {"token": "tok"}

    class FakeWorker:
        def __init__(self):
            self.enqueued = []

        def enqueue(self, steam_ids):
            self.enqueued.append(list(steam_ids))
            return len(steam_ids)

    class FakeInfo:
        text = ""

        def setText(self, text):
            self.text = text

    coord = AccountCoordinator.__new__(AccountCoordinator)
    coord._grid = FakeGrid()
    coord._ctrl = FakeCtrl()
    coord._info = FakeInfo()
    coord._check_worker = FakeWorker()
    coord._check_names = {}
    coord._check_stats = {"done": 0, "pending": 0, "dead": 0, "failed": 0}
    coord._check_dead = []
    coord._check_pending_ids = set()
    coord._check_batch_total = 0
    coord._check_batch_done = 0
    coord.apply_card_metadata = lambda: None
    coord._prompt_dead_accounts = lambda dead: None

    coord.check_accounts(accounts)

    assert cards["a"].state == "queued"
    assert cards["b"].state == "queued"
    assert coord._check_pending_ids == {"a", "b"}
    assert coord._check_batch_total == 2

    coord._on_check_started("a")
    assert cards["a"].state == "checking"
    assert coord._info.text == "Checking 1/2 — Alice…"

    coord._on_check_finished("a", None)
    assert cards["a"].state == "idle"
    assert "a" not in coord._check_pending_ids

    coord._on_check_started("b")
    assert coord._info.text == "Checking 2/2 — Bob…"

    coord._on_check_finished("b", None)
    assert cards["b"].state == "idle"

    coord._on_checks_drained()
    assert coord._check_batch_total == 0
    assert coord._check_batch_done == 0
    assert coord._check_pending_ids == set()


def test_check_accounts_single_account_status_has_no_counter():
    from warestore.presentation.account_manager.features.accounts.coordinator import (
        AccountCoordinator,
    )

    class FakeCard:
        def __init__(self, acc):
            self.acc = acc
            self.state = "idle"

        def set_check_state(self, state):
            self.state = state

    acc = {"steamid": "a", "account_name": "Alice"}
    card = FakeCard(acc)

    class FakeGrid:
        def cards(self):
            return [card]

    class FakeCtrl:
        def saved_token_entry(self, sid):
            return {"token": "tok"}

    class FakeWorker:
        def enqueue(self, steam_ids):
            return len(steam_ids)

    class FakeInfo:
        text = ""

        def setText(self, text):
            self.text = text

    coord = AccountCoordinator.__new__(AccountCoordinator)
    coord._grid = FakeGrid()
    coord._ctrl = FakeCtrl()
    coord._info = FakeInfo()
    coord._check_worker = FakeWorker()
    coord._check_names = {}
    coord._check_stats = {"done": 0, "pending": 0, "dead": 0, "failed": 0}
    coord._check_dead = []
    coord._check_pending_ids = set()
    coord._check_batch_total = 0
    coord._check_batch_done = 0
    coord.apply_card_metadata = lambda: None

    coord.check_accounts([acc])
    coord._on_check_started("a")
    assert coord._info.text == "Checking Alice…"
