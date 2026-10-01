import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

from warestore.presentation.account_manager.features.accounts.coordinator import (
    AccountCoordinator,
)

SOURCE = "76561198000000001"
OTHER = "76561198000000002"


class FakeCtrl:
    def __init__(self, tokens):
        self.tokens = tokens
        self.saved = []

    def saved_token_entry(self, sid):
        return {"token": "t"} if sid in self.tokens else {}

    def save_settings(self, settings):
        self.saved.append(dict(settings))


def _coord(*, source=SOURCE, tokens=(), grid_sids=(), cache=None):
    coord = AccountCoordinator.__new__(AccountCoordinator)
    coord._settings = {"cs2_config_source_sid": source}
    coord._ctrl = FakeCtrl(set(tokens))
    coord._grid = SimpleNamespace(steam_ids=lambda: list(grid_sids))
    coord._status_cache = dict(cache or {})
    return coord


def test_deleted_source_is_cleared():
    coord = _coord(tokens={OTHER})
    assert coord._forget_deleted_source({OTHER}) is True
    assert coord._settings["cs2_config_source_sid"] == ""
    assert coord._ctrl.saved[-1]["cs2_config_source_sid"] == ""


def test_source_still_listed_is_kept():
    coord = _coord(tokens=set())
    assert coord._forget_deleted_source({SOURCE}) is False
    assert coord._settings["cs2_config_source_sid"] == SOURCE


def test_source_with_a_saved_token_is_kept():
    # Not in Steam's login list right now, but still in the manager (token saved).
    coord = _coord(tokens={SOURCE})
    assert coord._forget_deleted_source(set()) is False
    assert coord._settings["cs2_config_source_sid"] == SOURCE


def test_no_source_set_is_a_no_op():
    coord = _coord(source="")
    assert coord._forget_deleted_source(set()) is False
    assert coord._ctrl.saved == []


def test_reload_only_fetches_accounts_without_cached_status():
    coord = _coord(grid_sids=[SOURCE, OTHER], cache={SOURCE: {"state": 1}})
    assert coord._status_targets(full=False) == [OTHER]


def test_full_refresh_fetches_every_account():
    coord = _coord(grid_sids=[SOURCE, OTHER], cache={SOURCE: {"state": 1}})
    assert coord._status_targets(full=True) == [SOURCE, OTHER]
