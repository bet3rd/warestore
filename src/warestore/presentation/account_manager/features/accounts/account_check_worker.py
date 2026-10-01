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
import time

from PyQt5.QtCore import QThread, pyqtSignal

from warestore.application.account_manager.account_check import CheckSteps, SourceLoadout

logger = logging.getLogger(__name__)


class AccountCheckQueue:
    """FIFO of (steam_id, steps) pairs. ``steps=None`` means "whatever the
    user's settings say", treated here as the strongest/"full" level. A
    re-enqueue of an id already queued merges the two requests — None wins,
    otherwise each step runs if either asked for it (e.g. "Refresh stats" then
    "Override Config" does both) — and never drops a step already queued."""

    def __init__(self) -> None:
        self._items: dict[str, CheckSteps | None] = {}
        self._current: str | None = None

    def add(self, steam_ids: list[str], steps: CheckSteps | None = None) -> int:
        added = 0
        for sid in steam_ids:
            if not sid or sid == self._current:
                continue
            if sid in self._items:
                self._items[sid] = _merge(self._items[sid], steps)
                continue
            self._items[sid] = steps
            added += 1
        return added

    def clear(self) -> list[str]:
        """Drop every queued item; returns the ids that were dropped."""
        dropped = list(self._items)
        self._items.clear()
        return dropped

    def pop(self) -> tuple[str, CheckSteps | None] | None:
        if not self._items:
            return None
        sid = next(iter(self._items))
        return sid, self._items.pop(sid)

    def set_current(self, sid: str | None) -> None:
        self._current = sid

    def __len__(self) -> int:
        return len(self._items)


def _merge(a: CheckSteps | None, b: CheckSteps | None) -> CheckSteps | None:
    if a is None or b is None:
        return None
    return CheckSteps(
        loadout=a.loadout or b.loadout,
        stats=a.stats or b.stats,
        workshop=a.workshop or b.workshop,
    )


class AccountCheckWorker(QThread):
    # Pause between two checks: each is a Steam sign-in, and a burst of them
    # from one IP is what trips Steam's rate limit.
    CHECK_GAP_SECONDS = 3.0

    started_account = pyqtSignal(str)
    finished_account = pyqtSignal(str, object)  # (steam_id, CheckResult)
    drained = pyqtSignal()

    def __init__(self, ctrl) -> None:
        super().__init__()
        self._ctrl = ctrl
        self._queue = AccountCheckQueue()
        self._lock = threading.Lock()
        self._source = None
        self._sleep = time.sleep
        # A batch enqueued while run() is exiting would otherwise sit unprocessed.
        self.finished.connect(self._restart_if_pending)

    def enqueue(self, steam_ids: list[str], steps: CheckSteps | None = None) -> int:
        with self._lock:
            added = self._queue.add(steam_ids, steps)
        if added and not self.isRunning():
            self.start()
        return added

    def clear_pending(self) -> list[str]:
        """Drop everything still queued (the running check finishes)."""
        with self._lock:
            return self._queue.clear()

    def _restart_if_pending(self) -> None:
        with self._lock:
            pending = len(self._queue)
        if pending and not self.isRunning():
            self.start()

    def _source_loadout(self, steam_id: str, steps: CheckSteps | None) -> SourceLoadout:
        """The source loadout for ``steam_id``, read at most once per drain and
        only when it could matter: this item's loadout step is on (falling
        back to the user's settings when ``steps`` is None), a source is set,
        and this account isn't the source itself (reading it would be a
        pointless extra CM logon — the service already skips the loadout step
        when target == source)."""
        loadout_on = steps.loadout if steps is not None else self._ctrl.account_check_steps().loadout
        if not loadout_on:
            return SourceLoadout(reason="loadout step off")
        wanted = self._ctrl.cs2_config_source()
        if not wanted:
            return SourceLoadout(reason="no CS2 config source set")
        if steam_id == wanted:
            return SourceLoadout(steam_id=wanted)
        if self._source is None or self._source.steam_id != wanted:
            self._source = self._ctrl.read_source_loadout()
        return self._source

    def run(self) -> None:
        checked_any = False
        while True:
            with self._lock:
                more = len(self._queue) > 0
            if more and checked_any and self.CHECK_GAP_SECONDS > 0:
                self._sleep(self.CHECK_GAP_SECONDS)
            with self._lock:
                item = self._queue.pop()
                sid, steps = item if item is not None else (None, None)
                self._queue.set_current(sid)
            if sid is None:
                break
            checked_any = True
            self.started_account.emit(sid)
            try:
                result = self._ctrl.check_account(
                    sid, source=self._source_loadout(sid, steps), steps=steps
                )
            except Exception:  # noqa: BLE001 - never crash the worker thread
                logger.exception("account-check: worker failed for %s", sid)
                result = None
            self.finished_account.emit(sid, result)
        # The cached source loadout is only valid for this drain — a later
        # drain (even with the same source setting) re-reads it, so a stale
        # loadout from before the source account's own last check is never
        # copied onto a later batch.
        self._source = None
        self.drained.emit()
