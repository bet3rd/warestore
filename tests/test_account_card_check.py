import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QAbstractAnimation
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import QApplication, QGraphicsOpacityEffect

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


def test_set_premier_leaves_cooldown_untouched(_app):
    card = _card()
    card.set_cs2_rank(15_000, 5, 1_234, 30, 2)
    card.set_premier(16_000, 31)
    assert card._premier_rating == 16_000 and card._premier_wins == 31
    assert card._cs2_cooldown_expires == 1_234
    assert card._wingman_rank == 5 and card._wingman_wins == 2


def test_set_cs2_cooldown_leaves_premier_untouched(_app):
    card = _card()
    card.set_cs2_rank(15_000, 5, 1_234, 30, 2)
    card.set_cs2_cooldown(9_999)
    assert card._cs2_cooldown_expires == 9_999
    assert card._premier_rating == 15_000 and card._premier_wins == 30
    assert card._wingman_rank == 5 and card._wingman_wins == 2


def test_set_check_update_only_applies_values_that_arrived(_app):
    card = _card()
    card.set_cs2_rank(15_000, 5, 1_234, 30, 2)
    # Only Wingman arrived this check — Premier and cooldown stay as they were.
    card.set_check_update(wingman_rank=7, wingman_wins=9)
    assert card._wingman_rank == 7 and card._wingman_wins == 9
    assert card._premier_rating == 15_000 and card._premier_wins == 30
    assert card._cs2_cooldown_expires == 1_234


def test_set_check_update_with_nothing_arrived_is_a_no_op(_app):
    card = _card()
    card.set_cs2_rank(15_000, 5, 1_234, 30, 2)
    card.set_check_update()
    assert (card._premier_rating, card._premier_wins) == (15_000, 30)
    assert (card._wingman_rank, card._wingman_wins) == (5, 2)
    assert card._cs2_cooldown_expires == 1_234


def test_check_state_checking_starts_and_stops_the_spinner(_app):
    card = _card()
    card.set_check_state("checking")
    assert card._spin_anim is not None
    assert card._spin_anim.state() == QAbstractAnimation.Running
    card.set_check_state("idle")
    assert card._spin_anim.state() == QAbstractAnimation.Stopped


def test_check_state_queued_dims_the_card_and_idle_undims(_app):
    card = _card()
    card.set_check_state("queued")
    eff = card.graphicsEffect()
    assert isinstance(eff, QGraphicsOpacityEffect)
    assert abs(eff.opacity() - 0.6) < 1e-6
    card.set_check_state("idle")
    assert card.graphicsEffect() is None


def test_check_state_tooltip_rows(_app):
    card = _card()
    card.set_check_state("queued")
    assert "Queued…" in card.toolTip()
    card.set_check_state("checking")
    assert "Checking…" in card.toolTip()
    assert "Queued…" not in card.toolTip()
    card.set_check_state("idle")
    assert "Checking…" not in card.toolTip()
    assert "Queued…" not in card.toolTip()


def test_set_checking_wrapper_still_works(_app):
    card = _card()
    card.set_checking(True)
    assert card._check_state == "checking"
    assert "Checking…" in card.toolTip()
    card.set_checking(False)
    assert card._check_state == "idle"
    assert "Checking…" not in card.toolTip()


def test_check_ring_renders_without_raising_in_every_state(_app):
    card = _card()
    for state in ("idle", "queued", "checking", "idle"):
        card.set_check_state(state)
        card.grab()
