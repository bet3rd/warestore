# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""CS2 rank fetch for a single account, run off the UI thread.

Each worker handles exactly ONE account; batch sweeps (multi-select or the
"fetch all" button) are driven by AccountCoordinator, which runs one worker at a
time — never concurrently, since minting a web session touches the account. The
gateway is read-only w.r.t. the token.
"""

from __future__ import annotations

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from warestore.application.account_manager.controller import AccountManagerController

logger = logging.getLogger(__name__)


class Cs2RankWorker(QThread):
    done = pyqtSignal(str, object)  # (steam_id, rank dict | None)

    def __init__(self, steam_id: str, refresh_token: str, *, ctrl: AccountManagerController):
        super().__init__()
        self._steam_id = steam_id
        self._token = refresh_token
        self._ctrl = ctrl

    def run(self) -> None:
        logger.info("cs2-rank: on-demand fetch started for %s", self._steam_id)
        data = None
        try:
            data = self._ctrl.fetch_cs2_rank(self._steam_id, self._token)
        except Exception:  # noqa: BLE001 - never crash the worker thread
            logger.exception("cs2-rank: worker failed for %s", self._steam_id)
        logger.info("cs2-rank: on-demand fetch done for %s (got=%s)",
                    self._steam_id, data is not None)
        self.done.emit(self._steam_id, data)
