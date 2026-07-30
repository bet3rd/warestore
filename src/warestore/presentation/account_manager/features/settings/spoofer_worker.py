# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtCore import QThread, pyqtSignal


class SpooferInstallWorker(QThread):
    """Downloads the HWID spoofer (injector + hardware pool) off the UI thread."""

    done = pyqtSignal(bool, str)  # success, error message

    def __init__(self, controller) -> None:
        super().__init__()
        self._ctrl = controller

    def run(self) -> None:
        try:
            self._ctrl.install_spoofer()
            self.done.emit(True, "")
        except Exception as exc:  # network / IO failure
            self.done.emit(False, str(exc))
