# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Routes the `warestore` logger into the in-app log panel, the console, and a
persistent log file on disk.

Domain/infrastructure code logs through the stdlib (`logging.getLogger(__name__)`)
and stays unaware of the UI. The presentation layer attaches the sinks here so
the existing `[*]`/`[!]`/`[warn]`/`[dbg]` look of the log panel is preserved.

The on-disk log lives in a ``logs`` folder next to the rest of the user data
(under ``%APPDATA%/SteamLoginTool_CLI``) and rotates, so it survives restarts
and crashes without growing unbounded. It carries timestamps and logger names
that the terse panel format omits, which is what makes it useful for
after-the-fact debugging. File logging is best-effort: if the file can't be
opened (locked, read-only, disk full) the app still runs on panel + console.
"""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from warestore.config.settings import ACCOUNT_MANAGER_DATA_DIR
from warestore.presentation.account_manager.support.app_log import app_log

_LEVEL_PREFIX = {
    logging.DEBUG: "[dbg]",
    logging.INFO: "[*]",
    logging.WARNING: "[warn]",
    logging.ERROR: "[!]",
    logging.CRITICAL: "[!]",
}

LOG_DIR = os.path.join(ACCOUNT_MANAGER_DATA_DIR, "logs")
LOG_FILE = os.path.join(LOG_DIR, "warestore.log")

# 1 MB per file, 3 rolled backups -> ~4 MB worst case.
_MAX_BYTES = 1_000_000
_BACKUP_COUNT = 3


def log_file_path() -> str:
    """Absolute path of the current (un-rotated) log file."""
    return LOG_FILE


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


def _file_handler() -> logging.Handler | None:
    """A rotating file sink, or None if the log file can't be opened."""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_FILE,
            maxBytes=_MAX_BYTES,
            backupCount=_BACKUP_COUNT,
            encoding="utf-8",
        )
    except OSError:
        # No writable data dir: keep the panel/console sinks rather than dying.
        return None
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


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

    file_handler = _file_handler()
    if file_handler is not None:
        logger.addHandler(file_handler)
    else:
        logger.warning("Could not open the log file at %s - logging to screen only", LOG_FILE)

    return logger
