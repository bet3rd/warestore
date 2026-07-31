# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from PyQt5.QtCore import QThread, pyqtSignal

from warestore.application.account_manager.controller import AccountManagerController
from warestore.presentation.account_manager.ui.avatars import ensure_avatar_downloaded


class StatusFetchWorker(QThread):
    progress = pyqtSignal(str)
    done = pyqtSignal(dict)

    def __init__(
        self,
        steamids: list[str],
        *,
        ctrl: AccountManagerController,
    ):
        super().__init__()
        self._ctrl = ctrl
        self.steamids = steamids

    def run(self):
        result = self._ctrl.fetch_profile_statuses(
            self.steamids,
            on_progress=self.progress.emit,
        )
        # Ban/level info needs an API key; both are no-ops without one.
        for sid, info in self._ctrl.fetch_bans(self.steamids).items():
            result.setdefault(sid, {})["ban"] = info
        for sid, level in self._ctrl.fetch_levels(self.steamids).items():
            result.setdefault(sid, {})["level"] = level
        # Fetch fresh avatars off the UI thread; hash-keyed cache means an
        # unchanged picture is downloaded at most once. The UI thread turns the
        # cached file into a pixmap.
        for info in result.values():
            path = ensure_avatar_downloaded(info.get("avatar", ""), info.get("avatar_hash", ""))
            if path:
                info["avatar_path"] = path
        self.done.emit(result)
