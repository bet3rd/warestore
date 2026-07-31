# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Application orchestration for the account manager."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from pathlib import Path

from warestore.application.account_manager.facade import AccountManagerFacade
from warestore.domain.accounts.activity import format_last_played as format_last_played_label
from warestore.domain.accounts.cooldown import format_cooldown_remaining
from warestore.domain.accounts.models import AccountRecord

logger = logging.getLogger(__name__)


class UserdataScanUnsafe(Exception):
    """Raised when the userdata-cleanup safety set can't be established (Steam's
    login list or the token store couldn't be read). The scan refuses rather
    than proceeding with weakened protection, so nothing in-use is deleted."""


class AccountManagerController:
    def __init__(self, facade: AccountManagerFacade | None = None) -> None:
        self._facade = facade or AccountManagerFacade()

    # --- settings ---

    def load_settings(self) -> dict:
        return self._facade.settings.load()

    def save_settings(self, settings: dict) -> None:
        self._facade.settings.save(settings)

    # --- steam process ---

    def steam_install_path(self) -> str | None:
        return self._facade.steam_login.process.install_path()

    def kill_steam(self) -> None:
        self._facade.steam_login.process.kill()

    def launch_steam(self, *, open_cs2: bool = False) -> None:
        self._facade.steam_login.process.launch(open_cs2=open_cs2)

    # --- accounts / login ---

    def list_steam_accounts(self) -> list[dict]:
        return self._facade.steam_login.list_accounts_from_steam()

    def extract_tokens_from_steam(self) -> int:
        return self._facade.steam_login.extract_tokens_from_steam()

    def perform_token_login(self, raw_token: str, disable_remote_play: bool = False) -> bool:
        return self._facade.steam_login.perform_token_login(raw_token, disable_remote_play)

    def switch_account(
        self, acc: dict, persona_state: int = 7, disable_remote_play: bool = False
    ) -> bool:
        return self._facade.steam_login.switch_account(
            acc, persona_state, disable_remote_play
        )

    def delete_account(self, steam_id: str) -> bool:
        return self._facade.steam_login.delete_loginuser(steam_id)

    def set_cs2_launch_options(
        self, steam_dir: str, steam_id: str, options: str
    ) -> None:
        self._facade.steam_login.set_cs2_launch_options(steam_dir, steam_id, options)

    def disable_cs2_workshop(self, steam_dir: str, steam_id: str) -> int:
        return self._facade.steam_login.disable_cs2_workshop(steam_dir, steam_id)

    # --- cs2 config seeding ---

    def cs2_config_source(self) -> str:
        """SteamID of the account whose CS2 config seeds new accounts ("" = off)."""
        return self.load_settings().get("cs2_config_source_sid", "")

    def set_cs2_config_source(self, steam_id: str) -> None:
        settings = self.load_settings()
        settings["cs2_config_source_sid"] = steam_id
        self.save_settings(settings)

    def seed_cs2_config_if_new(self, target_steam_id: str) -> bool:
        """Copy the source account's CS2 config into a not-yet-seeded target.

        No-op (False) when no source is configured, the target *is* the source,
        or the target was already seeded once. Seeding happens at most once per
        account so the user's own later config edits are never overwritten. The
        seeded flag is only set after a successful copy, so a source that has no
        730 folder yet is retried on the next login rather than marked done.
        """
        source = self.cs2_config_source()
        if not source or source == target_steam_id:
            return False
        if self.get_metadata(target_steam_id).cs2_seeded:
            return False
        steam_dir = self.steam_install_path()
        if not steam_dir:
            return False
        # Config folder is seeded once (launch options are handled separately, on
        # every switch — see apply_source_launch_options).
        if self._facade.cs2_config.copy_config(steam_dir, source, target_steam_id):
            self._facade.metadata.set_cs2_seeded(target_steam_id, True)
            return True
        return False

    def apply_cs2_config(self, target_steam_id: str) -> bool:
        """Force-copy the source CS2 config into a target, overriding any existing.

        Unlike seed_cs2_config_if_new this ignores the seeded flag — it's the
        manual "Override Config" action. The target's existing 730 folder is
        still backed up first (handled by the gateway).
        """
        source = self.cs2_config_source()
        if not source or source == target_steam_id:
            return False
        steam_dir = self.steam_install_path()
        if not steam_dir:
            return False
        if self._facade.cs2_config.copy_config(steam_dir, source, target_steam_id):
            self._facade.steam_login.copy_cs2_launch_options(steam_dir, source, target_steam_id)
            self._facade.metadata.set_cs2_seeded(target_steam_id, True)
            return True
        return False

    def apply_source_launch_options(self, target_steam_id: str) -> bool:
        """Copy the CS2 source account's launch options onto the target.

        Not gated on the seed-once flag — this runs on every native switch so
        every account tracks the source's launch options. No-op when no source
        is set or the target is the source.
        """
        source = self.cs2_config_source()
        if not source or source == target_steam_id:
            return False
        steam_dir = self.steam_install_path()
        if not steam_dir:
            return False
        return self._facade.steam_login.copy_cs2_launch_options(
            steam_dir, source, target_steam_id
        )

    # --- leftover userdata cleanup ---

    def scan_unused_userdata(self) -> list:
        """Leftover userdata folders with no entry in Steam's login list.

        Cross-references saved tokens so callers can tell apart folders that
        are genuinely dead from ones WareStore can still log into.

        Fails closed: if either protective source — Steam's login list or the
        (possibly encrypted) token store — can't be read, this raises
        `UserdataScanUnsafe` instead of returning a set with weakened
        protection, so a locked vault or corrupt loginusers.vdf can never cause
        an in-use account to be classified as deletable.
        """
        steam_dir = self.steam_install_path()
        if not steam_dir:
            raise UserdataScanUnsafe("Steam install folder not found.")

        try:
            login_ids = self._facade.steam_login.login_steam_ids()
        except Exception as exc:
            raise UserdataScanUnsafe(
                f"Couldn't read Steam's login list (loginusers.vdf): {exc}"
            ) from exc

        try:
            token_ids = set(self._facade.tokens.load_all_strict().keys())
        except Exception as exc:
            raise UserdataScanUnsafe(
                "Couldn't read your saved tokens, so accounts WareStore manages "
                "can't be protected from deletion. If a master password is set, "
                f"unlock it and try again. ({exc})"
            ) from exc

        names = self._facade.steam_login.account_names_by_id32()
        return self._facade.userdata.scan(steam_dir, login_ids, token_ids, names)

    def delete_userdata_folders(self, folders: list) -> tuple[int, int, list[str]]:
        return self._facade.userdata.delete(folders)

    def find_injector_exe(self) -> str | None:
        """Return injector.exe path, or None if the spoofer isn't installed.

        The injector is not bundled — the user installs it on demand from
        Settings, which downloads it into a persistent per-user dir (see
        injector_stage). In dev it may sit at the repo root / cwd instead.
        """
        from warestore.infrastructure.steam.injector_stage import injector_path

        p = injector_path()
        if os.path.exists(p):
            return p
        if not getattr(sys, "frozen", False):
            candidate = os.path.join(os.getcwd(), "injector.exe")
            if os.path.exists(candidate):
                return candidate
        return None

    def spoofer_installed(self) -> bool:
        """Whether the HWID spoofer (injector.exe) is present."""
        from warestore.infrastructure.steam.injector_stage import is_installed

        return is_installed()

    def install_spoofer(self) -> None:
        """Download the injector and its hardware pool. Raises on failure."""
        from warestore.infrastructure.steam.injector_stage import download_injector

        download_injector()
        injector = self.find_injector_exe()
        if injector:
            self.ensure_hardware_pool(injector)

    def ensure_hardware_pool(self, injector_path: str) -> bool:
        """Download hardware_pool.json next to the injector if not already there."""
        from warestore.infrastructure.steam.hardware_pool_gateway import ensure
        return ensure(injector_path)

    def launch_steam_with_spoofer(
        self, injector_path: str, *, open_cs2: bool = False
    ) -> None:
        self._facade.steam_login.process.launch_with_spoofer(
            injector_path, open_cs2=open_cs2
        )

    def hwid_profile_names(self) -> frozenset[str]:
        """Return account names that have a stored HWID profile."""
        injector = self.find_injector_exe()
        if not injector:
            return frozenset()
        injector_dir = os.path.dirname(injector)
        return frozenset(self._facade.hwid_profiles.all_profiles(injector_dir).keys())

    def reset_hwid_profile(self, account_name: str) -> bool:
        """Delete the stored HWID profile so a fresh one is generated next login."""
        injector = self.find_injector_exe()
        if not injector:
            logger.warning("reset_hwid_profile: injector.exe not found")
            return False
        injector_dir = os.path.dirname(injector)
        return self._facade.hwid_profiles.delete(account_name, injector_dir)

    # --- tokens ---

    def rekey_vault(self, new_key: bytes | None) -> None:
        """Re-encrypt the saved-token file to a new key (or None for DPAPI)."""
        self._facade.tokens.rekey(new_key)

    def load_tokens(self) -> dict:
        return self._facade.tokens.load_all()

    def saved_token_entry(self, steam_id: str) -> dict:
        return self.load_tokens().get(steam_id, {})

    # --- metadata ---

    def get_metadata(self, steam_id: str) -> AccountRecord:
        return self._facade.metadata.get(steam_id)

    def set_last_played(self, steam_id: str, played: bool = True) -> None:
        self._facade.metadata.set_last_played(steam_id, played)

    def set_cooldown(self, steam_id: str, duration_seconds: int) -> None:
        self._facade.metadata.set_cooldown(steam_id, duration_seconds)

    def clear_cooldown(self, steam_id: str) -> None:
        self._facade.metadata.clear_cooldown(steam_id)

    def set_account_color(self, steam_id: str, color: str) -> None:
        self._facade.metadata.set_color(steam_id, color)

    def delete_metadata(self, steam_id: str) -> None:
        self._facade.metadata.delete(steam_id)

    @staticmethod
    def format_last_played(timestamp: int) -> str:
        return format_last_played_label(timestamp)

    @staticmethod
    def format_cooldown(until_ts: int) -> str:
        return format_cooldown_remaining(until_ts)

    # --- parsing / jwt ---

    def sanitize_entry(self, raw: str) -> str | None:
        return self._facade.parser.sanitize_entry(raw)

    def parse_bulk_tokens(self, text: str) -> list[str]:
        return self._facade.parser.parse_bulk(text)

    def is_entry_importable(self, entry: str) -> bool:
        jwt = self._facade.parser.jwt_from_entry(entry)
        return self.verify_token_expiry(jwt) >= 0

    def classify_bulk_tokens(self, text: str) -> tuple[list[str], list[str]]:
        importable: list[str] = []
        expired: list[str] = []
        for entry in self.parse_bulk_tokens(text):
            if self.is_entry_importable(entry):
                importable.append(entry)
            else:
                expired.append(entry)
        return importable, expired

    def verify_token_expiry(self, token: str) -> int:
        return self._facade.jwt.verify_expiry(token)

    def purge_expired_tokens(self) -> int:
        tokens = self._facade.tokens.load_all()
        removed = 0
        for steam_id, entry in list(tokens.items()):
            token = entry.get("token", "")
            if not token or self._facade.jwt.verify_expiry(token) >= 0:
                continue
            del tokens[steam_id]
            removed += 1
        if removed:
            self._facade.tokens.save_all(tokens)
        return removed

    # --- updates ---

    def check_updates(self) -> dict:
        return self._facade.updates.check()

    # --- external ---

    def fetch_profile_statuses(
        self,
        steam_ids: list[str],
        on_progress: Callable[[str], None] | None = None,
    ) -> dict[str, dict]:
        # With an API key, use the batched GetPlayerSummaries; otherwise fall
        # back to the (per-account, rate-limited) community profile XML.
        api_key = self.load_settings().get("steam_api_key", "")
        if api_key:
            return self._facade.summaries.fetch_statuses(
                api_key, steam_ids, on_progress=on_progress
            )
        return self._facade.profiles.fetch_statuses(steam_ids, on_progress=on_progress)

    def fetch_bans(self, steam_ids: list[str]) -> dict[str, dict]:
        api_key = self.load_settings().get("steam_api_key", "")
        return self._facade.bans.fetch_bans(api_key, steam_ids)

    def fetch_levels(self, steam_ids: list[str]) -> dict[str, int]:
        api_key = self.load_settings().get("steam_api_key", "")
        return self._facade.levels.fetch_levels(api_key, steam_ids)

    def validate_api_key(self, key: str) -> str:
        """Return "valid", "invalid", or "error" for a Steam Web API key."""
        return self._facade.api_key.validate(key)
