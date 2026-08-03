# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os
import sys

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractScrollArea,
    QButtonGroup,
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QVBoxLayout,
)

from warestore.presentation.account_manager.ui.theme import (
    enable_dark_title_bar,
    schedule_capture_exclusion_for_widget,
)


def _fmt_size(num_bytes: int) -> str:
    mb = num_bytes / (1024 * 1024)
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else f"{mb:.0f} MB"


class UserdataCleanupDialog(QDialog):
    """Pick which leftover userdata folders to delete.

    Two scopes, because "not in Steam's login list" is not the same as unused:
    token-managed accounts are absent from that list by design.
    """

    def __init__(self, parent, folders: list, *, exclude_from_capture: bool = True):
        super().__init__(parent)
        self._exclude_from_capture = exclude_from_capture
        self._dead = [f for f in folders if not f.token_managed]
        self._managed = [f for f in folders if f.token_managed]

        self.setObjectName("warestore_dialog")
        self.setWindowTitle("Clean unused Steam data")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(14)

        title = QLabel("Clean unused Steam data")
        title.setObjectName("dialog_title")
        layout.addWidget(title)

        dead_size = sum(f.size_bytes for f in self._dead)
        managed_size = sum(f.size_bytes for f in self._managed)

        intro = QLabel(
            "Leftover <b>userdata</b> folders Steam never removed. "
            "Close Steam before cleaning."
        )
        intro.setObjectName("info")
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        layout.addWidget(intro)

        self._group = QButtonGroup(self)

        self.rb_dead = QRadioButton(
            f"Dead only — {len(self._dead)} folders, {_fmt_size(dead_size)}"
        )
        self.rb_dead.setChecked(True)
        self.rb_dead.setToolTip(
            "Folders with no Steam login entry and no saved token.\n"
            "Nothing you can still log into is touched."
        )
        self._group.addButton(self.rb_dead)
        layout.addWidget(self.rb_dead)

        dead_note = QLabel("Nothing you can still log into is affected.")
        dead_note.setObjectName("info")
        dead_note.setWordWrap(True)
        layout.addWidget(dead_note)

        self.rb_all = QRadioButton(
            f"Everything not in Steam — {len(self._dead) + len(self._managed)} folders, "
            f"{_fmt_size(dead_size + managed_size)}"
        )
        self._group.addButton(self.rb_all)
        layout.addWidget(self.rb_all)

        cs2_managed = sum(1 for f in self._managed if f.has_cs2_config)
        warn = QLabel(
            f"Also deletes {len(self._managed)} folders ({_fmt_size(managed_size)}) for "
            f"accounts WareStore still has tokens for, including {cs2_managed} CS2 "
            f"configs. They would be re-seeded from the source account on next login."
        )
        warn.setObjectName("warning")
        warn.setWordWrap(True)
        layout.addWidget(warn)

        # Show exactly which accounts each choice would remove, so the user can
        # eyeball the list before an irreversible delete.
        list_label = QLabel("Accounts that will be removed:")
        list_label.setObjectName("info")
        layout.addWidget(list_label)

        self._list = QListWidget()
        self._list.setObjectName("userdata_list")
        self._list.setFixedHeight(150)
        self._list.setSelectionMode(QListWidget.NoSelection)
        self._list.setFocusPolicy(Qt.NoFocus)
        layout.addWidget(self._list)

        self.rb_dead.toggled.connect(self._refresh_list)
        self.rb_all.toggled.connect(self._refresh_list)
        self._refresh_list()

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()
        btn_row.addWidget(self._make_button("Cancel", self.reject, primary=False))
        self._btn_clean = self._make_button("Clean", self.accept, primary=True)
        self._btn_clean.setEnabled(bool(folders))
        btn_row.addWidget(self._btn_clean)
        layout.addLayout(btn_row)

        self.adjustSize()
        self.setFixedSize(self.size())
        self.setWindowModality(Qt.WindowModal)

    def _make_button(self, text: str, on_click, *, primary: bool) -> QPushButton:
        btn = QPushButton(text)
        if not primary:
            btn.setObjectName("secondary")
        btn.setMinimumSize(108, 36)
        btn.setStyleSheet("min-height: 0; padding: 6px 16px; font-size: 12px;")
        btn.clicked.connect(on_click)
        return btn

    def selected_folders(self) -> list:
        return self._dead + self._managed if self.rb_all.isChecked() else self._dead

    def _refresh_list(self) -> None:
        """List the accounts the current choice would delete, largest first."""
        self._list.clear()
        for f in self.selected_folders():
            name = f.account_name or f"account {f.account_id32}"
            tags = ""
            if f.has_cs2_config:
                tags += " · CS2"
            if f.token_managed:
                tags += " · has saved token"
            self._list.addItem(f"{name} — {_fmt_size(f.size_bytes)}{tags}")

    def showEvent(self, event):
        enable_dark_title_bar(int(self.winId()))
        schedule_capture_exclusion_for_widget(self, enabled=self._exclude_from_capture)
        super().showEvent(event)


