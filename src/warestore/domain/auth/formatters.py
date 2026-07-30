# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""JWT display formatters for UI."""


def format_jwt_expiry_label(expires_in: int) -> str:
    if expires_in < 0:
        return "JWT expired"
    if expires_in < 3600:
        return f"JWT {max(1, expires_in // 60)}m"
    if expires_in < 86400 * 2:
        return f"JWT {expires_in // 3600}h"
    return ""
