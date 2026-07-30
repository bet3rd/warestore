# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Windows screen-capture exclusion via SetWindowDisplayAffinity.

Microsoft documents that UpdateLayeredWindow (Qt WA_TranslucentBackground) conflicts
with SetWindowDisplayAffinity — affinity may appear set but capture still includes the
window. Workaround: avoid UpdateLayeredWindow, use DWM frame extension for transparency,
and keep WS_EX_LAYERED via a WM_STYLECHANGING hook (see Windows.UI.Composition issue #56
and lindexi/Walterlv WPF WindowChrome approach).

Refs:
- https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setwindowdisplayaffinity
- https://github.com/microsoft/Windows.UI.Composition-Win32-Samples/issues/56
"""

from __future__ import annotations

import sys
from ctypes import Structure, c_int, c_ulong, wintypes

# WINDOW_DISPLAY_AFFINITY (winuser.h)
WDA_NONE = 0x00000000
WDA_EXCLUDEFROMCAPTURE = 0x00000011

# winuser.h
WM_STYLECHANGING = 0x007C
GWL_EXSTYLE = -20
WS_EX_LAYERED = 0x00080000


class STYLESTRUCT(Structure):
    _fields_ = [("styleOld", c_ulong), ("styleNew", c_ulong)]


class MARGINS(Structure):
    _fields_ = [
        ("cxLeftWidth", c_int),
        ("cxRightWidth", c_int),
        ("cyTopHeight", c_int),
        ("cyBottomHeight", c_int),
    ]


def capture_exclusion_available() -> bool:
    return sys.platform == "win32"


def _user32():
    import ctypes

    lib = ctypes.WinDLL("user32", use_last_error=True)
    lib.SetWindowDisplayAffinity.argtypes = [wintypes.HWND, wintypes.DWORD]
    lib.SetWindowDisplayAffinity.restype = wintypes.BOOL
    lib.GetWindowDisplayAffinity.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    lib.GetWindowDisplayAffinity.restype = wintypes.BOOL
    return lib


def get_window_capture_exclusion(hwnd: int) -> int | None:
    if not capture_exclusion_available() or hwnd <= 0:
        return None
    import ctypes

    aff = wintypes.DWORD()
    if _user32().GetWindowDisplayAffinity(wintypes.HWND(hwnd), ctypes.byref(aff)):
        return int(aff.value)
    return None


def set_window_capture_exclusion(hwnd: int, exclude: bool = True) -> bool:
    """Exclude *hwnd* from software screen capture (OBS, Discord, Snipping Tool).

    Requires Windows 10 version 2004+ for WDA_EXCLUDEFROMCAPTURE.
    """
    if not capture_exclusion_available() or hwnd <= 0:
        return False

    affinity = WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE
    return bool(_user32().SetWindowDisplayAffinity(wintypes.HWND(hwnd), affinity))


def extend_frame_into_client_area(hwnd: int) -> None:
    """Transparent client via DWM — not UpdateLayeredWindow."""
    if not capture_exclusion_available() or hwnd <= 0:
        return
    try:
        import ctypes

        margins = MARGINS(-1, -1, -1, -1)
        ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd), ctypes.byref(margins))
    except Exception:
        pass


def handle_style_changing_layered_hook(message_address: int) -> bool:
    """Keep WS_EX_LAYERED when Qt/WPF would strip it without AllowsTransparency.

    Call from QWidget.nativeEvent when eventType is b'windows_generic_MSG'.
    Returns True if the message was handled.
    """
    if not capture_exclusion_available():
        return False
    try:
        import ctypes

        msg = ctypes.wintypes.MSG.from_address(message_address)
    except (TypeError, ValueError, OverflowError):
        return False

    if msg.message != WM_STYLECHANGING:
        return False
    if c_int(msg.wParam).value != GWL_EXSTYLE:
        return False

    style = STYLESTRUCT.from_address(msg.lParam)
    style.styleNew |= WS_EX_LAYERED
    return True


def apply_capture_exclusion_for_widget(widget, *, enabled: bool) -> bool:
    """Apply capture exclusion to a QWidget's native window handle."""
    try:
        hwnd = int(widget.winId())
    except Exception:
        return False
    return set_window_capture_exclusion(hwnd, exclude=enabled)


def schedule_capture_exclusion_for_widget(widget, *, enabled: bool) -> None:
    """Apply now and re-apply after Qt finishes window creation / flag changes."""
    if sys.platform == "win32":
        try:
            extend_frame_into_client_area(int(widget.winId()))
        except Exception:
            pass
    apply_capture_exclusion_for_widget(widget, enabled=enabled)
    if not capture_exclusion_available():
        return
    try:
        from PyQt5.QtCore import QTimer
    except ImportError:
        return

    def reapply() -> None:
        if sys.platform == "win32":
            try:
                extend_frame_into_client_area(int(widget.winId()))
            except Exception:
                pass
        apply_capture_exclusion_for_widget(widget, enabled=enabled)

    QTimer.singleShot(0, reapply)
    QTimer.singleShot(250, reapply)


def install_capture_exclusion_popup_filter(app, *, enabled_getter) -> object | None:
    """Exclude QMenu popups (separate HWNDs) from screen capture when shown."""
    if not capture_exclusion_available():
        return None
    try:
        from PyQt5.QtCore import QEvent, QObject
        from PyQt5.QtWidgets import QMenu
    except ImportError:
        return None

    class _CaptureExclusionPopupFilter(QObject):
        def eventFilter(self, obj, event):
            if event.type() == QEvent.Show and isinstance(obj, QMenu):
                schedule_capture_exclusion_for_widget(obj, enabled=bool(enabled_getter()))
            return super().eventFilter(obj, event)

    filt = _CaptureExclusionPopupFilter()
    app.installEventFilter(filt)
    return filt