class UpdateDialog(QDialog):
    def __init__(
        self,
        parent,
        download_url: str,
        latest_version: str,
        force_update: bool,
        *,
        change_log: str = "",
        exclude_from_capture: bool = True,
    ):
        super().__init__(parent)
        self.download_url = download_url
        self.force_update = force_update
        self._exclude_from_capture = exclude_from_capture

        self.setObjectName("warestore_dialog")
        self.setWindowTitle("Update Available")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setFixedWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(16)

        title = QLabel("Update required" if force_update else "Update available")
        title.setObjectName("dialog_title")
        layout.addWidget(title)

        version = QLabel(
            f"Version {latest_version} is available."
            if not force_update
            else f"Version {latest_version} is required to continue."
        )
        version.setObjectName("info")
        version.setWordWrap(True)
        layout.addWidget(version)

        notes = (change_log or "").strip()
        if notes:
            changelog = QLabel(notes)
            changelog.setObjectName("changelog")
            changelog.setWordWrap(True)
            changelog.setTextFormat(Qt.MarkdownText)
            changelog.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            changelog.setStyleSheet(
                "color: #b8b8b8; font-size: 12px; background: transparent;"
                " border: none; padding: 10px 12px;"
            )
            # Scroll the notes inside a fixed-height frame so a long changelog can't
            # stretch the window; short ones still size snugly (AdjustToContents).
            changelog_scroll = QScrollArea()
            changelog_scroll.setWidget(changelog)
            changelog_scroll.setWidgetResizable(True)
            changelog_scroll.setFrameShape(QFrame.NoFrame)
            changelog_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            changelog_scroll.setSizeAdjustPolicy(QAbstractScrollArea.AdjustToContents)
            changelog_scroll.setMaximumHeight(180)
            changelog_scroll.setStyleSheet(
                "QScrollArea { background: #1a1a1a; border: 1px solid #2a2a2a;"
                " border-radius: 6px; }"
            )
            changelog_scroll.viewport().setStyleSheet("background: transparent;")
            layout.addWidget(changelog_scroll)

        if not force_update:
            prompt = QLabel("Download and install now?")
            prompt.setObjectName("info")
            layout.addWidget(prompt)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.addStretch()

        if force_update:
            btn_row.addWidget(self._make_button("Update now", self._update_now, primary=True))
        else:
            btn_row.addWidget(self._make_button("Not now", self.reject, primary=False))
            btn_row.addWidget(self._make_button("Update now", self._update_now, primary=True))

        layout.addLayout(btn_row)

        self.adjustSize()
        self.setFixedSize(self.size())

        self.setWindowModality(
            Qt.ApplicationModal if force_update else Qt.WindowModal
        )

    def _make_button(self, text: str, on_click, *, primary: bool) -> QPushButton:
        btn = QPushButton(text)
        if not primary:
            btn.setObjectName("secondary")
        # Minimum (not fixed) size + padding so the label never clips when the
        # display scaling enlarges the font; both buttons share the same floor
        # so they stay visually balanced.
        btn.setMinimumSize(108, 36)
        btn.setStyleSheet("min-height: 0; padding: 6px 16px; font-size: 12px;")
        btn.clicked.connect(on_click)
        return btn

    def showEvent(self, event):
        enable_dark_title_bar(int(self.winId()))
        schedule_capture_exclusion_for_widget(self, enabled=self._exclude_from_capture)
        super().showEvent(event)

    def _update_now(self):
        os.system(f"start {self.download_url}")
        if self.force_update:
            sys.exit(0)
        self.accept()

    def closeEvent(self, event):
        if self.force_update:
            sys.exit(0)
        super().closeEvent(event)
