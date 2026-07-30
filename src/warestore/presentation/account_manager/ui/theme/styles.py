# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import ctypes
import sys
from pathlib import Path


def _qss_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / (
            "warestore/presentation/account_manager/ui/theme/qss"
        )
    return Path(__file__).resolve().parent / "qss"


_QSS_FILES = ("base.qss", "dialogs.qss", "window.qss")


def _load_qss() -> str:
    qss_dir = _qss_dir()
    parts: list[str] = []
    for name in _QSS_FILES:
        parts.append(qss_dir.joinpath(name).read_text(encoding="utf-8").strip())
    return "\n\n".join(parts) + "\n"


QSS = _load_qss()


def project_root() -> Path:
    return Path(__file__).resolve().parents[6]


def ensure_app_icon_file() -> Path:
    """Create assets/warestore.ico when missing (dev + PyInstaller bundle)."""
    assets_dir = project_root() / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)
    icon_path = assets_dir / "warestore.ico"
    if icon_path.exists():
        return icon_path

    from PyQt5.QtCore import Qt
    from PyQt5.QtGui import QColor, QFont, QIcon, QPainter, QPixmap

    size = 64
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor("#880808"))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(4, 4, size - 8, size - 8, 12, 12)
    painter.setPen(QColor("#ffffff"))
    painter.setFont(QFont("Segoe UI", 30, QFont.Bold))
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "W")
    painter.end()
    if not pixmap.save(str(icon_path), "ICO"):
        raise OSError(f"Failed to write icon: {icon_path}")
    return icon_path


def app_icon_path() -> str:
    import sys

    if getattr(sys, "frozen", False):
        bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        for base in (bundle / "assets", Path(sys.executable).parent):
            candidate = base / "warestore.ico"
            if candidate.exists():
                return str(candidate)

    return str(ensure_app_icon_file())


def app_icon() -> "QIcon":
    from PyQt5.QtGui import QIcon

    path = app_icon_path()
    icon = QIcon(path)
    return icon if not icon.isNull() else QIcon()


def enable_dark_title_bar(hwnd: int) -> None:
    try:
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd,
            20,
            ctypes.byref(ctypes.c_int(1)),
            ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass
