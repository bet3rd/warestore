# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QFont, QPalette
from PyQt5.QtWidgets import QApplication

from warestore.infrastructure.persistence import SettingsRepository
from warestore.presentation.account_manager.support.app_log import app_log
from warestore.presentation.account_manager.support.logging_setup import configure_logging
from warestore.presentation.account_manager.support.single_instance import (
    acquire_single_instance_lock,
    activate_existing_instance,
)
from warestore.presentation.account_manager.support.vault_unlock import setup_or_unlock_vault
from warestore.presentation.account_manager.ui.theme import QSS, app_icon
from warestore.application.account_manager.bootstrap import create_account_manager_app
from warestore.presentation.account_manager.window import MainWindow


def _make_streams_unicode_safe() -> None:
    """Windows consoles/pipes default to cp1252, but log lines contain arrows
    (→) and other non-Latin-1 glyphs. Reconfigure the real streams to escape
    un-encodable characters instead of raising UnicodeEncodeError when logs are
    mirrored to the terminal. sys.__stdout__ is the same object, so the logging
    console handler benefits too. No-op when there's no console (frozen build).
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


class _TeeStdout:
    def __init__(self, original):
        self._original = original

    def write(self, data: str) -> None:
        if self._original is not None:
            try:
                self._original.write(data)
            except UnicodeEncodeError:
                # Last-resort guard if the underlying stream couldn't be made
                # lenient; never let a log line crash the app.
                self._original.write(data.encode("ascii", "backslashreplace").decode("ascii"))
        if data and data.strip():
            for line in data.splitlines():
                if line.strip():
                    app_log.append(line)

    def flush(self) -> None:
        if self._original is not None:
            self._original.flush()


def _dark_palette() -> QPalette:
    """Dark base palette for Fusion.

    The QSS styles the main window and the custom #warestore_dialog, but native
    dialogs (QMessageBox / QInputDialog) and tooltips fall through to the palette.
    Without this they render on Fusion's default light background. This keeps any
    QSS-uncovered widget dark instead of white.
    """
    pal = QPalette()
    window = QColor("#141414")
    base = QColor("#1e1e1e")
    text = QColor("#e0e0e0")
    disabled = QColor("#555555")

    pal.setColor(QPalette.Window, window)
    pal.setColor(QPalette.WindowText, text)
    pal.setColor(QPalette.Base, base)
    pal.setColor(QPalette.AlternateBase, QColor("#1a1a1a"))
    pal.setColor(QPalette.ToolTipBase, base)
    pal.setColor(QPalette.ToolTipText, text)
    pal.setColor(QPalette.Text, text)
    pal.setColor(QPalette.Button, base)
    pal.setColor(QPalette.ButtonText, text)
    pal.setColor(QPalette.BrightText, QColor("#ffffff"))
    pal.setColor(QPalette.Highlight, QColor("#880808"))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))

    for role in (QPalette.WindowText, QPalette.Text, QPalette.ButtonText):
        pal.setColor(QPalette.Disabled, role, disabled)

    return pal


def _apply_interface_scale() -> None:
    """Set QT_SCALE_FACTOR from the saved interface scale BEFORE QApplication is
    created — Qt only reads it at construction, so a scale change needs a restart
    (surfaced in Settings). 100 (%) is the default and applies no scaling."""
    try:
        scale = int(SettingsRepository().load().get("dpi_scale", 100))
    except (Exception, ValueError, TypeError):  # noqa: BLE001 - never block startup
        return
    if scale > 0 and scale != 100:
        os.environ["QT_SCALE_FACTOR"] = str(scale / 100)


def main() -> None:
    _make_streams_unicode_safe()
    # Atomic single-instance gate — taken before any UI (including the vault
    # dialog) so two launches fired in quick succession can't both slip past.
    # If the lock is held, another instance is running: ask it to surface its
    # window (best effort), then exit.
    if not acquire_single_instance_lock():
        activate_existing_instance()
        return

    _apply_interface_scale()
    # Qt5 ignores a pixmap's devicePixelRatio in QIcon/QPixmap/QLabel unless this
    # is on (it's off by default) — without it every DPR-tagged icon/avatar is
    # treated as 1x and upscaled (blurry) when the interface is scaled. Must be
    # set before the QApplication is constructed.
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setPalette(_dark_palette())
    app.setStyleSheet(QSS)
    app.setFont(QFont("Segoe UI", 10))
    app.setQuitOnLastWindowClosed(False)

    sys.stdout = _TeeStdout(sys.stdout)
    sys.stderr = _TeeStdout(sys.stderr)
    # After the tee is installed: the logging console handler targets the real
    # sys.__stdout__, so records reach the terminal without being re-appended to
    # app_log (the tee feeds app_log too, which would double each line).
    configure_logging()

    app.setWindowIcon(app_icon())

    # First-launch choice / per-launch unlock for the token vault. Runs before
    # the app is built because the token repository needs the key up front.
    vault_key = setup_or_unlock_vault(SettingsRepository())

    app_bundle = create_account_manager_app(vault_key=vault_key)
    win = MainWindow(app_bundle)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
