# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""User-selectable accent colour: one base colour -> every shade the UI uses.

The QSS files reference shades as ``@accent``-style tokens; ``render_qss`` fills
them in. Painted widgets read ``current()`` at paint time so a live change only
needs a restyle + repaint.
"""

import re
from dataclasses import dataclass

from PyQt5.QtGui import QColor

DEFAULT_ACCENT = "#880808"

ACCENT_PRESETS: tuple[tuple[str, str], ...] = (
    ("Red", DEFAULT_ACCENT),
    ("Blue", "#1f5fa8"),
    ("Purple", "#6a2fa8"),
    ("Green", "#2e7d3a"),
    ("Orange", "#b3560f"),
    ("Pink", "#a8286e"),
)

_PANEL_BG = QColor("#141414")
_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")
_TOKEN_RE = re.compile(r"@([a-z][a-z-]*)")


@dataclass(frozen=True)
class AccentShades:
    base: str
    hover: str
    pressed: str
    disabled_bg: str
    disabled_text: str
    border: str  # checked checkbox outline
    bright: str  # accent used as text / icon on the dark background
    bright_hover: str
    sel_bg: str  # selected account card
    sel_border: str
    on_accent: str  # text drawn on top of `base`


# The original hand-tuned red, kept exact so the default look doesn't shift.
_DEFAULT_SHADES = AccentShades(
    base="#880808",
    hover="#a00a0a",
    pressed="#660606",
    disabled_bg="#3a1616",
    disabled_text="#6a3030",
    border="#aa1010",
    bright="#cc4444",
    bright_hover="#e46060",
    sel_bg="#261a1a",
    sel_border="#cc1111",
    on_accent="#ffffff",
)


def parse_hex(value) -> str | None:
    """Lower-case ``#rrggbb`` for ``#rgb`` / ``rrggbb`` / … input, else None."""
    if not isinstance(value, str):
        return None
    m = _HEX_RE.match(value.strip())
    if not m:
        return None
    digits = m.group(1).lower()
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return "#" + digits


def normalize_accent(value) -> str:
    """Lower-case ``#rrggbb`` for a valid hex colour, else the default."""
    return parse_hex(value) or DEFAULT_ACCENT


def _mix(a: QColor, b: QColor, t: float) -> str:
    return QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
    ).name()


def accent_shades(accent: str) -> AccentShades:
    accent = normalize_accent(accent)
    if accent == DEFAULT_ACCENT:
        return _DEFAULT_SHADES
    base = QColor(accent)
    h, s, l, _ = base.getHslF()
    h = max(h, 0.0)  # achromatic colours report hue -1
    bright = QColor.fromHslF(h, min(1.0, s * 0.85 + 0.1), min(0.8, max(0.52, l + 0.25)))
    luminance = 0.2126 * base.redF() + 0.7152 * base.greenF() + 0.0722 * base.blueF()
    return AccentShades(
        base=base.name(),
        hover=base.lighter(118).name(),
        pressed=base.darker(133).name(),
        disabled_bg=_mix(_PANEL_BG, base, 0.28),
        disabled_text=_mix(_PANEL_BG, base, 0.5),
        border=base.lighter(125).name(),
        bright=bright.name(),
        bright_hover=bright.lighter(115).name(),
        sel_bg=_mix(_PANEL_BG, base, 0.12),
        sel_border=QColor.fromHslF(h, s, min(0.8, max(0.42, l + 0.1))).name(),
        on_accent="#ffffff" if luminance < 0.55 else "#101010",
    )


def render_qss(template: str, shades: AccentShades) -> str:
    """Replace ``@accent``, ``@accent-hover``, ``@on-accent`` … with colours."""
    values = {
        "accent": shades.base,
        "accent-hover": shades.hover,
        "accent-pressed": shades.pressed,
        "accent-disabled-bg": shades.disabled_bg,
        "accent-disabled-text": shades.disabled_text,
        "accent-border": shades.border,
        "accent-bright": shades.bright,
        "accent-bright-hover": shades.bright_hover,
        "on-accent": shades.on_accent,
    }
    return _TOKEN_RE.sub(lambda m: values[m.group(1)], template)


_current = _DEFAULT_SHADES


def current() -> AccentShades:
    return _current


def set_current(accent: str) -> AccentShades:
    global _current
    _current = accent_shades(accent)
    return _current
