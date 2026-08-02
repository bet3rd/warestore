# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account cooldown presets and formatting."""

from datetime import datetime

COOLDOWN_PRESETS: tuple[tuple[str, int], ...] = (
    ("20 hours", 20 * 3600),
    ("7 days", 7 * 86400),
    ("31 days", 31 * 86400),
    ("181 days", 181 * 86400),
)


def is_cooldown_active(until_ts: int, *, now: datetime | None = None) -> bool:
    if until_ts <= 0:
        return False
    current = now or datetime.now()
    return until_ts > int(current.timestamp())


def format_cooldown_remaining(until_ts: int, *, now: datetime | None = None) -> str:
    if until_ts <= 0:
        return ""
    current = now or datetime.now()
    remaining = until_ts - int(current.timestamp())
    if remaining <= 0:
        return ""
    if remaining < 60:
        return f"CD {remaining}s"
    if remaining < 3600:
        mins, secs = divmod(remaining, 60)
        if secs:
            return f"CD {mins}m {secs}s"
        return f"CD {mins}m"
    if remaining < 86400 * 2:
        hours, rem = divmod(remaining, 3600)
        mins = rem // 60
        if mins:
            return f"CD {hours}h {mins}m"
        return f"CD {hours}h"
    days = remaining // 86400
    if days < 30:
        return f"CD {days}d"
    return f"CD {days // 30}mo"


def format_cooldown_short(until_ts: int, *, now: datetime | None = None) -> str:
    """Compact label for the card: minutes only when under an hour, otherwise a
    single coarser unit (hours / days / months). The tooltip uses the full
    formatter (:func:`format_cooldown_remaining`) which keeps minutes."""
    if until_ts <= 0:
        return ""
    current = now or datetime.now()
    remaining = until_ts - int(current.timestamp())
    if remaining <= 0:
        return ""
    if remaining < 3600:
        return f"CD {max(1, remaining // 60)}m"
    if remaining < 86400:
        return f"CD {remaining // 3600}h"
    days = remaining // 86400
    if days < 30:
        return f"CD {days}d"
    return f"CD {days // 30}mo"


def cooldown_progress(
    until_ts: int,
    duration_seconds: int,
    *,
    now: datetime | None = None,
) -> float:
    if until_ts <= 0 or duration_seconds <= 0:
        return 0.0
    current = now or datetime.now()
    remaining = until_ts - int(current.timestamp())
    if remaining <= 0:
        return 0.0
    return max(0.0, min(1.0, remaining / duration_seconds))
