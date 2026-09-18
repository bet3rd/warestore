<div align="center">

<img src="assets/warestore.ico" width="96" alt="WareStore">

<h1>WareStore Account Manager</h1>

<p>Switch between dozens of Steam accounts in one click — no passwords, no Steam Guard, nothing of yours deleted.</p>

[![Latest release](https://img.shields.io/github/v/release/bet3rd/warestore?label=version&color=crimson)](https://github.com/bet3rd/warestore/releases/latest)
[![Downloads](https://img.shields.io/github/downloads/bet3rd/warestore/total?color=crimson)](https://github.com/bet3rd/warestore/releases)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%2B-blue)](https://github.com/bet3rd/warestore/releases/latest)
[![License](https://img.shields.io/badge/license-GPL--3.0-green)](LICENSE)

<h3>
<a href="#download">Download</a>
<span> · </span>
<a href="#features">Features</a>
<span> · </span>
<a href="#privacy--safety">Privacy</a>
<span> · </span>
<a href="https://warestore.cc">Website</a>
</h3>

</div>

---

WareStore is a Windows desktop app for managing a large collection of Steam accounts through their refresh tokens. It signs any account in instantly, straight from a saved token, and adds it alongside the accounts already on the machine — it never wipes what's there.

## Download

**[Download the latest installer](https://github.com/bet3rd/warestore/releases/latest)**

It installs to Program Files and upgrades in place, so your accounts and settings survive updates.

**Requirements:** Windows 10 or 11 (64-bit). Runs elevated — there's a UAC prompt on launch, because it manages Steam's files and processes.

Windows SmartScreen may warn on first run, as the installer isn't code-signed. Choose **More info → Run anyway**.

## Features

- **One-click switching** — sign in from a saved token by double-clicking a card or pressing `Alt`+`Enter`.
- **Add accounts three ways** — paste a single token, bulk-import a list, or auto-extract the accounts already signed in.
- **Organized roster** — color tags, instant search, and filters for cooldowns, bans and untagged accounts.
- **Status on every card** — level, online state, VAC/game/trade bans, a live cooldown bar, and the account's CS2 friend code.
- **CS2 config cloning** — copy binds, crosshair, sensitivity and video settings from one account to the rest, and they stay put.
- **Matchmaking ranks (GCPD)** — pull Premier and Wingman rank, wins and cooldown status for one account or the whole roster.
- **Cooldown tracking** — countdowns on the card, plus a tray notification the moment one clears.
- **Invisible sign-in** — every switch logs in as Invisible, and the window can be hidden from screen capture (Discord, OBS).
- **Optional HWID spoofer** — installed on demand from Settings; it is **not** bundled with the app.

## Privacy & safety

**WareStore stores no passwords and uploads nothing.** Your refresh tokens never leave your PC. They're encrypted at rest with Windows DPAPI by default, or AES-256-GCM behind an optional master password with a recovery code. Saves are crash-safe, so a crash or power loss mid-write can't leave you with a corrupted vault.

The only network calls are read-only: checking for updates, and fetching public profile data from Steam's own API if you add a free API key. To switch accounts it reads and writes Steam's own login files and restarts Steam — all of it local. Cleanups and deletions always show you exactly what they'll remove first.

## Getting started

1. **Add an account** — paste a token in the top bar and press **Login**.
2. **Switch** — double-click any card.
3. **Light up the badges** *(optional)* — add a free [Steam Web API key](https://steamcommunity.com/dev/apikey) in Settings for ban and level info.
4. **Lock it down** *(optional)* — set a master password in Settings; you'll get a one-time recovery code.

Tokens can be `username----eyJ…` or a bare `eyJ…`. For many at once, use **Settings → Bulk Import**, one per line.

## The rest of the toolkit

| Tool | What it's for |
| --- | --- |
| [Steam-JWT-Tool](https://github.com/bet3rd/Steam-JWT-Tool) | Open-source, login only — same login logic as WareStore. |
| [Cache Extract Tool](https://bet3rd.github.io/cache-extract) | Only got an `.exe` instead of a token? Recover it in your browser. |
| [steam_hwid_spoofer](https://github.com/bet3rd/steam_hwid_spoofer) | The standalone HWID spoofer. |

Also mirrored on [GitLab](https://gitlab.com/bet3rd) in case GitHub acts up.

## Building from source

```bat
git clone https://github.com/bet3rd/warestore.git
cd warestore
uv sync
uv run warestore
```

Build the installer with `scripts\build.bat` (requires Inno Setup 6). See **[CONTRIBUTING.md](CONTRIBUTING.md)** for the full developer guide and project layout.

## License

WareStore Account Manager is licensed under the **[GPL-3.0-or-later](LICENSE)** — use it, study it, share it, modify it; distributed forks stay open under the same license. Contributions welcome.

---

<sub>Not affiliated with, endorsed by, or sponsored by Valve Corporation. Steam and Counter-Strike are trademarks of Valve Corporation. © 2026 bet3rd</sub>
