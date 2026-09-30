# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Colour swatches and a dark, app-styled colour picker popover
(saturation/value square + hue bar + hex field)."""

from PyQt5.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from warestore.presentation.account_manager.ui.theme.accent import parse_hex


class ColorSwatch(QWidget):
    """Round, clickable colour dot; a ring marks the selected one."""

    clicked = pyqtSignal(str)

    SIZE = 24

    def __init__(self, color: str, tooltip: str = "", parent=None) -> None:
        super().__init__(parent)
        self._color = color
        self._selected = False
        self.setFixedSize(self.SIZE, self.SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)

    @property
    def color(self) -> str:
        return self._color

    def set_color(self, color: str) -> None:
        self._color = color
        self.update()

    def set_selected(self, selected: bool) -> None:
        if selected != self._selected:
            self._selected = selected
            self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self._color)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._selected:
            painter.setPen(QPen(QColor("#e0e0e0"), 1.6))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(1, 1, self.SIZE - 2, self.SIZE - 2))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._color))
        painter.drawEllipse(QRectF(4.5, 4.5, self.SIZE - 9, self.SIZE - 9))
        painter.end()


def _drag_handle(painter: QPainter, draw) -> None:
    """Dark halo + white outline so the handle reads on any colour."""
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(QColor(0, 0, 0, 140), 3))
    draw()
    painter.setPen(QPen(QColor("#ffffff"), 1.6))
    draw()


class _SVSquare(QWidget):
    """Saturation (x) / value (y) plane for the current hue."""

    changed = pyqtSignal(float, float)
    released = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(150)
        self.setCursor(Qt.CrossCursor)
        self._hue = 0.0
        self._s = 1.0
        self._v = 1.0
        self._cache: QPixmap | None = None

    def set_hue(self, hue: float) -> None:
        if hue != self._hue:
            self._hue = hue
            self._cache = None
            self.update()

    def set_sv(self, s: float, v: float) -> None:
        self._s, self._v = s, v
        self.update()

    def _plane(self) -> QPixmap:
        if self._cache is None:
            dpr = self.devicePixelRatioF()
            pm = QPixmap(round(self.width() * dpr), round(self.height() * dpr))
            pm.setDevicePixelRatio(dpr)
            pm.fill(Qt.transparent)
            painter = QPainter(pm)
            painter.setRenderHint(QPainter.Antialiasing)
            rect = QRectF(0, 0, self.width(), self.height())
            clip = QPainterPath()
            clip.addRoundedRect(rect, 6, 6)
            painter.setClipPath(clip)
            sat = QLinearGradient(rect.topLeft(), rect.topRight())
            sat.setColorAt(0, QColor("#ffffff"))
            sat.setColorAt(1, QColor.fromHsvF(self._hue, 1, 1))
            painter.fillRect(rect, QBrush(sat))
            val = QLinearGradient(rect.topLeft(), rect.bottomLeft())
            val.setColorAt(0, QColor(0, 0, 0, 0))
            val.setColorAt(1, QColor(0, 0, 0, 255))
            painter.fillRect(rect, QBrush(val))
            painter.end()
            self._cache = pm
        return self._cache

    def resizeEvent(self, _event):
        self._cache = None

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.drawPixmap(0, 0, self._plane())
        center = QPointF(self._s * (self.width() - 1), (1 - self._v) * (self.height() - 1))
        _drag_handle(painter, lambda: painter.drawEllipse(center, 6, 6))
        painter.end()

    def _pick(self, pos) -> None:
        s = min(1.0, max(0.0, pos.x() / (self.width() - 1)))
        v = min(1.0, max(0.0, 1 - pos.y() / (self.height() - 1)))
        self.set_sv(s, v)
        self.changed.emit(s, v)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pick(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._pick(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.released.emit()


class _HueBar(QWidget):
    changed = pyqtSignal(float)
    released = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self.setFixedHeight(14)
        self.setCursor(Qt.PointingHandCursor)
        self._hue = 0.0

    def set_hue(self, hue: float) -> None:
        self._hue = hue
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(0, 2, self.width(), self.height() - 4)
        grad = QLinearGradient(track.topLeft(), track.topRight())
        for i in range(7):
            grad.setColorAt(i / 6, QColor.fromHsvF((i / 6) % 1.0, 1, 1))
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(grad))
        painter.drawRoundedRect(track, 5, 5)
        x = 6 + self._hue * (self.width() - 12)
        knob = QRectF(x - 5, 0, 10, self.height())
        painter.setBrush(QColor.fromHsvF(self._hue, 1, 1))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(knob, 4, 4)
        _drag_handle(painter, lambda: painter.drawRoundedRect(knob, 4, 4))
        painter.end()

    def _pick(self, pos) -> None:
        hue = min(0.9999, max(0.0, (pos.x() - 6) / (self.width() - 12)))
        self.set_hue(hue)
        self.changed.emit(hue)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._pick(event.pos())

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.LeftButton:
            self._pick(event.pos())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.released.emit()


class _CompareChip(QWidget):
    """Left half: the colour before opening; right half: the current pick."""

    def __init__(self, old: QColor) -> None:
        super().__init__()
        self.setFixedSize(56, 28)
        self.old = old
        self.new = old

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 6, 6)
        painter.setClipPath(path)
        half = rect.width() / 2
        painter.fillRect(QRectF(rect.left(), rect.top(), half, rect.height()), self.old)
        painter.fillRect(QRectF(rect.left() + half, rect.top(), half, rect.height()), self.new)
        painter.setClipping(False)
        painter.setPen(QPen(QColor("#2a2a2a"), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)
        painter.end()


class ColorPickerPopover(QWidget):
    """Frameless popup anchored under a widget.

    Emits ``colorChanged`` when a drag ends or a valid hex is typed — not per
    mouse move, since listeners restyle the whole app — then exactly one of
    ``accepted(hex)`` (Apply / Enter) or ``rejected()`` (Cancel / Esc / click-away).
    """

    colorChanged = pyqtSignal(str)
    accepted = pyqtSignal(str)
    rejected = pyqtSignal()

    WIDTH = 240
    RADIUS = 10.0
    BG = QColor("#181818")
    BORDER = QColor("#2e2e2e")

    def __init__(self, initial: str, parent=None) -> None:
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setFixedWidth(self.WIDTH)
        self._finished = False
        start = QColor(initial)
        h, s, v, _ = start.getHsvF()
        self._h = max(h, 0.0)  # achromatic colours report hue -1
        self._s, self._v = s, v

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        self._square = _SVSquare()
        self._hue_bar = _HueBar()
        layout.addWidget(self._square)
        layout.addWidget(self._hue_bar)

        hex_row = QHBoxLayout()
        hex_row.setSpacing(8)
        self._chip = _CompareChip(start)
        hex_row.addWidget(self._chip)
        hash_label = QLabel("#")
        hash_label.setStyleSheet("color: #686868; font-size: 12px;")
        hex_row.addWidget(hash_label)
        self._hex = QLineEdit()
        self._hex.setMaxLength(7)
        self._hex.setFixedHeight(28)
        self._hex.setStyleSheet(
            "QLineEdit { font-family: Consolas, monospace; font-size: 12px; padding: 0 6px; }"
        )
        hex_row.addWidget(self._hex, 1)
        layout.addLayout(hex_row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.setObjectName("secondary")
        btn_apply = QPushButton("Apply")
        for btn in (btn_cancel, btn_apply):
            btn.setFixedHeight(28)
            btn.setStyleSheet("min-height: 0; padding: 0 12px;")
        buttons.addStretch()
        buttons.addWidget(btn_cancel)
        buttons.addWidget(btn_apply)
        layout.addLayout(buttons)

        self._square.changed.connect(self._on_sv)
        self._hue_bar.changed.connect(self._on_hue)
        self._square.released.connect(self._emit_color)
        self._hue_bar.released.connect(self._emit_color)
        self._hex.textEdited.connect(self._on_hex)
        self._hex.returnPressed.connect(self._accept)
        btn_cancel.clicked.connect(self.close)
        btn_apply.clicked.connect(self._accept)

        self._sync()

    def color(self) -> str:
        return QColor.fromHsvF(self._h, self._s, self._v).name()

    def _sync(self, *, from_hex: bool = False) -> None:
        self._square.set_hue(self._h)
        self._square.set_sv(self._s, self._v)
        self._hue_bar.set_hue(self._h)
        hex_color = self.color()
        self._chip.new = QColor(hex_color)
        self._chip.update()
        if not from_hex:
            self._hex.setText(hex_color[1:])

    def _emit_color(self) -> None:
        self.colorChanged.emit(self.color())

    def _on_sv(self, s: float, v: float) -> None:
        self._s, self._v = s, v
        self._sync()

    def _on_hue(self, hue: float) -> None:
        self._h = hue
        self._sync()

    def _on_hex(self, text: str) -> None:
        parsed = parse_hex(text)
        if parsed is None:
            return
        h, s, v, _ = QColor(parsed).getHsvF()
        if h >= 0:
            self._h = h
        self._s, self._v = s, v
        self._sync(from_hex=True)
        self._emit_color()

    def _accept(self) -> None:
        if parse_hex(self._hex.text()) is None:
            self._hex.selectAll()
            return
        self._finished = True
        self.accepted.emit(self.color())
        self.close()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(event)

    def closeEvent(self, event):
        if not self._finished:
            self._finished = True
            self.rejected.emit()
        super().closeEvent(event)

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        painter.fillPath(path, self.BG)
        painter.setPen(QPen(self.BORDER, 1))
        painter.drawPath(path)
        painter.end()

    def popup_below(self, anchor: QWidget) -> None:
        """Show right-aligned under ``anchor`` and focus the hex field."""
        self.adjustSize()
        corner = anchor.mapToGlobal(anchor.rect().bottomRight())
        x, y = corner.x() - self.width(), corner.y() + 6
        screen = QApplication.screenAt(corner)
        if screen is not None:
            area = screen.availableGeometry()
            if y + self.height() > area.bottom():  # no room below: open above
                y = anchor.mapToGlobal(anchor.rect().topLeft()).y() - self.height() - 6
            x = min(max(x, area.left()), area.right() - self.width())
            y = max(y, area.top())
        self.move(x, y)
        self.show()
        self._hex.setFocus()
        self._hex.selectAll()
