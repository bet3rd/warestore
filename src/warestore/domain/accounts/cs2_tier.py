# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Which CS2 matchmaking tier an account is in.

Prime comes only from the CS2 Game Coordinator (never GCPD). Premier unlocks
at CS2 level 10 for a Prime account (nfatool's MinimumPremierLevel).
"""

from __future__ import annotations

PREMIER = "premier"
PREMIER_READY = "premier_ready"
PRIME = "prime"
NON_PRIME = "non_prime"
UNKNOWN = "unknown"

PREMIER_MIN_LEVEL = 10

TIER_LABELS = {
    NON_PRIME: "Non-Prime",
    PRIME: "Prime",
    PREMIER_READY: "Premier-ready",
    PREMIER: "Premier",
}


def cs2_tier(*, prime: int, level: int, premier_rating: int) -> str:
    """``prime``: 1 Prime, 0 non-Prime, -1 never read."""
    if premier_rating > 0:
        return PREMIER
    if prime == 1:
        return PREMIER_READY if level >= PREMIER_MIN_LEVEL else PRIME
    if prime == 0:
        return NON_PRIME
    return UNKNOWN
