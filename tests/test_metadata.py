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


def test_set_profiles_persists_and_preserves(tmp_path):
    repo = AccountMetadataRepository(path=str(tmp_path / "meta.json"))
    repo.set_color("1", "#cc4444")  # pre-existing data must survive the batch write
    repo.set_profiles(
        {
            "1": {"persona": "Neo", "avatar_hash": "abc123"},
            "2": {"persona": "Trinity", "avatar_hash": "def456"},
        }
    )
    r1 = repo.get("1")
    assert (r1.persona, r1.avatar_hash, r1.color) == ("Neo", "abc123", "#cc4444")
    assert repo.get("2").persona == "Trinity"


def test_set_profiles_ignores_empty_values(tmp_path):
    repo = AccountMetadataRepository(path=str(tmp_path / "meta.json"))
    repo.set_profiles({"1": {"persona": "Neo", "avatar_hash": "abc"}})
    # a later fetch that returns no persona/hash must not wipe the cached ones
    repo.set_profiles({"1": {"persona": "", "avatar_hash": ""}})
    rec = repo.get("1")
    assert (rec.persona, rec.avatar_hash) == ("Neo", "abc")


def test_all_returns_records(tmp_path):
    repo = AccountMetadataRepository(path=str(tmp_path / "meta.json"))
    repo.set_profiles({"1": {"persona": "Neo", "avatar_hash": "abc"}})
    allrecs = repo.all()
    assert allrecs["1"].persona == "Neo"


def test_cs2_rank_persists_and_survives_reload(tmp_path):
    path = str(tmp_path / "meta.json")
    repo = AccountMetadataRepository(path=path)
    repo.set_color("1", "#cc4444")  # pre-existing data must survive
    repo.set_cs2_rank(
        "1",
        premier_rating=18567,
        wingman_rank=12,
        cooldown_expires=1796253080,
        premier_wins=1234,
        wingman_wins=56,
    )

    # New repo instance = reads from disk (simulates relaunch / reload).
    rec = AccountMetadataRepository(path=path).get("1")
    assert rec.premier_rating == 18567
    assert rec.premier_wins == 1234
    assert rec.wingman_rank == 12
    assert rec.wingman_wins == 56
    assert rec.cs2_cooldown_expires == 1796253080
    assert rec.color == "#cc4444"  # untouched


def test_cs2_rank_defaults_when_absent(tmp_path):
    repo = AccountMetadataRepository(path=str(tmp_path / "meta.json"))
    repo.set_color("1", "#cc4444")
    rec = repo.get("1")
    assert rec.premier_rating == -1 and rec.wingman_rank == -1 and rec.cs2_cooldown_expires == 0
    assert rec.premier_wins == -1 and rec.wingman_wins == -1
