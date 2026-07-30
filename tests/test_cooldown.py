from datetime import datetime, timedelta

from warestore.domain.accounts.cooldown import (
    cooldown_progress,
    format_cooldown_remaining,
    is_cooldown_active,
)
from warestore.infrastructure.persistence.metadata_repository import (
    AccountMetadataRepository,
)


def test_format_cooldown_hours():
    now = datetime(2026, 1, 1, 12, 0, 0)
    until = int((now + timedelta(hours=20)).timestamp())
    assert format_cooldown_remaining(until, now=now) == "CD 20h"


def test_format_cooldown_seconds():
    now = datetime(2026, 1, 1, 12, 0, 0)
    until = int((now + timedelta(seconds=30)).timestamp())
    assert format_cooldown_remaining(until, now=now) == "CD 30s"


def test_format_cooldown_minutes_and_seconds():
    now = datetime(2026, 1, 1, 12, 0, 0)
    until = int((now + timedelta(minutes=1, seconds=15)).timestamp())
    assert format_cooldown_remaining(until, now=now) == "CD 1m 15s"


def test_cooldown_progress():
    now = datetime(2026, 1, 1, 12, 0, 0)
    until = int((now + timedelta(seconds=30)).timestamp())
    assert cooldown_progress(until, 60, now=now) == 0.5
    assert cooldown_progress(until, 0, now=now) == 0.0


def test_format_cooldown_days():
    now = datetime(2026, 1, 1, 12, 0, 0)
    until = int((now + timedelta(days=7)).timestamp())
    assert format_cooldown_remaining(until, now=now) == "CD 7d"


def test_format_cooldown_expired():
    now = datetime(2026, 1, 1, 12, 0, 0)
    until = int((now - timedelta(hours=1)).timestamp())
    assert format_cooldown_remaining(until, now=now) == ""


def test_metadata_set_and_clear_cooldown(tmp_path, monkeypatch):
    path = tmp_path / "account_metadata.json"
    repo = AccountMetadataRepository(str(path))
    repo.set_cooldown("76561198000000001", 3600)
    record = repo.get("76561198000000001")
    assert record.cooldown_until > 0
    assert record.cooldown_duration == 3600
    label = format_cooldown_remaining(record.cooldown_until)
    assert label.startswith("CD ")

    repo.clear_cooldown("76561198000000001")
    cleared = repo.get("76561198000000001")
    assert cleared.cooldown_until == 0
    assert cleared.cooldown_duration == 0


def test_is_cooldown_active():
    now = datetime(2026, 1, 1, 12, 0, 0)
    future = int((now + timedelta(hours=1)).timestamp())
    past = int((now - timedelta(hours=1)).timestamp())
    assert is_cooldown_active(future, now=now)
    assert not is_cooldown_active(past, now=now)
    assert not is_cooldown_active(0, now=now)


def test_presenter_pop_expired_cooldowns(monkeypatch):
    import time as time_mod

    from warestore.application.account_manager.presenter import AccountManagerPresenter

    fixed_now = 1_000_000
    monkeypatch.setattr(time_mod, "time", lambda: fixed_now)

    class _Ctrl:
        def __init__(self):
            self.cleared: list[str] = []
            self._until = {"1": fixed_now - 10, "2": fixed_now + 100}

        def get_metadata(self, steam_id: str):
            from warestore.domain.accounts.models import AccountRecord

            return AccountRecord(cooldown_until=self._until.get(steam_id, 0))

        def clear_cooldown(self, steam_id: str) -> None:
            self.cleared.append(steam_id)
            self._until.pop(steam_id, None)

    ctrl = _Ctrl()
    p = AccountManagerPresenter(ctrl)  # type: ignore[arg-type]
    accounts = [
        {"steamid": "1", "account_name": "alice"},
        {"steamid": "2", "account_name": "bob"},
    ]
    watch = {"1": fixed_now - 10, "2": fixed_now + 100}
    expired = p.pop_expired_cooldowns(watch, accounts)
    assert expired == ["alice"]
    assert "1" not in watch
    assert "2" in watch
    assert ctrl.cleared == ["1"]
