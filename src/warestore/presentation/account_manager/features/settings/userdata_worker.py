# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Background scan/delete for leftover Steam userdata folders.

Both phases touch the filesystem heavily (walking ~100 folders to size them,
then removing gigabytes), so neither may run on the UI thread.
"""

import logging

from PyQt5.QtCore import QThread, pyqtSignal

from warestore.application.account_manager.controller import (
    AccountManagerController,
    UserdataScanUnsafe,
)

logger = logging.getLogger(__name__)


class UserdataScanWorker(QThread):
    # (folders, error): on success error is None; on a fail-closed abort folders
    # is None and error is a user-facing message. The two are NOT interchangeable
    # — an empty list means "nothing to clean", None means "couldn't verify".
    done = pyqtSignal(object, object)

    def __init__(self, *, ctrl: AccountManagerController) -> None:
        super().__init__()
        self._ctrl = ctrl

    def run(self) -> None:
        try:
            self.done.emit(self._ctrl.scan_unused_userdata(), None)
        except UserdataScanUnsafe as exc:
            logger.warning(f"userdata scan refused (unsafe): {exc}")
            self.done.emit(None, str(exc))
        except Exception as exc:
            logger.exception(f"userdata scan failed: {exc}")
            self.done.emit(None, "Couldn't scan Steam userdata. See the log for details.")


class UserdataDeleteWorker(QThread):
    done = pyqtSignal(int, int, object)  # count, bytes_freed, errors

    def __init__(self, folders: list, *, ctrl: AccountManagerController) -> None:
        super().__init__()
        self._folders = folders
        self._ctrl = ctrl

    def run(self) -> None:
        try:
            count, freed, errors = self._ctrl.delete_userdata_folders(self._folders)
            self.done.emit(count, freed, errors)
        except Exception as exc:
            logger.exception(f"userdata delete failed: {exc}")
            self.done.emit(0, 0, [str(exc)])
