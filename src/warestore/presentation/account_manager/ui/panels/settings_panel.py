# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import sys

from PyQt5.QtCore import QRectF, Qt, pyqtSignal
from PyQt5.QtGui import QBrush, QColor, QPainter, QPainterPath, QPalette, QPixmap
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from warestore.presentation.account_manager.ui.chrome import HeaderBar, RoundedPanel
from warestore.presentation.account_manager.ui.section import SectionLabel


def _warning_icon(px: int = 14) -> QPixmap:
    """An amber warning triangle (with an exclamation mark), painted so its visual
    centre is the pixmap centre — so it lines up with adjacent text when the label
    is vertically centred. 2x-supersampled + devicePixelRatio for crispness."""
    ratio = 2
    pm = QPixmap(px * ratio, px * ratio)
    pm.fill(Qt.transparent)
    pm.setDevicePixelRatio(ratio)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    s = float(px)
    triangle = QPainterPath()
    triangle.moveTo(s / 2, s * 0.11)
    triangle.lineTo(s * 0.93, s * 0.85)
    triangle.lineTo(s * 0.07, s * 0.85)
    triangle.closeSubpath()
    p.setPen(Qt.NoPen)
    p.setBrush(QBrush(QColor("#e0a021")))
    p.drawPath(triangle)
    # Exclamation mark cut into the triangle (dark).
    p.setBrush(QBrush(QColor("#231a06")))
    bar_w = s * 0.11
    p.drawRoundedRect(
        QRectF(s / 2 - bar_w / 2, s * 0.37, bar_w, s * 0.27), bar_w / 2, bar_w / 2
    )
    dot = s * 0.13
    p.drawEllipse(QRectF(s / 2 - dot / 2, s * 0.69, dot, dot))
    p.end()
    return pm


class BulkTokenEdit(QPlainTextEdit):
    """Avoids re-entrant textChanged handlers during bulk set/paste (Qt crash on Windows)."""

    bulk_changed = pyqtSignal()

    def setPlainText(self, text: str) -> None:
        self.blockSignals(True)
        super().setPlainText(text)
        self.blockSignals(False)
        self.bulk_changed.emit()

    def insertFromMimeData(self, source) -> None:
        if source is not None and source.hasText():
            self.blockSignals(True)
            super().insertFromMimeData(source)
            self.blockSignals(False)
            self.bulk_changed.emit()
            return
        super().insertFromMimeData(source)


