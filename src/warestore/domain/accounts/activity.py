# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account activity display helpers."""

from datetime import datetime, timedelta


def format_last_played(timestamp: int) -> str:
    if timestamp <= 0:
        return "Never"
    played_at = datetime.fromtimestamp(timestamp)
    delta = datetime.now() - played_at
    if delta < timedelta(hours=1):
        minutes = delta.seconds // 60
        return f"{minutes}m ago" if minutes else "Just now"
    if delta < timedelta(days=1):
        return f"{delta.seconds // 3600}h ago"
    return played_at.strftime("%b %d %Y")
