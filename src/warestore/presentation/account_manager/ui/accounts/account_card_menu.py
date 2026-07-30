# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import webbrowser

from PyQt5.QtCore import QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QMenu

from warestore.application.account_manager.view_models import AccountCardMenuState

COLOR_CHOICES: tuple[tuple[str, str], ...] = (
    ("None", ""),
    ("Red", "#cc4444"),
    ("Amber", "#d4a017"),
    ("Green", "#5ba85e"),
    ("Blue", "#4a9eda"),
    ("Purple", "#9b59b6"),
    ("Gray", "#888888"),
)


def _color_dot(hex_value: str) -> QIcon:
    """A small filled dot of the tag colour (hollow ring for the 'None' choice)."""
    ratio = 2
    size = 16
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(ratio)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    rect = QRectF(4, 4, 8, 8)
    if hex_value:
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(hex_value))
    else:
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(QColor("#777777"), 1.2))
    painter.drawEllipse(rect)
    painter.end()
    return QIcon(pm)


def show_account_card_menu(
    *,
    parent,
    account: dict,
    menu_state: AccountCardMenuState,
    targets: list[dict],
    export_count: int,
    global_pos,
    on_switch,
    on_relogin,
    on_copy_export,
    on_export_file,
    on_delete,
    on_cooldown_set,
    on_cooldown_custom,
    on_color_set,
    on_cs2_source_set=None,
    on_cs2_apply=None,
    on_reset_hwid=None,
    has_hwid_profile: bool = False,
) -> None:
    multi = len(targets) > 1
    token_available = menu_state.has_saved_token
    username = menu_state.username
    steam_id = menu_state.steam_id

    menu = QMenu(parent)
    if multi:
        menu.addAction(f"{len(targets)} accounts selected").setEnabled(False)
        menu.addSeparator()

    act_switch = menu.addAction("Switch account")
    act_switch.setEnabled(not multi)
    act_relogin = menu.addAction("Re-login with saved token")
    act_relogin.setEnabled(token_available and not multi)
    menu.addSeparator()
    act_copy_user = menu.addAction("Copy username")
    act_copy_user.setEnabled(not multi and bool(username))
    act_copy = menu.addAction("Copy token")
    act_copy.setEnabled(token_available and not multi)
    menu.addSeparator()
    act_copy_export = menu.addAction(
        f"Export {export_count} tokens to clipboard"
        if export_count != 1
        else "Export token to clipboard"
    )
    act_copy_export.setEnabled(export_count > 0)
    act_export_file = menu.addAction(
        f"Export {export_count} tokens to file…"
        if export_count != 1
        else "Export token to file…"
    )
    act_export_file.setEnabled(export_count > 0)
    menu.addSeparator()
    act_profile = menu.addAction("Open Steam Profile")
    act_profile.setEnabled(not multi and bool(steam_id))
    menu.addSeparator()

    color_menu = menu.addMenu(f"Color tag ({len(targets)})" if multi else "Color tag")
    for label, value in COLOR_CHOICES:
        act = color_menu.addAction(label)
        act.setIcon(_color_dot(value))
        act.setCheckable(True)
        act.setChecked(not multi and menu_state.color == value)
        act.triggered.connect(
            lambda _checked=False, v=value: on_color_set(targets, v)
        )

    act_cs2_source = None
    act_cs2_apply = None
    if on_cs2_source_set is not None or on_cs2_apply is not None:
        cs2_menu = menu.addMenu(f"CS2 Config ({len(targets)})" if multi else "CS2 Config")
        if on_cs2_source_set is not None:
            act_cs2_source = cs2_menu.addAction("Set Account as Source")
            act_cs2_source.setCheckable(True)
            act_cs2_source.setChecked(not multi and menu_state.is_cs2_source)
            # Designating a source is a single-account action.
            act_cs2_source.setEnabled(not multi and bool(steam_id))
        if on_cs2_apply is not None:
            act_cs2_apply = cs2_menu.addAction(
                f"Override Config ({len(targets)})" if multi else "Override Config"
            )
            # Needs a source set, and overriding the source with itself is a no-op.
            can_override = menu_state.has_cs2_source and not (
                not multi and menu_state.is_cs2_source
            )
            act_cs2_apply.setEnabled(can_override)

    menu.addSeparator()

    cooldown_menu = menu.addMenu(f"Cooldown ({len(targets)})" if multi else "Cooldown")
    for label, seconds in menu_state.cooldown_presets:
        act = cooldown_menu.addAction(label)
        act.triggered.connect(
            lambda _checked=False, s=seconds: on_cooldown_set(targets, s)
        )
    act_custom = cooldown_menu.addAction("Custom…")
    act_custom.triggered.connect(lambda _checked=False: on_cooldown_custom(targets))
    if menu_state.has_cooldown and not multi:
        cooldown_menu.addSeparator()
        act_clear = cooldown_menu.addAction("Clear cooldown")
        act_clear.triggered.connect(lambda _checked=False: on_cooldown_set(targets, 0))
    elif multi:
        cooldown_menu.addSeparator()
        act_clear = cooldown_menu.addAction("Clear cooldown")
        act_clear.triggered.connect(lambda _checked=False: on_cooldown_set(targets, 0))

    if on_reset_hwid and not multi:
        menu.addSeparator()
        act_reset_hwid = menu.addAction(
            "Reset HWID" if has_hwid_profile else "Reset HWID (no profile)"
        )
        act_reset_hwid.setEnabled(has_hwid_profile)
    else:
        act_reset_hwid = None

    menu.addSeparator()
    act_delete = menu.addAction(
        f"Delete {len(targets)} accounts" if multi else "Delete account"
    )

    chosen = menu.exec_(global_pos)
    if chosen == act_switch and not multi:
        on_switch(account)
    elif chosen == act_relogin and token_available and not multi:
        on_relogin(account)
    elif chosen == act_copy_user and username and not multi:
        QApplication.clipboard().setText(username)
    elif chosen == act_copy and token_available and not multi:
        token = menu_state.saved_token
        if token:
            QApplication.clipboard().setText(token)
    elif chosen == act_copy_export and export_count > 0:
        on_copy_export(targets)
    elif chosen == act_export_file and export_count > 0:
        on_export_file(targets)
    elif chosen == act_profile and steam_id and not multi:
        webbrowser.open(f"https://steamcommunity.com/profiles/{steam_id}")
    elif act_cs2_source is not None and chosen == act_cs2_source and not multi and steam_id:
        on_cs2_source_set(account)
    elif act_cs2_apply is not None and chosen == act_cs2_apply:
        on_cs2_apply(targets)
    elif chosen == act_reset_hwid and on_reset_hwid and not multi:
        on_reset_hwid(account)
    elif chosen == act_delete:
        on_delete(targets)
