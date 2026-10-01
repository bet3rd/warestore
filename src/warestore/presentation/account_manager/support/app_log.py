# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""In-memory log ring buffer; stdout is tee'd here from main.

Written from worker threads (account checks, status fetches) and read by the
log panel on the Qt thread, so access is locked. ``version`` moves on every
change, letting the panel redraw only when there's something new.
"""

import threading
from collections import deque


class AppLog:
    def __init__(self, max_lines: int = 400) -> None:
        self._buffer: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    def append(self, line: str) -> None:
        text = line.rstrip("\n")
        if text:
            with self._lock:
                self._buffer.append(text)
                self._version += 1

    def lines(self) -> list[str]:
        with self._lock:
            return list(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
            self._version += 1


app_log = AppLog()
