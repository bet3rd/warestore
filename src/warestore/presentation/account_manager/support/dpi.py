# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Display scaling: Windows' per-monitor scale, times the user's Interface scale.

Qt follows each monitor's Windows scale (``AA_EnableHighDpiScaling`` with the
exact, unrounded factor — Qt5 would otherwise round 150% up to 200%), and the
Interface scale setting multiplies on top via ``QT_SCALE_FACTOR``.

Before this, the app ignored Windows' scale and the Interface scale was the
only factor, so users raised it to compensate. Its meaning changed, so it is
reset to 100% once (``dpi_scale_follows_windows`` marks that it happened).
"""

from __future__ import annotations

MIGRATED_KEY = "dpi_scale_follows_windows"


def migrate_interface_scale(settings: dict) -> bool:
    """Reset the Interface scale to 100% the first time this version runs.
    Returns True when ``settings`` changed and should be saved."""
    if settings.get(MIGRATED_KEY):
        return False
    settings["dpi_scale"] = 100
    settings[MIGRATED_KEY] = True
    return True


def scale_factor_env(settings: dict) -> str | None:
    """The QT_SCALE_FACTOR value for the Interface scale, or None for 100%."""
    try:
        scale = int(settings.get("dpi_scale", 100) or 100)
    except (TypeError, ValueError):
        return None
    if scale <= 0 or scale == 100:
        return None
    return str(scale / 100)
