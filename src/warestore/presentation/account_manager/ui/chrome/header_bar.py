# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget


class HeaderBar(QWidget):
    def __init__(
        self,
        title: str,
        on_minimize,
        on_close,
        show_minimize: bool = True,
        draggable: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.setFixedHeight(42)
        self._drag_pos: QPoint | None = None
        self._draggable = draggable

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        layout.setSpacing(4)

        label = QLabel(title)
        label.setObjectName("title")
        label.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(label)
        layout.addStretch()

        if show_minimize:
            btn_min = QPushButton("⎯")
            btn_min.setObjectName("win-min")
            btn_min.setFixedSize(30, 30)
            btn_min.clicked.connect(on_minimize)
            layout.addWidget(btn_min)

        btn_close = QPushButton("✕")
        btn_close.setObjectName("win-close")
        btn_close.setFixedSize(30, 30)
        btn_close.clicked.connect(on_close)
        layout.addWidget(btn_close)

    def mousePressEvent(self, event):
        if self._draggable and event.button() == Qt.LeftButton:
            self._drag_pos = event.globalPos() - self.window().frameGeometry().topLeft()

    def mouseMoveEvent(self, event):
        if self._draggable and event.buttons() == Qt.LeftButton and self._drag_pos is not None:
            self.window().move(event.globalPos() - self._drag_pos)

    def mouseReleaseEvent(self, _event):
        self._drag_pos = None
