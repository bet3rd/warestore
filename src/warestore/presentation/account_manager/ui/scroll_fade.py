# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""A soft fade at the bottom edge of a scroll area.

Shown only while there's more content below, and eased out over the last
``height`` pixels of scroll so it doesn't pop. Purely visual: it ignores the
mouse, so whatever is under it stays clickable.
"""

from __future__ import annotations

from PyQt5.QtCore import QEvent, QObject, QRect, Qt
from PyQt5.QtGui import QColor, QLinearGradient, QPainter
from PyQt5.QtWidgets import QScrollArea, QWidget

PANEL_BG = QColor("#141414")


class _BottomFade(QWidget):
    def __init__(self, area: QScrollArea, color: QColor, height: int) -> None:
        super().__init__(area)
        self._area = area
        self._color = QColor(color)
        self._height = height
        self._strength = 0.0
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)
        bar = area.verticalScrollBar()
        bar.valueChanged.connect(self._sync)
        bar.rangeChanged.connect(self._sync)
        self._filter = _ResizeWatch(self._sync)
        area.installEventFilter(self._filter)
        area.viewport().installEventFilter(self._filter)
        self._sync()

    def strength(self) -> float:
        return self._strength

    def _sync(self, *_args) -> None:
        bar = self._area.verticalScrollBar()
        remaining = bar.maximum() - bar.value()
        self._strength = max(0.0, min(1.0, remaining / self._height)) if self._height else 0.0
        vp = self._area.viewport().geometry()
        self.setGeometry(QRect(vp.left(), vp.bottom() - self._height + 1, vp.width(), self._height))
        self.setVisible(self._strength > 0.0)
        self.raise_()
        self.update()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        clear = QColor(self._color)
        clear.setAlpha(0)
        solid = QColor(self._color)
        solid.setAlpha(int(230 * self._strength))
        gradient = QLinearGradient(0, 0, 0, self.height())
        gradient.setColorAt(0.0, clear)
        gradient.setColorAt(1.0, solid)
        painter.fillRect(self.rect(), gradient)
        painter.end()


class _ResizeWatch(QObject):
    def __init__(self, callback) -> None:
        super().__init__()
        self._callback = callback

    def eventFilter(self, _obj, event) -> bool:
        if event.type() in (QEvent.Resize, QEvent.Show, QEvent.LayoutRequest):
            self._callback()
        return False


def attach_bottom_fade(area: QScrollArea, *, color: QColor = PANEL_BG, height: int = 28) -> QWidget:
    """Add the fade to ``area``; returns the overlay (kept alive by its parent)."""
    return _BottomFade(area, color, height)
