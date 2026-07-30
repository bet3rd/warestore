# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtWidgets import QMenu

from warestore.presentation.account_manager.ui.accounts.account_card_menu import (
    COLOR_CHOICES,
)


class _StayOpenMenu(QMenu):
    """A QMenu that keeps itself open when a checkable item is toggled, so the
    user can flip several filters in one visit. Non-checkable items (e.g. the
    Clear action) close it normally."""

    def mouseReleaseEvent(self, event):
        action = self.activeAction()
        if action is not None and action.isEnabled() and action.isCheckable():
            action.trigger()  # toggles + emits, without closing the menu
            return
        super().mouseReleaseEvent(event)


def show_account_filter_menu(*, parent, global_pos, state: dict, on_change) -> None:
    """Show the accounts filter popup.

    `state` is a live dict {"colors": set[str], "no_cooldown": bool,
    "no_bans": bool} that this menu mutates in place; `on_change(state)` is
    invoked after every toggle so the grid can re-filter immediately.
    """
    menu = _StayOpenMenu(parent)
    header = menu.addAction("Filter by")
    header.setEnabled(False)
    menu.addSeparator()

    def _any_active() -> bool:
        return bool(state["colors"] or state["no_cooldown"] or state["no_bans"])

    def _changed() -> None:
        # Keep the Clear item in sync without waiting for the menu to reopen.
        act_clear.setEnabled(_any_active())
        on_change(state)

    for label, value in COLOR_CHOICES:
        text = "Untagged" if value == "" else label
        act = menu.addAction(text)
        act.setCheckable(True)
        act.setChecked(value in state["colors"])

        def _toggle_color(checked, v=value):
            if checked:
                state["colors"].add(v)
            else:
                state["colors"].discard(v)
            _changed()

        act.toggled.connect(_toggle_color)

    menu.addSeparator()

    act_cd = menu.addAction("No cooldown")
    act_cd.setCheckable(True)
    act_cd.setChecked(state["no_cooldown"])

    def _toggle_cd(checked):
        state["no_cooldown"] = checked
        _changed()

    act_cd.toggled.connect(_toggle_cd)

    act_bans = menu.addAction("No bans")
    act_bans.setCheckable(True)
    act_bans.setChecked(state["no_bans"])

    def _toggle_bans(checked):
        state["no_bans"] = checked
        _changed()

    act_bans.toggled.connect(_toggle_bans)

    menu.addSeparator()
    act_clear = menu.addAction("Clear filters")

    def _clear():
        state["colors"].clear()
        state["no_cooldown"] = False
        state["no_bans"] = False
        _changed()

    act_clear.triggered.connect(_clear)
    act_clear.setEnabled(_any_active())

    menu.exec_(global_pos)
