# Contributing to WareStore

Thanks for your interest in improving WareStore. It's licensed under
**GPL-3.0-or-later**, and contributions are welcome under the same terms.

## Prerequisites

- **Windows 10 or 11** (64-bit) — WareStore is Windows-only.
- **[uv](https://docs.astral.sh/uv/)** — the package/venv manager. Install it with
  `scripts\install-uv.bat`, or follow the
  [uv install guide](https://docs.astral.sh/uv/getting-started/installation/).
  uv fetches the right Python (3.12+) for you.
- **Steam** installed — for anything beyond the unit tests.
- **[Inno Setup 6](https://jrsoftware.org/isinfo.php)** — only needed to build the installer.

## Setup & run

```bat
git clone https://github.com/bet3rd/warestore.git
cd warestore
uv sync            REM install dependencies into a local .venv
uv run warestore   REM launch the app from source
```

> WareStore reads and writes Steam's files, registry keys, and processes, so run
> your terminal **as administrator** for full functionality when testing account
> switching.

## Tests

```bat
uv run pytest
```

(or `scripts\test.bat`)

## Build the installer

```bat
scripts\build.bat
```

Produces `dist\WareStoreSetup.exe` (PyInstaller onedir → Inno Setup installer).
Requires Inno Setup 6 on your PATH or in its default install location.

## Project layout

WareStore follows a layered / hexagonal architecture under `src/warestore/`:

| Layer | What lives there |
|---|---|
| `domain/` | Pure logic — models, JWT parsing, VDF patching, login orchestration |
| `application/` | Use-case controllers, the service facade, presenters, view-models |
| `infrastructure/` | Steam filesystem/registry/crypto/process gateways, encrypted persistence, external APIs |
| `presentation/` | The PyQt5 UI — window, panels, account cards, feature coordinators, theme |

Dependencies point inward (`presentation → application → domain`); the
`infrastructure` layer implements the ports the inner layers define.

## Submitting changes

1. Fork the repo and create a branch off `main`.
2. Make your change, keep it consistent with the surrounding code, and add or
   adjust tests where it makes sense. Run `uv run pytest` before opening a PR.
3. Sign off your commits with the
   [Developer Certificate of Origin](https://developercertificate.org/):
   `git commit -s` adds a `Signed-off-by` line certifying you wrote the code and
   can contribute it under the project's license.
4. Open a pull request describing what changed and why.

By contributing, you agree that your contributions are licensed under
**GPL-3.0-or-later**, the same license as the project.
