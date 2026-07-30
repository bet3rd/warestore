from datetime import datetime, timedelta

from warestore.domain.accounts.activity import format_last_played
from warestore.infrastructure.persistence.metadata_repository import AccountMetadataRepository


def test_format_last_played_never():
    assert format_last_played(0) == "Never"


def test_format_last_played_just_now(monkeypatch):
    ts = int(datetime.now().timestamp())
    assert format_last_played(ts) == "Just now"


def test_format_last_played_hours_ago():
    ts = int((datetime.now() - timedelta(hours=3)).timestamp())
    assert format_last_played(ts) == "3h ago"


def test_color_persists(tmp_path):
    repo = AccountMetadataRepository(path=str(tmp_path / "meta.json"))
    repo.set_color("76561198000000001", "#5ba85e")

    rec = repo.get("76561198000000001")
    assert rec.color == "#5ba85e"


def test_color_independent_of_cooldown(tmp_path):
    repo = AccountMetadataRepository(path=str(tmp_path / "meta.json"))
    repo.set_cooldown("111", 3600)
    repo.set_color("111", "#cc4444")
    rec = repo.get("111")
    assert rec.color == "#cc4444"
    assert rec.cooldown_duration == 3600  # color write preserved cooldown
