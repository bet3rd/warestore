import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt5.QtCore import QPoint, Qt
from PyQt5.QtGui import QMouseEvent
from PyQt5.QtWidgets import QApplication

from warestore.presentation.account_manager.ui.color_picker import ColorPickerPopover


@pytest.fixture(scope="module")
def _app():
    return QApplication.instance() or QApplication([])


def _mouse(widget, kind, x, y, buttons=Qt.LeftButton):
    button = Qt.NoButton if kind == QMouseEvent.MouseMove else Qt.LeftButton
    QApplication.sendEvent(widget, QMouseEvent(kind, QPoint(x, y), button, buttons, Qt.NoModifier))


@pytest.fixture
def picker(_app):
    pop = ColorPickerPopover("#1f5fa8")
    pop.resize(pop.WIDTH, 300)
    pop.show()
    changes: list[str] = []
    pop.colorChanged.connect(changes.append)
    yield pop, changes
    pop._finished = True  # don't emit rejected during teardown
    pop.close()


def test_dragging_does_not_preview_until_release(picker):
    # Restyling the whole app costs tens of ms, so a drag must not fire
    # colorChanged per mouse move — only once, when the drag ends.
    pop, changes = picker
    square = pop._square
    _mouse(square, QMouseEvent.MouseButtonPress, 10, 10)
    for x in range(12, 120, 4):
        _mouse(square, QMouseEvent.MouseMove, x, 40)
    assert changes == []
    _mouse(square, QMouseEvent.MouseButtonRelease, 120, 40, Qt.NoButton)
    assert changes == [pop.color()]


def test_hue_drag_previews_once_on_release(picker):
    pop, changes = picker
    bar = pop._hue_bar
    _mouse(bar, QMouseEvent.MouseButtonPress, 20, 7)
    for x in range(22, 150, 5):
        _mouse(bar, QMouseEvent.MouseMove, x, 7)
    assert changes == []
    _mouse(bar, QMouseEvent.MouseButtonRelease, 150, 7, Qt.NoButton)
    assert changes == [pop.color()]


def test_dragging_still_updates_the_picker_itself(picker):
    pop, _changes = picker
    before = pop._hex.text()
    _mouse(pop._square, QMouseEvent.MouseButtonPress, 5, 5)
    _mouse(pop._square, QMouseEvent.MouseMove, 150, 120)
    assert pop._hex.text() != before
    assert pop._chip.new.name() == pop.color()


def test_valid_hex_previews_invalid_does_not(picker):
    pop, changes = picker
    pop._on_hex("0f8")
    pop._on_hex("0f8a")
    pop._on_hex("0f8a80")
    assert changes == ["#00ff88", "#0f8a80"]
