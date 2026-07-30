# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

class SteamRegistryGateway:
    def set_autologin_with_remember(self, account_name: str) -> None:
        import winreg

        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
        winreg.SetValueEx(key, "AutoLoginUser", 0, winreg.REG_SZ, account_name)
        winreg.SetValueEx(key, "RememberPassword", 0, winreg.REG_DWORD, 1)
        winreg.CloseKey(key)
