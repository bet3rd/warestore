# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

from warestore.presentation.account_manager.ui.theme import (
    enable_dark_title_bar,
    schedule_capture_exclusion_for_widget,
)


class CooldownCustomDialog(QDialog):
    def __init__(self, parent=None, *, exclude_from_capture: bool = True):
        super().__init__(parent)
        self._exclude_from_capture = exclude_from_capture
        self.setObjectName("warestore_dialog")
        self.setWindowTitle("Custom cooldown")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Custom cooldown")
        title.setObjectName("dialog_title")
        layout.addWidget(title)

        hint = QLabel("Set days, hours, minutes, and seconds — they add together.")
        hint.setObjectName("info")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        field_lbl = QLabel("Duration")
        field_lbl.setObjectName("field_label")
        layout.addWidget(field_lbl)

        row = QHBoxLayout()
        row.setSpacing(10)
        self._days, days_col = self._duration_field("days", 365)
        self._hours, hours_col = self._duration_field("hours", 999)
        self._minutes, minutes_col = self._duration_field("minutes", 59)
        self._seconds, seconds_col = self._duration_field("seconds", 59)
        for col in (days_col, hours_col, minutes_col, seconds_col):
            row.addLayout(col, 1)
        layout.addLayout(row)

        for spin in (self._days, self._hours, self._minutes, self._seconds):
            spin.valueChanged.connect(self._sync_apply)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("secondary")
        cancel_btn.setFixedSize(92, 36)
        cancel_btn.setStyleSheet("min-height: 0; padding: 0;")
        cancel_btn.clicked.connect(self.reject)
        self._apply_btn = QPushButton("Apply")
        self._apply_btn.setFixedSize(92, 36)
        self._apply_btn.setStyleSheet("min-height: 0; padding: 0;")
        self._apply_btn.clicked.connect(self.accept)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(self._apply_btn)
        layout.addLayout(btn_row)

        self._sync_apply()
        self.adjustSize()
        self.setFixedSize(self.size())

    def _duration_field(
        self, label: str, maximum: int, *, default: int = 0
    ) -> tuple[QSpinBox, QVBoxLayout]:
        col = QVBoxLayout()
        col.setSpacing(6)
        spin = QSpinBox()
        spin.setButtonSymbols(QSpinBox.NoButtons)
        spin.setRange(0, maximum)
        spin.setValue(default)
        spin.setFixedHeight(36)
        spin.setAlignment(Qt.AlignCenter)
        col.addWidget(spin)
        unit_lbl = QLabel(label)
        unit_lbl.setObjectName("unit_label")
        unit_lbl.setAlignment(Qt.AlignCenter)
        col.addWidget(unit_lbl)
        return spin, col

    def showEvent(self, event):
        enable_dark_title_bar(int(self.winId()))
        schedule_capture_exclusion_for_widget(self, enabled=self._exclude_from_capture)
        super().showEvent(event)

    def _total_seconds(self) -> int:
        return (
            self._days.value() * 86400
            + self._hours.value() * 3600
            + self._minutes.value() * 60
            + self._seconds.value()
        )

    def _sync_apply(self) -> None:
        self._apply_btn.setEnabled(self._total_seconds() > 0)

    def duration_seconds(self) -> int:
        return self._total_seconds()
