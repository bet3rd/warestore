# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Background account checks, one account at a time.

Each check is a CM logon as the account, so checks never run concurrently. The
CS2 config source's loadout is read once and reused until the source setting
changes. ValvePython (gevent) runs here, off the Qt thread.
"""

from __future__ import annotations

import logging
import threading

from PyQt5.QtCore import QThread, pyqtSignal

logger = logging.getLogger(__name__)


class AccountCheckQueue:
    def __init__(self) -> None:
        self._items: list[str] = []
        self._current: str | None = None

    def add(self, steam_ids: list[str]) -> int:
        added = 0
        for sid in steam_ids:
            if sid and sid != self._current and sid not in self._items:
                self._items.append(sid)
                added += 1
        return added

    def pop(self) -> str | None:
        return self._items.pop(0) if self._items else None

    def set_current(self, sid: str | None) -> None:
        self._current = sid

    def __len__(self) -> int:
        return len(self._items)


class AccountCheckWorker(QThread):
    started_account = pyqtSignal(str)
    finished_account = pyqtSignal(str, object)  # (steam_id, CheckResult)
    drained = pyqtSignal()

    def __init__(self, ctrl) -> None:
        super().__init__()
        self._ctrl = ctrl
        self._queue = AccountCheckQueue()
        self._lock = threading.Lock()
        self._source = None
        # A batch enqueued while run() is exiting would otherwise sit unprocessed.
        self.finished.connect(self._restart_if_pending)

    def enqueue(self, steam_ids: list[str]) -> int:
        with self._lock:
            added = self._queue.add(steam_ids)
        if added and not self.isRunning():
            self.start()
        return added

    def _restart_if_pending(self) -> None:
        with self._lock:
            pending = len(self._queue)
        if pending and not self.isRunning():
            self.start()

    def _source_loadout(self):
        wanted = self._ctrl.cs2_config_source()
        if self._source is None or self._source.steam_id != wanted:
            self._source = self._ctrl.read_source_loadout()
        return self._source

    def run(self) -> None:
        while True:
            with self._lock:
                sid = self._queue.pop()
                self._queue.set_current(sid)
            if sid is None:
                break
            self.started_account.emit(sid)
            try:
                result = self._ctrl.check_account(sid, source=self._source_loadout())
            except Exception:  # noqa: BLE001 - never crash the worker thread
                logger.exception("account-check: worker failed for %s", sid)
                result = None
            self.finished_account.emit(sid, result)
        self._source = None if self._source is None or self._source.loadout is None else self._source
        self.drained.emit()
