# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import logging
import os
import subprocess
import time

logger = logging.getLogger(__name__)

# Prevent console windows from flashing on screen when spawning child processes.
_NO_WINDOW = subprocess.CREATE_NO_WINDOW


class SteamProcessGateway:
    _PROCESSES = (
        "steam.exe",
        "steamservice.exe",
        "steamwebhelper.exe",
        "steamerrorreporter.exe",
        "streaming_client.exe",
    )

    def kill(self) -> None:
        logger.info("Killing Steam processes...")
        for proc in self._PROCESSES:
            subprocess.run(
                ["taskkill", "/F", "/IM", proc],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=_NO_WINDOW,
            )
        time.sleep(1.5)

    def install_path(self) -> str | None:
        try:
            import winreg

            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam")
            path, _ = winreg.QueryValueEx(key, "SteamPath")
            winreg.CloseKey(key)
            return path.replace("/", "\\")
        except OSError:
            return None

    def local_vdf_path(self) -> str:
        return os.path.join(os.getenv("LOCALAPPDATA", ""), "Steam", "local.vdf")

    def launch(self, *, open_cs2: bool = False) -> None:
        steam_dir = self.install_path()
        steam_exe = os.path.join(steam_dir, "steam.exe") if steam_dir else None
        if steam_exe and os.path.exists(steam_exe):
            args = [steam_exe]
            if open_cs2:
                args += ["-applaunch", "730"]
            subprocess.Popen(args)
            logger.info(f'Steam launched{" → CS2 (730)" if open_cs2 else ""}.')
        else:
            # `start` is a cmd builtin, so shell=True is required here (unlike the
            # taskkill/injector calls, which invoke real executables directly).
            url = "steam://rungameid/730" if open_cs2 else "steam://open/main"
            subprocess.run(["start", url], shell=True, creationflags=_NO_WINDOW)
            logger.info(f'Steam launched via protocol{" (CS2)" if open_cs2 else ""}.')

    def kill_injectors(self) -> None:
        # Each injector runs in wait-for-steam mode and never exits on its own,
        # so without this they pile up one-per-login (each with a cmd.exe child).
        # /T also clears those child processes.
        subprocess.run(
            ["taskkill", "/F", "/T", "/IM", "injector.exe"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=_NO_WINDOW,
        )

    def launch_with_spoofer(self, injector_path: str, *, open_cs2: bool = False) -> None:
        # Reap any leftover injectors from previous logins before spawning a new
        # one — only a single wait-for-steam watcher should ever be running.
        self.kill_injectors()
        # Injector kills any lingering steam.exe then waits for the next one.
        # Give it time to finish its own kill + enter the watch loop before
        # Steam starts, otherwise steam.exe wins the race.
        logger.info(f"Launching injector (wait-for-steam mode): {injector_path}")
        subprocess.Popen([injector_path], creationflags=_NO_WINDOW)
        time.sleep(2.0)
        self.launch(open_cs2=open_cs2)
