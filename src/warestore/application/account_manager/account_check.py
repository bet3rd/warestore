# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account check: one CS2 server session per account — token, stats, Workshop,
loadout — with each step's outcome recorded and results saved to metadata."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from warestore.infrastructure.steam.cs2_cm_mint import CmLogonError, TokenRejectedError
from warestore.infrastructure.steam.cs2_gc_proto import Loadout
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
    in_use: bool = False
    in_use_reason: str = ""
    outcomes: dict[str, StepOutcome] = field(default_factory=dict)
    profile_ok: bool = False
    cooldown_ok: bool = False
    gcpd_ok: bool = False
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

    @property
    def stats_ok(self) -> bool:
        return self.profile_ok or self.cooldown_ok or self.gcpd_ok

    def summary(self) -> str:
        if self.token_dead:
            return "token rejected by Steam"
        if self.in_use:
            return f"skipped — {self.in_use_reason or 'account in use'}"
        parts: list[str] = []
        stats = self.outcomes.get("stats")
        if stats and stats.status == "ok" and self.cs2_level >= 0:
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
            logger.info("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(reason=reason)
        name = self._name_for(sid)
        token = self._token_for(sid)
        if not token:
            reason = "source account has no saved token"
            logger.info("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(steam_id=sid, name=name, reason=reason)
        try:
            with self._session_factory(token, read_only=True, deadline=deadline) as session:
                loadout = session.read_loadout()
                logger.info("account-check: source loadout read from %s", name)
                return SourceLoadout(steam_id=sid, name=name, loadout=loadout)
        except AccountInUseError as exc:
            reason = f"source account is {exc}"
            logger.info("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(steam_id=sid, name=name, reason=reason)
        except TokenRejectedError:
            reason = "source account's token was rejected"
            logger.info("account-check: source loadout skipped: %s", reason)
            return SourceLoadout(steam_id=sid, name=name, reason=reason)
        except Exception as exc:  # noqa: BLE001
            logger.warning("account-check: reading source loadout failed: %s", type(exc).__name__)
            reason = "couldn't read the source loadout"
            logger.info("account-check: source loadout skipped: %s", reason)
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
        logger.info("account-check: %s (…%s) — signing in (offline)…", acct_name, _short_id(steam_id))
        token = self._token_for(steam_id)
        if not token:
            for name in STEP_NAMES:
                result.outcomes[name] = StepOutcome("failed", "no saved token")
            return result
        t0 = time.monotonic()
        try:
            with self._session_factory(token, deadline=deadline) as session:
                logger.info("account-check: %s — CS2 server answered in %.1fs", acct_name, time.monotonic() - t0)
                self._run_steps(session, steps, source, result, deadline, acct_name)
        except TokenRejectedError:
            result.token_dead = True
            logger.warning("account-check: %s — token rejected by Steam", acct_name)
            return result
        except AccountInUseError as exc:
            result.in_use = True
            result.in_use_reason = str(exc)
            logger.info("account-check: %s — skipped: %s", acct_name, result.in_use_reason or "account in use")
            self._metadata.set_account_check(steam_id, pending=True)
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
        logger.info("account-check: %s — done: %s", acct_name, result.summary())
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
            logger.info("account-check: %s — GCPD scrape failed: %s", name, type(exc).__name__)
            gcpd = None

        if profile is None and cooldown is None and gcpd is None:
            return StepOutcome("failed", "no reply")

        missing: list[str] = []

        if profile is not None:
            result.cs2_level = profile.level
            result.profile_ok = True
            level_txt = str(profile.level) if profile.level >= 0 else "unknown"
        else:
            level_txt = "unknown"
            missing.append("profile didn't answer")

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

        if cooldown is not None:
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

        line = (
            f"account-check: {name} — stats: CS2 level {level_txt}, "
            f"Premier {premier_txt}, Wingman {wingman_txt}, {cooldown_txt}"
        )
        if missing:
            line += " (" + ", ".join(missing) + ")"
        logger.info(line)
        return StepOutcome("ok")

    def _workshop(self, session, result: CheckResult, name: str) -> StepOutcome:
        removed, failed = session.clear_workshop()
        result.workshop_removed = removed
        result.workshop_failed = failed
        logger.info("account-check: %s — Workshop: %d removed, %d failed", name, removed, failed)
        return StepOutcome("ok" if not failed else "failed", f"{failed} not removed" if failed else "")

    def _loadout(self, session, source: SourceLoadout, result: CheckResult, name: str) -> StepOutcome:
        if source.loadout is None:
            reason = source.reason or "no source loadout"
            logger.info("account-check: %s — loadout skipped: %s", name, reason)
            return StepOutcome("skipped", reason)
        if source.steam_id == result.steam_id:
            reason = "this is the source account"
            logger.info("account-check: %s — loadout skipped: %s", name, reason)
            return StepOutcome("skipped", reason)
        matched, total, changed = session.write_loadout(source.loadout)
        result.loadout_matched, result.loadout_total = matched, total
        result.loadout_source = source.name or source.steam_id
        logger.info(
            "account-check: %s — loadout: %d slots changed, %d/%d match (from %s)",
            name, changed, matched, total, result.loadout_source,
        )
        return StepOutcome("ok" if matched == total else "failed", f"{matched}/{total} slots")

    def _save(self, result: CheckResult) -> None:
        kw: dict = {"summary": result.summary(), "now": int(self._wall_clock())}
        if result.profile_ok:
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
