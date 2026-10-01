from PyQt5.QtCore import QRect

from warestore.presentation.account_manager.support.dpi import migrate_interface_scale
from warestore.presentation.account_manager.support.window_position import title_bar_visible

SCREENS = [QRect(0, 0, 2560, 1400), QRect(2560, 0, 1707, 920)]  # 1440p + 4K@150%


def test_position_on_a_screen_is_kept():
    assert title_bar_visible(100, 100, 600, SCREENS)
    assert title_bar_visible(2600, 50, 600, SCREENS)


def test_position_off_every_screen_is_rejected():
    assert not title_bar_visible(4500, 300, 600, SCREENS)  # past the right edge
    assert not title_bar_visible(100, 1390, 600, SCREENS)  # title bar below the bottom
    assert not title_bar_visible(-2000, 100, 600, SCREENS)  # an unplugged left monitor


def test_a_mostly_hidden_title_bar_is_rejected():
    assert not title_bar_visible(2530, 100, 600, [QRect(0, 0, 2560, 1400)])  # 30px showing


def test_the_dpi_reset_forgets_the_old_window_position():
    settings = {"dpi_scale": 110, "window_x": 3000, "window_y": 400}
    migrate_interface_scale(settings)
    assert settings["window_x"] is None and settings["window_y"] is None
