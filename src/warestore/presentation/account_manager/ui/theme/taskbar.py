# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Hide a top-level window's taskbar button (and optionally its Alt+Tab entry).

Taskbar button rules: an unowned window without WS_EX_TOOLWINDOW gets a button.
- "hide": give the window a hidden owner, the same trick WinForms/WPF use for
  ShowInTaskbar=False. No button, but Alt+Tab still lists it.
- "hide_alt_tab": WS_EX_TOOLWINDOW. Gone from both the taskbar and Alt+Tab.

Explorer doesn't re-read these on a visible window, so ITaskbarList DeleteTab /
AddTab updates the button right away. Qt resets the owner on every show, so
callers re-apply after showing (see MainWindow.showEvent).

Refs:
- https://learn.microsoft.com/en-us/windows/win32/shell/taskbar#managing-taskbar-buttons
- https://learn.microsoft.com/en-us/windows/win32/api/shobjidl_core/nn-shobjidl_core-itaskbarlist
"""

from __future__ import annotations

import sys
import uuid
from ctypes import POINTER, WINFUNCTYPE, byref, c_long, c_ssize_t, c_ubyte, c_void_p, wintypes

TASKBAR_SHOW = "show"
TASKBAR_HIDE = "hide"
TASKBAR_HIDE_ALT_TAB = "hide_alt_tab"
TASKBAR_MODES = (TASKBAR_SHOW, TASKBAR_HIDE, TASKBAR_HIDE_ALT_TAB)

# winuser.h
GWL_EXSTYLE = -20
GWLP_HWNDPARENT = -8
GW_OWNER = 4
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_APPWINDOW = 0x00040000
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020

# shobjidl_core.h — ITaskbarList vtable: IUnknown (0-2), HrInit, AddTab, DeleteTab
_CLSID_TASKBAR_LIST = "56FDF344-FD6D-11d0-958A-006097C9A090"
_IID_ITASKBAR_LIST = "56FDF342-FD6D-11d0-958A-006097C9A090"
_VT_RELEASE, _VT_HRINIT, _VT_ADDTAB, _VT_DELETETAB = 2, 3, 4, 5
_CLSCTX_INPROC_SERVER = 0x1
_COINIT_APARTMENTTHREADED = 0x2

_owner_hwnd: int | None = None


def taskbar_mode_available() -> bool:
    return sys.platform == "win32"


def normalize_taskbar_mode(mode) -> str:
    return mode if mode in TASKBAR_MODES else TASKBAR_SHOW


def _user32():
    import ctypes

    lib = ctypes.WinDLL("user32", use_last_error=True)
    # 32-bit user32 has no *LongPtr exports; the plain versions are pointer-sized there.
    get_long = getattr(lib, "GetWindowLongPtrW", lib.GetWindowLongW)
    set_long = getattr(lib, "SetWindowLongPtrW", lib.SetWindowLongW)
    get_long.argtypes = [wintypes.HWND, wintypes.INT]
    get_long.restype = c_ssize_t
    set_long.argtypes = [wintypes.HWND, wintypes.INT, c_ssize_t]
    set_long.restype = c_ssize_t
    lib.get_long, lib.set_long = get_long, set_long
    lib.GetWindow.argtypes = [wintypes.HWND, wintypes.UINT]
    lib.GetWindow.restype = wintypes.HWND
    lib.IsWindow.argtypes = [wintypes.HWND]
    lib.IsWindow.restype = wintypes.BOOL
    lib.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND, wintypes.INT, wintypes.INT,
        wintypes.INT, wintypes.INT, wintypes.UINT,
    ]
    lib.SetWindowPos.restype = wintypes.BOOL
    lib.CreateWindowExW.argtypes = [
        wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
        wintypes.INT, wintypes.INT, wintypes.INT, wintypes.INT,
        wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
    ]
    lib.CreateWindowExW.restype = wintypes.HWND
    return lib


def _hidden_owner(user32) -> int:
    """A never-shown top-level window to own the hidden-button window."""
    global _owner_hwnd
    if _owner_hwnd and user32.IsWindow(_owner_hwnd):
        return _owner_hwnd
    hwnd = user32.CreateWindowExW(0, "STATIC", "", 0, 0, 0, 0, 0, None, None, None, None)
    _owner_hwnd = int(hwnd or 0)
    return _owner_hwnd


def _guid(text: str):
    return (c_ubyte * 16).from_buffer_copy(uuid.UUID(text).bytes_le)


def _taskbar_tab(hwnd: int, *, add: bool) -> bool:
    """ITaskbarList AddTab/DeleteTab — updates the button of a visible window now."""
    import ctypes

    ole32 = ctypes.OleDLL("ole32")
    ole32.CoInitializeEx.restype = c_long
    ole32.CoCreateInstance.restype = c_long
    # Qt's GUI thread is already an STA; S_OK/S_FALSE both need a matching uninit.
    hr_init = ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
    try:
        obj = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(_guid(_CLSID_TASKBAR_LIST)), None, _CLSCTX_INPROC_SERVER,
            byref(_guid(_IID_ITASKBAR_LIST)), byref(obj),
        )
        if hr < 0 or not obj.value:
            return False
        vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents

        def method(index, *argtypes):
            return WINFUNCTYPE(c_long, c_void_p, *argtypes)(vtbl[index])

        try:
            if method(_VT_HRINIT)(obj) < 0:
                return False
            index = _VT_ADDTAB if add else _VT_DELETETAB
            return method(index, wintypes.HWND)(obj, hwnd) >= 0
        finally:
            method(_VT_RELEASE)(obj)
    finally:
        if hr_init in (0, 1):
            ole32.CoUninitialize()


def set_window_taskbar_mode(hwnd: int, mode: str) -> bool:
    """Apply *mode* to *hwnd*. Returns True if anything changed.

    A no-op when the window is already in that state, so it's cheap to call
    on every show/layout pass.
    """
    if not taskbar_mode_available() or hwnd <= 0:
        return False
    mode = normalize_taskbar_mode(mode)
    user32 = _user32()

    ex = user32.get_long(hwnd, GWL_EXSTYLE)
    owner = int(user32.GetWindow(hwnd, GW_OWNER) or 0)
    ours = bool(_owner_hwnd) and owner == _owner_hwnd

    want_owner = mode == TASKBAR_HIDE
    if mode == TASKBAR_HIDE_ALT_TAB:
        new_ex = (ex & ~WS_EX_APPWINDOW) | WS_EX_TOOLWINDOW
    elif mode == TASKBAR_HIDE:
        # WS_EX_APPWINDOW forces a button even on an owned window.
        new_ex = ex & ~(WS_EX_APPWINDOW | WS_EX_TOOLWINDOW)
    else:
        new_ex = ex & ~WS_EX_TOOLWINDOW

    changed = False
    if new_ex != ex:
        user32.set_long(hwnd, GWL_EXSTYLE, new_ex)
        changed = True
    if want_owner and not ours:
        owner_hwnd = _hidden_owner(user32)
        if not owner_hwnd:
            return changed
        user32.set_long(hwnd, GWLP_HWNDPARENT, owner_hwnd)
        changed = True
    elif not want_owner and ours:
        user32.set_long(hwnd, GWLP_HWNDPARENT, 0)
        changed = True

    if not changed:
        return False
    user32.SetWindowPos(
        hwnd, None, 0, 0, 0, 0,
        SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_FRAMECHANGED,
    )
    try:
        _taskbar_tab(hwnd, add=mode == TASKBAR_SHOW)
    except OSError:
        pass
    return True


def schedule_taskbar_mode_for_widget(widget, *, mode: str) -> None:
    """Apply now and re-apply after Qt finishes showing (it resets the owner)."""
    if not taskbar_mode_available():
        return

    def apply() -> None:
        try:
            set_window_taskbar_mode(int(widget.winId()), mode)
        except Exception:
            pass

    apply()
    try:
        from PyQt5.QtCore import QTimer
    except ImportError:
        return
    QTimer.singleShot(0, apply)
    QTimer.singleShot(250, apply)
