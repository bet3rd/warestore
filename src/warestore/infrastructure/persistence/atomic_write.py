# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Crash-safe file replacement.

Writing straight into the destination (``open(path, "w")``) truncates it before
the new bytes land, so a crash, freeze, power loss, disk-full or antivirus lock
mid-write leaves a half-written file -- and for the token vault that means every
saved refresh token is gone, unrecoverably.

These helpers never touch the destination until the new contents are complete
and flushed to disk: write a uniquely-named temp file in the *same* directory
(so the final step is a same-filesystem rename), fsync it, then ``os.replace``
it over the target. ``os.replace`` is atomic on Windows and POSIX alike, so a
reader sees either the old file or the new one, never a truncated one. The temp
file is cleaned up if anything fails.

Serialization happens in the caller *before* these are invoked, so a value that
fails to encode can't destroy the existing file either.
"""

from __future__ import annotations

import logging
import os
import tempfile

logger = logging.getLogger(__name__)


def atomic_write_bytes(path: str, data: bytes) -> None:
    """Replace `path` with `data`, atomically. Raises OSError on failure."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)

    tmp_path: str | None = None
    try:
        # Same directory as the target: os.replace is only atomic within one
        # filesystem, and the system temp dir is often a different volume.
        fd, tmp_path = tempfile.mkstemp(
            dir=directory, prefix=f".{os.path.basename(path)}.", suffix=".tmp"
        )
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())  # durable before the rename, not just buffered
        os.replace(tmp_path, path)
        tmp_path = None  # ownership transferred; nothing to clean up
    finally:
        if tmp_path is not None and os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError as exc:  # pragma: no cover - best-effort cleanup
                logger.warning(f"Could not remove temp file {tmp_path}: {exc}")


def atomic_write_text(path: str, text: str, encoding: str = "utf-8") -> None:
    """Replace `path` with `text`, atomically."""
    atomic_write_bytes(path, text.encode(encoding))
