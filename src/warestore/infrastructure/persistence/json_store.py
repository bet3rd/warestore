# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Shared JSON file persistence with consistent error handling."""

import json
import logging
from typing import Any

from warestore.infrastructure.persistence.atomic_write import atomic_write_text

logger = logging.getLogger(__name__)


class JsonStore:
    """A JSON-backed document on disk.

    A missing file is normal (first run) and returns the default silently;
    a corrupt or unreadable file is logged and also falls back to the default,
    instead of being indistinguishable from "no data".
    """

    def __init__(self, path: str) -> None:
        self._path = path

    def read(self, default: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return dict(default or {})
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"Could not read {self._path}: {exc}")
            return dict(default or {})

    def write(self, data: dict[str, Any]) -> None:
        # Serialize first, then swap the file in atomically: a crash mid-write
        # must never leave a truncated document behind.
        atomic_write_text(self._path, json.dumps(data, indent=2))
