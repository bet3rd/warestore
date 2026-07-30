# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtWidgets import QLabel


class SectionLabel(QLabel):
    def __init__(self, text: str) -> None:
        super().__init__(text.upper())
        self.setObjectName("section")
