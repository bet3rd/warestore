# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Shared account selection helpers for presentation coordinators."""


def normalize_account_targets(accounts: dict | list[dict]) -> list[dict]:
    if isinstance(accounts, dict):
        return [accounts]
    return list(accounts)
