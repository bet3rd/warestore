# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Backward-compatible re-exports. Prefer ui.accounts and ui.chrome."""

from warestore.presentation.account_manager.ui.accounts import AccountCard, AccountGrid
from warestore.presentation.account_manager.ui.chrome import HeaderBar, RoundedPanel

_RoundedPanel = RoundedPanel

__all__ = ["AccountCard", "AccountGrid", "HeaderBar", "RoundedPanel", "_RoundedPanel"]
