# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import io
import os

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap

try:
    from PIL import Image as PILImage

    PIL_AVAILABLE = True
except ImportError:
    PILImage = None
    PIL_AVAILABLE = False

AVATAR_SIZE = 54


def _make_circular_pixmap(src: QPixmap, size: int) -> QPixmap:
    result = QPixmap(size, size)
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0.0, 0.0, float(size), float(size))
    painter.setClipPath(clip)
    painter.drawPixmap(QRect(0, 0, size, size), src)
    painter.end()
    return result


def make_placeholder_pixmap(size: int) -> QPixmap:
    pix = QPixmap(size, size)
    pix.fill(Qt.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(QColor("#303038")))
    painter.drawEllipse(0, 0, size, size)
    clip = QPainterPath()
    clip.addEllipse(0.0, 0.0, float(size), float(size))
    painter.setClipPath(clip)
    head_r = size // 5
    cx = size // 2
    painter.setBrush(QBrush(QColor("#585860")))
    painter.drawEllipse(cx - head_r, size // 4, head_r * 2, head_r * 2)
    body_w, body_h = int(size * 0.6), int(size * 0.45)
    painter.drawEllipse((size - body_w) // 2, size // 2 + head_r // 2, body_w, body_h)
    painter.end()
    return pix


def load_avatar_pixmap(steam_dir: str, steamid64: str) -> QPixmap:
    if steam_dir and steamid64:
        for ext in ("png", "jpg"):
            path = os.path.join(steam_dir, "config", "avatarcache", f"{steamid64}.{ext}")
            if os.path.exists(path):
                try:
                    if PIL_AVAILABLE:
                        img = PILImage.open(path).convert("RGBA").resize(
                            (AVATAR_SIZE, AVATAR_SIZE),
                            PILImage.LANCZOS,
                        )
                        buf = io.BytesIO()
                        img.save(buf, format="PNG")
                        buf.seek(0)
                        src = QPixmap()
                        src.loadFromData(buf.read())
                        if not src.isNull():
                            return _make_circular_pixmap(src, AVATAR_SIZE)
                    else:
                        src = QPixmap(path)
                        if not src.isNull():
                            src = src.scaled(
                                AVATAR_SIZE,
                                AVATAR_SIZE,
                                Qt.IgnoreAspectRatio,
                                Qt.SmoothTransformation,
                            )
                            return _make_circular_pixmap(src, AVATAR_SIZE)
                except Exception:
                    pass
    return make_placeholder_pixmap(AVATAR_SIZE)
