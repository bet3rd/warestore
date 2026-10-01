import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QDialog

from warestore.presentation.account_manager.ui.dialogs import RejectedTokenDialog


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def test_no_title_bar_and_dont_add_is_the_default(_app):
    dlg = RejectedTokenDialog(None)
    assert dlg.windowFlags() & Qt.FramelessWindowHint
    assert dlg.btn_skip.isDefault() and not dlg.btn_keep.isDefault()


def test_keep_accepts_and_dont_add_rejects(_app):
    dlg = RejectedTokenDialog(None)
    dlg.btn_keep.click()
    assert dlg.result() == QDialog.Accepted
    dlg = RejectedTokenDialog(None)
    dlg.btn_skip.click()
    assert dlg.result() == QDialog.Rejected
