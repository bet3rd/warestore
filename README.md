# WareStore

Windows desktop app for managing Steam accounts via refresh tokens. Reads and writes Steam config files (`loginusers.vdf`, `config.vdf`, `local.vdf`) and stores saved tokens in `%APPDATA%\SteamLoginTool_CLI\`.

## Requirements

- Windows 10+
- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — `scripts\install-uv.bat` or [install guide](https://docs.astral.sh/uv/getting-started/installation/)
- Steam installed

## Build

```bat
scripts\build.bat
```

Output: `dist\WareStore.exe`

## Run

Build first, then:

```bat
scripts\start.bat
```

Dev (from source):

```bat
scripts\start-dev.bat
```

## Usage

- **Login** — paste `username----eyJ…` or a bare JWT, then click Login.
- **Switch** — double-click an account card, or select one and press Alt+Enter.
- **Settings** — bulk import, CS2 launch options, Steam Web API key (ban/level badges), master-password vault, tray behavior. The log panel toggles from the icon next to Refresh.

Account data (tokens, settings) lives under `%APPDATA%\SteamLoginTool_CLI\`.

## Tests

```bat
scripts\test.bat
```

## CI / Releases

GitHub Actions on `windows-latest`:

| Workflow | Trigger | What it does |
|----------|---------|--------------|
| **CI** | push, PR | `uv sync`, `pytest` |
| **Release** | push to `kway`, push `v*` tag, manual | tests → **always build** → artifact on every run; GitHub Release upload when semver bumps, tag is missing a release, or `kway` is ahead of the latest tag (rebuild same version) |

Version lives in `src/warestore/__init__.py`. [python-semantic-release](https://python-semantic-release.readthedocs.io/) picks the bump from commits since the last tag:

- `fix:` → patch
- `feat:` → minor
- `BREAKING CHANGE` / `feat!:` → major
- `refactor:` / `ci:` / `chore:` → no bump (but **build still runs**; exe is republished under the current tag if `kway` moved forward)

**One-time setup** — after the release workflow is on the branch you want to ship:

```bat
scripts\tag-baseline.bat
git push origin v3.0.0
```

That git tag is only the semver baseline. The workflow creates the GitHub Release and attaches `WareStore.exe`. If a tag exists but has no GitHub release yet, the next `kway` push backfills it.

Re-tag to move the baseline (e.g. after CI fixes): `git tag -fa v3.0.0 && git push origin v3.0.0 --force`

Every push to `kway` builds `WareStore.exe` (download from Actions artifacts). GitHub Releases update when the version bumps or when new commits land after the latest tag — use `fix:`/`feat:` when you want the version number to move too.

## Project layout

```
src/warestore/
  presentation/           PyQt5 UI, feature coordinators, entry point
  application/            Use cases, controller, bootstrap
  domain/                 Models, JWT parsing, VDF patching, login logic
  infrastructure/         Steam filesystem, registry, crypto, external APIs
  features/updates/       Version check
tests/
scripts/                  install-uv.bat, build.bat, start.bat, start-dev.bat
```
