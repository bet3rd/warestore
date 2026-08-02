# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QBrush, QColor, QIcon, QPainter, QPen, QPixmap, QPolygonF
from PyQt5.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from warestore.presentation.account_manager.ui.accounts import AccountGrid
from warestore.presentation.account_manager.ui.chrome import HeaderBar
from warestore.presentation.account_manager.ui.section import SectionLabel


def _rank_bars_icon() -> QIcon:
    """Ascending leaderboard bars — the 'fetch CS2 ranks for all accounts' button."""
    ratio = 2  # 2x supersample; AA_UseHighDpiPixmaps keeps it crisp when scaled
    size = 16
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(ratio)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#8f8f8f")))
    painter.drawRoundedRect(QRectF(2.5, 9.5, 3, 4), 1, 1)
    painter.drawRoundedRect(QRectF(6.5, 6, 3, 7.5), 1, 1)
    painter.drawRoundedRect(QRectF(10.5, 2.5, 3, 11), 1, 1)
    painter.end()
    return QIcon(pm)


def _funnel_icon(active: bool) -> QIcon:
    """Outline funnel for the filter button; filled accent when a filter is on."""
    ratio = 2  # 2x supersample; AA_UseHighDpiPixmaps keeps it crisp when scaled
    size = 16
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(ratio)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.Antialiasing)
    points = [(2.5, 3), (13.5, 3), (9.2, 8.5), (9.2, 13), (6.8, 13), (6.8, 8.5)]
    poly = QPolygonF([QPointF(x, y) for x, y in points])
    color = QColor("#cc4444") if active else QColor("#8f8f8f")
    painter.setPen(QPen(color, 1.4))
    painter.setBrush(QBrush(color) if active else Qt.NoBrush)
    painter.drawPolygon(poly)
    painter.end()
    return QIcon(pm)


