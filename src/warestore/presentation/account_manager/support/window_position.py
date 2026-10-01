# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Is a saved window position still on a screen?

A saved position can point off-screen: a monitor was unplugged, the layout
changed, or the position was saved in different units (before WareStore
followed Windows' display scale). Restoring it would leave the window
invisible, so it's only used when enough of the title bar lands on a screen
to grab and drag.
"""

from __future__ import annotations

from PyQt5.QtCore import QRect

TITLE_BAR_H = 32
_MIN_VISIBLE_W = 120
_MIN_VISIBLE_H = 20


def title_bar_visible(x: int, y: int, width: int, screens: list[QRect]) -> bool:
    """True when the title bar at (x, y) overlaps some screen's available
    area by at least 120x20 px."""
    bar = QRect(x, y, max(1, width), TITLE_BAR_H)
    for area in screens:
        hit = bar.intersected(area)
        if hit.width() >= _MIN_VISIBLE_W and hit.height() >= _MIN_VISIBLE_H:
            return True
    return False