class SettingsPanel:
    """Side settings surface (startup, account checks, security, bulk import)."""

    def __init__(self, panel: RoundedPanel, settings: dict, *, on_close) -> None:
        self._settings = settings
        self.cb_cs2 = QCheckBox("Open CS2 on Login")
        self.le_opts = QLineEdit()
        self.cb_workshop = QCheckBox("Auto-disable Workshop maps on switch")
        self.cb_remote_play = QCheckBox("Disable Remote Play on login")
        self.cb_add_only = QCheckBox("Add account only (don't open Steam)")
        self.cb_spoof = QCheckBox("Run HWID spoofer on login")
        self.btn_install_spoofer = QPushButton("Install spoofer")
        self.spoofer_row = QWidget()
        self.cb_close_to_tray = QCheckBox("Close to tray (X hides window)")
        self.cb_auto_remove_expired = QCheckBox("Remove expired tokens on refresh")
        self.cb_gcpd_on_launch = QCheckBox("Fetch CS2 ranks on launch")
        self.cb_exclude_capture = QCheckBox("Hide from screen capture (Discord, OBS)")
        self.cmb_dpi = QComboBox()
        self.le_api_key = QLineEdit()
        self.lbl_api_status = QLabel("")
        self.btn_master = QPushButton()
        self.btn_clean_userdata = QPushButton("Clean unused Steam data…")
        self.txt_bulk = BulkTokenEdit()
        self.btn_import = QPushButton("Import")
        self.btn_browse = QPushButton("Browse File…")
        self.lbl_status = QLabel()
        self._on_close = on_close
        self._build(panel)

    def scroll_to_top(self) -> None:
        """Reset the settings scroll to the top (called when the panel opens)."""
        self._scroll.verticalScrollBar().setValue(0)

    def set_spoofer_installed(self, installed: bool) -> None:
        """Reflect whether the HWID spoofer is installed: enable/disable the
        run-on-login checkbox and show the install button + status."""
        self.cb_spoof.setEnabled(installed)
        self.btn_install_spoofer.setVisible(not installed)
        self.btn_install_spoofer.setEnabled(True)
        self.cb_spoof.blockSignals(True)
        self.cb_spoof.setChecked(
            self._settings.get("spoof_on_login", False) if installed else False
        )
        self.cb_spoof.blockSignals(False)

    def _add_separator(self, layout) -> None:
        """Section divider with more room above than below, so each section
        reads as a distinct group rather than an evenly-spaced list."""
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 10, 0, 2)
        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        v.addWidget(sep)
        layout.addWidget(box)

    def _build(self, panel: RoundedPanel) -> None:
        root = QVBoxLayout(panel)
        root.setContentsMargins(0, 0, 0, 12)
        root.setSpacing(0)

        self.header = HeaderBar(
            "Settings",
            on_minimize=lambda: None,
            on_close=self._on_close,
            show_minimize=False,
            draggable=False,
        )
        root.addWidget(self.header)

        sep = QFrame()
        sep.setObjectName("separator")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(1)
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setAttribute(Qt.WA_NoSystemBackground)
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(6)
        scroll.setWidget(inner)
        root.addWidget(scroll, 1)

        layout.addWidget(SectionLabel("Startup"))

        # Checkboxes live in their own container with roomier spacing than the
        # tighter header/hint/action grouping used by the sections below.
        startup_box = QWidget()
        startup = QVBoxLayout(startup_box)
        startup.setContentsMargins(0, 0, 0, 0)
        startup.setSpacing(10)
        _outer_layout = layout
        layout = startup

        self.cb_cs2.setChecked(self._settings.get("open_cs2", False))
        layout.addWidget(self.cb_cs2)

        self.le_opts.setPlaceholderText("CS2 launch options  (e.g. -nojoy -high)")
        self.le_opts.setText(self._settings.get("cs2_launch_options", ""))
        self.le_opts.setVisible(self._settings.get("open_cs2", False))
        layout.addWidget(self.le_opts)

        self.cb_workshop.setChecked(self._settings.get("disable_workshop", False))
        self.cb_workshop.setToolTip(
            "On every account switch, marks the account's CS2 Workshop\n"
            "subscriptions as disabled locally so Steam won't download or\n"
            "mount them. Nothing is unsubscribed — it's reversible."
        )
        layout.addWidget(self.cb_workshop)

        self.cb_remote_play.setChecked(self._settings.get("disable_remote_play", True))
        self.cb_remote_play.setToolTip(
            "Turns off Steam Settings → Remote Play → Enable Remote Play for\n"
            "each account as it's logged in, so streaming never starts up."
        )
        layout.addWidget(self.cb_remote_play)

        self.cb_add_only.setChecked(self._settings.get("add_account_only", False))
        self.cb_add_only.setToolTip(
            "Writes the login and sets it as the next account, but leaves\n"
            "Steam closed instead of relaunching it. Steam is still closed\n"
            "briefly so the changes can be saved. Overrides 'Open CS2 on Login'."
        )
        layout.addWidget(self.cb_add_only)

        self.cb_spoof.setChecked(self._settings.get("spoof_on_login", False))
        self.cb_spoof.setToolTip(
            "Launches Steam via the HWID spoofer injector. Steam starts\n"
            "suspended, the spoofer DLL is injected, then Steam resumes — hooks\n"
            "are active before steamclient64.dll loads. Spoofing is per-session;\n"
            "re-applied automatically on every switch."
        )
        # Checkbox + inline "Install spoofer" button. The spoofer isn't bundled;
        # the button (hidden once installed) downloads it on demand.
        spoof_row = QHBoxLayout(self.spoofer_row)
        spoof_row.setContentsMargins(0, 0, 0, 0)
        spoof_row.setSpacing(8)
        spoof_row.addWidget(self.cb_spoof)
        spoof_row.addStretch()
        # Quiet inline link so the row stays the same height as the other
        # checkboxes (a real button would make this row taller and break rhythm).
        self.btn_install_spoofer.setFlat(True)
        self.btn_install_spoofer.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: #cc4444;"
            " font-size: 12px; padding: 0; min-height: 0; }"
            "QPushButton:hover { color: #e46060; }"
            "QPushButton:disabled { color: #6a3030; }"
        )
        self.btn_install_spoofer.setCursor(Qt.PointingHandCursor)
        self.btn_install_spoofer.setToolTip(
            "Downloads the HWID spoofer from the spoofer repo into your\n"
            "app-data folder. Not included in the base install."
        )
        spoof_row.addWidget(self.btn_install_spoofer)
        layout.addWidget(self.spoofer_row)

        self.cb_close_to_tray.setChecked(self._settings.get("close_to_tray", False))
        self.cb_close_to_tray.setToolTip(
            "When on, X hides to tray and shows a notification. "
            "Starting the app again opens the existing window. "
            "When off, X quits the app."
        )
        layout.addWidget(self.cb_close_to_tray)

        self.cb_auto_remove_expired.setChecked(
            self._settings.get("auto_remove_expired_tokens", False)
        )
        self.cb_auto_remove_expired.setToolTip(
            "Deletes expired JWT entries from tokens.json when accounts are loaded or refreshed."
        )
        layout.addWidget(self.cb_auto_remove_expired)

        gcpd_row = QWidget()
        gcpd_h = QHBoxLayout(gcpd_row)
        gcpd_h.setContentsMargins(0, 0, 0, 0)
        gcpd_h.setSpacing(6)
        self.cb_gcpd_on_launch.setChecked(
            self._settings.get("gcpd_check_on_launch", False)
        )
        self.cb_gcpd_on_launch.setToolTip(
            "On startup, fetches each account's CS2 Premier/Wingman rank and\n"
            "competitive cooldown from Steam (GCPD), one account at a time.\n"
            "Only accounts with a saved token are checked."
        )
        gcpd_h.addWidget(self.cb_gcpd_on_launch, 0, Qt.AlignVCenter)
        gcpd_warn = QLabel()
        gcpd_warn.setPixmap(_warning_icon(14))
        gcpd_warn.setToolTip(
            "<div style='color:#e0a021; white-space:nowrap'>"
            "With many accounts this can hit Steam's rate limit.<br>"
            "Fetches run one at a time to ease it, but a large roster<br>"
            "may still be slow or get throttled — consider running it<br>"
            "manually with the button next to Refresh instead."
            "</div>"
        )
        gcpd_h.addWidget(gcpd_warn, 0, Qt.AlignVCenter)
        gcpd_h.addStretch()
        layout.addWidget(gcpd_row)

        self.cb_exclude_capture.setChecked(self._settings.get("exclude_from_capture", True))
        self.cb_exclude_capture.setToolTip(
            "Hides this app from Discord/OBS\n"
            "display capture (Windows 10 2004+).\n"
            "Not a security guarantee."
        )
        if sys.platform != "win32":
            self.cb_exclude_capture.setEnabled(False)
            self.cb_exclude_capture.setToolTip("Windows only.")
        layout.addWidget(self.cb_exclude_capture)

        layout = _outer_layout
        layout.addWidget(startup_box)

        self._add_separator(layout)

        layout.addWidget(SectionLabel("Display"))
        dpi_row = QHBoxLayout()
        dpi_row.setContentsMargins(0, 0, 0, 0)
        dpi_row.addWidget(QLabel("Interface scale"))
        dpi_row.addStretch()
        for pct in (100, 110, 125, 150, 200):
            self.cmb_dpi.addItem(f"{pct}%", pct)
        current_scale = int(self._settings.get("dpi_scale", 100) or 100)
        idx = self.cmb_dpi.findData(current_scale)
        self.cmb_dpi.setCurrentIndex(idx if idx >= 0 else 0)
        self.cmb_dpi.setFixedWidth(96)
        dpi_row.addWidget(self.cmb_dpi)
        layout.addLayout(dpi_row)
        dpi_hint = QLabel("Scales the whole interface. Applies after restarting WareStore.")
        dpi_hint.setObjectName("info")
        dpi_hint.setWordWrap(True)
        layout.addWidget(dpi_hint)

        self._add_separator(layout)

        checks_hdr = QHBoxLayout()
        checks_hdr.setContentsMargins(0, 0, 0, 0)
        checks_hdr.addWidget(SectionLabel("Account Checks"))
        checks_hdr.addStretch()
        self.lbl_api_status.setObjectName("info")
        checks_hdr.addWidget(self.lbl_api_status)
        layout.addLayout(checks_hdr)

        api_hint = QLabel(
            "Steam Web API key enables VAC/game/trade ban badges on cards. "
            'Get one free at <a href="https://steamcommunity.com/dev/apikey">'
            "steamcommunity.com/dev/apikey</a>."
        )
        api_hint.setObjectName("info")
        api_hint.setWordWrap(True)
        api_hint.setTextFormat(Qt.RichText)
        api_hint.setTextInteractionFlags(Qt.TextBrowserInteraction)
        api_hint.setOpenExternalLinks(True)
        link_pal = api_hint.palette()
        link_pal.setColor(QPalette.Link, QColor("#cc4444"))
        api_hint.setPalette(link_pal)
        layout.addWidget(api_hint)

        self.le_api_key.setPlaceholderText("Steam Web API key (optional)")
        self.le_api_key.setText(self._settings.get("steam_api_key", ""))
        self.le_api_key.setEchoMode(QLineEdit.PasswordEchoOnEdit)
        layout.addWidget(self.le_api_key)

        self._add_separator(layout)

        layout.addWidget(SectionLabel("Security"))

        self.lbl_master = QLabel()
        self.lbl_master.setObjectName("info")
        self.lbl_master.setWordWrap(True)
        layout.addWidget(self.lbl_master)

        self.btn_master.setObjectName("secondary")
        self.btn_master.setFixedHeight(32)
        layout.addWidget(self.btn_master)
        self.refresh_master_state()

        self._add_separator(layout)

        layout.addWidget(SectionLabel("Maintenance"))

        clean_hint = QLabel(
            "Steam keeps a userdata folder per account even after it leaves the "
            "login list. Removes the leftovers and frees the disk space."
        )
        clean_hint.setObjectName("info")
        clean_hint.setWordWrap(True)
        layout.addWidget(clean_hint)

        self.btn_clean_userdata.setObjectName("secondary")
        self.btn_clean_userdata.setFixedHeight(32)
        layout.addWidget(self.btn_clean_userdata)

        self._add_separator(layout)

        layout.addWidget(SectionLabel("Bulk Import"))

        hint = QLabel("One token per line — username----eyA... or eyA...")
        hint.setObjectName("info")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.txt_bulk.setPlaceholderText("username----eyABC...\neyABC...")
        self.txt_bulk.setFixedHeight(108)
        layout.addWidget(self.txt_bulk)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self.btn_browse.setObjectName("secondary")
        self.btn_browse.setFixedHeight(32)
        btn_row.addWidget(self.btn_browse, 1)
        self.btn_import.setEnabled(False)
        self.btn_import.setFixedHeight(32)
        btn_row.addWidget(self.btn_import, 1)
        layout.addLayout(btn_row)

        self.lbl_status.setObjectName("info")
        layout.addWidget(self.lbl_status)

        self._scroll = scroll

    def refresh_master_state(self) -> None:
        if self._settings.get("vault_mode") == "password":
            self.lbl_master.setText("Token vault is protected by a master password.")
            self.btn_master.setText("Change or remove master password…")
        else:
            self.lbl_master.setText(
                "Tokens are encrypted to this Windows account (DPAPI). Add a master "
                "password for a layer even local software can't bypass."
            )
            self.btn_master.setText("Set master password…")
