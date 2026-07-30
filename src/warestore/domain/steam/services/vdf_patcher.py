# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging
import os
import re
from datetime import datetime

logger = logging.getLogger(__name__)


class VdfPatcher:
    def merge_loginuser_entry(
        self,
        users: dict,
        steam_id: str,
        username: str,
        timestamp: str | None = None,
    ) -> None:
        entry = users.get(steam_id)
        if not isinstance(entry, dict):
            entry = {}
        entry["AccountName"] = username
        entry.setdefault("PersonaName", username)
        entry["RememberPassword"] = "1"
        entry["WantsOfflineMode"] = "0"
        entry["SkipOfflineModeWarning"] = "0"
        entry["AllowAutoLogin"] = "1"
        entry["MostRecent"] = "1"
        entry["Timestamp"] = timestamp or str(int(datetime.now().timestamp()))
        users[steam_id] = entry
        for uid, udata in users.items():
            if uid != steam_id and isinstance(udata, dict):
                udata["MostRecent"] = "0"

    def patch_loginusers_text(self, text: str, steam_id: str, username: str) -> str:
        ts = str(int(datetime.now().timestamp()))
        text = self.set_most_recent(text, steam_id)
        if f'"{steam_id}"' not in text:
            return self.append_loginuser_block(text, steam_id, username, ts)
        return self.patch_user_fields(
            text,
            steam_id,
            {
                "AccountName": username,
                "RememberPassword": "1",
                "WantsOfflineMode": "0",
                "SkipOfflineModeWarning": "0",
                "AllowAutoLogin": "1",
                "Timestamp": ts,
            },
        )

    def patch_user_fields(self, text: str, steamid: str, fields: dict[str, str]) -> str:
        bounds = self._user_block_bounds(text, steamid)
        if bounds is None:
            return text
        start, end = bounds
        block = text[start:end]
        for field, value in fields.items():
            block = self._patch_field_in_block(block, field, value)
        return text[:start] + block + text[end:]

    def append_loginuser_block(
        self, text: str, steamid: str, username: str, timestamp: str
    ) -> str:
        block = (
            f'\n\t"{steamid}"\n'
            f"\t{{\n"
            f'\t\t"AccountName"\t\t"{username}"\n'
            f'\t\t"PersonaName"\t\t"{username}"\n'
            f'\t\t"RememberPassword"\t\t"1"\n'
            f'\t\t"WantsOfflineMode"\t\t"0"\n'
            f'\t\t"SkipOfflineModeWarning"\t\t"0"\n'
            f'\t\t"AllowAutoLogin"\t\t"1"\n'
            f'\t\t"MostRecent"\t\t"1"\n'
            f'\t\t"Timestamp"\t\t"{timestamp}"\n'
            f"\t}}\n"
        )
        if '"users"' in text:
            users_idx = text.find('"users"')
            brace = text.find("{", users_idx)
            if brace != -1:
                return text[: brace + 1] + block + text[brace + 1 :]
        return '"users"\n{\n' + block + "\n}\n" if not text.strip() else text + block

    def set_most_recent(self, text: str, target_steamid: str) -> str:
        text = re.sub(r'("MostRecent"(\s+))"[^"]*"', r'\1"0"', text)
        bounds = self._user_block_bounds(text, target_steamid)
        if bounds is None:
            return text
        start, end = bounds
        block = text[start:end]
        new_block = re.sub(r'("MostRecent"(\s+))"0"', r'\1"1"', block, count=1)
        return text[:start] + new_block + text[end:]

    def patch_connect_cache(self, text: str, crc_key: str, hex_value: str) -> str:
        key_pattern = rf'("{re.escape(crc_key)}"\s+)("[^"]*")'
        if re.search(key_pattern, text):
            return re.sub(key_pattern, rf'\1"{hex_value}"', text, count=1)
        marker = '"ConnectCache"'
        idx = text.find(marker)
        if idx == -1:
            return text
        brace = text.find("{", idx)
        if brace == -1:
            return text
        entry = f'\n\t\t"{crc_key}"\t\t"{hex_value}"'
        return text[: brace + 1] + entry + text[brace + 1 :]

    def disable_user_chooser(self, steam_dir: str, files: "VdfFileGateway") -> None:
        config_path = os.path.join(steam_dir, "config", "config.vdf")
        if not os.path.exists(config_path):
            return
        try:
            text = files.read_text(config_path)
            if "AlwaysShowUserChooser" not in text:
                return
            new_text = self.patch_field(text, "AlwaysShowUserChooser", "0")
            if new_text != text:
                files.write_text(config_path, new_text)
        except Exception as exc:
            logger.warning(f"AlwaysShowUserChooser patch failed: {exc}")

    def patch_field(self, text: str, field: str, value: str) -> str:
        return re.sub(
            rf'("{re.escape(field)}"(\s+))"[^"]*"',
            rf'\1"{value}"',
            text,
        )

    def _patch_field_in_block(self, block: str, field: str, value: str) -> str:
        if f'"{field}"' in block:
            return self.patch_field(block, field, value)
        return block.rstrip() + f'\n\t\t"{field}"\t\t"{value}"\n'

    def _user_block_bounds(self, text: str, steamid: str) -> tuple[int, int] | None:
        sid_idx = text.find(f'"{steamid}"')
        if sid_idx == -1:
            return None
        brace_open = text.find("{", sid_idx)
        if brace_open == -1:
            return None
        depth, i = 1, brace_open + 1
        while i < len(text) and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        return brace_open, i
