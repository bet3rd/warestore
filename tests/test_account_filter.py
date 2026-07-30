import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from types import SimpleNamespace

import pytest
from PyQt5.QtWidgets import QApplication

from warestore.presentation.account_manager.ui.accounts.account_grid import AccountGrid

RED = "#cc4444"
BLUE = "#4a9eda"


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def _card(*, name="acct", color="", cooldown=False, banned=False):
    return SimpleNamespace(
        acc={"account_name": name, "persona_name": ""},
        color_tag=color,
        is_on_cooldown=cooldown,
        is_banned=banned,
    )


def test_no_filters_match_all(_app):
    g = AccountGrid()
    assert g.has_active_filters() is False
    assert g._card_matches(_card(name="bob")) is True


def test_color_filter(_app):
    g = AccountGrid()
    g.set_filters(colors={RED}, no_cooldown=False, no_bans=False)
    assert g.has_active_filters() is True
    assert g._card_matches(_card(color=RED)) is True
    assert g._card_matches(_card(color=BLUE)) is False
    assert g._card_matches(_card(color="")) is False


def test_untagged_filter(_app):
    g = AccountGrid()
    g.set_filters(colors={""}, no_cooldown=False, no_bans=False)
    assert g._card_matches(_card(color="")) is True
    assert g._card_matches(_card(color=RED)) is False


def test_no_cooldown_filter(_app):
    g = AccountGrid()
    g.set_filters(colors=set(), no_cooldown=True, no_bans=False)
    assert g._card_matches(_card(cooldown=False)) is True
    assert g._card_matches(_card(cooldown=True)) is False


def test_no_bans_filter(_app):
    g = AccountGrid()
    g.set_filters(colors=set(), no_cooldown=False, no_bans=True)
    assert g._card_matches(_card(banned=False)) is True
    assert g._card_matches(_card(banned=True)) is False


def test_search_and_filters_combine(_app):
    g = AccountGrid()
    g.set_filters(colors={RED}, no_cooldown=False, no_bans=False)
    g._search_query = "bob"
    assert g._card_matches(_card(name="bob", color=RED)) is True
    assert g._card_matches(_card(name="alice", color=RED)) is False  # search excludes
    assert g._card_matches(_card(name="bob", color="")) is False  # colour excludes


def test_clear_via_empty_filters(_app):
    g = AccountGrid()
    g.set_filters(colors={RED}, no_cooldown=True, no_bans=True)
    assert g.has_active_filters() is True
    g.set_filters(colors=set(), no_cooldown=False, no_bans=False)
    assert g.has_active_filters() is False
    assert g._card_matches(_card(color=BLUE, cooldown=True, banned=True)) is True
