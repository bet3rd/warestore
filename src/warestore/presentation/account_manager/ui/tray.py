# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging

from PyQt5.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from warestore.presentation.account_manager.ui.theme import app_icon

logger = logging.getLogger(__name__)

_TRAY_TOOLTIP = "WareStore Account Manager"
_TRAY_TOOLTIP_HIDDEN = "WareStore — running in tray (click to open)"


def notify_cooldown_finished(
    tray: QSystemTrayIcon | None,
    window,
    account_names: list[str],
) -> None:
    if not account_names:
        return
    if len(account_names) == 1:
        body = f"{account_names[0]} is ready to use."
    else:
        body = f"{len(account_names)} accounts ready: {', '.join(account_names[:3])}"
        if len(account_names) > 3:
            body += f" +{len(account_names) - 3} more"

    title = "Cooldown finished"
    if tray is not None and QSystemTrayIcon.supportsMessages():
        tray.showMessage(title, body, QSystemTrayIcon.Information, 6000)
    if window.isVisible():
        window.info_label.setText(body)
    for name in account_names:
        logger.info(f"Cooldown finished: {name}")


def notify_hidden_to_tray(tray: QSystemTrayIcon) -> None:
    tray.setToolTip(_TRAY_TOOLTIP_HIDDEN)
    if QSystemTrayIcon.supportsMessages():
        tray.showMessage(
            "WareStore",
            "Minimized to tray — still running. Use the tray icon to open.",
            QSystemTrayIcon.Information,
            4500,
        )


def restore_tray_tooltip(tray: QSystemTrayIcon) -> None:
    tray.setToolTip(_TRAY_TOOLTIP)


def setup_tray(window) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(window)
    tray.setIcon(app_icon())
    if tray.icon().isNull():
        logger.error("Tray icon unavailable — close will quit the app.")
        return None
    menu = QMenu()
    act_show = menu.addAction("Show WareStore")
    act_show.triggered.connect(window.show)
    act_refresh = menu.addAction("Refresh accounts")
    act_refresh.triggered.connect(window.load_accounts)
    menu.addSeparator()
    act_quit = menu.addAction("Quit")
    act_quit.triggered.connect(QApplication.instance().quit)
    tray.setContextMenu(menu)
    def _on_activated(reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            window.show()
            window.raise_()
            window.activateWindow()

    tray.activated.connect(_on_activated)
    tray.setToolTip(_TRAY_TOOLTIP)
    tray.show()
    return tray
