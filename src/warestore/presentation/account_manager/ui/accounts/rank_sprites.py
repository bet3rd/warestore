# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""CS2 rank sprite loading + rating/rank maps for the account card.

Premier is a colored tier banner (0-6, by CS-Rating band); the rating number is
drawn on top by the card. Wingman is one of the 18 skill-group emblems (1-18);
id 0 is Valve's "unranked" badge, which the card treats as "no rank" and skips.
Pixmaps are cached (kind, id, size) so the grid repaints cheaply.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap

# CS-Rating tier boundaries; tier = how many boundaries the rating clears (0-6).
_PREMIER_BOUNDS = (5000, 10000, 15000, 20000, 25000, 30000)

# rank_id (rank_type_id 7) -> display name, for the tooltip.
WINGMAN_NAMES = {
    1: "Silver I", 2: "Silver II", 3: "Silver III", 4: "Silver IV",
    5: "Silver Elite", 6: "Silver Elite Master",
    7: "Gold Nova I", 8: "Gold Nova II", 9: "Gold Nova III", 10: "Gold Nova Master",
    11: "Master Guardian I", 12: "Master Guardian II", 13: "Master Guardian Elite",
    14: "Distinguished Master Guardian",
    15: "Legendary Eagle", 16: "Legendary Eagle Master",
    17: "Supreme Master First Class", 18: "The Global Elite",
}

_pixmap_cache: dict = {}
_source_cache: dict = {}


def _ranks_dir() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        return base / "assets" / "ranks"
    # src/warestore/presentation/account_manager/ui/accounts/rank_sprites.py -> repo root
    return Path(__file__).resolve().parents[6] / "assets" / "ranks"


def premier_tier(rating: int) -> int:
    return sum(rating >= b for b in _PREMIER_BOUNDS)


def has_premier(rating: int | None) -> bool:
    return bool(rating) and rating > 0


def has_wingman(rank_id: int | None) -> bool:
    return bool(rank_id) and 1 <= rank_id <= 18


def _load_source(path: Path) -> QPixmap:
    pm = _source_cache.get(path)
    if pm is None:
        pm = QPixmap(str(path))  # null QPixmap if the file is missing
        _source_cache[path] = pm
    return pm


def wingman_emblem(rank_id: int | None, height: int) -> QPixmap | None:
    """Skill-group emblem scaled to `height`. None if unranked / out of range."""
    if not has_wingman(rank_id):
        return None
    key = ("w", rank_id, height)
    pm = _pixmap_cache.get(key)
    if pm is None:
        src = _load_source(_ranks_dir() / "wingman" / f"{rank_id}.png")
        pm = src.scaledToHeight(height, Qt.SmoothTransformation) if not src.isNull() else src
        _pixmap_cache[key] = pm
    return None if pm.isNull() else pm
