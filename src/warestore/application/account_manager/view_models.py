# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Presentation view-models for account manager UI."""

from __future__ import annotations

from dataclasses import dataclass

from warestore.domain.accounts.cooldown import COOLDOWN_PRESETS


@dataclass(frozen=True, slots=True)
class AccountCardMenuState:
    username: str
    steam_id: str
    saved_token: str
    has_saved_token: bool
    has_cooldown: bool
    color: str = ""
    has_hwid_profile: bool = False
    is_cs2_source: bool = False
    has_cs2_source: bool = False
    cooldown_presets: tuple[tuple[str, int], ...] = COOLDOWN_PRESETS


@dataclass(frozen=True, slots=True)
class AccountCardViewState:
    jwt_expires_in: int
    cooldown_label: str
    cooldown_progress: float
    menu: AccountCardMenuState
    color: str = ""
