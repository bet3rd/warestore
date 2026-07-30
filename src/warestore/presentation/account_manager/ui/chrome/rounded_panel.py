# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtCore import QRectF
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPen
from PyQt5.QtWidgets import QWidget


class RoundedPanel(QWidget):
    RADIUS = 12.0
    BG = QColor("#141414")
    BORDER = QColor("#282828")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        painter.fillPath(path, QBrush(self.BG))
        painter.setPen(QPen(self.BORDER, 1.0))
        painter.drawPath(path)
        painter.end()