class MainPanel:
    """Token row, scrollable account grid, and status bar."""

    HEADER_H = 42
    SEP_H = 1
    TOKEN_ROW_H = 34
    ACCOUNTS_HDR_H = 28
    STATUS_ROW_H = 28
    FOOTER_PAD_V = 8
    LOG_PANEL_H = 72
    LAYOUT_SPACING = 6
    MAX_VISIBLE_GRID_ROWS = 2
    SCROLL_BOTTOM_PAD = 12
    GRID_SCROLL_INSET = 0
    GRID_SCROLL_BORDER = 0
    BODY_MARGIN_H = 32

    def __init__(
        self,
        parent: QWidget,
        settings: dict,
        *,
        on_minimize,
        on_close,
    ) -> None:
        self.entry = QLineEdit()
        self._btn_login = QPushButton("Login")
        self._token_err = QLabel("")
        self._search = QLineEdit()
        self._btn_filter = QPushButton()
        self.account_grid = AccountGrid()
        self._grid_scroll = QScrollArea()
        self._scroll_content = QWidget()
        self.info_label = QLabel("")
        self._btn_log = QPushButton("▤")
        self._btn_settings = QPushButton("⚙")
        self._log_panel = QPlainTextEdit()
        self._login_token_ok = False
        self._busy_message = ""
        self._login_strip = QFrame()
        self._footer = QFrame()
        self._status_row = QWidget()
        self._shell: QWidget = parent
        self._settings = settings
        self._on_minimize = on_minimize
        self._on_close = on_close
        self._build(parent)

    @staticmethod
    def _section_sep() -> QFrame:
        sep = QFrame()
        sep.setObjectName("section_sep")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(MainPanel.SEP_H)
        return sep

    def _build(self, parent: QWidget) -> None:
        root = QVBoxLayout(parent)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        header = HeaderBar(
            "WareStore Account Manager",
            on_minimize=self._on_minimize,
            on_close=self._on_close,
        )
        root.addWidget(header)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(self.SEP_H)
        root.addWidget(sep)

        body = QWidget()
        body.setAttribute(Qt.WA_NoSystemBackground)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(self.LAYOUT_SPACING)
        root.addWidget(body)

        self._login_strip.setObjectName("login_strip")
        login_layout = QVBoxLayout(self._login_strip)
        login_layout.setContentsMargins(0, 0, 0, 0)
        login_layout.setSpacing(6)

        tok_row = QHBoxLayout()
        tok_row.setSpacing(8)
        self.entry.setObjectName("token")
        self.entry.setPlaceholderText("username----eyJ…  or bare JWT")
        self.entry.setFixedHeight(self.TOKEN_ROW_H)
        tok_row.addWidget(self.entry, 1)
        btn_paste = QPushButton("Paste")
        btn_paste.setObjectName("secondary")
        btn_paste.setFixedSize(52, self.TOKEN_ROW_H)
        btn_paste.setStyleSheet("min-height: 0; padding: 0; font-size: 11px;")
        self._btn_paste = btn_paste
        tok_row.addWidget(btn_paste)
        self._btn_login.setFixedSize(60, self.TOKEN_ROW_H)
        self._btn_login.setStyleSheet("min-height: 0; padding: 0;")
        self._btn_login.setEnabled(False)
        tok_row.addWidget(self._btn_login)
        login_layout.addLayout(tok_row)

        self._token_err.setObjectName("token_err")
        self._token_err.setWordWrap(True)
        self._token_err.setVisible(False)
        login_layout.addWidget(self._token_err)
        layout.addWidget(self._login_strip)

        layout.addWidget(self._section_sep())

        acc_hdr = QHBoxLayout()
        acc_hdr.setContentsMargins(0, 0, 0, 0)
        acc_hdr.addWidget(SectionLabel("Accounts"))
        acc_hdr.addStretch()
        self._btn_filter.setObjectName("gear")
        self._btn_filter.setFixedSize(self.ACCOUNTS_HDR_H, self.ACCOUNTS_HDR_H)
        self._btn_filter.setToolTip("Filter accounts")
        self._btn_filter.setIcon(_funnel_icon(False))
        self._btn_filter.setIconSize(QSize(16, 16))
        acc_hdr.addWidget(self._btn_filter)
        acc_hdr.addSpacing(6)
        self._search.setObjectName("search")
        self._search.setPlaceholderText("Search…")
        self._search.setFixedSize(148, self.ACCOUNTS_HDR_H)
        acc_hdr.addWidget(self._search)
        layout.addLayout(acc_hdr)

        scroll_layout = QVBoxLayout(self._scroll_content)
        scroll_layout.setContentsMargins(0, 0, 0, 0)
        scroll_layout.setSpacing(0)
        scroll_layout.addWidget(self.account_grid)

        self._grid_scroll.setWidget(self._scroll_content)
        self._grid_scroll.setWidgetResizable(False)
        self._grid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._grid_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._grid_scroll.setFrameShape(QFrame.NoFrame)
        self._grid_scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout.addWidget(self._grid_scroll)

        layout.addWidget(self._section_sep())

        self._footer.setObjectName("footer")
        footer_layout = QVBoxLayout(self._footer)
        footer_layout.setContentsMargins(10, 0, 10, 0)
        footer_layout.setSpacing(8)

        status_layout = QHBoxLayout(self._status_row)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(6)
        self.info_label.setObjectName("info")
        status_layout.addWidget(self.info_label, 1)
        self._btn_log.setObjectName("gear")
        self._btn_log.setFixedSize(24, 24)
        self._btn_log.setCheckable(True)
        # Always start with the log panel closed, regardless of last session.
        self._btn_log.setChecked(False)
        self._btn_log.setToolTip("Toggle log panel")
        status_layout.addWidget(self._btn_log)
        self._btn_cs2_ranks = QPushButton()
        self._btn_cs2_ranks.setObjectName("gear")
        self._btn_cs2_ranks.setFixedSize(24, 24)
        self._btn_cs2_ranks.setToolTip("Fetch CS2 ranks for all accounts")
        self._btn_cs2_ranks.setIcon(_rank_bars_icon())
        self._btn_cs2_ranks.setIconSize(QSize(16, 16))
        status_layout.addWidget(self._btn_cs2_ranks)
        self._btn_refresh = QPushButton("↻")
        self._btn_refresh.setObjectName("gear")
        self._btn_refresh.setFixedSize(24, 24)
        self._btn_refresh.setToolTip("Refresh accounts")
        status_layout.addWidget(self._btn_refresh)
        self._btn_settings.setObjectName("gear")
        self._btn_settings.setFixedSize(24, 24)
        status_layout.addWidget(self._btn_settings)
        footer_layout.addWidget(self._status_row)
        layout.addWidget(self._footer)

        self._log_panel.setObjectName("log")
        self._log_panel.setReadOnly(True)
        self._log_panel.setMaximumBlockCount(400)
        self._log_panel.setFixedHeight(self.LOG_PANEL_H)
        self._log_panel.setVisible(False)
        layout.addWidget(self._log_panel)

        self.header = header
        self._body = body

    def set_filter_active(self, active: bool) -> None:
        self._btn_filter.setIcon(_funnel_icon(active))

    def paste_token(self) -> str:
        text = QApplication.clipboard().text().strip()
        if text:
            self.entry.setText(text)
        return text

    def _grid_row_count(self) -> int:
        count = max(1, len(self.account_grid.filtered_cards()) or self.account_grid.card_count())
        return (count + AccountGrid.COLS - 1) // AccountGrid.COLS

    @classmethod
    def preferred_width(cls, *, needs_vscroll: bool = False) -> int:
        style = QApplication.style()
        vbar = (
            style.pixelMetric(QStyle.PM_ScrollBarExtent) if needs_vscroll else 0
        )
        grid_w = AccountGrid.content_width() + cls.GRID_SCROLL_INSET
        return grid_w + cls.BODY_MARGIN_H + vbar

    def _scroll_metrics(self) -> tuple[int, int, int, bool]:
        """scroll_w, content_h, scroll_area_h, needs_vertical_scroll."""
        rows = self._grid_row_count()
        scroll_w = AccountGrid.content_width() + self.GRID_SCROLL_INSET
        grid_h = AccountGrid.height_for_rows(rows)
        content_h = grid_h + self.GRID_SCROLL_INSET + self.SCROLL_BOTTOM_PAD
        needs_vscroll = rows > self.MAX_VISIBLE_GRID_ROWS
        if needs_vscroll:
            view_h = (
                AccountGrid.height_for_rows(self.MAX_VISIBLE_GRID_ROWS)
                + self.GRID_SCROLL_INSET
                + self.SCROLL_BOTTOM_PAD
            )
        else:
            view_h = content_h
        scroll_area_h = view_h + self.GRID_SCROLL_BORDER
        return scroll_w, content_h, scroll_area_h, needs_vscroll

    def _login_strip_height(self) -> int:
        h = self.TOKEN_ROW_H
        if self._token_err.isVisible() and self._token_err.text():
            h += self.LAYOUT_SPACING + self._token_err.sizeHint().height()
        return h

    def _footer_height(self) -> int:
        return self.FOOTER_PAD_V + self.STATUS_ROW_H

    def _body_height(self, scroll_area_h: int) -> int:
        sp = self.LAYOUT_SPACING
        m = self._body.layout().contentsMargins()
        h = m.top() + m.bottom()
        h += self._login_strip_height() + sp
        h += self.SEP_H + sp
        h += self.ACCOUNTS_HDR_H + sp
        h += scroll_area_h + sp
        h += self.SEP_H + sp
        h += self._footer_height()
        if self._log_panel.isVisible():
            h += sp + self.LOG_PANEL_H
        return h

    def sync_height(self, host) -> None:
        scroll_w, content_h, scroll_area_h, needs_vscroll = self._scroll_metrics()
        self.account_grid._resize_to_content()
        self._scroll_content.setFixedSize(scroll_w, content_h)

        style = QApplication.style()
        vbar_w = (
            style.pixelMetric(QStyle.PM_ScrollBarExtent) if needs_vscroll else 0
        )
        self._grid_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarAsNeeded if needs_vscroll else Qt.ScrollBarAlwaysOff
        )
        self._grid_scroll.setFixedSize(scroll_w + vbar_w, scroll_area_h)

        body_h = self._body_height(scroll_area_h)
        total = self.HEADER_H + self.SEP_H + body_h
        win_w = self.preferred_width(needs_vscroll=needs_vscroll)
        self._body.setFixedHeight(body_h)
        self._shell.setFixedHeight(self.HEADER_H + self.SEP_H + body_h)
        self._shell.setFixedWidth(win_w)
        host.setFixedWidth(win_w)
        host.setFixedHeight(total)

    def window_width(self, *, settings_open: bool, settings_w: int, gap: int) -> int:
        _, _, _, needs_vscroll = self._scroll_metrics()
        w = self.preferred_width(needs_vscroll=needs_vscroll)
        if settings_open:
            return w + gap + settings_w
        return w

    def set_login_token_ok(self, ok: bool) -> None:
        self._login_token_ok = ok
        self._apply_login_button_state()

    def _apply_login_button_state(self) -> None:
        busy = bool(self._busy_message)
        self._btn_login.setEnabled(self._login_token_ok and not busy)

    def set_busy(self, busy: bool, message: str = "") -> str | None:
        prev = self._busy_message
        self._busy_message = message if busy else ""
        self.entry.setEnabled(not busy)
        self._apply_login_button_state()
        self._search.setEnabled(not busy)
        self.account_grid.setEnabled(not busy)
        if busy and message:
            self.info_label.setText(message)
        elif not busy and prev and self.info_label.text() == prev:
            self.info_label.setText("")
        return prev if not busy else None

    def refresh_log(self) -> None:
        if not self._log_panel.isVisible():
            return
        from warestore.presentation.account_manager.support.app_log import app_log

        self._log_panel.setPlainText("\n".join(app_log.lines()[-80:]))

    def set_log_visible(self, visible: bool) -> None:
        self._log_panel.setVisible(visible)
