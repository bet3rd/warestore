# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from __future__ import annotations

from collections.abc import Callable

from PyQt5.QtCore import (
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    QRectF,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLabel, QVBoxLayout, QWidget

from warestore.application.account_manager.view_models import (
    AccountCardMenuState,
    AccountCardViewState,
)
from warestore.domain.auth.formatters import format_jwt_expiry_label
from warestore.presentation.account_manager.ui.accounts.account_card_menu import (
    show_account_card_menu,
)
from warestore.presentation.account_manager.ui.avatars import (
    AVATAR_SIZE,
    circular_avatar_from_file,
    make_placeholder_pixmap,
)

_STATUS_COLORS: dict[int, QColor] = {
    0: QColor("#505050"),
    1: QColor("#5ba85e"),
    2: QColor("#e07b39"),
    3: QColor("#c9a227"),
    4: QColor("#8a7a3a"),
}
_IN_GAME_COLOR = QColor("#4a9eda")
_COOLDOWN_ACCENT = QColor("#d4a017")


class AccountCard(QWidget):
    CARD_W = 120
    CARD_H = 120
    SUB_H = 12
    RADIUS = 10.0
    _SUB_STYLE_DEFAULT = "color: #787878; background: transparent; border: none;"
    _SUB_STYLE_JWT = "color: #aa5544; background: transparent; border: none;"
    _SUB_STYLE_COOLDOWN = "color: #d4a017; background: transparent; border: none; font-weight: 600;"

    _BASE_R, _BASE_G, _BASE_B = 0x1E, 0x1E, 0x1E
    _HOV_R, _HOV_G, _HOV_B = 0x2E, 0x2A, 0x2A
    _SEL_BG = QColor("#261a1a")
    _SEL_BORDER = QColor("#cc1111")

    clicked = pyqtSignal(object, object)
    double_clicked = pyqtSignal(object)
    relogin_requested = pyqtSignal(object)

    def __init__(self, acc: dict, avatar: QPixmap, parent=None):
        super().__init__(parent)
        self.acc = acc
        self._sel = False
        self._t = 0.0
        self._status_state: int = -1
        self._status_game: str = ""
        self._status_stale: bool = False
        self._expiry_label: str = ""
        self._cooldown_label: str = ""
        self._cooldown_active: bool = False
        self._cooldown_progress: float = 0.0
        self._color: str = ""
        self._ban: dict | None = None
        self._level: int | None = None
        self._menu_state = AccountCardMenuState(
            username=acc.get("account_name", ""),
            steam_id=acc.get("steamid", ""),
            saved_token="",
            has_saved_token=False,
            has_cooldown=False,
        )
        self._hovering: bool = False

        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_Hover)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 8, 4, 6)
        layout.setSpacing(6)
        layout.setAlignment(Qt.AlignCenter)

        self._avatar_label = QLabel()
        self._avatar_label.setFixedSize(AVATAR_SIZE, AVATAR_SIZE)
        self._avatar_label.setAlignment(Qt.AlignCenter)
        self._avatar_label.setStyleSheet("background: transparent; border: none;")
        self._avatar_label.setPixmap(
            avatar if (avatar and not avatar.isNull()) else make_placeholder_pixmap(AVATAR_SIZE)
        )
        layout.addWidget(self._avatar_label, 0, Qt.AlignCenter)

        display = acc.get("persona_name") or acc.get("account_name", "")
        name_font = QFont("Segoe UI", 9, QFont.Bold)
        name_metrics = QFontMetrics(name_font)
        self._nm_lbl = QLabel(name_metrics.elidedText(display, Qt.ElideRight, self.CARD_W - 10))
        self._nm_lbl.setAlignment(Qt.AlignCenter)
        self._nm_lbl.setFont(name_font)
        self._nm_lbl.setStyleSheet("color: #b8b8b8; background: transparent; border: none;")
        layout.addWidget(self._nm_lbl, 0, Qt.AlignCenter)

        self._sub_lbl = QLabel("", self)
        self._sub_lbl.setAlignment(Qt.AlignCenter)
        self._sub_lbl.setFont(QFont("Segoe UI", 7))
        self._sub_lbl.setGeometry(4, self.CARD_H, self.CARD_W - 8, self.SUB_H)
        self._sub_eff = QGraphicsOpacityEffect(self._sub_lbl)
        self._sub_eff.setOpacity(0.0)
        self._sub_lbl.setGraphicsEffect(self._sub_eff)

        self._sub_pos_anim = QPropertyAnimation(self._sub_lbl, b"pos", self)
        self._sub_pos_anim.setDuration(220)
        self._sub_pos_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._sub_op_anim = QPropertyAnimation(self._sub_eff, b"opacity", self)
        self._sub_op_anim.setDuration(180)
        self._sub_op_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._sub_visible = False
        self._update_sub_content()

    @property
    def menu_state(self) -> AccountCardMenuState:
        return self._menu_state

    @property
    def color_tag(self) -> str:
        return self._color

    @property
    def is_on_cooldown(self) -> bool:
        return self._cooldown_active

    @property
    def is_banned(self) -> bool:
        return self._ban_color() is not None

    def set_selected(self, selected: bool):
        self._sel = selected
        if not selected:
            self._t = 0.0
            self._nm_lbl.setStyleSheet("color: #b8b8b8; background: transparent; border: none;")
        else:
            self._nm_lbl.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        self._update_sub_content()
        self._sync_sub_visibility()
        self.update()

    def set_status(self, state: int, game: str, *, stale: bool = False) -> None:
        self._status_state = state
        self._status_game = game
        self._status_stale = stale
        self._refresh_tooltip()
        self.update()

    def set_ban_info(self, info: dict | None) -> None:
        self._ban = info or None
        self._refresh_tooltip()
        self.update()

    def set_level(self, level: int | None) -> None:
        self._level = level
        self._refresh_tooltip()
        self.update()

    def set_persona(self, name: str) -> None:
        """Update the displayed persona name (e.g. from a status refresh)."""
        if not name or name == self.acc.get("persona_name"):
            return
        self.acc["persona_name"] = name
        metrics = QFontMetrics(self._nm_lbl.font())
        self._nm_lbl.setText(metrics.elidedText(name, Qt.ElideRight, self.CARD_W - 10))
        self._refresh_tooltip()

    def set_avatar_from_file(self, path: str) -> None:
        """Swap in a freshly-fetched avatar from a cached image file."""
        pix = circular_avatar_from_file(path)
        if pix is not None and not pix.isNull():
            self._avatar_label.setPixmap(pix)

    def _ban_summary(self) -> str:
        b = self._ban
        if not b:
            return ""
        parts: list[str] = []
        if b.get("vac"):
            count = b.get("vac_count", 0)
            parts.append(f"VAC banned ×{count}" if count > 1 else "VAC banned")
        if b.get("game_bans"):
            n = b["game_bans"]
            label = f"Game ban ×{n}" if n > 1 else "Game ban"
            parts.append(f"{label} ({b.get('days_since', 0)}d ago)")
        if b.get("trade", "none") not in ("none", ""):
            parts.append(f"Trade: {b['trade']}")
        if b.get("community"):
            parts.append("Community banned")
        return ", ".join(parts)

    def _ban_color(self) -> QColor | None:
        b = self._ban
        if not b:
            return None
        if b.get("vac") or b.get("game_bans"):
            return QColor("#cc3333")
        if b.get("community") or b.get("trade", "none") not in ("none", ""):
            return QColor("#e07b39")
        return None

    def _refresh_tooltip(self) -> None:
        parts: list[str] = []
        username = self.acc.get("account_name", "")
        if username:
            parts.append(username)
        ban_summary = self._ban_summary()
        if ban_summary:
            parts.append(f"⛔ {ban_summary}")
        if self._level is not None:
            parts.append(f"Level {self._level}")
        if self._expiry_label:
            parts.append(self._expiry_label)
        if self._cooldown_label:
            parts.append(self._cooldown_label)
        if self._status_game:
            parts.append(self._status_game)
        elif self._status_stale and self._status_state >= 0:
            parts.append("Status unavailable")
        self.setToolTip(" · ".join(parts))

    def set_jwt_expiry(self, expires_in: int) -> None:
        self._expiry_label = format_jwt_expiry_label(expires_in)
        self._update_sub_content()
        self._sync_sub_visibility()

    def set_view_state(self, state: AccountCardViewState) -> None:
        self._menu_state = state.menu
        self._color = state.color
        self.set_jwt_expiry(state.jwt_expires_in)
        self.set_cooldown_label(state.cooldown_label, progress=state.cooldown_progress)
        self._refresh_tooltip()
        self.update()

    def set_cooldown_label(self, label: str, *, progress: float = 1.0) -> None:
        self._cooldown_label = label
        self._cooldown_active = bool(label)
        self._cooldown_progress = progress if self._cooldown_active else 0.0
        self._update_sub_content()
        self._sync_sub_visibility()
        self.update()

    def _sub_y_show(self) -> int:
        return self.CARD_H - self.SUB_H - 8

    def _sub_y_hide(self) -> int:
        return self.CARD_H

    def _update_sub_content(self) -> None:
        metrics = QFontMetrics(self._sub_lbl.font())
        width = self.CARD_W - 10
        if self._hovering:
            if self._expiry_label:
                text = self._expiry_label
                style = self._SUB_STYLE_JWT
            else:
                username = self.acc.get("account_name", "")
                text = metrics.elidedText(username, Qt.ElideRight, width) if username else ""
                style = self._SUB_STYLE_DEFAULT
        elif self._cooldown_label:
            text = metrics.elidedText(self._cooldown_label, Qt.ElideRight, width)
            style = self._SUB_STYLE_COOLDOWN
        elif self._sel:
            if self._expiry_label:
                text = self._expiry_label
                style = self._SUB_STYLE_JWT
            else:
                username = self.acc.get("account_name", "")
                text = metrics.elidedText(username, Qt.ElideRight, width) if username else ""
                style = self._SUB_STYLE_DEFAULT
        else:
            text = ""
            style = self._SUB_STYLE_DEFAULT
        self._sub_lbl.setText(text)
        self._sub_lbl.setStyleSheet(style)
        self._refresh_tooltip()

    def _sync_sub_visibility(self) -> None:
        show = bool(self._sub_lbl.text()) and (
            self._hovering or self._cooldown_active or self._sel
        )
        self._run_sub_anims(show)

    def _run_sub_anims(self, show: bool) -> None:
        if show and not self._sub_lbl.text():
            show = False
        if show == self._sub_visible:
            if show:
                self._update_sub_content()
            return
        self._sub_visible = show
        y = self._sub_y_show() if show else self._sub_y_hide()
        opacity = 1.0 if show else 0.0

        self._sub_pos_anim.stop()
        self._sub_pos_anim.setStartValue(self._sub_lbl.pos())
        self._sub_pos_anim.setEndValue(QPoint(4, y))
        self._sub_pos_anim.start()

        self._sub_op_anim.stop()
        self._sub_op_anim.setStartValue(self._sub_eff.opacity())
        self._sub_op_anim.setEndValue(opacity)
        self._sub_op_anim.start()

    def _lerp_bg(self) -> QColor:
        t = self._t
        return QColor(
            int(self._BASE_R + (self._HOV_R - self._BASE_R) * t),
            int(self._BASE_G + (self._HOV_G - self._BASE_G) * t),
            int(self._BASE_B + (self._HOV_B - self._BASE_B) * t),
        )

    def _on_anim(self, value):
        self._t = float(value)
        channel = int(0xB8 + (0xFF - 0xB8) * self._t)
        self._nm_lbl.setStyleSheet(
            f"color: rgb({channel},{channel},{channel}); background: transparent; border: none;"
        )
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        bg = self._SEL_BG if self._sel else self._lerp_bg()
        painter.fillPath(path, QBrush(bg))
        if self._color:
            tag = QColor(self._color)
            if tag.isValid():
                # Subtle colour-tag wash over the whole card (drawn under the
                # selection border and the badges/labels that follow).
                tag.setAlpha(48)
                painter.fillPath(path, QBrush(tag))
        if self._sel:
            painter.setPen(QPen(self._SEL_BORDER, 1.5))
            painter.drawPath(path)

        if self._status_state >= 0:
            in_game = bool(self._status_game)
            if self._status_stale:
                dot_color = QColor("#6a5040")
            else:
                dot_color = _IN_GAME_COLOR if in_game else _STATUS_COLORS.get(
                    self._status_state, _STATUS_COLORS[0]
                )
            dot_r = 5
            dot_x = self.width() - dot_r * 2 - 6
            dot_y = 6
            painter.setPen(QPen(QColor(self._BASE_R, self._BASE_G, self._BASE_B), 2.0))
            painter.setBrush(QBrush(dot_color))
            painter.drawEllipse(dot_x, dot_y, dot_r * 2, dot_r * 2)

        ban_color = self._ban_color()
        if ban_color is not None:
            dot_r = 5
            dot_x = 6
            dot_y = self.height() - dot_r * 2 - 6
            painter.setPen(QPen(QColor(self._BASE_R, self._BASE_G, self._BASE_B), 2.0))
            painter.setBrush(QBrush(ban_color))
            painter.drawEllipse(dot_x, dot_y, dot_r * 2, dot_r * 2)

        if self._cooldown_active:
            bar_max_w = self.width() - 16
            fill_w = max(0.0, bar_max_w * self._cooldown_progress)
            if fill_w >= 1:
                bar = QPainterPath()
                bar.addRoundedRect(
                    QRectF(8, self.height() - 5, fill_w, 3),
                    1.5,
                    1.5,
                )
                painter.fillPath(bar, QBrush(_COOLDOWN_ACCENT))

        if self._level is not None:
            # Top-left corner (left of the centered avatar); the bottom-right is
            # left clear for the username/expiry sub-label that slides up there.
            painter.setPen(QPen(QColor("#9a9a9a")))
            painter.setFont(QFont("Segoe UI", 7))
            painter.drawText(
                QRectF(8, 4, 26, 12),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"Lv{self._level}",
            )

        painter.end()

    def enterEvent(self, _event):
        self._hovering = True
        self._update_sub_content()
        self._sync_sub_visibility()
        if not self._sel:
            self._anim.stop()
            self._anim.setStartValue(self._t)
            self._anim.setEndValue(1.0)
            self._anim.start()

    def leaveEvent(self, _event):
        self._hovering = False
        self._update_sub_content()
        self._sync_sub_visibility()
        if not self._sel:
            self._anim.stop()
            self._anim.setStartValue(self._t)
            self._anim.setEndValue(0.0)
            self._anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.acc, event.modifiers())

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.acc)

    def contextMenuEvent(self, event):
        from warestore.presentation.account_manager.ui.accounts.account_grid import AccountGrid

        grid = self.parent()
        if not isinstance(grid, AccountGrid):
            return

        targets = grid.resolve_menu_targets(self.acc)
        show_account_card_menu(
            parent=self,
            account=self.acc,
            menu_state=self._menu_state,
            targets=targets,
            export_count=grid.count_with_tokens(targets),
            global_pos=event.globalPos(),
            on_switch=lambda acc: self.double_clicked.emit(acc),
            on_relogin=lambda acc: self.relogin_requested.emit(acc),
            on_copy_export=grid.export_copy_requested.emit,
            on_export_file=grid.export_file_requested.emit,
            on_delete=grid.delete_requested.emit,
            on_cooldown_set=grid.cooldown_set_requested.emit,
            on_cooldown_custom=grid.cooldown_custom_requested.emit,
            on_color_set=grid.color_set_requested.emit,
            on_cs2_source_set=grid.cs2_source_set_requested.emit,
            on_cs2_apply=grid.cs2_apply_requested.emit,
            on_reset_hwid=grid.hwid_reset_requested.emit,
            has_hwid_profile=self._menu_state.has_hwid_profile,
        )
