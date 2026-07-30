# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Routes the `warestore` logger into the in-app log panel and the console.

Domain/infrastructure code logs through the stdlib (`logging.getLogger(__name__)`)
and stays unaware of the UI. The presentation layer attaches the sinks here so
the existing `[*]`/`[!]`/`[warn]`/`[dbg]` look of the log panel is preserved.
"""

import logging
import sys

from warestore.presentation.account_manager.support.app_log import app_log

_LEVEL_PREFIX = {
    logging.DEBUG: "[dbg]",
    logging.INFO: "[*]",
    logging.WARNING: "[warn]",
    logging.ERROR: "[!]",
    logging.CRITICAL: "[!]",
}


class _PrefixFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        prefix = _LEVEL_PREFIX.get(record.levelno, "[*]")
        text = f"{prefix} {record.getMessage()}"
        if record.exc_info:
            text += "\n" + self.formatException(record.exc_info)
        return text


class _AppLogHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            app_log.append(self.format(record))
        except Exception:  # pragma: no cover - logging must never raise
            self.handleError(record)


def configure_logging(level: int = logging.INFO) -> logging.Logger:
    """Configure the `warestore` logger once; safe to call repeatedly."""
    logger = logging.getLogger("warestore")
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger

    formatter = _PrefixFormatter()

    app_handler = _AppLogHandler()
    app_handler.setFormatter(formatter)
    logger.addHandler(app_handler)

    # Mirror to the real console. Use the original stdout (not the tee in main),
    # so records reach the terminal without being re-appended to app_log.
    # In a windowed PyInstaller build there is no console — skip it then.
    if sys.__stdout__ is not None:
        console = logging.StreamHandler(sys.__stdout__)
        console.setFormatter(formatter)
        logger.addHandler(console)

    return logger
