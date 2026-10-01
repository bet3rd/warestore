import logging

import pytest

from warestore.application.account_manager.account_check import (
    AccountCheckService,
    CheckSteps,
    SourceLoadout,
)
from warestore.infrastructure.steam import cs2_gc_proto as gp
from warestore.infrastructure.steam.cs2_cm_mint import TokenRejectedError
from warestore.infrastructure.steam.cs2_session import AccountInUseError, GcUnavailableError
from warestore.infrastructure.steam.gcpd_parser import COOLDOWN_PERMANENT, Cs2Rank

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

    def __init__(self, token, *, read_only=False, web_only=False, deadline=None):
        self.token = token
        self.read_only = read_only
        self.web_only = web_only
        self.deadline = deadline
        self.calls = []
        FakeSession.last = self
        if web_only:
            FakeSession.web = self
        else:
            FakeSession.full = self

    def __enter__(self):
        key = "web_enter" if self.web_only else "enter"
        if key in self.script:
            raise self.script[key]
        return self

    def prime(self):
        return self._step("prime", True)

    def gcpd_level(self):
        return self._step("gcpd_level", 14)

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

    def cooldown_reason(self):
        return self.script.get("cooldown_reason", 0)

    def gcpd_rank(self):
        return self._step("gcpd_rank", None)

    def clear_workshop(self):
        return self._step("clear_workshop", (3, 0))

    def write_loadout(self, want):
        return self._step("write_loadout", (30, 30, 2))

    def read_loadout(self):
        return self._step("read_loadout", LOADOUT)


