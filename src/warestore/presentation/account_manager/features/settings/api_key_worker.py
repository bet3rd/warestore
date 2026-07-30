# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from warestore.application.account_manager.controller import AccountManagerController

logger = logging.getLogger(__name__)


class ApiKeyValidateWorker(QThread):
    """Validates a Steam Web API key off the UI thread; emits the verdict."""

    done = pyqtSignal(str)  # "valid" | "invalid" | "error"

    def __init__(self, key: str, *, ctrl: AccountManagerController) -> None:
        super().__init__()
        self._key = key
        self._ctrl = ctrl

    def run(self) -> None:
        try:
            self.done.emit(self._ctrl.validate_api_key(self._key))
        except Exception as exc:
            logger.warning(f"API key validation worker error: {exc}")
            self.done.emit("error")
