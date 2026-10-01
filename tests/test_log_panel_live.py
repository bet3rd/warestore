import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import threading

import pytest
from PyQt5.QtWidgets import QApplication, QWidget

from warestore.presentation.account_manager.support.app_log import app_log
from warestore.presentation.account_manager.ui.panels.main_panel import MainPanel


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def _panel():
    host = QWidget()
    panel = MainPanel(host, {}, on_minimize=lambda: None, on_close=lambda: None)
    host.show()
    return host, panel


def test_open_log_panel_picks_up_lines_from_other_threads(_app):
    host, panel = _panel()
    panel.set_log_visible(True)
    panel.refresh_log()
    t = threading.Thread(target=lambda: app_log.append("[*] account-check: from a worker"))
    t.start()
    t.join()
    panel._poll_log()  # what the 500 ms timer does
    assert "from a worker" in panel._log_panel.toPlainText()
    host.close()


def test_poll_only_runs_while_the_panel_is_open(_app):
    host, panel = _panel()
    panel.set_log_visible(True)
    assert panel._log_timer.isActive()
    panel.set_log_visible(False)
    assert not panel._log_timer.isActive()
    host.close()
