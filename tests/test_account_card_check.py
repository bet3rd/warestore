import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication

from warestore.application.account_manager.view_models import (
    AccountCardMenuState,
    AccountCardViewState,
)
from warestore.presentation.account_manager.ui.accounts.account_card import AccountCard, format_ago


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def _state(**kw):
    menu = AccountCardMenuState(username="alice", steam_id="76561198000000001", saved_token="",
                                has_saved_token=False, has_cooldown=False)
    return AccountCardViewState(jwt_expires_in=3600, cooldown_label="", menu=menu, **kw)


def _card():
    return AccountCard({"steamid": "76561198000000001", "account_name": "alice"}, QPixmap(1, 1))


def test_format_ago():
    assert format_ago(1000, 1030) == "just now"
    assert format_ago(1000, 1000 + 180) == "3m ago"
    assert format_ago(1000, 1000 + 7200) == "2h ago"
    assert format_ago(1000, 1000 + 3 * 86400) == "3d ago"


def test_tooltip_shows_cs2_level_and_last_check(_app):
    card = _card()
    card.set_view_state(_state(cs2_level=6, last_check=1, last_check_summary="Workshop −3"))
    tip = card.toolTip()
    assert "CS2 level" in tip and ">6<" in tip
    assert "Workshop −3" in tip


def test_tooltip_shows_pending_and_checking(_app):
    card = _card()
    card.set_view_state(_state(check_pending=True))
    assert "Check pending" in card.toolTip()
    card.set_checking(True)
    assert "Checking…" in card.toolTip()
    card.set_checking(False)
    assert "Checking…" not in card.toolTip()
