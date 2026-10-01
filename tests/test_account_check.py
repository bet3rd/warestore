import pytest

from warestore.application.account_manager.account_check import (
    AccountCheckService,
    CheckSteps,
    SourceLoadout,
)
from warestore.infrastructure.steam import cs2_gc_proto as gp
from warestore.infrastructure.steam.cs2_cm_mint import TokenRejectedError
from warestore.infrastructure.steam.cs2_session import AccountInUseError, GcUnavailableError

TARGET = "76561198000000002"
SOURCE = "76561198000000001"
LOADOUT = gp.resolve_loadout({(gp.TEAM_T, 4): 64})


class FakeMeta:
    def __init__(self):
        self.calls = []

    def set_account_check(self, steam_id, **kw):
        self.calls.append((steam_id, kw))


class FakeSession:
    script = {}

    def __init__(self, token, *, read_only=False):
        self.token = token
        self.read_only = read_only
        self.calls = []
        FakeSession.last = self

    def __enter__(self):
        if "enter" in self.script:
            raise self.script["enter"]
        return self

    def __exit__(self, *exc):
        return False

    def _step(self, name, value):
        self.calls.append(name)
        if isinstance(self.script.get(name), Exception):
            raise self.script[name]
        return self.script.get(name, value)

    def profile(self):
        return self._step("profile", gp.GcProfile(level=6, premier_rating=15_000, premier_wins=30))

    def cooldown_seconds(self):
        return self._step("cooldown_seconds", 0)

    def clear_workshop(self):
        return self._step("clear_workshop", (3, 0))

    def write_loadout(self, want):
        return self._step("write_loadout", (30, 30))

    def read_loadout(self):
        return self._step("read_loadout", LOADOUT)


@pytest.fixture
def svc():
    FakeSession.script = {}
    meta = FakeMeta()
    service = AccountCheckService(
        token_for=lambda sid: "tok-" + sid,
        name_for=lambda sid: "src" if sid == SOURCE else sid,
        source_steam_id=lambda: SOURCE,
        metadata=meta,
        session_factory=FakeSession,
        clock=lambda: 0.0,
        wall_clock=lambda: 1_700_000_000,
    )
    return service, meta


def _source():
    return SourceLoadout(steam_id=SOURCE, name="src", loadout=LOADOUT)


def test_all_steps_run_in_order_and_are_saved(svc):
    service, meta = svc
    result = service.check(TARGET, CheckSteps(), _source())
    assert FakeSession.last.calls == ["profile", "cooldown_seconds", "clear_workshop", "write_loadout"]
    assert {k: o.status for k, o in result.outcomes.items()} == {"stats": "ok", "workshop": "ok", "loadout": "ok"}
    sid, kw = meta.calls[-1]
    assert sid == TARGET and kw["cs2_level"] == 6 and kw["premier_rating"] == 15_000
    assert "Workshop −3" in kw["summary"] and "Loadout from src" in kw["summary"]


def test_a_failing_step_does_not_stop_the_rest(svc):
    service, _ = svc
    FakeSession.script = {"clear_workshop": ConnectionError("boom")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["workshop"].status == "failed"
    assert result.outcomes["loadout"].status == "ok"


def test_disabled_steps_are_not_run(svc):
    service, _ = svc
    service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert FakeSession.last.calls == ["profile", "cooldown_seconds"]


def test_loadout_skipped_for_the_source_itself_and_without_source(svc):
    service, _ = svc
    assert service.check(SOURCE, CheckSteps(), _source()).outcomes["loadout"].status == "skipped"
    no_src = SourceLoadout(reason="no CS2 config source set")
    out = service.check(TARGET, CheckSteps(), no_src).outcomes["loadout"]
    assert out.status == "skipped" and "no CS2 config source" in out.detail


def test_rejected_token_flags_dead_and_saves_nothing(svc):
    service, meta = svc
    FakeSession.script = {"enter": TokenRejectedError("Revoked")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.token_dead and meta.calls == []


def test_in_use_marks_pending(svc):
    service, meta = svc
    FakeSession.script = {"enter": AccountInUseError()}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.in_use and meta.calls[-1] == (TARGET, {"pending": True})


def test_gc_unavailable_fails_every_step(svc):
    service, meta = svc
    FakeSession.script = {"enter": GcUnavailableError()}
    result = service.check(TARGET, CheckSteps(), _source())
    assert {o.status for o in result.outcomes.values()} == {"failed"}
    assert "CS2 servers didn't answer" in result.outcomes["stats"].detail
    assert meta.calls == []


def test_deadline_skips_remaining_steps(svc):
    service, _ = svc
    times = iter([0.0])  # first read (before stats) is in time, every later one is not
    service._clock = lambda: next(times, 99.0)
    result = service.check(TARGET, CheckSteps(), _source(), deadline=10.0)
    assert result.outcomes["stats"].status == "ok"
    assert result.outcomes["workshop"].status == "skipped"
    assert result.outcomes["loadout"].status == "skipped"


def test_read_source_loadout(svc):
    service, _ = svc
    src = service.read_source_loadout()
    assert src.loadout == LOADOUT and src.name == "src" and FakeSession.last.read_only


def test_read_source_without_token():
    service = AccountCheckService(
        token_for=lambda sid: "", name_for=lambda sid: sid, source_steam_id=lambda: SOURCE,
        metadata=FakeMeta(), session_factory=FakeSession,
    )
    src = service.read_source_loadout()
    assert src.loadout is None and "no saved token" in src.reason


def test_steps_from_settings():
    assert CheckSteps.from_settings({"account_check_workshop": False}) == CheckSteps(workshop=False)
