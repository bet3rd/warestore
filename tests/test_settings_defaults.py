from warestore.infrastructure.persistence.settings_repository import SettingsRepository


def test_account_check_defaults_are_on(tmp_path):
    settings = SettingsRepository(str(tmp_path / "settings.json")).load()
    for key in ("account_check_on_add", "account_check_loadout",
                "account_check_stats", "account_check_workshop"):
        assert settings[key] is True
    assert "disable_workshop" not in settings
