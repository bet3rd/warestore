import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtWidgets import QApplication, QMenu

from warestore.application.account_manager.view_models import AccountCardMenuState
from warestore.presentation.account_manager.ui.accounts import account_card_menu


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def _layout(menu):
    out = []
    for act in menu.actions():
        if act.isSeparator():
            out.append("-")
        elif act.menu() is not None:
            out.append((act.text(), _layout(act.menu())))
        else:
            out.append(act.text())
    return out


def _open_menu(monkeypatch, **kw):
    seen = {}

    def fake_exec(self, *_a):
        seen["layout"] = _layout(self)
        return None

    monkeypatch.setattr(QMenu, "exec_", fake_exec)
    state = AccountCardMenuState(
        username="alice", steam_id="76561198000000001", saved_token="tok",
        has_saved_token=True, has_cooldown=False, has_cs2_source=True,
    )
    noop = lambda *a, **k: None  # noqa: E731
    account_card_menu.show_account_card_menu(
        parent=None, account={"steamid": "76561198000000001"}, menu_state=state,
        targets=[{"steamid": "76561198000000001"}], export_count=1, global_pos=None,
        on_switch=noop, on_relogin=noop, on_copy_export=noop, on_export_file=noop,
        on_delete=noop, on_cooldown_set=noop, on_cooldown_custom=noop, on_color_set=noop,
        on_cs2_source_set=noop, on_cs2_apply=noop, on_reset_hwid=noop,
        on_refresh_stats=noop, on_check=noop, **kw,
    )
    return seen["layout"]


def test_top_level_is_compact(_app, monkeypatch):
    top = [item if isinstance(item, str) else item[0] for item in _open_menu(monkeypatch)]
    assert top == [
        "Switch account", "Re-login with saved token", "-",
        "Copy", "Open Steam Profile", "-",
        "CS2", "Color tag", "Cooldown", "-",
        "Reset HWID (no profile)", "Delete account",
    ]


def test_copy_and_cs2_submenus(_app, monkeypatch):
    subs = {item[0]: item[1] for item in _open_menu(monkeypatch) if isinstance(item, tuple)}
    assert subs["Copy"] == [
        "Username", "Friend code", "-", "Export token to clipboard", "Export token to file…",
    ]
    assert subs["CS2"] == [
        "Check account", "Refresh stats", "-", "Set as config source", "Override config + loadout",
    ]
