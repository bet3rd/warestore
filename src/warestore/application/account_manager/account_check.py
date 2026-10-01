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

logger = logging.getLogger(__name__)

STEP_NAMES = ("stats", "workshop", "loadout")


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
    outcomes: dict[str, StepOutcome] = field(default_factory=dict)
    stats_ok: bool = False
    cs2_level: int = -1
    premier_rating: int = -1
    premier_wins: int = -1
    cooldown_expires: int = 0
    workshop_removed: int = 0
    loadout_matched: int = 0
    loadout_total: int = 0
    loadout_source: str = ""

    def summary(self) -> str:
        if self.token_dead:
            return "token rejected by Steam"
        if self.in_use:
            return "skipped — account in use"
        parts: list[str] = []
        stats = self.outcomes.get("stats")
        if stats and stats.status == "ok" and self.cs2_level >= 0:
            parts.append(f"CS2 level {self.cs2_level}")
        work = self.outcomes.get("workshop")
        if work and work.status == "ok":
            parts.append(f"Workshop −{self.workshop_removed}")
        load = self.outcomes.get("loadout")
        if load and load.status == "ok":
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

    def read_source_loadout(self) -> SourceLoadout:
        sid = self._source_steam_id()
        if not sid:
            return SourceLoadout(reason="no CS2 config source set")
        name = self._name_for(sid)
        token = self._token_for(sid)
        if not token:
            return SourceLoadout(steam_id=sid, name=name, reason="source account has no saved token")
        try:
            with self._session_factory(token, read_only=True) as session:
                return SourceLoadout(steam_id=sid, name=name, loadout=session.read_loadout())
        except AccountInUseError:
            return SourceLoadout(steam_id=sid, name=name, reason="source account is in CS2 right now")
        except TokenRejectedError:
            return SourceLoadout(steam_id=sid, name=name, reason="source account's token was rejected")
        except Exception as exc:  # noqa: BLE001
            logger.warning("account-check: reading source loadout failed: %s", type(exc).__name__)
            return SourceLoadout(steam_id=sid, name=name, reason="couldn't read the source loadout")

    def check(
        self,
        steam_id: str,
        steps: CheckSteps,
        source: SourceLoadout,
        *,
        deadline: float | None = None,
    ) -> CheckResult:
        result = CheckResult(steam_id=steam_id)
        token = self._token_for(steam_id)
        if not token:
            for name in STEP_NAMES:
                result.outcomes[name] = StepOutcome("failed", "no saved token")
            return result
        try:
            with self._session_factory(token) as session:
                self._run_steps(session, steps, source, result, deadline)
        except TokenRejectedError:
            result.token_dead = True
            return result
        except AccountInUseError:
            result.in_use = True
            self._metadata.set_account_check(steam_id, pending=True)
            return result
        except (GcUnavailableError, CmLogonError, OSError) as exc:
            logger.warning("account-check: %s for %s", type(exc).__name__, steam_id)
            for name in STEP_NAMES:
                result.outcomes.setdefault(name, StepOutcome("failed", "CS2 servers didn't answer"))
            return result
        self._save(result)
        return result

    def _run_steps(self, session, steps: CheckSteps, source: SourceLoadout,
                   result: CheckResult, deadline: float | None) -> None:
        def out_of_time() -> bool:
            return deadline is not None and self._clock() >= deadline

        plan = [
            ("stats", steps.stats, lambda: self._stats(session, result)),
            ("workshop", steps.workshop, lambda: self._workshop(session, result)),
            ("loadout", steps.loadout, lambda: self._loadout(session, source, result)),
        ]
        for name, enabled, run in plan:
            if not enabled:
                continue
            if out_of_time():
                result.outcomes[name] = StepOutcome("skipped", "time limit reached")
                continue
            try:
                result.outcomes[name] = run()
            except Exception as exc:  # noqa: BLE001 - one step never stops the rest
                logger.warning("account-check: %s failed for %s: %s", name, result.steam_id, type(exc).__name__)
                result.outcomes[name] = StepOutcome("failed", type(exc).__name__)

    def _stats(self, session, result: CheckResult) -> StepOutcome:
        profile = session.profile()
        cooldown = session.cooldown_seconds()
        if profile is None and cooldown is None:
            return StepOutcome("failed", "no reply")
        if profile is not None:
            result.cs2_level = profile.level
            result.premier_rating = profile.premier_rating
            result.premier_wins = profile.premier_wins
        if cooldown is not None:
            result.cooldown_expires = int(self._wall_clock()) + cooldown if cooldown > 0 else 0
        result.stats_ok = True
        return StepOutcome("ok")

    def _workshop(self, session, result: CheckResult) -> StepOutcome:
        removed, failed = session.clear_workshop()
        result.workshop_removed = removed
        return StepOutcome("ok" if not failed else "failed", f"{failed} not removed" if failed else "")

    def _loadout(self, session, source: SourceLoadout, result: CheckResult) -> StepOutcome:
        if source.loadout is None:
            return StepOutcome("skipped", source.reason or "no source loadout")
        if source.steam_id == result.steam_id:
            return StepOutcome("skipped", "this is the source account")
        matched, total = session.write_loadout(source.loadout)
        result.loadout_matched, result.loadout_total = matched, total
        result.loadout_source = source.name or source.steam_id
        return StepOutcome("ok" if matched == total else "failed", f"{matched}/{total} slots")

    def _save(self, result: CheckResult) -> None:
        kw: dict = {"summary": result.summary(), "now": int(self._wall_clock())}
        if result.stats_ok:
            kw.update(
                cs2_level=result.cs2_level,
                premier_rating=result.premier_rating,
                premier_wins=result.premier_wins,
                cooldown_expires=result.cooldown_expires,
            )
        self._metadata.set_account_check(result.steam_id, **kw)
