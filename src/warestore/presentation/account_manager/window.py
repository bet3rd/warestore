# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os

from PyQt5.QtCore import Qt, QTimer, QEvent
from PyQt5.QtGui import QKeyEvent
from PyQt5.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QVBoxLayout, QWidget

from warestore.application.account_manager.bootstrap import (
    AccountManagerApp,
    create_account_manager_app,
)
from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.presenter import AccountManagerPresenter
from warestore.presentation.account_manager.features import (
    AccountCoordinator,
    CooldownCoordinator,
    LoginCoordinator,
    SettingsCoordinator,
)
from warestore.presentation.account_manager.support.single_instance import InstanceServer
from warestore.presentation.account_manager.ui.chrome import RoundedPanel as _RoundedPanel
from warestore.presentation.account_manager.ui.panels import MainPanel, SettingsPanel
from warestore.presentation.account_manager.ui.theme import (
    app_icon,
    enable_dark_title_bar,
    handle_style_changing_layered_hook,
    install_capture_exclusion_popup_filter,
    schedule_capture_exclusion_for_widget,
)
from warestore.presentation.account_manager.ui.tray import (
    notify_hidden_to_tray,
    restore_tray_tooltip,
    setup_tray,
)


class MainWindow(QMainWindow):
    SETTINGS_W = 380
    GAP = 8

    def __init__(
        self,
        app: AccountManagerApp | None = None,
        *,
        controller: AccountManagerController | None = None,
        presenter: AccountManagerPresenter | None = None,
    ):
        super().__init__()
        bundle = app or create_account_manager_app()
        self._controller = controller or bundle.controller
        self._presenter = presenter or bundle.presenter

        self.setWindowTitle("WareStore Account Manager")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setFixedWidth(MainPanel.preferred_width())
        self.setWindowIcon(app_icon())
        self._use_dwm_transparency = os.name == "nt"
        if self._use_dwm_transparency:
            # Avoid WA_TranslucentBackground — it uses UpdateLayeredWindow, which
            # conflicts with SetWindowDisplayAffinity (Microsoft issue #56).
            self.setAttribute(Qt.WA_NoSystemBackground, True)
        else:
            self.setAttribute(Qt.WA_TranslucentBackground)

        self._settings: dict = self._controller.load_settings()
        self._settings_open = False
        self._tray = None

        outer = QWidget()
        if not self._use_dwm_transparency:
            outer.setAttribute(Qt.WA_TranslucentBackground)
        self.setCentralWidget(outer)

        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        row = QWidget()
        if not self._use_dwm_transparency:
            row.setAttribute(Qt.WA_TranslucentBackground)
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(self.GAP)

        left = _RoundedPanel()
        left.setObjectName("central")
        self._right = _RoundedPanel()
        self._right.setObjectName("settings")
        self._right.setFixedWidth(self.SETTINGS_W)
        self._right.hide()
        row_layout.addWidget(left)
        row_layout.addWidget(self._right)
        outer_layout.addWidget(row)

        self._left = left
        self._ui = MainPanel(
            left,
            self._settings,
            on_minimize=self.showMinimized,
            on_close=self._on_close_requested,
        )
        self._settings_ui = SettingsPanel(
            self._right,
            self._settings,
            on_close=self._open_settings,
        )

        self._accounts = AccountCoordinator(
            self,
            self._presenter,
            self._controller,
            self._settings,
            account_grid=self._ui.account_grid,
            info_label=self._ui.info_label,
            sync_layout=self._sync_layout,
            refresh_log=self._ui.refresh_log,
            is_switch_busy=lambda: self._login.is_busy(),
            on_accounts_loaded=lambda: self._cooldowns.sync_watch(
                self._accounts.accounts_on_grid()
            ),
            get_search_text=lambda: self._ui._search.text(),
            filter_accounts=self._ui.account_grid.filter_accounts,
        )
        self._login = LoginCoordinator(
            self,
            self._controller,
            self._presenter,
            entry=self._ui.entry,
            token_err=self._ui._token_err,
            set_login_enabled=self._ui.set_login_token_ok,
            set_busy=self._set_busy,
            set_status=self._ui.info_label.setText,
            sync_layout=self._sync_layout,
            refresh_log=self._ui.refresh_log,
            reload_accounts=self._accounts.load_accounts,
            get_selected_account=lambda: self._accounts.selected_account,
            set_selected_account=lambda acc: setattr(self._accounts, "selected_account", acc),
        )
        self._settings_coord = SettingsCoordinator(
            self,
            self._controller,
            self._settings,
            self._settings_ui,
            set_busy=self._set_busy,
            set_status=self._ui.info_label.setText,
            sync_layout=self._sync_layout,
            refresh_log=self._ui.refresh_log,
            reload_accounts=self._accounts.load_accounts,
            set_log_visible=self._ui.set_log_visible,
            toggle_settings_open=self._open_settings,
            apply_capture_exclusion=self.apply_capture_exclusion,
        )
        self._cooldowns = CooldownCoordinator(
            self,
            self._presenter,
            self._controller,
            accounts_on_grid=self._accounts.accounts_on_grid,
            refresh_cards=self._accounts.apply_card_metadata,
            set_status=self._ui.info_label.setText,
        )

        self._filter_state: dict = {"colors": set(), "no_cooldown": False, "no_bans": False}

        self._wire_panels()
        self._sync_layout()
        self._restore_window_position()
        self._accounts.load_accounts()
        QTimer.singleShot(300, self._settings_coord.check_updates)
        if self._settings.get("gcpd_check_on_launch"):
            # Defer so the grid renders first; then sweep every account's CS2
            # rank sequentially (see AccountCoordinator.fetch_all_cs2_ranks).
            QTimer.singleShot(800, self._accounts.fetch_all_cs2_ranks)

        self._tray = setup_tray(self)
        self._instance_server = InstanceServer(self)
        self._capture_popup_filter = install_capture_exclusion_popup_filter(
            QApplication.instance(),
            enabled_getter=lambda: bool(self._settings.get("exclude_from_capture", True)),
        )
        self._cooldowns.set_notify_targets(self._tray, self)
        self._settings_ui.cb_close_to_tray.setEnabled(self._tray is not None)
        if self._tray is None:
            self._settings_ui.cb_close_to_tray.setToolTip(
                "System tray unavailable — X will always quit the app."
            )

    def _wire_panels(self) -> None:
        ui = self._ui
        su = self._settings_ui
        ui.entry.returnPressed.connect(self._login.login)
        ui.entry.textChanged.connect(
            lambda text: self._login.validate_token_text(
                text, sync_layout=self._sync_layout
            )
        )
        ui._btn_paste.clicked.connect(self._paste_token)
        ui._btn_login.clicked.connect(self._login.login)
        ui._search.textChanged.connect(self._on_search)
        ui.account_grid.account_selected.connect(self._accounts.select_accounts)
        ui.account_grid.account_double_clicked.connect(self._login.switch_account)
        ui.account_grid.delete_requested.connect(self._accounts.delete_accounts)
        ui.account_grid.export_copy_requested.connect(self._accounts.copy_export_tokens)
        ui.account_grid.export_file_requested.connect(self._accounts.export_tokens_to_file)
        ui.account_grid.relogin_requested.connect(self._login.relogin)
        ui.account_grid.cooldown_set_requested.connect(self._cooldowns.set_cooldown)
        ui.account_grid.cooldown_custom_requested.connect(self._cooldowns.open_custom_dialog)
        ui.account_grid.color_set_requested.connect(self._accounts.set_color)
        ui.account_grid.cs2_source_set_requested.connect(self._accounts.set_cs2_source)
        ui.account_grid.cs2_apply_requested.connect(self._accounts.apply_cs2_source)
        ui.account_grid.cs2_rank_requested.connect(self._accounts.fetch_cs2_ranks)
        ui.account_grid.hwid_reset_requested.connect(self._accounts.reset_hwid)
        ui._btn_cs2_ranks.clicked.connect(self._accounts.fetch_all_cs2_ranks)
        ui._btn_refresh.clicked.connect(self._accounts.load_accounts)
        ui._btn_filter.clicked.connect(self._on_filter)
        ui._btn_settings.clicked.connect(self._settings_coord.toggle_panel)
        su.cb_cs2.toggled.connect(self._settings_coord.on_cs2_toggle)
        su.le_opts.textChanged.connect(self._settings_coord.on_opts_change)
        su.cb_workshop.toggled.connect(self._settings_coord.on_workshop_toggle)
        su.cb_remote_play.toggled.connect(self._settings_coord.on_remote_play_toggle)
        su.btn_clean_userdata.clicked.connect(self._settings_coord.on_clean_userdata)
        su.cb_add_only.toggled.connect(self._settings_coord.on_add_only_toggle)
        su.cb_spoof.toggled.connect(self._settings_coord.on_spoof_toggle)
        su.btn_install_spoofer.clicked.connect(self._settings_coord.on_install_spoofer)
        su.le_api_key.textChanged.connect(self._settings_coord.on_api_key_change)
        su.btn_master.clicked.connect(self._settings_coord.on_master_password)
        ui._btn_log.toggled.connect(self._settings_coord.on_log_toggle)
        su.cb_close_to_tray.toggled.connect(self._settings_coord.on_close_to_tray_toggle)
        su.cb_auto_remove_expired.toggled.connect(
            self._settings_coord.on_auto_remove_expired_toggle
        )
        su.cb_gcpd_on_launch.toggled.connect(
            self._settings_coord.on_gcpd_check_toggle
        )
        su.cb_exclude_capture.toggled.connect(
            self._settings_coord.on_exclude_from_capture_toggle
        )
        su.txt_bulk.textChanged.connect(self._settings_coord.on_bulk_text_change)
        su.txt_bulk.bulk_changed.connect(self._settings_coord.on_bulk_text_change)
        su.btn_browse.clicked.connect(self._settings_coord.on_browse_file)
        su.btn_import.clicked.connect(self._settings_coord.on_import)

    def _paste_token(self) -> None:
        text = self._ui.paste_token()
        if text:
            self._login.validate_token_text(text, sync_layout=self._sync_layout)

    def _on_search(self, text: str) -> None:
        self._ui.account_grid.filter_accounts(text)
        self._sync_layout()

    def _on_filter(self) -> None:
        from warestore.presentation.account_manager.ui.accounts.account_filter_menu import (
            show_account_filter_menu,
        )

        btn = self._ui._btn_filter
        show_account_filter_menu(
            parent=btn,
            global_pos=btn.mapToGlobal(btn.rect().bottomRight()),
            state=self._filter_state,
            on_change=self._apply_filters,
        )

    def _apply_filters(self, state: dict) -> None:
        self._ui.account_grid.set_filters(
            colors=set(state["colors"]),
            no_cooldown=state["no_cooldown"],
            no_bans=state["no_bans"],
        )
        active = bool(state["colors"] or state["no_cooldown"] or state["no_bans"])
        self._ui.set_filter_active(active)
        self._sync_layout()

    def _sync_layout(self) -> None:
        self._ui.sync_height(self)
        self._right.setFixedHeight(self._left.height())
        self.setFixedWidth(
            self._ui.window_width(
                settings_open=self._settings_open,
                settings_w=self.SETTINGS_W,
                gap=self.GAP,
            )
        )
        if self._settings_open:
            self._right.show()
        else:
            self._right.hide()
        self.apply_capture_exclusion()

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._ui.set_busy(busy, message)

    def _close_to_tray_enabled(self) -> bool:
        return bool(self._settings.get("close_to_tray", False) and self._tray is not None)

    def _close_settings_panel(self) -> None:
        if not self._settings_open:
            return
        self._settings_open = False
        self._right.hide()

    def _hide_to_tray(self) -> None:
        self._close_settings_panel()
        self.hide()
        if self._tray is not None:
            notify_hidden_to_tray(self._tray)

    def _on_close_requested(self) -> None:
        self._save_window_position()
        self._controller.save_settings(self._settings)
        if self._close_to_tray_enabled():
            self._hide_to_tray()
        else:
            self._close_settings_panel()
            QApplication.quit()

    def _restore_window_position(self) -> None:
        x, y = self._settings.get("window_x"), self._settings.get("window_y")
        if isinstance(x, int) and isinstance(y, int):
            self.move(x, y)

    def _save_window_position(self) -> None:
        pos = self.pos()
        self._settings["window_x"] = pos.x()
        self._settings["window_y"] = pos.y()
        self._controller.save_settings(self._settings)

    def _open_settings(self) -> None:
        self._settings_open = not self._settings_open
        self._sync_layout()

    @property
    def info_label(self):
        return self._ui.info_label

    @property
    def entry(self):
        return self._ui.entry

    def load_accounts(self) -> None:
        self._accounts.load_accounts()

    def keyPressEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key_Escape:
            self._ui.account_grid.clear_selection()
            self._accounts.select_accounts([])
            event.accept()
            return
        if event.key() == Qt.Key_Up:
            self._ui.account_grid.select_prev()
            event.accept()
            return
        if event.key() == Qt.Key_Down:
            self._ui.account_grid.select_next()
            event.accept()
            return
        if event.key() == Qt.Key_Return and event.modifiers() == Qt.AltModifier:
            if self._accounts.selected_account:
                self._login.switch_selected()
                event.accept()
                return
        super().keyPressEvent(event)

    def nativeEvent(self, eventType, message):
        if (
            self._use_dwm_transparency
            and eventType == b"windows_generic_MSG"
            and handle_style_changing_layered_hook(int(message))
        ):
            return True, 0
        return super().nativeEvent(eventType, message)

    def showEvent(self, event):
        enable_dark_title_bar(int(self.winId()))
        schedule_capture_exclusion_for_widget(
            self,
            enabled=bool(self._settings.get("exclude_from_capture", True)),
        )
        if self._tray is not None:
            restore_tray_tooltip(self._tray)
        super().showEvent(event)

    def changeEvent(self, event):
        if event.type() == QEvent.WinIdChange:
            QTimer.singleShot(0, self.apply_capture_exclusion)
        super().changeEvent(event)

    def apply_capture_exclusion(self) -> None:
        schedule_capture_exclusion_for_widget(
            self,
            enabled=bool(self._settings.get("exclude_from_capture", True)),
        )

    def closeEvent(self, event):
        if self._close_to_tray_enabled():
            self._save_window_position()
            self._controller.save_settings(self._settings)
            event.ignore()
            self._hide_to_tray()
            return
        self._on_close_requested()
        event.accept()
