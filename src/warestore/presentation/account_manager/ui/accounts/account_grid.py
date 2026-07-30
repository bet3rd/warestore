# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QGridLayout, QWidget

from warestore.application.account_manager.view_models import AccountCardViewState
from warestore.presentation.account_manager.ui.accounts.account_card import AccountCard
from warestore.presentation.account_manager.ui.avatars import (
    AVATAR_SIZE,
    load_avatar_pixmap,
    make_placeholder_pixmap,
)


class AccountGrid(QWidget):
    COLS = 5
    GAP = 8

    @classmethod
    def content_width(cls) -> int:
        return cls.COLS * AccountCard.CARD_W + (cls.COLS - 1) * cls.GAP

    @classmethod
    def height_for_rows(cls, row_count: int) -> int:
        rows = max(1, row_count)
        margins = 18
        return rows * AccountCard.CARD_H + (rows - 1) * cls.GAP + margins

    account_selected = pyqtSignal(object)
    account_double_clicked = pyqtSignal(object)
    delete_requested = pyqtSignal(object)
    relogin_requested = pyqtSignal(object)
    export_copy_requested = pyqtSignal(object)
    export_file_requested = pyqtSignal(object)
    cooldown_set_requested = pyqtSignal(object, int)
    cooldown_custom_requested = pyqtSignal(object)
    color_set_requested = pyqtSignal(object, str)
    cs2_source_set_requested = pyqtSignal(object)
    cs2_apply_requested = pyqtSignal(object)
    hwid_reset_requested = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setFocusPolicy(Qt.StrongFocus)

        self._grid = QGridLayout(self)
        self._grid.setContentsMargins(0, 2, 0, 16)
        self._grid.setSpacing(self.GAP)
        self._grid.setAlignment(Qt.AlignTop | Qt.AlignLeft)

        self._cards: list[AccountCard] = []
        self._selected_sids: set[str] = set()
        self._primary_sid: str | None = None
        self._search_query = ""
        self._filter_colors: set[str] = set()
        self._filter_no_cooldown = False
        self._filter_no_bans = False

    def cards(self) -> list[AccountCard]:
        return list(self._cards)

    def card_count(self) -> int:
        return len(self._cards)

    def steam_ids(self) -> list[str]:
        return [card.acc["steamid"] for card in self._cards if card.acc.get("steamid")]

    def accounts(self) -> list[dict]:
        return [card.acc for card in self._cards]

    def apply_view_states(self, state_for: Callable[[dict], AccountCardViewState]) -> None:
        for card in self._cards:
            card.set_view_state(state_for(card.acc))

    def resolve_menu_targets(self, acc: dict) -> list[dict]:
        sid = acc.get("steamid", "")
        if sid and sid not in self._selected_sids:
            self._select_single(acc)
            return [acc]
        return self.selected_accounts()

    def populate(self, accounts: list[dict], steam_dir: str | None) -> None:
        for card in self._cards:
            card.deleteLater()
        self._cards.clear()
        self._selected_sids.clear()
        self._primary_sid = None

        for i, acc in enumerate(accounts):
            avatar = (
                load_avatar_pixmap(steam_dir, acc["steamid"])
                if steam_dir
                else make_placeholder_pixmap(AVATAR_SIZE)
            )
            card = AccountCard(acc, avatar)
            card.clicked.connect(self._on_click)
            card.double_clicked.connect(self.account_double_clicked)
            card.relogin_requested.connect(self.relogin_requested)
            self._grid.addWidget(card, i // self.COLS, i % self.COLS)
            self._cards.append(card)
        self._resize_to_content()

    def has_active_filters(self) -> bool:
        return bool(self._filter_colors or self._filter_no_cooldown or self._filter_no_bans)

    def _card_matches(self, card: AccountCard) -> bool:
        q = self._search_query.lower().strip()
        if q:
            acc = card.acc
            hay = f"{acc.get('account_name', '')} {acc.get('persona_name', '')}".lower()
            if q not in hay:
                return False
        if self._filter_colors and card.color_tag not in self._filter_colors:
            return False
        if self._filter_no_cooldown and card.is_on_cooldown:
            return False
        if self._filter_no_bans and card.is_banned:
            return False
        return True

    def filtered_cards(self) -> list[AccountCard]:
        if not self._search_query.strip() and not self.has_active_filters():
            return list(self._cards)
        return [card for card in self._cards if self._card_matches(card)]

    def set_filters(
        self, *, colors: set[str], no_cooldown: bool, no_bans: bool
    ) -> None:
        self._filter_colors = set(colors)
        self._filter_no_cooldown = no_cooldown
        self._filter_no_bans = no_bans
        self.reapply_filters()

    def reapply_filters(self) -> None:
        """Re-evaluate visibility for the current search + filter state."""
        self.filter_accounts(self._search_query)

    def _resize_to_content(self) -> None:
        count = max(1, len(self.filtered_cards()) or len(self._cards))
        rows = (count + self.COLS - 1) // self.COLS
        self.setFixedSize(self.content_width(), self.height_for_rows(rows))

    def _relayout_visible(self) -> None:
        visible = self.filtered_cards()
        for card in self._cards:
            self._grid.removeWidget(card)
        for i, card in enumerate(visible):
            self._grid.addWidget(card, i // self.COLS, i % self.COLS)
        self._resize_to_content()

    def filter_accounts(self, query: str) -> None:
        self._search_query = query
        for card in self._cards:
            card.setVisible(self._card_matches(card))
        self._relayout_visible()

    def select_next(self) -> None:
        visible = self.filtered_cards()
        if not visible:
            return
        idx = self._primary_index(visible)
        self._select_single(visible[(idx + 1) % len(visible)].acc)

    def select_prev(self) -> None:
        visible = self.filtered_cards()
        if not visible:
            return
        idx = self._primary_index(visible)
        self._select_single(visible[(idx - 1) % len(visible)].acc)

    def clear_selection(self) -> None:
        self._selected_sids.clear()
        self._primary_sid = None
        self._sync_selection_visuals()
        self.account_selected.emit([])

    def selected_accounts(self) -> list[dict]:
        if not self._selected_sids:
            return []
        by_sid = {card.acc.get("steamid", ""): card.acc for card in self._cards}
        ordered: list[dict] = []
        if self._primary_sid and self._primary_sid in self._selected_sids:
            ordered.append(by_sid[self._primary_sid])
        for sid in self._selected_sids:
            if sid != self._primary_sid and sid in by_sid:
                ordered.append(by_sid[sid])
        return ordered

    def targets_for_action(self, acc: dict) -> list[dict]:
        sid = acc.get("steamid", "")
        if sid and sid in self._selected_sids:
            return self.selected_accounts()
        return [acc]

    def count_with_tokens(self, targets: list[dict]) -> int:
        by_sid = {card.acc.get("steamid", ""): card for card in self._cards}
        count = 0
        for acc in targets:
            card = by_sid.get(acc.get("steamid", ""))
            if card and card.menu_state.has_saved_token:
                count += 1
        return count

    def _primary_index(self, visible: list[AccountCard]) -> int:
        if self._primary_sid:
            for i, card in enumerate(visible):
                if card.acc.get("steamid", "") == self._primary_sid:
                    return i
        return -1

    def _select_single(self, acc: dict) -> None:
        sid = acc.get("steamid", "")
        self._selected_sids = {sid} if sid else set()
        self._primary_sid = sid or None
        self._sync_selection_visuals()
        self.account_selected.emit(self.selected_accounts())

    def _on_click(self, acc: dict, modifiers) -> None:
        sid = acc.get("steamid", "")
        if not sid:
            return

        if modifiers & Qt.ControlModifier:
            if sid in self._selected_sids:
                self._selected_sids.discard(sid)
                if self._primary_sid == sid:
                    self._primary_sid = next(iter(self._selected_sids), None)
            else:
                self._selected_sids.add(sid)
                self._primary_sid = sid
        else:
            self._selected_sids = {sid}
            self._primary_sid = sid

        self._sync_selection_visuals()
        self.account_selected.emit(self.selected_accounts())

    def _sync_selection_visuals(self) -> None:
        for card in self._cards:
            sid = card.acc.get("steamid", "")
            card.set_selected(bool(sid and sid in self._selected_sids))

    def selected_account(self) -> dict | None:
        accounts = self.selected_accounts()
        return accounts[0] if accounts else None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and event.modifiers() == Qt.NoModifier:
            self.clear_selection()
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.clear_selection()
            event.accept()
            return
        super().keyPressEvent(event)

    def setEnabled(self, enabled: bool):
        super().setEnabled(enabled)
        for card in self._cards:
            card.setEnabled(enabled)
