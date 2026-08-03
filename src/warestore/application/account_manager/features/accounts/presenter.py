# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

"""Account loading and card view-model use cases."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from warestore.application.account_manager.controller import AccountManagerController
from warestore.application.account_manager.view_models import (
    AccountCardMenuState,
    AccountCardViewState,
)
from warestore.domain.auth.formatters import JWT_NO_TOKEN

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AccountLoadResult:
    accounts: list[dict]
    steam_dir: str | None
    status_message: str
    removed_expired: int = 0


class AccountsPresenter:
    def __init__(self, ctrl: AccountManagerController) -> None:
        self._ctrl = ctrl

    def load_accounts(self) -> AccountLoadResult:
        steam_dir = self._ctrl.steam_install_path()
        if not steam_dir:
            logger.error("Steam installation not found.")
            return AccountLoadResult([], None, "Steam not found.")

        accounts = self._ctrl.list_steam_accounts()
        if not accounts:
            logger.error("No accounts found in loginusers.vdf.")
            return AccountLoadResult([], steam_dir, "")

        # Prefer the persona name + avatar cached from the last status refresh, so
        # cards show current info immediately instead of stale loginusers.vdf data.
        meta = self._ctrl.all_metadata()
        for acc in accounts:
            record = meta.get(acc.get("steamid", ""))
            if not record:
                continue
            if record.persona:
                acc["persona_name"] = record.persona
            if record.avatar_hash:
                acc["avatar_hash"] = record.avatar_hash
            # Cached CS2 rank/cooldown so the card shows it again after a reload.
            acc["premier_rating"] = record.premier_rating
            acc["premier_wins"] = record.premier_wins
            acc["wingman_rank"] = record.wingman_rank
            acc["wingman_wins"] = record.wingman_wins
            acc["cs2_cooldown_expires"] = record.cs2_cooldown_expires

        logger.info(f"Loaded {len(accounts)} account(s).")
        extracted = self._ctrl.extract_tokens_from_steam()
        if extracted:
            logger.info(f"Extracted {extracted} new token(s) from ConnectCache.")

        removed_expired = 0
        removed_tokenless = 0
        if self._ctrl.load_settings().get("auto_remove_expired_tokens"):
            removed_expired = self._ctrl.purge_expired_tokens()
            if removed_expired:
                logger.info(f"Removed {removed_expired} expired token(s) from AppData.")
            # After the purge, also delete accounts left with no token from
            # Steam's login list, then drop them from the displayed grid.
            removed_tokenless = self._ctrl.purge_tokenless_accounts()
            if removed_tokenless:
                logger.info(
                    f"Removed {removed_tokenless} tokenless account(s) from loginusers.vdf."
                )
                token_ids = set(self._ctrl.load_tokens().keys())
                accounts = [a for a in accounts if a.get("steamid", "") in token_ids]

        status = f"Loaded {len(accounts)} account(s)."
        if removed_expired:
            status += f" Removed {removed_expired} expired token(s)."
        if removed_tokenless:
            status += f" Removed {removed_tokenless} tokenless account(s)."
        return AccountLoadResult(
            accounts,
            steam_dir,
            status,
            removed_expired,
        )

    def jwt_expiry_for(self, steam_id: str) -> int:
        token = self._ctrl.saved_token_entry(steam_id).get("token", "")
        if not token:
            return JWT_NO_TOKEN
        return self._ctrl.verify_token_expiry(token)

    def card_menu_for(
        self,
        acc: dict,
        *,
        has_cooldown: bool,
        color: str = "",
        has_hwid_profile: bool = False,
    ) -> AccountCardMenuState:
        steam_id = acc.get("steamid", "")
        token = self._ctrl.saved_token_entry(steam_id).get("token", "")
        cs2_source = self._ctrl.cs2_config_source()
        return AccountCardMenuState(
            username=acc.get("account_name", ""),
            steam_id=steam_id,
            saved_token=token,
            has_saved_token=bool(token),
            has_cooldown=has_cooldown,
            color=color,
            has_hwid_profile=has_hwid_profile,
            is_cs2_source=bool(steam_id) and steam_id == cs2_source,
            has_cs2_source=bool(cs2_source),
        )

    def card_view_state_for(
        self,
        acc: dict,
        *,
        cooldown_label: str,
        hwid_profile_names: frozenset[str] = frozenset(),
    ) -> AccountCardViewState:
        steam_id = acc.get("steamid", "")
        record = self._ctrl.get_metadata(steam_id) if steam_id else None
        color = record.color if record else ""
        account_name = acc.get("account_name", "")
        return AccountCardViewState(
            jwt_expires_in=self.jwt_expiry_for(steam_id),
            cooldown_label=cooldown_label,
            cooldown_expires=record.cooldown_until if record else 0,
            menu=self.card_menu_for(
                acc,
                has_cooldown=bool(cooldown_label),
                color=color,
                has_hwid_profile=account_name in hwid_profile_names,
            ),
            color=color,
        )

    @staticmethod
    def account_display_name(acc: dict) -> str:
        return acc.get("persona_name") or acc.get("account_name", "account")

    def delete_account(self, steam_id: str) -> bool:
        if not steam_id:
            return False
        if self._ctrl.delete_account(steam_id):
            self._ctrl.delete_metadata(steam_id)
            # Purge the saved token too, otherwise the account reappears on the
            # next refresh (extract_tokens_from_steam re-populates from the vault).
            self._ctrl.remove_token(steam_id)
            return True
        return False
