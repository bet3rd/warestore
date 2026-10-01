from warestore.presentation.account_manager.support.dpi import (
    MIGRATED_KEY,
    migrate_interface_scale,
    scale_factor_env,
)


def test_old_interface_scale_is_reset_once():
    settings = {"dpi_scale": 110}
    assert migrate_interface_scale(settings) is True
    assert settings["dpi_scale"] == 100 and settings[MIGRATED_KEY] is True
    settings["dpi_scale"] = 125  # the user picks a new zoom afterwards
    assert migrate_interface_scale(settings) is False
    assert settings["dpi_scale"] == 125


def test_scale_factor_env():
    assert scale_factor_env({"dpi_scale": 100}) is None
    assert scale_factor_env({}) is None
    assert scale_factor_env({"dpi_scale": 125}) == "1.25"
    assert scale_factor_env({"dpi_scale": "junk"}) is None
