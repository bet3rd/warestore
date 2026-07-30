# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging
import os
import time
from datetime import datetime

from warestore.config.settings import STEAMID64_BASE
from warestore.domain.accounts.ports import TokenStore
from warestore.domain.accounts.services.token_parser import TokenParser
from warestore.domain.auth.jwt_service import SteamJwtService
from warestore.domain.steam.models import LoginUser
from warestore.domain.steam.ports import (
    PersonaPort,
    SteamCryptoPort,
    SteamProcessPort,
    SteamRegistryPort,
    VdfFilePort,
)
from warestore.domain.steam.services.vdf_patcher import VdfPatcher

logger = logging.getLogger(__name__)


class SteamLoginService:
    def __init__(
        self,
        *,
        process: SteamProcessPort,
        files: VdfFilePort,
        crypto: SteamCryptoPort,
        registry: SteamRegistryPort,
        persona: PersonaPort,
        tokens: TokenStore,
        jwt: SteamJwtService,
        parser: TokenParser,
        vdf: VdfPatcher | None = None,
    ) -> None:
        self._process = process
        self._files = files
        self._vdf = vdf or VdfPatcher()
        self._crypto = crypto
        self._registry = registry
        self._persona = persona
        self._tokens = tokens
        self._jwt = jwt
        self._parser = parser

    @property
    def process(self) -> SteamProcessPort:
        return self._process

    def list_accounts_from_steam(self) -> list[dict]:
        steam_dir = self._process.install_path()
        if not steam_dir:
            return []
        path = os.path.join(steam_dir, "config", "loginusers.vdf")
        return [user.to_dict() for user in self.parse_loginusers(path)]

    def parse_loginusers(self, path: str) -> list[LoginUser]:
        if not os.path.exists(path):
            return []
        try:
            data = self._files.read_vdf(path)
            accounts: list[LoginUser] = []
            for steamid, info in data.get("users", {}).items():
                if len(steamid) == 17 and steamid.startswith("76"):
                    accounts.append(
                        LoginUser(
                            steam_id=steamid,
                            account_name=info.get("AccountName", ""),
                            persona_name=info.get("PersonaName", ""),
                            timestamp=int(info.get("Timestamp", 0)),
                            most_recent=info.get("MostRecent", "0"),
                        )
                    )
            accounts.sort(key=lambda item: item.timestamp, reverse=True)
            return accounts[:200]
        except Exception as exc:
            logger.error(f"loginusers.vdf parse error: {exc}")
            return []

    def login_steam_ids(self) -> set[str]:
        """The COMPLETE set of SteamID64s in loginusers.vdf.

        Unlike `parse_loginusers` this is uncapped (no 200 display limit) and
        raises rather than swallowing errors — it backs the userdata-cleanup
        safety check, which must fail closed. Raises FileNotFoundError if Steam
        or loginusers.vdf is missing, or a parse error if the file is corrupt.
        """
        steam_dir = self._process.install_path()
        if not steam_dir:
            raise FileNotFoundError("Steam install path not found.")
        path = os.path.join(steam_dir, "config", "loginusers.vdf")
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        data = self._files.read_vdf(path)  # propagates parse errors on a corrupt file
        return {
            sid
            for sid in data.get("users", {})
            if len(sid) == 17 and sid.startswith("76")
        }

    def account_names_by_id32(self) -> dict[str, str]:
        """Map userdata folder id (SteamID32) -> account name.

        Sourced from config.vdf's Accounts table (which still lists long-gone
        accounts) with loginusers.vdf as a fallback, so a cleanup UI can show
        *which* accounts it would remove instead of opaque numeric folders.
        """
        names: dict[str, str] = {}
        steam_dir = self._process.install_path()
        if not steam_dir:
            return names

        def add(steam_id64: str, name: str) -> None:
            try:
                id32 = str(int(steam_id64) - STEAMID64_BASE)
            except (TypeError, ValueError):
                return
            if name:
                names.setdefault(id32, name)

        config_path = os.path.join(steam_dir, "config", "config.vdf")
        if os.path.exists(config_path):
            try:
                data = self._files.read_vdf(config_path)
                accounts = (
                    data.get("InstallConfigStore", {})
                    .get("Software", {})
                    .get("Valve", {})
                    .get("Steam", {})
                    .get("Accounts", {})
                )
                for name, info in accounts.items():
                    if isinstance(info, dict):
                        add(info.get("SteamID", ""), name)
            except Exception as exc:
                logger.warning(f"config.vdf name map failed: {exc}")

        try:
            loginusers = os.path.join(steam_dir, "config", "loginusers.vdf")
            for user in self.parse_loginusers(loginusers):
                add(user.steam_id, user.account_name)
        except Exception:
            pass
        return names

    def extract_tokens_from_steam(self) -> int:
        steam_dir = self._process.install_path()
        if not steam_dir:
            return 0
        loginusers_path = os.path.join(steam_dir, "config", "loginusers.vdf")
        accounts = self.parse_loginusers(loginusers_path)
        if not accounts:
            return 0
        local_vdf = self._process.local_vdf_path()
        if not os.path.exists(local_vdf):
            return 0
        try:
            vdf_data = self._files.read_vdf(local_vdf)
            connect_cache = (
                vdf_data.get("MachineUserConfigStore", {})
                .get("Software", {})
                .get("Valve", {})
                .get("Steam", {})
                .get("ConnectCache", {})
            )
        except Exception as exc:
            logger.warning(f"local.vdf read error: {exc}")
            return 0
        if not connect_cache:
            return 0

        saved = self._tokens.load_all()
        new_count = 0
        for acc in accounts:
            if not acc.account_name or acc.steam_id in saved:
                continue
            encrypted = connect_cache.get(self._crypto.crc32_key(acc.account_name), "")
            if not encrypted:
                # No cached refresh token for this account yet (e.g. never
                # fully logged in) — nothing to extract.
                continue
            try:
                token = self._crypto.decrypt(encrypted, acc.account_name)
            except Exception as exc:
                # DPAPI blob mismatched/corrupted for this one account —
                # skip it rather than aborting extraction for everyone else.
                logger.warning(f"Token decrypt failed for {acc.account_name}: {exc}")
                continue
            # ConnectCache can hold non-JWT junk; only keep refresh-token JWTs.
            if self._jwt.looks_like_jwt(token):
                saved[acc.steam_id] = {
                    "username": acc.account_name,
                    "token": token,
                    "ts": time.time(),
                }
                new_count += 1
                logger.info(f"Extracted token: {acc.account_name}")
        if new_count:
            self._tokens.save_all(saved)
        return new_count

    def perform_token_login(self, raw_token: str, disable_remote_play: bool = False) -> bool:
        try:
            logger.info("=== Token Login Start ===")
            steam_dir = self._process.install_path()
            if not steam_dir:
                logger.error("Steam path not found.")
                return False

            steam_config = os.path.join(steam_dir, "config")
            token = self._parser.sanitize_token(raw_token)
            username: str | None = None
            jwt_token = token

            if "----" in token:
                username, jwt_token = (
                    self._parser.sanitize_token(p) for p in token.split("----", 1)
                )
            elif ":" in token:
                username, jwt_token = (
                    self._parser.sanitize_token(p) for p in token.split(":", 1)
                )

            if not self._jwt.is_valid_format(jwt_token):
                logger.error("Invalid JWT.")
                return False

            steam_id = self._jwt.decode_steam_id(jwt_token)
            if not steam_id:
                logger.error("Could not decode SteamID from token.")
                return False
            if not username:
                username = steam_id

            logger.info(f"Account: {username} ({steam_id})")

            encrypted = self._crypto.encrypt(jwt_token, username)
            crc32_key = self._crypto.crc32_key(username)
            logger.info("Token encrypted.")

            config_path = os.path.join(steam_config, "config.vdf")
            if not os.path.exists(config_path):
                logger.error(f"config.vdf not found: {config_path}")
                return False

            vdf_data = self._files.read_vdf(config_path)
            (
                vdf_data.setdefault("InstallConfigStore", {})
                .setdefault("Software", {})
                .setdefault("Valve", {})
                .setdefault("Steam", {})
                .setdefault("Accounts", {})
            )[username] = {"SteamID": steam_id}
            self._files.write_vdf(config_path, vdf_data)
            logger.info("config.vdf updated.")

            loginusers_path = os.path.join(steam_config, "loginusers.vdf")
            if os.path.exists(loginusers_path):
                text = self._files.read_text(loginusers_path)
                if text.strip() and '"users"' in text:
                    new_text = self._vdf.patch_loginusers_text(text, steam_id, username)
                    if new_text != text:
                        self._files.write_text(loginusers_path, new_text)
                else:
                    vdf_data = self._files.read_vdf(loginusers_path)
                    self._vdf.merge_loginuser_entry(
                        vdf_data.setdefault("users", {}), steam_id, username
                    )
                    self._files.write_vdf(loginusers_path, vdf_data)
                logger.info("loginusers.vdf updated.")

            self._persona.set_state(steam_dir, steam_id, state=7)
            if disable_remote_play:
                self._persona.set_remote_play(steam_dir, steam_id, False)

            local_vdf = self._process.local_vdf_path()
            if os.path.exists(local_vdf):
                text = self._files.read_text(local_vdf)
                if text.strip() and '"ConnectCache"' in text:
                    new_text = self._vdf.patch_connect_cache(text, crc32_key, encrypted)
                    if new_text != text:
                        self._files.write_text(local_vdf, new_text)
                else:
                    vdf_data = self._files.read_vdf(local_vdf)
                    (
                        vdf_data.setdefault("MachineUserConfigStore", {})
                        .setdefault("Software", {})
                        .setdefault("Valve", {})
                        .setdefault("Steam", {})
                        .setdefault("ConnectCache", {})
                    )[crc32_key] = encrypted
                    self._files.write_vdf(local_vdf, vdf_data)
                logger.info("local.vdf (ConnectCache) updated.")
            else:
                logger.warning(f"local.vdf not found: {local_vdf}")

            self._tokens.store(steam_id, username, jwt_token)
            self._registry.set_autologin_with_remember(username)
            self._vdf.disable_user_chooser(steam_dir, self._files)
            logger.info("Token login pipeline complete.")
            return True
        except Exception as exc:
            logger.exception(f"Login error: {exc}")
            return False

    def switch_account(
        self, acc: dict, persona_state: int = 7, disable_remote_play: bool = False
    ) -> bool:
        steam_dir = self._process.install_path()
        if not steam_dir:
            logger.error("Steam path not found.")
            return False

        loginusers_path = os.path.join(steam_dir, "config", "loginusers.vdf")
        if not os.path.exists(loginusers_path):
            logger.error("loginusers.vdf not found.")
            return False

        try:
            text = self._files.read_text(loginusers_path)
            offline_val = "1" if persona_state == 0 else "0"
            text = self._vdf.patch_user_fields(
                text,
                acc["steamid"],
                {
                    "AllowAutoLogin": "1",
                    "RememberPassword": "1",
                    "WantsOfflineMode": offline_val,
                    "SkipOfflineModeWarning": offline_val,
                },
            )
            text = self._vdf.set_most_recent(text, acc["steamid"])
            self._files.write_text(loginusers_path, text)

            self._registry.set_autologin_with_remember(acc["account_name"])
            self._persona.set_state(steam_dir, acc["steamid"], persona_state)
            if disable_remote_play:
                self._persona.set_remote_play(steam_dir, acc["steamid"], False)
            self._vdf.disable_user_chooser(steam_dir, self._files)
            logger.info(f'Switched → {acc["account_name"]} (ePersonaState={persona_state})')
            return True
        except Exception as exc:
            logger.exception(f"Switch error: {exc}")
            return False

    def delete_loginuser(self, steam_id: str) -> bool:
        steam_dir = self._process.install_path()
        if not steam_dir:
            return False
        loginusers_path = os.path.join(steam_dir, "config", "loginusers.vdf")
        if not os.path.exists(loginusers_path):
            return False
        try:
            vdf_data = self._files.read_vdf(loginusers_path)
            users = vdf_data.get("users", {})
            if steam_id not in users:
                return False
            del users[steam_id]
            self._files.write_vdf(loginusers_path, vdf_data)
            logger.info(f"Deleted account {steam_id}.")
            return True
        except Exception as exc:
            logger.error(f"Delete error: {exc}")
            return False

    def set_cs2_launch_options(self, steam_dir: str, steam_id: str, options: str) -> None:
        self._persona.set_cs2_launch_options(steam_dir, steam_id, options)

    def disable_cs2_workshop(self, steam_dir: str, steam_id64: str) -> int:
        """Stop CS2 (730) from downloading this account's Workshop items.

        Downloads are driven by the account's *subscription list*, not the shared
        install manifest (`appworkshop_730.acf`) — clearing that manifest just
        makes Steam re-download. Instead we flip every entry's `disabled_locally`
        to "1" in `userdata/<id32>/ugc/730_subscriptions.vdf`. That is Steam's own
        "subscribed but don't fetch/mount on this machine" state: reversible, and
        nothing is unsubscribed server-side. Because the switch flow writes this
        while Steam is closed, the client honours it on the next launch.

        Returns the number of items disabled.
        """
        try:
            steamid32 = int(steam_id64) - STEAMID64_BASE
        except (TypeError, ValueError):
            logger.warning(f"disable_cs2_workshop: invalid SteamID {steam_id64!r}")
            return 0

        subs_path = os.path.join(
            steam_dir, "userdata", str(steamid32), "ugc", "730_subscriptions.vdf"
        )
        if not os.path.exists(subs_path):
            # No local subscription list -> nothing subscribed to download.
            logger.info("730_subscriptions.vdf not found — no Workshop subs to disable.")
            return 0

        try:
            data = self._files.read_vdf(subs_path)
            subscribed = data.get("subscribedfiles", {})
            changed = 0
            for entry in subscribed.values():
                if isinstance(entry, dict) and "publishedfileid" in entry:
                    if entry.get("disabled_locally") != "1":
                        entry["disabled_locally"] = "1"
                        changed += 1
            if changed:
                self._files.write_vdf(subs_path, data)
            logger.info(f"CS2 Workshop: disabled {changed} subscription(s) for {steamid32}.")
            return changed
        except Exception as exc:
            logger.warning(f"disable_cs2_workshop: {exc}")
            return 0
