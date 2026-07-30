<div align="center">

# WareStore Account Manager

**Switch between dozens of Steam accounts in one click — no passwords, no Steam Guard, nothing of yours deleted.**

[![Latest release](https://img.shields.io/github/v/release/bet3rd/warestore?label=version&color=crimson)](https://github.com/bet3rd/warestore/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/bet3rd/warestore/total?color=crimson)](https://github.com/bet3rd/warestore/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2B-blue)](https://github.com/bet3rd/warestore/releases/latest)
[![Website](https://img.shields.io/badge/website-warestore.cc-crimson)](https://warestore.cc)

### [⬇ Download the latest installer](https://github.com/bet3rd/warestore/releases/latest/download/WareStoreSetup.exe)

</div>

---

**WareStore Account Manager** is a Windows desktop app for managing a large collection of Steam accounts through their refresh tokens — the "rented accounts" you juggle by the dozen. It signs any account in **instantly**, straight from a saved token: no password, no Steam Guard, no waiting. Every account is **added** to Steam alongside the others — it never wipes what's already there — and it keeps the whole roster organized, labeled, and readable at a glance.

It was built to make managing that many accounts feel effortless, and it's free for everyone.

## Features

- **⚡ Instant account switching** — sign in from a saved refresh token in one click (double-click a card or `Alt`+`Enter`). It closes Steam, sets the account, and relaunches — no credentials typed, and no other account touched.
- **📥 Add accounts your way** — paste a single token, bulk-import a whole list (one per line), or let it **auto-extract** tokens for accounts already signed into Steam on the machine.
- **🗂️ Organize the roster** — color tags, a searchable grid, and a filter menu (by color, untagged, no-cooldown, no-bans) to find any account fast.
- **🔎 Status at a glance** — every card shows the account's **level**, **online/away/in-game status**, **VAC / game / trade ban** flags, and a live **cooldown** bar, with a rich tooltip for the details.
- **⏱️ Cooldown tracking** — mark competitive cooldowns with presets or a custom duration, watch the countdown tick down on the card, and get a tray notification the moment one clears.
- **🎮 CS2 tools** — copy your CS2 config from a source account to the rest automatically, set per-account launch options, open CS2 on login, and stop CS2 from re-downloading Workshop maps on every switch.
- **🕶️ Play it quiet** — every account is logged in as **Invisible**, so switching never flashes you online; Remote Play can be disabled on login; and the window can be **hidden from screen capture** (Discord, OBS).
- **🔒 Your tokens, locked down** — tokens are **encrypted on your PC** (Windows DPAPI by default, or AES-256 behind an **optional master password** with a recovery code). Add a free Steam Web API key to light up ban and level badges.
- **🧹 Safe cleanup** — reclaim disk from leftover Steam `userdata` folders, with a dialog that lists exactly which accounts it will remove **before** anything is deleted.
- **🛠️ Optional HWID tool** — an on-demand HWID spoofer you install from Settings only if you want it (it is **not** bundled with the app), with a per-account reset.
- **✨ Quality of life** — bulk import, keyboard navigation, multi-select actions, a built-in log panel, system-tray support, single-instance focus, a dark UI throughout, and automatic update checks.

## Download & Install

**[⬇ Download `WareStoreSetup.exe`](https://github.com/bet3rd/warestore/releases/latest/download/WareStoreSetup.exe)** — or grab it from the [Releases page](https://github.com/bet3rd/warestore/releases/latest).

Run the installer and you're set. It installs like normal software:

- Installs to `C:\Program Files\WareStore` with a Start Menu shortcut and a clean uninstaller.
- Upgrades **in place** — your saved accounts and settings are preserved across updates.
- The optional HWID tool is **downloaded on demand** from Settings, never bundled, keeping the base install lean.

**Requirements**

- Windows 10 or 11 (64-bit).
- Runs elevated (a UAC prompt on launch) — it needs administrator rights to manage Steam's files and processes.
- The "hide from screen capture" feature needs Windows 10 version 2004 or newer; everything else works on any Windows 10.

## Getting started

1. **Add an account.** Paste a token into the top bar and press **Login**. Tokens can be `username----eyJ…`, a bare `eyJ…` JWT, or — for many at once — one per line in **Settings → Bulk Import**.
2. **Switch.** Double-click any card (or select it and press `Alt`+`Enter`) to sign into that account.
3. **Light up the badges (optional).** Drop a free [Steam Web API key](https://steamcommunity.com/dev/apikey) into Settings to show ban and level info on every card.
4. **Lock it down (optional).** Set a master password in Settings for a layer even local software can't bypass — you'll get a one-time recovery code.
5. **Spoof HWID (optional).** Enable the HWID tool from Settings; it installs on demand.

## Privacy & safety

WareStore Account Manager is built to keep your accounts on **your** machine.

- **No telemetry, no token upload.** Your refresh tokens never leave your PC — they're only written into Steam's own encrypted store and your local, encrypted vault. The only network calls the app makes are read-only: checking for updates, and (optionally, with your API key) fetching public profile status, bans, and levels from Steam's own API.
- **Encrypted at rest.** Tokens are protected with Windows DPAPI by default, or AES-256-GCM when you set a master password.
- **It manages Steam directly.** To switch accounts, it reads and writes Steam's login files (`loginusers.vdf`, `config.vdf`, the `ConnectCache`) and closes/relaunches Steam. That's how a password-less switch works — and it's all local.
- **Irreversible actions are gated.** Cleanup and deletions always show you exactly what they'll do first.

## Updates

WareStore Account Manager checks for new versions on launch and shows you the changelog when one's available. Choosing to update opens the latest installer, which upgrades your install in place and keeps all your data.

## The WareStore toolkit

The Account Manager is the flagship of the **WareStore** family — a few more Steam tools round it out:

- **[Steam-JWT-Tool](https://github.com/bet3rd/Steam-JWT-Tool)** — an open-source, login-only tool that runs on the same login logic as WareStore Account Manager. Add a token, sign in, done.
- **[Cache Extract Tool](https://bet3rd.github.io/cache-extract)** ([source](https://github.com/bet3rd/cache-extract)) — bought an account and only got an `.exe` you can't verify? Upload it and get the token back. Everything is processed locally in your browser.
- **[steam_hwid_spoofer](https://github.com/bet3rd/steam_hwid_spoofer)** — the standalone HWID spoofer. Build it yourself or grab a prebuilt binary from the [Releases](https://github.com/bet3rd/steam_hwid_spoofer/releases) page.

## Links & mirror

- **Website:** [warestore.cc](https://warestore.cc)
- **GitLab mirror:** [gitlab.com/bet3rd](https://gitlab.com/bet3rd) — all projects are mirrored there in case GitHub ever acts up.

## Building from source

WareStore Account Manager is a Python / PyQt5 app managed with [uv](https://docs.astral.sh/uv/):

```bat
git clone https://github.com/bet3rd/warestore.git
cd warestore
uv sync
uv run warestore
```

Build the Windows installer with `scripts\build.bat` (requires Inno Setup 6). See
**[CONTRIBUTING.md](CONTRIBUTING.md)** for the full developer guide, project
layout, and how to submit changes.

## License

WareStore Account Manager is licensed under the **[GNU General Public License v3.0 or later](LICENSE)** — you're free to use, study, share, and modify it, and any distributed fork must stay open under the same license.

Contributions are welcome under the same license — see [CONTRIBUTING.md](CONTRIBUTING.md).

© 2026 bet3rd
