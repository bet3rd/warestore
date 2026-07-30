# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from warestore.application.account_manager.controller import AccountManagerController

logger = logging.getLogger(__name__)


class BulkImportWorker(QThread):
    progress = pyqtSignal(int, int)
    status = pyqtSignal(str)
    done = pyqtSignal(int, int)

    def __init__(
        self,
        tokens: list[str],
        *,
        ctrl: AccountManagerController,
    ):
        super().__init__()
        self._ctrl = ctrl
        self.tokens = tokens

    def run(self):
        success, total = 0, len(self.tokens)
        for i, tok in enumerate(self.tokens):
            self.progress.emit(i + 1, total)
            self.status.emit(f"Importing {i + 1} / {total}…")
            self._ctrl.kill_steam()
            try:
                if self._ctrl.perform_token_login(tok):
                    success += 1
            except Exception as exc:
                logger.error(f"Bulk import token {i + 1} error: {exc}")
        self.done.emit(success, total)
