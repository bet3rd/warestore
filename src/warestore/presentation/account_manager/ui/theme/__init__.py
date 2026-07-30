# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

from warestore.presentation.account_manager.ui.theme.styles import (
    QSS,
    app_icon,
    app_icon_path,
    enable_dark_title_bar,
    ensure_app_icon_file,
    project_root,
)
from warestore.presentation.account_manager.ui.theme.capture import (
    apply_capture_exclusion_for_widget,
    capture_exclusion_available,
    extend_frame_into_client_area,
    get_window_capture_exclusion,
    handle_style_changing_layered_hook,
    install_capture_exclusion_popup_filter,
    schedule_capture_exclusion_for_widget,
    set_window_capture_exclusion,
)

__all__ = [
    "QSS",
    "app_icon",
    "app_icon_path",
    "enable_dark_title_bar",
    "ensure_app_icon_file",
    "project_root",
    "apply_capture_exclusion_for_widget",
    "capture_exclusion_available",
    "extend_frame_into_client_area",
    "get_window_capture_exclusion",
    "handle_style_changing_layered_hook",
    "install_capture_exclusion_popup_filter",
    "schedule_capture_exclusion_for_widget",
    "set_window_capture_exclusion",
]
