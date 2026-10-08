import sys

import pytest

from warestore.infrastructure.persistence.settings_repository import SettingsRepository
from warestore.presentation.account_manager.ui.theme import taskbar
from warestore.presentation.account_manager.ui.theme.taskbar import (
    GW_OWNER,
    GWL_EXSTYLE,
    TASKBAR_HIDE,
    TASKBAR_HIDE_ALT_TAB,
    TASKBAR_SHOW,
    WS_EX_TOOLWINDOW,
    normalize_taskbar_mode,
    set_window_taskbar_mode,
    taskbar_mode_available,
)


def test_taskbar_mode_default_is_show(tmp_path):
    settings = SettingsRepository(str(tmp_path / "settings.json")).load()
    assert settings["taskbar_mode"] == TASKBAR_SHOW


@pytest.mark.parametrize("value", [None, "", "bogus", 1])
def test_normalize_unknown_mode_falls_back_to_show(value):
    assert normalize_taskbar_mode(value) == TASKBAR_SHOW


def test_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert taskbar_mode_available() is False
    assert set_window_taskbar_mode(12345, TASKBAR_HIDE) is False


def test_invalid_hwnd():
    if not taskbar_mode_available():
        return
    assert set_window_taskbar_mode(0, TASKBAR_HIDE) is False


@pytest.fixture
def hidden_hwnd():
    """A never-shown top-level window, so the test doesn't touch the real taskbar."""
    if not taskbar_mode_available():
        pytest.skip("Windows only")
    user32 = taskbar._user32()
    hwnd = int(user32.CreateWindowExW(0, "STATIC", "", 0, 0, 0, 0, 0, None, None, None, None))
    assert hwnd
    yield user32, hwnd
    user32.DestroyWindow(hwnd)


def _state(user32, hwnd):
    tool = bool(user32.get_long(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW)
    owner = int(user32.GetWindow(hwnd, GW_OWNER) or 0)
    return tool, owner


def test_modes_switch_style_and_owner(hidden_hwnd):
    user32, hwnd = hidden_hwnd

    assert set_window_taskbar_mode(hwnd, TASKBAR_SHOW) is False  # already shown
    assert _state(user32, hwnd) == (False, 0)

    assert set_window_taskbar_mode(hwnd, TASKBAR_HIDE) is True
    tool, owner = _state(user32, hwnd)
    assert not tool and owner == taskbar._owner_hwnd
    assert set_window_taskbar_mode(hwnd, TASKBAR_HIDE) is False  # idempotent

    assert set_window_taskbar_mode(hwnd, TASKBAR_HIDE_ALT_TAB) is True
    assert _state(user32, hwnd) == (True, 0)
    assert set_window_taskbar_mode(hwnd, TASKBAR_HIDE_ALT_TAB) is False

    assert set_window_taskbar_mode(hwnd, TASKBAR_SHOW) is True
    assert _state(user32, hwnd) == (False, 0)
