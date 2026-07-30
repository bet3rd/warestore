# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""In-memory log ring buffer; stdout is tee'd here from main."""

from collections import deque


class AppLog:
    def __init__(self, max_lines: int = 400) -> None:
        self._buffer: deque[str] = deque(maxlen=max_lines)

    def append(self, line: str) -> None:
        text = line.rstrip("\n")
        if text:
            self._buffer.append(text)

    def lines(self) -> list[str]:
        return list(self._buffer)

    def clear(self) -> None:
        self._buffer.clear()


app_log = AppLog()
