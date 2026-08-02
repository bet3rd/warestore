# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import io
import os
import urllib.request

from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPixmap
from PyQt5.QtWidgets import QApplication

from warestore.config.settings import ACCOUNT_MANAGER_DATA_DIR


def _dpr() -> float:
    """Effective device-pixel ratio (interface scale); 1.0 if no app yet.

    Avatars are rasters, so they render at this ratio (with setDevicePixelRatio)
    to stay crisp when the interface is scaled — needs AA_UseHighDpiPixmaps.
    """
    app = QApplication.instance()
    return float(app.devicePixelRatio()) if app is not None else 1.0


try:
    from PIL import Image as PILImage

    PIL_AVAILABLE = True
except ImportError:
    PILImage = None
    PIL_AVAILABLE = False

AVATAR_SIZE = 54

# Fresh avatars fetched via the Steam Web API are cached here, keyed by Steam's
# avatarhash, so an unchanged picture is only ever downloaded once.
_AVATAR_CACHE_DIR = os.path.join(ACCOUNT_MANAGER_DATA_DIR, "avatars")


def _make_circular_pixmap(src: QPixmap, size: int, dpr: float = 1.0) -> QPixmap:
    result = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    result.setDevicePixelRatio(dpr)  # paint in LOGICAL coords; crisp at scale
    result.fill(Qt.transparent)
    painter = QPainter(result)
    painter.setRenderHint(QPainter.Antialiasing)
    clip = QPainterPath()
    clip.addEllipse(0.0, 0.0, float(size), float(size))
    painter.setClipPath(clip)
    painter.drawPixmap(QRect(0, 0, size, size), src)
    painter.end()
    return result


def make_placeholder_pixmap(size: int, dpr: float | None = None) -> QPixmap:
    dpr = _dpr() if dpr is None else dpr
    pix = QPixmap(max(1, round(size * dpr)), max(1, round(size * dpr)))
    pix.setDevicePixelRatio(dpr)
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


def circular_avatar_from_file(path: str, dpr: float | None = None) -> QPixmap | None:
    """Load an image file into a circular AVATAR_SIZE pixmap. None on failure.

    Rendered at ``AVATAR_SIZE * dpr`` physical px (device-pixel ratio set) so the
    avatar stays crisp when the interface is scaled. Must run on the UI thread.
    """
    dpr = _dpr() if dpr is None else dpr
    phys = max(1, round(AVATAR_SIZE * dpr))
    try:
        if PIL_AVAILABLE:
            img = PILImage.open(path).convert("RGBA").resize(
                (phys, phys), PILImage.LANCZOS
            )
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            buf.seek(0)
            src = QPixmap()
            src.loadFromData(buf.read())
        else:
            src = QPixmap(path)
            if not src.isNull():
                src = src.scaled(
                    phys, phys, Qt.IgnoreAspectRatio, Qt.SmoothTransformation
                )
        if not src.isNull():
            return _make_circular_pixmap(src, AVATAR_SIZE, dpr)
    except Exception:
        pass
    return None


def load_avatar_pixmap(steam_dir: str, steamid64: str, dpr: float | None = None) -> QPixmap:
    dpr = _dpr() if dpr is None else dpr
    if steam_dir and steamid64:
        for ext in ("png", "jpg"):
            path = os.path.join(steam_dir, "config", "avatarcache", f"{steamid64}.{ext}")
            if os.path.exists(path):
                pix = circular_avatar_from_file(path, dpr)
                if pix is not None:
                    return pix
    return make_placeholder_pixmap(AVATAR_SIZE, dpr)


def cached_avatar_path(avatar_hash: str) -> str:
    return os.path.join(_AVATAR_CACHE_DIR, f"{avatar_hash}.jpg")


def avatar_for(
    steam_dir: str, steamid64: str, avatar_hash: str = "", dpr: float | None = None
) -> QPixmap:
    """Best available avatar for a card at build time.

    Prefers the freshly-fetched avatar cached under `avatar_hash` (persisted from
    the last status refresh), then Steam's own avatarcache, then a placeholder.
    """
    dpr = _dpr() if dpr is None else dpr
    if avatar_hash:
        path = cached_avatar_path(avatar_hash)
        if os.path.exists(path):
            pix = circular_avatar_from_file(path, dpr)
            if pix is not None:
                return pix
    return load_avatar_pixmap(steam_dir, steamid64, dpr)


def ensure_avatar_downloaded(url: str, avatar_hash: str, timeout: int = 10) -> str | None:
    """Download `url` into the hash-keyed cache if not already present.

    No Qt here — safe to call off the UI thread (from the status worker). Returns
    the cached file path, or None on failure / missing inputs. Because the file
    is keyed by avatarhash, an unchanged avatar is fetched only once.
    """
    if not url or not avatar_hash:
        return None
    path = cached_avatar_path(avatar_hash)
    if os.path.exists(path):
        return path
    tmp = path + ".part"
    try:
        os.makedirs(_AVATAR_CACHE_DIR, exist_ok=True)
        urllib.request.urlretrieve(url, tmp)
        os.replace(tmp, path)
        return path
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except OSError:
            pass
        return None