@pytest.fixture
def svc():
    FakeSession.script = {}
    FakeSession.web = None
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
    assert FakeSession.last.calls == [
        "prime", "profile", "cooldown_seconds", "gcpd_rank", "clear_workshop", "write_loadout",
    ]
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
    assert FakeSession.last.calls == ["prime", "profile", "cooldown_seconds", "gcpd_rank"]


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
    FakeSession.script = {"enter": AccountInUseError("playing a game on this PC"),
                          "web_enter": ConnectionError("no network")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.in_use and meta.calls[-1] == (TARGET, {"pending": True})
    assert result.in_use_reason == "playing a game on this PC"
    assert result.summary() == "skipped — playing a game on this PC"


def test_in_use_without_a_reason_falls_back_in_the_summary(svc):
    service, _ = svc
    FakeSession.script = {"enter": AccountInUseError(), "web_enter": ConnectionError("no network")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.in_use_reason == ""
    assert result.summary() == "skipped — account in use"


def test_gc_unavailable_fails_every_step(svc):
    service, meta = svc
    FakeSession.script = {"enter": GcUnavailableError()}
    result = service.check(TARGET, CheckSteps(), _source())
    assert {o.status for o in result.outcomes.values()} == {"failed"}
    assert "CS2 servers didn't answer" in result.outcomes["stats"].detail
    assert meta.calls == []


def test_in_use_detected_mid_cooldown_cycle_stops_the_check(svc):
    """Fix round 1 (1): AccountInUseError raised by the cooldown leave/
    re-enter cycle must reach check()'s own in-use handling, not be recorded
    as a plain failed "stats" step — Workshop/loadout must never run against
    an account that turned out to be playing elsewhere mid-check."""
    service, meta = svc
    FakeSession.script = {"cooldown_seconds": AccountInUseError("playing on another device"),
                          "web_enter": ConnectionError("no network")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.in_use and result.in_use_reason == "playing on another device"
    assert "workshop" not in result.outcomes and "loadout" not in result.outcomes
    assert "clear_workshop" not in FakeSession.full.calls
    assert "write_loadout" not in FakeSession.full.calls
    assert meta.calls[-1] == (TARGET, {"pending": True})


def test_cooldown_time_limit_during_cycle_keeps_profile_data_and_tries_gcpd(svc):
    """Fix round 1 (2): a budget/deadline GcUnavailableError raised mid-cycle
    in cooldown_seconds() must be treated like a plain "didn't answer" — the
    profile data that already arrived must still save, and GCPD must still be
    attempted."""
    service, meta = svc
    FakeSession.script = {"cooldown_seconds": GcUnavailableError("time limit")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert FakeSession.last.calls[:4] == ["prime", "profile", "cooldown_seconds", "gcpd_rank"]
    assert result.outcomes["stats"].status == "ok"
    assert result.profile_ok and result.cs2_level == 6 and result.premier_rating == 15_000
    assert not result.cooldown_ok
    # the rest of the check still ran — this was not treated as fatal
    assert "clear_workshop" in FakeSession.last.calls
    assert "write_loadout" in FakeSession.last.calls
    sid, kw = meta.calls[-1]
    assert kw["cs2_level"] == 6 and kw["premier_rating"] == 15_000
    assert "cooldown_expires" not in kw


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


def test_read_source_loadout_in_use_reason_is_prefixed(svc):
    service, _ = svc
    FakeSession.script = {"enter": AccountInUseError("playing a game on this PC")}
    src = service.read_source_loadout()
    assert src.reason == "source account is playing a game on this PC"


def test_read_source_without_token():
    service = AccountCheckService(
        token_for=lambda sid: "", name_for=lambda sid: sid, source_steam_id=lambda: SOURCE,
        metadata=FakeMeta(), session_factory=FakeSession,
    )
    src = service.read_source_loadout()
    assert src.loadout is None and "no saved token" in src.reason


def test_steps_from_settings():
    assert CheckSteps.from_settings({"account_check_workshop": False}) == CheckSteps(workshop=False)


def test_deadline_is_passed_through_to_the_session_factory(svc):
    service, _ = svc
    service.check(TARGET, CheckSteps(), _source(), deadline=42.0)
    assert FakeSession.last.deadline == 42.0


def test_cooldown_timeout_does_not_overwrite_saved_cooldown(svc):
    service, meta = svc
    FakeSession.script = {"cooldown_seconds": None}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["stats"].status == "ok"  # profile still answered
    sid, kw = meta.calls[-1]
    assert "cooldown_expires" not in kw
    assert kw["cs2_level"] == 6 and kw["premier_rating"] == 15_000


def test_profile_timeout_does_not_overwrite_saved_level_or_premier(svc):
    service, meta = svc
    FakeSession.script = {"profile": None, "gcpd_level": -1}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["stats"].status == "ok"  # cooldown still answered
    sid, kw = meta.calls[-1]
    assert "cs2_level" not in kw and "premier_rating" not in kw and "premier_wins" not in kw


def test_loadout_partial_still_shows_in_the_summary(svc):
    service, _ = svc
    FakeSession.script = {"write_loadout": (27, 30, 3)}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["loadout"].status == "failed"
    assert "Loadout 27/30 from src" in result.summary()


def test_workshop_failed_count_shows_in_the_summary(svc):
    service, _ = svc
    FakeSession.script = {"clear_workshop": (5, 2)}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["workshop"].status == "failed"
    assert "Workshop −5 (2 failed)" in result.summary()


def test_unexpected_error_marks_remaining_steps_failed_and_saves_nothing(svc):
    service, meta = svc
    FakeSession.script = {"enter": ValueError("weird")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert {o.status for o in result.outcomes.values()} == {"failed"}
    assert all(o.detail == "unexpected error" for o in result.outcomes.values())
    assert meta.calls == []


def test_logs_are_readable_and_never_leak_the_token(svc, caplog):
    service, _ = svc
    caplog.set_level(logging.INFO)
    token = "tok-" + TARGET  # matches the svc fixture's token_for
    result = service.check(TARGET, CheckSteps(), _source())
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "signing in (offline)" in text
    assert "stats:" in text
    assert "Workshop:" in text
    assert "loadout:" in text
    assert f"done: {result.summary()}" in text
    assert token not in text


# --- GCPD folded into the stats step: merge rules ----------------------------


def test_premier_prefers_gc_rating_over_gcpd_when_gc_answers(svc):
    service, meta = svc
    FakeSession.script = {
        "gcpd_rank": Cs2Rank(premier_rating=9_000, premier_wins=5, wingman_rank=3, wingman_wins=2),
    }
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["stats"].status == "ok"
    assert result.premier_rating == 15_000  # GC profile's 15_000, not GCPD's 9_000
    assert result.premier_wins == 5  # GCPD wins preferred whenever GCPD answered
    assert result.wingman_rank == 3 and result.wingman_wins == 2
    sid, kw = meta.calls[-1]
    assert kw["premier_rating"] == 15_000 and kw["premier_wins"] == 5
    assert kw["wingman_rank"] == 3 and kw["wingman_wins"] == 2


def test_premier_falls_back_to_gcpd_when_gc_profile_is_unranked(svc):
    service, meta = svc
    FakeSession.script = {
        "profile": gp.GcProfile(level=6, premier_rating=-1, premier_wins=-1),
        "gcpd_rank": Cs2Rank(premier_rating=9_000, premier_wins=5, wingman_rank=-1, wingman_wins=-1),
    }
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.premier_rating == 9_000
    assert result.premier_wins == 5
    sid, kw = meta.calls[-1]
    assert kw["premier_rating"] == 9_000 and kw["premier_wins"] == 5


def test_gcpd_only_still_saves_premier_even_though_gc_profile_never_answered(svc):
    service, meta = svc
    FakeSession.script = {
        "profile": None,
        "cooldown_seconds": None,
        "gcpd_rank": Cs2Rank(premier_rating=9_000, premier_wins=5, wingman_rank=4, wingman_wins=1),
        "gcpd_level": -1,
    }
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["stats"].status == "ok"
    assert not result.profile_ok and result.gcpd_ok
    sid, kw = meta.calls[-1]
    assert "cs2_level" not in kw
    assert kw["premier_rating"] == 9_000 and kw["premier_wins"] == 5
    assert kw["wingman_rank"] == 4 and kw["wingman_wins"] == 1


def test_cooldown_falls_back_to_gcpd_permanent_cooldown_when_gc_silent(svc):
    service, meta = svc
    FakeSession.script = {
        "cooldown_seconds": None,
        "gcpd_rank": Cs2Rank(cooldown_expires_unix=COOLDOWN_PERMANENT, cooldown_reason="Competitive cooldown"),
    }
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.cooldown_ok and result.cooldown_expires == COOLDOWN_PERMANENT
    sid, kw = meta.calls[-1]
    assert kw["cooldown_expires"] == COOLDOWN_PERMANENT


def test_gcpd_failure_does_not_fail_stats_when_gc_answered(svc):
    service, meta = svc
    FakeSession.script = {"gcpd_rank": ConnectionError("boom")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.outcomes["stats"].status == "ok"
    assert result.profile_ok and not result.gcpd_ok
    sid, kw = meta.calls[-1]
    assert "wingman_rank" not in kw and "wingman_wins" not in kw
    assert kw["premier_rating"] == 15_000  # GC data still saved despite the GCPD exception


def test_stats_log_line_includes_wingman(svc, caplog):
    service, _ = svc
    caplog.set_level(logging.INFO)
    FakeSession.script = {
        "gcpd_rank": Cs2Rank(premier_rating=-1, premier_wins=41, wingman_rank=5, wingman_wins=12),
    }
    service.check(TARGET, CheckSteps(), _source())
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "Wingman 5" in text


def test_prime_is_read_from_the_gc_and_saved(svc):
    service, meta = svc
    FakeSession.script = {"prime": False}
    result = service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert result.prime == 0
    assert meta.calls[-1][1]["prime"] == 0


def test_unknown_prime_is_not_saved(svc):
    service, meta = svc
    FakeSession.script = {"prime": None}
    service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert "prime" not in meta.calls[-1][1]


def test_in_use_account_falls_back_to_web_only(svc):
    service, meta = svc
    gcpd = Cs2Rank(premier_rating=-1, wingman_rank=7, wingman_wins=3, cooldown_expires_unix=0)
    FakeSession.script = {"enter": AccountInUseError("playing on another device"), "gcpd_rank": gcpd}
    result = service.check(TARGET, CheckSteps(), _source())
    web = FakeSession.web
    assert web is not None and web.calls == ["gcpd_rank", "gcpd_level", "clear_workshop"]
    assert result.in_use and result.cs2_level == 14 and result.wingman_rank == 7
    assert result.outcomes["loadout"].status == "skipped"
    sid, kw = meta.calls[-1]
    assert kw["pending"] is True and kw["partial"] is True
    assert kw["cs2_level"] == 14 and kw["wingman_rank"] == 7 and kw["cooldown_expires"] == 0
    assert "prime" not in kw  # Prime only ever comes from the GC
    assert "web only" in kw["summary"]


def test_web_fallback_failure_still_flags_pending(svc):
    service, meta = svc
    FakeSession.script = {"enter": AccountInUseError("playing on another device"),
                          "web_enter": ConnectionError("no network")}
    result = service.check(TARGET, CheckSteps(), _source())
    assert result.in_use
    assert meta.calls[-1][1] == {"pending": True}


def test_web_fallback_not_tried_for_loadout_only_checks(svc):
    service, meta = svc
    FakeSession.script = {"enter": AccountInUseError("playing on another device")}
    service.check(TARGET, CheckSteps(stats=False, workshop=False), _source())
    assert FakeSession.web is None
    assert meta.calls[-1][1] == {"pending": True}


def test_missing_gc_level_falls_back_to_gcpd(svc):
    service, meta = svc
    FakeSession.script = {"profile": gp.GcProfile(level=-1, premier_rating=-1, premier_wins=-1)}
    result = service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert "gcpd_level" in FakeSession.last.calls
    assert result.cs2_level == 14 and meta.calls[-1][1]["cs2_level"] == 14


def test_unknown_level_is_never_saved_over_a_good_one(svc):
    service, meta = svc
    FakeSession.script = {"profile": gp.GcProfile(level=-1, premier_rating=-1, premier_wins=-1),
                          "gcpd_level": -1}
    service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert "cs2_level" not in meta.calls[-1][1]


def test_gc_level_skips_the_gcpd_level_fetch(svc):
    service, _ = svc
    service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert "gcpd_level" not in FakeSession.last.calls


def test_gcpd_never_beats_a_long_gc_cooldown(svc):
    """Live: banned accounts get a ~1-year 9110 penalty while GCPD says
    "Never" — the permanent one must win, or a ban shows as a cooldown."""
    service, meta = svc
    FakeSession.script = {
        "cooldown_seconds": 28_971_955, "cooldown_reason": 10,
        "gcpd_rank": Cs2Rank(cooldown_expires_unix=COOLDOWN_PERMANENT),
    }
    result = service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert result.cooldown_expires == COOLDOWN_PERMANENT
    assert meta.calls[-1][1]["cooldown_expires"] == COOLDOWN_PERMANENT


def test_permanent_penalty_reason_without_gcpd_is_permanent(svc):
    service, _ = svc
    FakeSession.script = {"cooldown_seconds": 30_837_845, "cooldown_reason": 10}
    result = service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert result.cooldown_expires == COOLDOWN_PERMANENT


def test_ordinary_penalty_stays_timed(svc):
    service, _ = svc
    FakeSession.script = {"cooldown_seconds": 502_496, "cooldown_reason": 22}
    result = service.check(TARGET, CheckSteps(loadout=False, workshop=False), _source())
    assert result.cooldown_expires == 1_700_000_000 + 502_496
