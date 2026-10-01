# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account check: one CS2 server session per account — token, stats, Workshop,
loadout — with each step's outcome recorded and results saved to metadata."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from warestore.domain.accounts.cs2_tier import PREMIER_MIN_LEVEL
from warestore.infrastructure.steam.cs2_cm_mint import (
    CmLogonError,
    RateLimitedError,
    TokenRejectedError,
)
from warestore.infrastructure.steam.cs2_gc_proto import PERMANENT_PENALTY_REASONS, Loadout
from warestore.infrastructure.steam.cs2_session import (
    AccountInUseError,
    Cs2Session,
    GcUnavailableError,
)
from warestore.infrastructure.steam.gcpd_parser import COOLDOWN_PERMANENT

logger = logging.getLogger(__name__)

STEP_NAMES = ("stats", "workshop", "loadout")


def _short_id(steam_id: str) -> str:
    """Last 6 digits of the SteamID, for a log line that doesn't need the whole thing."""
    return steam_id[-6:] if len(steam_id) > 6 else steam_id


def _format_hm(seconds: int) -> str:
    seconds = max(0, int(seconds))
    hours, minutes = divmod(seconds // 60, 60)
    return f"{hours}h {minutes}m"


@dataclass(frozen=True)
class CheckSteps:
    loadout: bool = True
    stats: bool = True
    workshop: bool = True

    @classmethod
    def from_settings(cls, settings: dict) -> "CheckSteps":
        return cls(
            loadout=bool(settings.get("account_check_loadout", True)),
            stats=bool(settings.get("account_check_stats", True)),
            workshop=bool(settings.get("account_check_workshop", True)),
        )


@dataclass(frozen=True)
class SourceLoadout:
    steam_id: str = ""
    name: str = ""
    loadout: Loadout | None = None
    reason: str = ""  # why loadout is None


@dataclass
class StepOutcome:
    status: str  # "ok" | "skipped" | "failed"
    detail: str = ""


@dataclass
class CheckResult:
    steam_id: str
    token_dead: bool = False
    rate_limited: bool = False  # Steam refused the sign-in: too many from this IP
    in_use: bool = False
    in_use_reason: str = ""
    outcomes: dict[str, StepOutcome] = field(default_factory=dict)
    web_only: bool = False  # in use: fell back to the web-only steps
    profile_ok: bool = False
    level_ok: bool = False
    cooldown_ok: bool = False
    gcpd_ok: bool = False
    prime: int = -1  # 1 Prime, 0 non-Prime, -1 unknown (GC only)
    service_medal: int = -1  # 1 earned one, 0 not, -1 unknown (GCPD)
    cs2_level: int = -1
    premier_rating: int = -1
    premier_wins: int = -1
    wingman_rank: int = -1
    wingman_wins: int = -1
    cooldown_expires: int = 0
    workshop_removed: int = 0
    workshop_failed: int = 0
    loadout_matched: int = 0
    loadout_total: int = 0
    loadout_source: str = ""
    stats_text: str = ""  # "Prime, CS2 level 12, Premier …" for the log line

    @property
    def stats_ok(self) -> bool:
        return self.profile_ok or self.cooldown_ok or self.gcpd_ok

    def log_line(self, elapsed: float) -> str:
        """The single INFO line for a finished check: full stats, then the rest."""
        text = self.summary()
        if self.stats_text:
            level = f"CS2 level {self.cs2_level}"
            parts = text.split(" · ")
            parts = [self.stats_text if p == level else p for p in parts]
            if self.stats_text not in parts:
                parts.insert(1 if self.web_only else 0, self.stats_text)
            text = " · ".join(p for p in parts if p != "nothing to do")
        return f"{text} ({elapsed:.1f}s)"

    def summary(self) -> str:
        if self.token_dead:
            return "token rejected by Steam"
        if self.rate_limited:
            return "Steam rate limit — try later or use a VPN/proxy"
        reason = self.in_use_reason or "account in use"
        if self.in_use and not self.web_only:
            return f"skipped — {reason}"
        parts: list[str] = [f"web only — {reason}"] if self.web_only else []
        stats = self.outcomes.get("stats")
        if stats and stats.status == "ok" and self.level_ok and self.cs2_level >= 0:
            parts.append(f"CS2 level {self.cs2_level}")
        work = self.outcomes.get("workshop")
        if work and work.status != "skipped":
            fail_note = f" ({self.workshop_failed} failed)" if self.workshop_failed > 0 else ""
            parts.append(f"Workshop −{self.workshop_removed}{fail_note}")
        if self.loadout_total > 0:
            ratio = "" if self.loadout_matched == self.loadout_total else f" {self.loadout_matched}/{self.loadout_total}"
            parts.append(f"Loadout{ratio} from {self.loadout_source}")
        failed = [k for k, o in self.outcomes.items() if o.status == "failed"]
        if failed:
            parts.append("failed: " + ", ".join(failed))
        return " · ".join(parts) or "nothing to do"


class AccountCheckService:
    def __init__(
        self,
        *,
        token_for: Callable[[str], str],
        name_for: Callable[[str], str],
        source_steam_id: Callable[[], str],
        metadata,
        session_factory=Cs2Session,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], float] = time.time,
    ) -> None:
        self._token_for = token_for
        self._name_for = name_for
        self._source_steam_id = source_steam_id
        self._metadata = metadata
        self._session_factory = session_factory
        self._clock = clock
        self._wall_clock = wall_clock

    def read_source_loadout(self, deadline: float | None = None) -> SourceLoadout:
        sid = self._source_steam_id()
        if not sid:
            reason = "no CS2 config source set"
            logger.debug("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(reason=reason)
        name = self._name_for(sid)
        token = self._token_for(sid)
        if not token:
            reason = "source account has no saved token"
            logger.debug("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(steam_id=sid, name=name, reason=reason)
        try:
            with self._session_factory(token, read_only=True, deadline=deadline) as session:
                loadout = session.read_loadout()
                logger.debug("account-check: source loadout read from %s", name)
                return SourceLoadout(steam_id=sid, name=name, loadout=loadout)
        except AccountInUseError as exc:
            reason = f"source account is {exc}"
            logger.debug("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(steam_id=sid, name=name, reason=reason)
        except TokenRejectedError:
            reason = "source account's token was rejected"
            logger.debug("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(steam_id=sid, name=name, reason=reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning("account-check: reading source loadout failed: %s", type(exc).__name__)
            reason = "couldn't read the source loadout"
            logger.debug("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(steam_id=sid, name=name, reason=reason)

    def check(
        self,
        steam_id: str,
        steps: CheckSteps,
        source: SourceLoadout,
        *,
        deadline: float | None = None,
    ) -> CheckResult:
        result = CheckResult(steam_id=steam_id)
        acct_name = self._name_for(steam_id)
        logger.debug("account-check: %s (…%s) — signing in (offline)…", acct_name, _short_id(steam_id))
        token = self._token_for(steam_id)
        if not token:
            for name in STEP_NAMES:
                result.outcomes[name] = StepOutcome("failed", "no saved token")
            return result
        t0 = time.monotonic()
        try:
            with self._session_factory(token, deadline=deadline) as session:
                logger.debug("account-check: %s — CS2 server answered in %.1fs", acct_name, time.monotonic() - t0)
                self._run_steps(session, steps, source, result, deadline, acct_name)
        except TokenRejectedError:
            result.token_dead = True
            logger.warning("account-check: %s — token rejected by Steam", acct_name)
            return result
        except AccountInUseError as exc:
            result.in_use = True
            result.in_use_reason = str(exc)
            reason = result.in_use_reason or "account in use"
            if not (steps.stats or steps.workshop):
                logger.info("account-check: %s — skipped: %s", acct_name, reason)
                self._metadata.set_account_check(steam_id, pending=True)
                return result
            logger.debug("account-check: %s — %s; web-only check (no CS2, no loadout)", acct_name, reason)
            self._web_only_check(token, steps, result, deadline, acct_name)
            if result.token_dead:
                return result
            if result.web_only:
                logger.info("account-check: %s — %s", acct_name, result.log_line(time.monotonic() - t0))
                self._save(result, partial=True)
            else:
                self._metadata.set_account_check(steam_id, pending=True)
            return result
        except RateLimitedError:
            result.rate_limited = True
            logger.warning("account-check: %s — Steam is rate-limiting sign-ins from this IP", acct_name)
            for name in STEP_NAMES:
                result.outcomes.setdefault(name, StepOutcome("failed", "Steam rate limit"))
            return result
        except GcUnavailableError as exc:
            # str(exc) names GC_CLIENT_VERSION and never contains a token — the
            # one clue worth logging in full for a stale-client diagnosis.
            logger.warning("account-check: %s for %s: %s", type(exc).__name__, steam_id, exc)
            for name in STEP_NAMES:
                result.outcomes.setdefault(name, StepOutcome("failed", "CS2 servers didn't answer"))
            return result
        except (CmLogonError, OSError) as exc:
            logger.warning("account-check: %s for %s", type(exc).__name__, steam_id)
            for name in STEP_NAMES:
                result.outcomes.setdefault(name, StepOutcome("failed", "CS2 servers didn't answer"))
            return result
        except Exception as exc:  # noqa: BLE001 - an unexpected error must never vanish
            logger.warning("account-check: unexpected %s for %s", type(exc).__name__, steam_id)
            for name in STEP_NAMES:
                result.outcomes.setdefault(name, StepOutcome("failed", "unexpected error"))
            return result
        logger.info("account-check: %s — %s", acct_name, result.log_line(time.monotonic() - t0))
        self._save(result)
        return result

    def _run_steps(self, session, steps: CheckSteps, source: SourceLoadout,
                   result: CheckResult, deadline: float | None, acct_name: str) -> None:
        def out_of_time() -> bool:
            return deadline is not None and self._clock() >= deadline

        plan = [
            ("stats", steps.stats, lambda: self._stats(session, result, acct_name)),
            ("workshop", steps.workshop, lambda: self._workshop(session, result, acct_name)),
            ("loadout", steps.loadout, lambda: self._loadout(session, source, result, acct_name)),
        ]
        for name, enabled, run in plan:
            if not enabled:
                continue
            if out_of_time():
                result.outcomes[name] = StepOutcome("skipped", "time limit reached")
                continue
            try:
                outcome = run()
            except AccountInUseError:
                # Must reach check()'s own handler (in_use=True, pending saved,
                # no further steps) rather than being recorded as a plain
                # failed step — the account turned out to be in use mid-check
                # (e.g. the cooldown cycle's leave/re-enter detected it).
                raise
            except Exception as exc:  # noqa: BLE001 - one step never stops the rest
                outcome = StepOutcome("failed", type(exc).__name__)
            result.outcomes[name] = outcome
            if outcome.status == "failed":
                logger.warning("account-check: %s — %s failed: %s", acct_name, name, outcome.detail or "failed")

    def _stats(self, session, result: CheckResult, name: str) -> StepOutcome:
        # A GcUnavailableError mid-call (a budget/deadline running out partway
        # through profile()'s wait or cooldown_seconds()'s leave/re-enter cycle)
        # is just that particular reply not arriving in time — it must not
        # discard a reply that already did arrive, nor skip GCPD.
        # AccountInUseError is NOT caught here: it must propagate (see
        # _run_steps) to check()'s own in-use handling.
        prime = session.prime()
        if prime is not None:
            result.prime = 1 if prime else 0
        try:
            profile = session.profile()
        except GcUnavailableError:
            profile = None
        try:
            cooldown = session.cooldown_seconds()
        except GcUnavailableError:
            cooldown = None
        try:
            gcpd = session.gcpd_rank()
        except Exception as exc:  # noqa: BLE001 - GCPD is best-effort; GC data must still save
            logger.debug("account-check: %s — GCPD scrape failed: %s", name, type(exc).__name__)
            gcpd = None

        if profile is None and cooldown is None and gcpd is None:
            return StepOutcome("failed", "no reply")

        missing: list[str] = []

        if profile is not None:
            result.profile_ok = True
            if profile.level >= 0:
                result.cs2_level = profile.level
                result.level_ok = True
        else:
            missing.append("profile didn't answer")
        if not result.level_ok:
            # Some accounts' GC profile carries no level; GCPD's account tab has it.
            try:
                level = session.gcpd_level()
            except Exception:  # noqa: BLE001 - best-effort, like the GCPD scrape
                level = -1
            if level >= 0:
                result.cs2_level = level
                result.level_ok = True
        level_txt = str(result.cs2_level) if result.level_ok else "unknown"
        if result.prime == 1 and not (result.level_ok and result.cs2_level >= PREMIER_MIN_LEVEL):
            # Only matters for a Prime account under 10: a service medal means
            # it already passed 10 (the medal resets the level).
            try:
                result.service_medal = session.gcpd_service_medal()
            except Exception:  # noqa: BLE001 - best-effort, like the GCPD scrape
                result.service_medal = -1

        if gcpd is not None:
            result.wingman_rank = gcpd.wingman_rank
            result.wingman_wins = gcpd.wingman_wins
            result.gcpd_ok = True
        else:
            missing.append("GCPD didn't answer")

        if profile is not None or gcpd is not None:
            gc_rating = profile.premier_rating if profile is not None else -1
            gc_wins = profile.premier_wins if profile is not None else -1
            gcpd_rating = gcpd.premier_rating if gcpd is not None else -1
            gcpd_wins = gcpd.premier_wins if gcpd is not None else -1
            result.premier_rating = gc_rating if gc_rating > 0 else (
                gcpd_rating if gcpd_rating > 0 else -1
            )
            result.premier_wins = gcpd_wins if gcpd_wins >= 0 else gc_wins
        premier_txt = f"{result.premier_rating:,}" if result.premier_rating > 0 else "unranked"
        if result.premier_rating > 0 and result.premier_wins >= 0:
            premier_txt += f" ({result.premier_wins} wins)"

        wingman_txt = "unknown" if gcpd is None else (
            str(result.wingman_rank) if result.wingman_rank > 0 else "unranked"
        )

        # A permanent penalty (a CS2 ban) wins over the GC's timed number: the
        # GC reports bans as a long countdown, GCPD as "Never".
        permanent = (
            (gcpd is not None and gcpd.cooldown_expires_unix >= COOLDOWN_PERMANENT)
            or (bool(cooldown) and session.cooldown_reason() in PERMANENT_PENALTY_REASONS)
        )
        if permanent:
            result.cooldown_expires = COOLDOWN_PERMANENT
            result.cooldown_ok = True
            cooldown_txt = "cooldown permanent (CS2 ban)"
        elif cooldown is not None:
            result.cooldown_expires = int(self._wall_clock()) + cooldown if cooldown > 0 else 0
            result.cooldown_ok = True
            cooldown_txt = "no cooldown" if cooldown <= 0 else f"cooldown {_format_hm(cooldown)} left"
        elif gcpd is not None:
            result.cooldown_expires = gcpd.cooldown_expires_unix
            result.cooldown_ok = True
            if gcpd.cooldown_expires_unix <= 0:
                cooldown_txt = "no cooldown"
            elif gcpd.cooldown_expires_unix >= COOLDOWN_PERMANENT:
                cooldown_txt = "cooldown permanent"
            else:
                remaining = max(0, gcpd.cooldown_expires_unix - int(self._wall_clock()))
                cooldown_txt = f"cooldown {_format_hm(remaining)} left"
        else:
            cooldown_txt = "unknown"
            missing.append("cooldown didn't answer")

        prime_txt = {1: "Prime", 0: "non-Prime"}.get(result.prime, "Prime unknown")
        line = (
            f"account-check: {name} — stats: {prime_txt}, CS2 level {level_txt}, "
            f"Premier {premier_txt}, Wingman {wingman_txt}, {cooldown_txt}"
        )
        if missing:
            line += " (" + ", ".join(missing) + ")"
        result.stats_text = line.split(" — stats: ", 1)[1]
        logger.debug(line)
        return StepOutcome("ok")

    def _web_only_check(self, token: str, steps: CheckSteps, result: CheckResult,
                        deadline: float | None, acct_name: str) -> None:
        """For an account that's playing (here or elsewhere): a plain CM logon
        that never starts CS2, so the other session keeps running. Gets what
        the web can give — GCPD stats + Workshop. Prime and the loadout need
        the CS2 servers, so they wait for a full check."""
        try:
            with self._session_factory(token, web_only=True, deadline=deadline) as session:
                result.web_only = True
                if steps.stats:
                    result.outcomes["stats"] = self._guard(
                        "stats", acct_name, lambda: self._web_stats(session, result, acct_name))
                if steps.workshop:
                    result.outcomes["workshop"] = self._guard(
                        "workshop", acct_name, lambda: self._workshop(session, result, acct_name))
                if steps.loadout:
                    result.outcomes["loadout"] = StepOutcome("skipped", "account in use")
        except TokenRejectedError:
            result.token_dead = True
            logger.warning("account-check: %s — token rejected by Steam", acct_name)
        except RateLimitedError:
            result.web_only = False
            result.rate_limited = True
            logger.warning("account-check: %s — Steam is rate-limiting sign-ins from this IP", acct_name)
        except Exception as exc:  # noqa: BLE001 - the fallback is best-effort
            result.web_only = False
            logger.info("account-check: %s — web-only check failed: %s", acct_name, type(exc).__name__)

    @staticmethod
    def _guard(name: str, acct_name: str, run) -> StepOutcome:
        try:
            outcome = run()
        except Exception as exc:  # noqa: BLE001 - one step never stops the rest
            outcome = StepOutcome("failed", type(exc).__name__)
        if outcome.status == "failed":
            logger.warning("account-check: %s — %s failed: %s", acct_name, name, outcome.detail or "failed")
        return outcome

    def _web_stats(self, session, result: CheckResult, name: str) -> StepOutcome:
        gcpd = session.gcpd_rank()
        level = session.gcpd_level()
        if gcpd is None and level < 0:
            return StepOutcome("failed", "GCPD didn't answer")
        result.service_medal = session.gcpd_service_medal()  # same page as the level
        if level >= 0:
            result.cs2_level = level
            result.level_ok = True
        if gcpd is not None:
            result.gcpd_ok = True
            result.premier_rating = gcpd.premier_rating if gcpd.premier_rating > 0 else -1
            result.premier_wins = gcpd.premier_wins
            result.wingman_rank = gcpd.wingman_rank
            result.wingman_wins = gcpd.wingman_wins
            result.cooldown_expires = gcpd.cooldown_expires_unix
            result.cooldown_ok = True
        result.stats_text = "CS2 level {}, Premier {}, Wingman {}, {}".format(
            level if level >= 0 else "unknown",
            f"{result.premier_rating:,}" if result.premier_rating > 0 else "unranked",
            result.wingman_rank if result.wingman_rank > 0 else "unranked",
            "no cooldown" if result.cooldown_expires <= 0 else (
                "cooldown permanent" if result.cooldown_expires >= COOLDOWN_PERMANENT else "on cooldown"
            ),
        )
        logger.debug("account-check: %s — web stats: %s", name, result.stats_text)
        return StepOutcome("ok")

    def _workshop(self, session, result: CheckResult, name: str) -> StepOutcome:
        removed, failed = session.clear_workshop()
        result.workshop_removed = removed
        result.workshop_failed = failed
        logger.debug("account-check: %s — Workshop: %d removed, %d failed", name, removed, failed)
        return StepOutcome("ok" if not failed else "failed", f"{failed} not removed" if failed else "")

    def _loadout(self, session, source: SourceLoadout, result: CheckResult, name: str) -> StepOutcome:
        if source.loadout is None:
            reason = source.reason or "no source loadout"
            logger.debug("account-check: %s — loadout skipped: %s", name, reason)
            return StepOutcome("skipped", reason)
        if source.steam_id == result.steam_id:
            reason = "this is the source account"
            logger.debug("account-check: %s — loadout skipped: %s", name, reason)
            return StepOutcome("skipped", reason)
        matched, total, changed = session.write_loadout(source.loadout)
        result.loadout_matched, result.loadout_total = matched, total
        result.loadout_source = source.name or source.steam_id
        logger.debug(
            "account-check: %s — loadout: %d slots changed, %d/%d match (from %s)",
            name, changed, matched, total, result.loadout_source,
        )
        return StepOutcome("ok" if matched == total else "failed", f"{matched}/{total} slots")

    def _save(self, result: CheckResult, *, partial: bool = False) -> None:
        kw: dict = {"summary": result.summary(), "now": int(self._wall_clock())}
        if partial:
            kw["pending"] = True
            kw["partial"] = True
        if result.prime >= 0:
            kw["prime"] = result.prime
        if result.service_medal >= 0:
            kw["service_medal"] = result.service_medal
        if result.level_ok:
            kw["cs2_level"] = result.cs2_level
        if result.profile_ok or result.gcpd_ok:
            kw["premier_rating"] = result.premier_rating
            kw["premier_wins"] = result.premier_wins
        if result.gcpd_ok:
            kw["wingman_rank"] = result.wingman_rank
            kw["wingman_wins"] = result.wingman_wins
        if result.cooldown_ok:
            kw["cooldown_expires"] = result.cooldown_expires
        self._metadata.set_account_check(result.steam_id, **kw)
