# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from __future__ import annotations

import time

from PyQt5.QtCore import (
    QByteArray,
    QEasingCurve,
    QPoint,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetrics,
    QImage,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtWidgets import QGraphicsOpacityEffect, QLabel, QWidget

from warestore.application.account_manager.view_models import (
    AccountCardMenuState,
    AccountCardViewState,
)
from warestore.domain.accounts.cooldown import (
    format_cooldown_remaining,
    format_cooldown_short,
)
from warestore.domain.auth.formatters import JWT_NO_TOKEN, format_jwt_expiry_label
from warestore.presentation.account_manager.ui.accounts.account_card_menu import (
    show_account_card_menu,
)
from warestore.presentation.account_manager.ui.avatars import (
    AVATAR_SIZE,
    circular_avatar_from_file,
    make_placeholder_pixmap,
)
from warestore.presentation.account_manager.ui.accounts.rank_sprites import (
    WINGMAN_NAMES,
    has_premier,
    has_wingman,
    premier_tier,
    wingman_emblem,
)

_STATUS_COLORS: dict[int, QColor] = {
    0: QColor("#505050"),
    1: QColor("#4a9eda"),  # online = blue
    2: QColor("#e07b39"),
    3: QColor("#c9a227"),
    4: QColor("#8a7a3a"),
}
_IN_GAME_COLOR = QColor("#5ba85e")  # in-game = green
_COOLDOWN_ACCENT = QColor("#d4a017")
# Translucent light hairline so the separator reads on any card background —
# plain, colour-tagged (the wash would swallow a fixed dark line), or selected.
_DIVIDER = QColor(255, 255, 255, 28)

# CS2 Premier (CS-Rating) tier palette (0-6): (accent border, number text, dark
# bg). Tiers are the 5000-rating bands (premier_tier): <5k grey, 5k blue, 10k
# blue, 15k purple, 20k pink, 25k red, 30k+ gold. The number is drawn in the text
# colour on the dark bg.
_PREMIER_TIERS = (
    ("#b1c4d9", "#eef2f7", "#2c2f37"),  # 0
    ("#5e98d9", "#8bc1ff", "#061c36"),  # 1
    ("#4c6aff", "#8a9dfe", "#060e37"),  # 2
    ("#8847ff", "#b48bff", "#180638"),  # 3
    ("#d32ce6", "#f177ff", "#320638"),  # 4
    ("#eb4b4b", "#ff8686", "#380606"),  # 5
    ("#ffd700", "#ffdf35", "#383006"),  # 6
)
# Number text colour per tier, for the rich tooltip (dark tooltip bg).
_PREMIER_TIER_COLORS = tuple(text for _a, text, _b in _PREMIER_TIERS)

# The Premier rating badge is skewed by -10deg; tan(10°) ≈ 0.176.
_PREM_SKEW = 0.176

# The two slanted accent bars for the Premier badge (SVG path, viewBox 17x32);
# the path is already slanted, so it is drawn upright (no shear). Filled per tier.
_BARS_PATH = (
    "M5.44 2.13A2.6 2.6 0 0 1 7.99 0h1.86a.6.6 0 0 1 .6.7L4.83 31.5a.6.6 0 0 1-.6.5h-2.3"
    "c-1 0-1.76-.9-1.58-1.89l5.1-27.98ZM11.82.99c.1-.57.6-.99 1.18-.99h2.93a.6.6 0 0 1 .59.7"
    "l-5.4 30.31c-.1.57-.6.99-1.18.99H7a.6.6 0 0 1-.59-.7L11.82.98Z"
)
_bars_cache: dict = {}
# The rating number is thick and tiny; render the whole badge at this factor and
# downscale so the bold Poppins stays crisp (open counters) instead of clogging.
_PREM_SS = 3
_badge_cache: dict = {}


def _premier_bars(accent: str, h: int) -> QPixmap:
    key = (accent, h)
    pm = _bars_cache.get(key)
    if pm is None:
        w = max(1, round(h * 17 / 32))
        svg = (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 17 32" '
            f'width="{w}" height="{h}"><path d="{_BARS_PATH}" fill="{accent}"/></svg>'
        )
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pm = QPixmap(w, h)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        renderer.render(p)
        p.end()
        _bars_cache[key] = pm
    return pm

_POPPINS: dict[int, str] = {}  # weight -> loaded family name
_POPPINS_LOADED = False


def _load_poppins() -> None:
    """Load the bundled Poppins ExtraBold once (the CS2 rating font). Falls back
    to Segoe UI silently if the asset isn't present."""
    global _POPPINS_LOADED
    if _POPPINS_LOADED:
        return
    _POPPINS_LOADED = True
    import sys
    from pathlib import Path

    from PyQt5.QtGui import QFontDatabase

    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "assets" / "fonts"
    else:
        base = Path(__file__).resolve().parents[6] / "assets" / "fonts"
    try:
        ttf = base / "Poppins-ExtraBold.ttf"
        if ttf.exists():
            fid = QFontDatabase.addApplicationFont(str(ttf))
            fams = QFontDatabase.applicationFontFamilies(fid)
            if fams:
                _POPPINS[800] = fams[0]
    except Exception:  # noqa: BLE001 - font is cosmetic
        pass


def _rating_font(px: int, weight: int = 800) -> QFont:
    _load_poppins()
    fam = _POPPINS.get(800)
    f = QFont(fam if fam else "Segoe UI")
    f.setPixelSize(px)
    if not fam:
        f.setWeight(QFont.Black if weight >= 800 else QFont.Bold)
    return f


class AccountCard(QWidget):
    # Portrait card: avatar + name up top, a divider, then a single footer line
    # carrying the CS2 rank / cooldown badges (see _paint_footer). 4 per row.
    CARD_W = 150
    CARD_H = 160
    SUB_H = 13
    AVATAR_DISP = 60
    RADIUS = 10.0

    AVATAR_Y = 20          # avatar top; centred horizontally
    NAME_Y = 84            # persona name band
    NAME_H = 18
    DIVIDER_Y = 112        # hairline splitting identity (above) from data (below)
    FOOTER_CY = 134        # centred in the below-divider zone (not pinned high)

    _SUB_STYLE_DEFAULT = "color: #787878; background: transparent; border: none;"
    _SUB_STYLE_JWT = "color: #aa5544; background: transparent; border: none;"

    _BASE_R, _BASE_G, _BASE_B = 0x1E, 0x1E, 0x1E
    _HOV_R, _HOV_G, _HOV_B = 0x2E, 0x2A, 0x2A
    _SEL_BG = QColor("#261a1a")
    _SEL_BORDER = QColor("#cc1111")

    clicked = pyqtSignal(object, object)
    double_clicked = pyqtSignal(object)
    relogin_requested = pyqtSignal(object)

    def __init__(self, acc: dict, avatar: QPixmap, parent=None):
        super().__init__(parent)
        self.acc = acc
        self._sel = False
        self._t = 0.0
        self._status_state: int = -1
        self._status_game: str = ""
        self._status_stale: bool = False
        self._expiry_label: str = ""
        self._jwt_expires_in: int | None = None
        self._cooldown_expires: int = 0
        self._cooldown_active: bool = False
        self._color: str = ""
        self._ban: dict | None = None
        self._level: int | None = None
        self._premier_rating: int = 0
        self._premier_wins: int = -1
        self._wingman_rank: int = 0
        self._wingman_wins: int = -1
        self._cs2_cooldown_expires: int = 0
        self._menu_state = AccountCardMenuState(
            username=acc.get("account_name", ""),
            steam_id=acc.get("steamid", ""),
            saved_token="",
            has_saved_token=False,
            has_cooldown=False,
        )
        self._hovering: bool = False

        self.setFixedSize(self.CARD_W, self.CARD_H)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_NoSystemBackground)
        self.setAttribute(Qt.WA_Hover)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(180)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)

        # Scale-down-on-press so a card acknowledges the click (Emil: pressable
        # things must feel heard). Springs back on release; interruptible.
        self._press_scale = 1.0
        self._press_anim = QVariantAnimation(self)
        self._press_anim.setDuration(120)
        self._press_anim.setEasingCurve(QEasingCurve.OutQuint)
        self._press_anim.valueChanged.connect(self._on_press_anim)

        # Fixed skeleton (no layout): every card places avatar/name at the same Y,
        # so the grid reads as a clean matrix regardless of a card's data.
        self._avatar_label = QLabel(self)
        self._avatar_label.setFixedSize(self.AVATAR_DISP, self.AVATAR_DISP)
        self._avatar_label.move((self.CARD_W - self.AVATAR_DISP) // 2, self.AVATAR_Y)
        self._avatar_label.setScaledContents(True)
        self._avatar_label.setAlignment(Qt.AlignCenter)
        self._avatar_label.setStyleSheet("background: transparent; border: none;")
        self._avatar_label.setPixmap(
            avatar if (avatar and not avatar.isNull()) else make_placeholder_pixmap(AVATAR_SIZE)
        )

        display = acc.get("persona_name") or acc.get("account_name", "")
        name_font = QFont("Segoe UI", 10, QFont.Bold)
        self._nm_lbl = QLabel(self)
        self._nm_lbl.setFont(name_font)
        self._nm_lbl.setAlignment(Qt.AlignCenter)
        self._nm_lbl.setGeometry(8, self.NAME_Y, self.CARD_W - 16, self.NAME_H)
        self._nm_lbl.setStyleSheet("color: #b8b8b8; background: transparent; border: none;")
        self._nm_lbl.setText(
            QFontMetrics(name_font).elidedText(display, Qt.ElideRight, self.CARD_W - 16)
        )

        # Sub-label: token/JWT health, revealed on hover/selection. Slides up from
        # below the card into a slot beneath the footer line.
        self._sub_lbl = QLabel("", self)
        self._sub_lbl.setAlignment(Qt.AlignCenter)
        self._sub_lbl.setFont(QFont("Segoe UI", 8))
        self._sub_lbl.setGeometry(8, self.CARD_H, self.CARD_W - 16, self.SUB_H)
        self._sub_eff = QGraphicsOpacityEffect(self._sub_lbl)
        self._sub_eff.setOpacity(0.0)
        self._sub_lbl.setGraphicsEffect(self._sub_eff)

        # Reveal easing: strong ease-out (Emil ≈ cubic-bezier(0.23,1,0.32,1)).
        # Durations are set per-direction in _run_sub_anims so pos + opacity stay
        # in sync and the exit is snappier than the deliberate enter.
        self._sub_pos_anim = QPropertyAnimation(self._sub_lbl, b"pos", self)
        self._sub_pos_anim.setEasingCurve(QEasingCurve.OutQuint)
        self._sub_op_anim = QPropertyAnimation(self._sub_eff, b"opacity", self)
        self._sub_op_anim.setEasingCurve(QEasingCurve.OutQuint)
        self._sub_visible = False
        self._update_sub_content()

        # Restore any cached CS2 rank/cooldown so a grid reload doesn't wipe a
        # previous on-demand fetch.
        self.set_cs2_rank(
            acc.get("premier_rating", -1),
            acc.get("wingman_rank", -1),
            acc.get("cs2_cooldown_expires", 0),
            acc.get("premier_wins", -1),
            acc.get("wingman_wins", -1),
        )

    @property
    def menu_state(self) -> AccountCardMenuState:
        return self._menu_state

    @property
    def color_tag(self) -> str:
        return self._color

    @property
    def is_on_cooldown(self) -> bool:
        return self._cooldown_active

    @property
    def is_banned(self) -> bool:
        return self._ban_color() is not None

    def set_selected(self, selected: bool):
        self._sel = selected
        if not selected:
            self._t = 0.0
            self._nm_lbl.setStyleSheet("color: #b8b8b8; background: transparent; border: none;")
        else:
            self._nm_lbl.setStyleSheet("color: #ffffff; background: transparent; border: none;")
        self._update_sub_content()
        self._sync_sub_visibility()
        self.update()

    def set_status(self, state: int, game: str, *, stale: bool = False) -> None:
        self._status_state = state
        self._status_game = game
        self._status_stale = stale
        self._refresh_tooltip()
        self.update()

    def set_ban_info(self, info: dict | None) -> None:
        self._ban = info or None
        self._refresh_tooltip()
        self.update()

    def set_level(self, level: int | None) -> None:
        self._level = level
        self._refresh_tooltip()
        self.update()

    def set_cs2_rank(
        self,
        premier_rating: int = 0,
        wingman_rank: int = 0,
        cooldown_expires: int = 0,
        premier_wins: int = -1,
        wingman_wins: int = -1,
    ) -> None:
        """CS2 Premier rating + Wingman rank id + competitive-cooldown expiry.

        Ranks of 0/-1 are unranked (drawn as nothing). Wins of -1 are unknown
        (omitted from the tooltip). A live cooldown expiry overrides the manual
        switch-cooldown shown on the card.
        """
        self._premier_rating = premier_rating or 0
        self._premier_wins = premier_wins
        self._wingman_rank = wingman_rank or 0
        self._wingman_wins = wingman_wins
        self._cs2_cooldown_expires = cooldown_expires or 0
        if self._timed_cooldown_active():
            self._set_cooldown(self._cs2_cooldown_expires)
        self._refresh_tooltip()
        self.update()

    # An expiry further out than any real timed cooldown (Steam uses a far-future
    # value for a "Never"/permanent cooldown) is a PERMANENT competitive ban — it
    # renders as a game ban, not a ticking cooldown.
    _PERMANENT_AFTER = 5 * 365 * 86400

    def _timed_cooldown_active(self) -> bool:
        rem = self._cs2_cooldown_expires - int(time.time())
        return 0 < rem <= self._PERMANENT_AFTER

    def _permanent_cooldown(self) -> bool:
        return self._cs2_cooldown_expires - int(time.time()) > self._PERMANENT_AFTER

    def set_persona(self, name: str) -> None:
        """Update the displayed persona name (e.g. from a status refresh)."""
        if not name or name == self.acc.get("persona_name"):
            return
        self.acc["persona_name"] = name
        metrics = QFontMetrics(self._nm_lbl.font())
        self._nm_lbl.setText(metrics.elidedText(name, Qt.ElideRight, self.CARD_W - 16))
        self._refresh_tooltip()

    def set_avatar_from_file(self, path: str) -> None:
        """Swap in a freshly-fetched avatar from a cached image file."""
        pix = circular_avatar_from_file(path)
        if pix is not None and not pix.isNull():
            self._avatar_label.setPixmap(pix)

    def _ban_rows(self) -> list[tuple[str, str]]:
        """(text, colour) for each active ban, most-severe first."""
        b = self._ban
        if not b:
            return []
        rows: list[tuple[str, str]] = []
        if b.get("vac"):
            n = b.get("vac_count", 0)
            rows.append((f"VAC banned ×{n}" if n > 1 else "VAC banned", "#d05555"))
        if b.get("game_bans"):
            n = b["game_bans"]
            head = f"Game ban ×{n}" if n > 1 else "Game ban"
            rows.append((f"{head} · {b.get('days_since', 0)}d ago", "#d05555"))
        if b.get("trade", "none") not in ("none", ""):
            rows.append((f"Trade hold · {b['trade']}", "#e07b39"))
        if b.get("community"):
            rows.append(("Community banned", "#e07b39"))
        return rows

    def _ban_color(self) -> QColor | None:
        # A permanent ("Never") competitive cooldown is effectively a game ban.
        if self._permanent_cooldown():
            return QColor("#cc3333")
        b = self._ban
        if not b:
            return None
        if b.get("vac") or b.get("game_bans"):
            return QColor("#cc3333")
        if b.get("community") or b.get("trade", "none") not in ("none", ""):
            return QColor("#e07b39")
        return None

    _STATUS_LABELS = {0: "Offline", 1: "Online", 2: "Away", 3: "Snooze", 4: "Busy"}

    def _status_tip(self) -> tuple[str, str] | None:
        """(text, colour) describing the live status, or None if unknown."""
        if self._status_state < 0:
            return None
        if self._status_stale:
            return ("Status unavailable", "#8a7a5a")
        if self._status_game:
            return (f"In-game · {self._status_game}", _IN_GAME_COLOR.name())
        colour = _STATUS_COLORS.get(self._status_state, _STATUS_COLORS[0]).name()
        return (self._STATUS_LABELS.get(self._status_state, "Online"), colour)

    def _token_tip(self) -> tuple[str, str] | None:
        """(text, colour) for token health: green healthy, gold soon, red gone."""
        v = self._jwt_expires_in
        if v is None:
            return None
        if v == JWT_NO_TOKEN:
            return ("No token", "#d05555")
        if v < 0:
            return ("Expired", "#d05555")
        days, rem = divmod(v, 86400)
        hours = rem // 3600
        if days >= 1:
            span = f"{days}d {hours}h" if hours else f"{days}d"
        elif hours >= 1:
            span = f"{hours}h"
        else:
            span = f"{max(1, v // 60)}m"
        colour = "#d4a017" if v < 2 * 86400 else "#5ba85e"
        return (f"Valid · {span} left", colour)

    @staticmethod
    def _esc(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    @staticmethod
    def _wins_suffix(wins: int) -> str:
        """' - N Wins' appended to a rank in the tooltip. Empty when unknown (-1)."""
        if wins < 0:
            return ""
        return f"<span style='color:#8a8a8a'> - {wins:,} {'Win' if wins == 1 else 'Wins'}</span>"

    def _refresh_tooltip(self) -> None:
        esc = self._esc
        persona = self.acc.get("persona_name") or self.acc.get("account_name", "")
        login = self.acc.get("account_name", "")
        steamid = self.acc.get("steamid", "")

        rows: list[tuple[str, str]] = []  # (label, value-html)
        if self._level is not None:
            rows.append(("Level", f"<span style='color:#d6d6d6'>{self._level}</span>"))
        status = self._status_tip()
        if status:
            rows.append((
                "Status",
                f"<span style='color:{status[1]}'>&#9679;</span>&nbsp;"
                f"<span style='color:#d6d6d6'>{esc(status[0])}</span>",
            ))
        if has_premier(self._premier_rating):
            tier_c = _PREMIER_TIER_COLORS[premier_tier(self._premier_rating)]
            prem = f"<span style='color:{tier_c};font-weight:600'>{self._premier_rating:,}</span>"
            rows.append(("Premier", prem + self._wins_suffix(self._premier_wins)))
        if has_wingman(self._wingman_rank):
            wing = f"<span style='color:#c9b06a'>{esc(WINGMAN_NAMES.get(self._wingman_rank, ''))}</span>"
            rows.append(("Wingman", wing + self._wins_suffix(self._wingman_wins)))
        if self._permanent_cooldown():
            rows.append(("Cooldown", "<span style='color:#d05555;font-weight:600'>Never · manual</span>"))
        elif self._cooldown_active:
            full = format_cooldown_remaining(self._cooldown_expires)  # tooltip: with minutes
            rows.append((
                "Cooldown",
                f"<span style='color:#d4a017;font-weight:600'>{esc(full)}</span>",
            ))
        for text, colour in self._ban_rows():
            rows.append((
                "Ban",
                f"<span style='color:{colour};font-weight:600'>&#9888; {esc(text)}</span>",
            ))
        token = self._token_tip()
        if token:
            rows.append(("Token", f"<span style='color:{token[1]}'>{esc(token[0])}</span>"))
        if self._color and QColor(self._color).isValid():
            rows.append((
                "Tag",
                f"<span style='color:{self._color};font-size:12pt'>&#9632;</span>",
            ))

        body = "".join(
            "<tr>"
            f"<td style='color:#6f6f6f;padding:1px 12px 1px 0;white-space:nowrap'>{label}</td>"
            f"<td style='padding:1px 0;white-space:nowrap'>{value}</td>"
            "</tr>"
            for label, value in rows
        )
        sub_parts = []
        if login and login != persona:
            sub_parts.append(esc(login))
        if steamid:
            sub_parts.append(f"<span style='color:#5f5f5f'>{esc(steamid)}</span>")
        subline = (
            f"<div style='color:#8a8a8a;margin-top:2px'>{' · '.join(sub_parts)}</div>"
            if sub_parts
            else ""
        )
        table = (
            f"<table cellspacing='0' cellpadding='0' style='margin-top:6px'>{body}</table>"
            if body
            else ""
        )
        self.setToolTip(
            "<div style='font-family:Segoe UI'>"
            f"<span style='font-size:11pt;font-weight:600;color:#ffffff'>{esc(persona)}</span>"
            f"{subline}{table}</div>"
        )

    def set_jwt_expiry(self, expires_in: int) -> None:
        self._jwt_expires_in = expires_in
        self._expiry_label = format_jwt_expiry_label(expires_in)
        self._update_sub_content()
        self._sync_sub_visibility()

    def set_view_state(self, state: AccountCardViewState) -> None:
        self._menu_state = state.menu
        self._color = state.color
        self.set_jwt_expiry(state.jwt_expires_in)
        # A live *timed* CS2 competitive cooldown overrides the manual
        # switch-cooldown, so re-applying card metadata can't wipe a freshly
        # fetched cooldown. (A permanent one shows as a ban, not a cooldown.)
        if self._timed_cooldown_active():
            self._set_cooldown(self._cs2_cooldown_expires)
        else:
            self._set_cooldown(state.cooldown_expires)
        self._refresh_tooltip()
        self.update()

    def _set_cooldown(self, expires: int) -> None:
        """Store the cooldown EXPIRY so the card can format it two ways: a short
        label on the footer (hours-only above an hour) and the full label in the
        tooltip (with minutes)."""
        self._cooldown_expires = expires or 0
        self._cooldown_active = 0 < (self._cooldown_expires - int(time.time()))
        self._refresh_tooltip()
        self.update()

    def _sub_y_show(self) -> int:
        return self.CARD_H - self.SUB_H - 1  # token line tucked against the bottom

    def _sub_y_hide(self) -> int:
        return self.CARD_H

    def _update_sub_content(self) -> None:
        # Reveal the token/JWT health on hover or selection; the footer line owns
        # rank/cooldown at rest, so the sub-label carries only the expiry now.
        if (self._hovering or self._sel) and self._expiry_label:
            metrics = QFontMetrics(self._sub_lbl.font())
            text = metrics.elidedText(self._expiry_label, Qt.ElideRight, self.CARD_W - 12)
            style = self._SUB_STYLE_JWT
        else:
            text = ""
            style = self._SUB_STYLE_DEFAULT
        self._sub_lbl.setText(text)
        self._sub_lbl.setStyleSheet(style)
        self._refresh_tooltip()

    def _sync_sub_visibility(self) -> None:
        show = bool(self._sub_lbl.text()) and (self._hovering or self._sel)
        self._run_sub_anims(show)

    def _run_sub_anims(self, show: bool) -> None:
        if show and not self._sub_lbl.text():
            show = False
        if show == self._sub_visible:
            if show:
                self._update_sub_content()
            return
        self._sub_visible = show
        y = self._sub_y_show() if show else self._sub_y_hide()
        opacity = 1.0 if show else 0.0
        # Enter is deliberate; exit gets out of the way fast. Same duration on
        # both properties keeps the slide and fade finishing together.
        dur = 180 if show else 130

        self._sub_pos_anim.stop()
        self._sub_pos_anim.setDuration(dur)
        self._sub_pos_anim.setStartValue(self._sub_lbl.pos())
        self._sub_pos_anim.setEndValue(QPoint(8, y))
        self._sub_pos_anim.start()

        self._sub_op_anim.stop()
        self._sub_op_anim.setDuration(dur)
        self._sub_op_anim.setStartValue(self._sub_eff.opacity())
        self._sub_op_anim.setEndValue(opacity)
        self._sub_op_anim.start()

    def _lerp_bg(self) -> QColor:
        t = self._t
        return QColor(
            int(self._BASE_R + (self._HOV_R - self._BASE_R) * t),
            int(self._BASE_G + (self._HOV_G - self._BASE_G) * t),
            int(self._BASE_B + (self._HOV_B - self._BASE_B) * t),
        )

    def _on_anim(self, value):
        self._t = float(value)
        channel = int(0xB8 + (0xFF - 0xB8) * self._t)
        self._nm_lbl.setStyleSheet(
            f"color: rgb({channel},{channel},{channel}); background: transparent; border: none;"
        )
        self.update()

    def _on_press_anim(self, value):
        self._press_scale = float(value)
        self.update()

    def _animate_press(self, target: float) -> None:
        self._press_anim.stop()
        self._press_anim.setStartValue(self._press_scale)
        self._press_anim.setEndValue(target)
        self._press_anim.start()

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        if self._press_scale != 1.0:
            # Scale the whole card about its centre for press feedback.
            cx, cy = self.width() / 2.0, self.height() / 2.0
            painter.translate(cx, cy)
            painter.scale(self._press_scale, self._press_scale)
            painter.translate(-cx, -cy)
        rect = QRectF(1.5, 1.5, self.width() - 3, self.height() - 3)
        path = QPainterPath()
        path.addRoundedRect(rect, self.RADIUS, self.RADIUS)
        bg = self._SEL_BG if self._sel else self._lerp_bg()
        painter.fillPath(path, QBrush(bg))
        if self._color:
            tag = QColor(self._color)
            if tag.isValid():
                # Subtle colour-tag wash over the whole card (drawn under the
                # selection border and the badges/labels that follow).
                tag.setAlpha(48)
                painter.fillPath(path, QBrush(tag))
        if self._sel:
            painter.setPen(QPen(self._SEL_BORDER, 1.5))
            painter.drawPath(path)

        # status dot (top-right)
        if self._status_state >= 0:
            in_game = bool(self._status_game)
            if self._status_stale:
                dot_color = QColor("#6a5040")
            else:
                dot_color = _IN_GAME_COLOR if in_game else _STATUS_COLORS.get(
                    self._status_state, _STATUS_COLORS[0]
                )
            dot_r = 5
            painter.setPen(QPen(QColor(self._BASE_R, self._BASE_G, self._BASE_B), 2.0))
            painter.setBrush(QBrush(dot_color))
            painter.drawEllipse(self.width() - dot_r * 2 - 8, 8, dot_r * 2, dot_r * 2)

        # ban dot (bottom-left)
        ban_color = self._ban_color()
        if ban_color is not None:
            dot_r = 5
            painter.setPen(QPen(QColor(self._BASE_R, self._BASE_G, self._BASE_B), 2.0))
            painter.setBrush(QBrush(ban_color))
            painter.drawEllipse(8, self.height() - dot_r * 2 - 8, dot_r * 2, dot_r * 2)

        # level (top-left)
        if self._level is not None:
            painter.setPen(QPen(QColor("#9a9a9a")))
            painter.setFont(QFont("Segoe UI", 8))
            painter.drawText(
                QRectF(12, 8, 46, 13),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"Lv{self._level}",
            )

        # divider between the identity block and the data footer
        painter.setPen(QPen(_DIVIDER, 1))
        painter.drawLine(16, self.DIVIDER_Y, self.width() - 16, self.DIVIDER_Y)

        self._paint_footer(painter)
        painter.end()

    def _paint_footer(self, painter: QPainter) -> None:
        """One centred line of CS2 data below the divider.

        Rule: show every present badge, except drop the Wingman emblem when both
        a Premier banner and a cooldown label would share the line (they'd
        overflow the card). A permanent cooldown shows as the ban dot, not here.
        Plain cards fall back to the muted login name so the line is never empty.
        """
        has_prem = has_premier(self._premier_rating)
        wing = wingman_emblem(self._wingman_rank, 16)
        cd_text = (
            format_cooldown_short(self._cooldown_expires)  # footer: hours-only above 1h
            if (self._cooldown_active and not self._permanent_cooldown())
            else ""
        )
        if has_prem and wing is not None and cd_text:
            wing = None

        items: list[tuple[str, object, int, int]] = []
        if has_prem:
            items.append(("prem", None, self._premier_pixmap(20).width(), 20))
        if wing is not None:
            items.append(("wing", wing, wing.width(), wing.height()))
        if cd_text:
            tw = QFontMetrics(QFont("Segoe UI", 8, QFont.Bold)).width(cd_text)
            items.append(("cd", cd_text, 6 + 5 + tw, 12))

        cy = self.FOOTER_CY
        if not items:
            login = self.acc.get("account_name", "")
            if login:
                painter.setFont(QFont("Segoe UI", 8))
                painter.setPen(QPen(QColor("#787878")))
                lg = QFontMetrics(painter.font()).elidedText(
                    login, Qt.ElideRight, self.CARD_W - 20
                )
                painter.drawText(
                    QRectF(10, cy - 8, self.CARD_W - 20, 16), Qt.AlignCenter, lg
                )
            return

        gap = 8
        total = sum(w for _, _, w, _ in items) + gap * (len(items) - 1)
        x = (self.CARD_W - total) / 2
        for kind, obj, w, h in items:
            y = cy - h / 2
            if kind == "prem":
                self._draw_premier_badge(painter, x, cy - h / 2, h)
            elif kind == "wing":
                painter.drawPixmap(int(round(x)), int(round(y)), obj)
            else:  # cooldown dot + label
                painter.setBrush(QBrush(_COOLDOWN_ACCENT))
                painter.setPen(Qt.NoPen)
                painter.drawEllipse(int(x), int(cy) - 3, 6, 6)
                painter.setFont(QFont("Segoe UI", 8, QFont.Bold))
                painter.setPen(QPen(_COOLDOWN_ACCENT))
                painter.drawText(
                    QRectF(x + 11, cy - 8, w, 16), Qt.AlignLeft | Qt.AlignVCenter, obj
                )
            x += w + gap

    def _premier_pixmap(self, h: int) -> QPixmap:
        """The CS2 Premier rating badge as a supersampled, cached QPixmap of
        height ``h`` (its width varies with the rating)."""
        key = (self._premier_rating, h)
        pm = _badge_cache.get(key)
        if pm is None:
            pm = self._render_premier_pixmap(h)
            _badge_cache[key] = pm
        return pm

    def _render_premier_pixmap(self, h: int) -> QPixmap:
        """Render the badge at ``h * _PREM_SS`` then downscale, so the bold
        Poppins number stays crisp: exact slanted accent bars (SVG) + a skewed
        (-10°) dark pill with an accent border + the tier-coloured number."""
        accent, text_c, bg_c = _PREMIER_TIERS[premier_tier(self._premier_rating)]
        H = h * _PREM_SS
        font = _rating_font(max(9 * _PREM_SS, round(H * 0.52)), 800)
        num = f"{self._premier_rating:,}"
        num_w = QFontMetrics(font).width(num)
        bw = max(1, round(H * 17 / 32))
        pill_x = bw - round(H * 0.28)  # margin-left: pill overlaps the bars
        pill_w = max(round(H * 1.9), num_w + round(H * 0.6))
        border = max(1.0, H * 0.055)
        radius = H * 0.11
        skew = round(_PREM_SKEW * H)

        img = QImage(pill_x + skew + pill_w, H, QImage.Format_ARGB32)
        img.fill(Qt.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.save()
        p.translate(pill_x + skew, 0)
        p.shear(-_PREM_SKEW, 0)
        pill = QRectF(0, border / 2, pill_w, H - border)
        path = QPainterPath()
        path.addRoundedRect(pill, radius, radius)
        p.fillPath(path, QBrush(QColor(bg_c)))
        ac = QColor(accent)
        ac.setAlpha(150)
        p.setPen(QPen(ac, border))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.setFont(font)
        p.setPen(QPen(QColor(text_c)))
        # Centre on the digits' cap height (the font line box has empty descender
        # space that makes AlignVCenter sit the number too high). Pill centre = H/2.
        fm = QFontMetrics(font)
        baseline = H / 2 + fm.capHeight() / 2
        tx = (pill_w - num_w) / 2
        p.drawText(QPointF(tx, baseline), num)
        p.restore()
        p.drawPixmap(0, 0, _premier_bars(accent, H))  # bars: path already slanted
        p.end()
        return QPixmap.fromImage(img.scaledToHeight(h, Qt.SmoothTransformation))

    def _draw_premier_badge(self, painter: QPainter, x: float, y: float, h: int) -> None:
        painter.drawPixmap(int(round(x)), int(round(y)), self._premier_pixmap(h))

    def enterEvent(self, _event):
        self._hovering = True
        self._update_sub_content()
        self._sync_sub_visibility()
        if not self._sel:
            self._anim.stop()
            self._anim.setStartValue(self._t)
            self._anim.setEndValue(1.0)
            self._anim.start()

    def leaveEvent(self, _event):
        self._hovering = False
        self._update_sub_content()
        self._sync_sub_visibility()
        if not self._sel:
            self._anim.stop()
            self._anim.setStartValue(self._t)
            self._anim.setEndValue(0.0)
            self._anim.start()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._animate_press(0.97)
            self.clicked.emit(self.acc, event.modifiers())

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._animate_press(1.0)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.double_clicked.emit(self.acc)

    def contextMenuEvent(self, event):
        from warestore.presentation.account_manager.ui.accounts.account_grid import AccountGrid

        grid = self.parent()
        if not isinstance(grid, AccountGrid):
            return

        targets = grid.resolve_menu_targets(self.acc)
        show_account_card_menu(
            parent=self,
            account=self.acc,
            menu_state=self._menu_state,
            targets=targets,
            export_count=grid.count_with_tokens(targets),
            global_pos=event.globalPos(),
            on_switch=lambda acc: self.double_clicked.emit(acc),
            on_relogin=lambda acc: self.relogin_requested.emit(acc),
            on_copy_export=grid.export_copy_requested.emit,
            on_export_file=grid.export_file_requested.emit,
            on_delete=grid.delete_requested.emit,
            on_cooldown_set=grid.cooldown_set_requested.emit,
            on_cooldown_custom=grid.cooldown_custom_requested.emit,
            on_color_set=grid.color_set_requested.emit,
            on_cs2_source_set=grid.cs2_source_set_requested.emit,
            on_cs2_apply=grid.cs2_apply_requested.emit,
            on_cs2_rank=grid.cs2_rank_requested.emit,
            on_reset_hwid=grid.hwid_reset_requested.emit,
            has_hwid_profile=self._menu_state.has_hwid_profile,
        )
