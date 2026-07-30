import sys
from ctypes import addressof, c_int, c_uint, wintypes

from warestore.presentation.account_manager.ui.theme.capture import (
    GWL_EXSTYLE,
    STYLESTRUCT,
    WM_STYLECHANGING,
    WS_EX_LAYERED,
    capture_exclusion_available,
    handle_style_changing_layered_hook,
    install_capture_exclusion_popup_filter,
    set_window_capture_exclusion,
)


def test_capture_exclusion_unavailable_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert capture_exclusion_available() is False
    assert set_window_capture_exclusion(12345, True) is False


def test_capture_exclusion_invalid_hwnd():
    if not capture_exclusion_available():
        return
    assert set_window_capture_exclusion(0, True) is False


def test_style_changing_hook_sets_layered_on_windows():
    if not capture_exclusion_available():
        return

    style = STYLESTRUCT(styleOld=0, styleNew=0)
    msg = wintypes.MSG()
    msg.message = WM_STYLECHANGING
    msg.wParam = GWL_EXSTYLE
    msg.lParam = addressof(style)

    assert handle_style_changing_layered_hook(addressof(msg)) is True
    assert style.styleNew & WS_EX_LAYERED


def test_style_changing_hook_accepts_unsigned_wparam():
    if not capture_exclusion_available():
        return

    style = STYLESTRUCT(styleOld=0, styleNew=0)
    msg = wintypes.MSG()
    msg.message = WM_STYLECHANGING
    msg.wParam = c_uint(GWL_EXSTYLE).value
    msg.lParam = addressof(style)

    assert handle_style_changing_layered_hook(addressof(msg)) is True
    assert style.styleNew & WS_EX_LAYERED


def test_style_changing_hook_ignores_other_messages():
    if not capture_exclusion_available():
        return

    msg = wintypes.MSG()
    msg.message = 0x0001
    assert handle_style_changing_layered_hook(addressof(msg)) is False


def test_popup_filter_skipped_off_windows(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")

    class FakeApp:
        def installEventFilter(self, _filt):
            raise AssertionError("should not install on non-windows")

    assert install_capture_exclusion_popup_filter(FakeApp(), enabled_getter=lambda: True) is None
