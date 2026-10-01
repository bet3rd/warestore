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
    q.set_current(q.pop()[0])  # "a" is running
    assert q.add(["a", "b", "c"]) == 1  # only "c" is new
    assert [q.pop(), q.pop(), q.pop()] == [("b", None), ("c", None), None]


STATS_ONLY = CheckSteps(loadout=False, workshop=False, stats=True)


def test_queue_items_carry_their_steps():
    q = AccountCheckQueue()
    q.add(["a"], STATS_ONLY)
    assert q.pop() == ("a", STATS_ONLY)


def test_queue_upgrades_a_stats_only_item_to_full_when_reenqueued_without_steps():
    q = AccountCheckQueue()
    assert q.add(["a"], STATS_ONLY) == 1
    assert q.add(["a"]) == 0  # already queued — this upgrades it, doesn't re-add it
    assert q.pop() == ("a", None)


def test_queue_never_downgrades_a_full_item_to_stats_only():
    q = AccountCheckQueue()
    assert q.add(["a"]) == 1  # full / settings-based
    assert q.add(["a"], STATS_ONLY) == 0  # must not downgrade it
    assert q.pop() == ("a", None)


class FakeCtrl:
    def __init__(self):
        self.source_reads = 0
        self.checked = []
        self.checked_steps = []
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
        self.checked_steps.append((steam_id, steps))
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


# --- retiring the separate rank fetch: stats-only queue items ---------------


def test_stats_only_steps_reach_check_account():
    ctrl = FakeCtrl()
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["a"], STATS_ONLY)
    worker.run()
    assert ctrl.checked_steps == [("a", STATS_ONLY)]


def test_no_source_read_for_a_stats_only_item_even_with_loadout_on():
    ctrl = FakeCtrl()
    worker = AccountCheckWorker(ctrl)
    worker._queue.add(["a"], STATS_ONLY)
    worker.run()
    assert ctrl.source_reads == 0
    assert ctrl.checked == [("a", "")]


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

        def enqueue(self, steam_ids, steps=None):
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
    coord._check_rate_limited = False
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
        def enqueue(self, steam_ids, steps=None):
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
    coord._check_rate_limited = False
    coord.apply_card_metadata = lambda: None

    coord.check_accounts([acc])
    coord._on_check_started("a")
    assert coord._info.text == "Checking Alice…"


LOADOUT_ONLY = CheckSteps(loadout=True, workshop=False, stats=False)


def test_queue_merges_two_limited_requests_for_the_same_account():
    q = AccountCheckQueue()
    q.add(["a"], STATS_ONLY)
    q.add(["a"], LOADOUT_ONLY)  # e.g. Refresh stats, then Override Config
    assert q.pop() == ("a", CheckSteps(loadout=True, workshop=False, stats=True))


def _menu_coord(settings_steps):
    from warestore.presentation.account_manager.features.accounts.coordinator import (
        AccountCoordinator,
    )

    class Ctrl:
        source = "src"

        def account_check_steps(self):
            return settings_steps

        def saved_token_entry(self, sid):
            return {"token": "tok"} if sid != "notoken" else {}

        def cs2_config_source(self):
            return self.source

        def apply_cs2_config(self, sid):
            return True

    coord = AccountCoordinator.__new__(AccountCoordinator)
    coord._ctrl = Ctrl()
    coord._info = type("Info", (), {"text": "", "setText": lambda self, t: setattr(self, "text", t)})()
    coord.apply_card_metadata = lambda: None
    coord.queued = []
    coord.check_accounts = lambda accounts, steps=None: coord.queued.append(
        ([a["steamid"] for a in accounts], steps))
    return coord




def test_override_config_also_copies_the_loadout():
    coord = _menu_coord(CheckSteps())
    coord.apply_cs2_source([{"steamid": "a"}, {"steamid": "src"}, {"steamid": "notoken"}])
    assert coord.queued == [(["a"], LOADOUT_ONLY)]



@pytest.fixture(autouse=True)
def _no_gap(monkeypatch):
    monkeypatch.setattr(AccountCheckWorker, "CHECK_GAP_SECONDS", 0.0)


def test_queue_clear_drops_everything_and_reports_it():
    q = AccountCheckQueue()
    q.add(["a", "b"])
    assert q.clear() == ["a", "b"] and q.pop() is None


def test_checks_are_spaced_but_not_before_the_first():
    ctrl = FakeCtrl()
    ctrl.loadout_on = False
    worker = AccountCheckWorker(ctrl)
    slept = []
    worker._sleep = slept.append
    worker.CHECK_GAP_SECONDS = 3.0
    worker._queue.add(["a", "b", "c"])
    worker.run()
    assert slept == [3.0, 3.0]


def test_coordinator_stops_the_queue_and_warns_on_a_rate_limit():
    from warestore.presentation.account_manager.features.accounts.coordinator import (
        AccountCoordinator,
    )

    class Card:
        def __init__(self):
            self.acc = {}
            self.state = "queued"

        def set_check_state(self, s):
            self.state = s

    cards = {"a": Card(), "b": Card(), "c": Card()}

    class Worker:
        def clear_pending(self):
            return ["b", "c"]

    coord = AccountCoordinator.__new__(AccountCoordinator)
    coord._card_for = cards.get
    coord._check_worker = Worker()
    coord._check_names = {}
    coord._check_stats = {"done": 0, "pending": 0, "dead": 0, "failed": 0}
    coord._check_dead = []
    coord._check_pending_ids = {"a", "b", "c"}
    coord._check_batch_total = 3
    coord._check_batch_done = 0
    coord._check_rate_limited = False
    coord._info = type("Info", (), {"text": "", "setText": lambda self, t: setattr(self, "text", t)})()
    coord.apply_card_metadata = lambda: None
    warned = []
    coord._warn_rate_limited = lambda: warned.append(1)
    coord._prompt_dead_accounts = lambda dead: None

    coord._on_check_finished("a", CheckResult(steam_id="a", rate_limited=True))
    assert {s: c.state for s, c in cards.items()} == {"a": "idle", "b": "idle", "c": "idle"}
    assert coord._check_pending_ids == set()
    coord._on_checks_drained()
    assert warned == [1]
    assert "VPN" in coord._info.text



def test_check_account_is_a_stats_only_check():
    coord = _menu_coord(CheckSteps(loadout=True, stats=True, workshop=True))
    coord.refresh_stats([{"steamid": "a"}])
    assert coord.queued == [(["a"], STATS_ONLY)]
