import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication, QScrollArea, QWidget

from warestore.presentation.account_manager.ui.scroll_fade import attach_bottom_fade


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def _area(content_h):
    area = QScrollArea()
    inner = QWidget()
    inner.setFixedSize(200, content_h)
    area.setWidget(inner)
    area.resize(220, 300)
    area.show()
    QApplication.processEvents()
    return area


def test_fade_shows_while_there_is_more_below(_app):
    area = _area(900)
    fade = attach_bottom_fade(area)
    QApplication.processEvents()
    assert fade.isVisible() and fade.strength() == 1.0
    bar = area.verticalScrollBar()
    bar.setValue(bar.maximum())
    QApplication.processEvents()
    assert not fade.isVisible()


def test_fade_eases_out_near_the_end(_app):
    area = _area(900)
    fade = attach_bottom_fade(area, height=24)
    bar = area.verticalScrollBar()
    bar.setValue(bar.maximum() - 12)
    QApplication.processEvents()
    assert 0.0 < fade.strength() < 1.0


def test_no_fade_when_nothing_scrolls(_app):
    area = _area(100)
    fade = attach_bottom_fade(area)
    QApplication.processEvents()
    assert not fade.isVisible()


def test_fade_sits_on_the_viewport_bottom_and_ignores_the_mouse(_app):
    area = _area(900)
    fade = attach_bottom_fade(area, height=24)
    QApplication.processEvents()
    vp = area.viewport().geometry()
    assert fade.geometry().bottom() == vp.bottom()
    assert fade.width() == vp.width() and fade.height() == 24
    assert fade.testAttribute(Qt.WA_TransparentForMouseEvents)
