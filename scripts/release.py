#!/usr/bin/env python
"""Cut a public WareStore release and regenerate version.json in one step.

The app's ``warestore.__version__`` is the single source of truth. This script:

  1. reads that version,
  2. (optionally) builds ``dist/WareStoreSetup.exe`` via scripts/build.bat,
  3. publishes a GitHub release on the public repo with the installer attached
     under the FIXED asset name ``WareStoreSetup.exe``,
  4. rewrites ``version.json`` on that repo so ``latest_version`` == the app
     version and ``download_url`` points at the stable
     ``releases/latest/download/WareStoreSetup.exe`` alias.

Because the asset name and download_url are constant, the two ways this used to
break -- ``latest_version`` drifting from ``__version__`` (permanent "update
available" dialog) and a version-pinned download_url 404-ing -- can't happen.

Requires the GitHub CLI (``gh``) authenticated with push access to the repo.

Examples
--------
    uv run python scripts/release.py --changelog "Optional spoofer + new installer"
    uv run python scripts/release.py -c "Hotfix" --force-below 2.1
    uv run python scripts/release.py -c "test" --dry-run      # print, change nothing
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSET_NAME = "WareStoreSetup.exe"
ASSET_PATH = ROOT / "dist" / ASSET_NAME
DEFAULT_REPO = "bet3rd/warestore"


def die(msg: str) -> None:
    print(f"[!] {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str], *, capture: bool = False) -> str:
    """Run a command, echoing it. Returns stdout when capture=True."""
    print(f"    $ {' '.join(cmd)}")
    result = subprocess.run(
        cmd, cwd=ROOT, text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    if result.returncode != 0:
        if capture and result.stderr:
            print(result.stderr, file=sys.stderr)
        die(f"command failed ({result.returncode}): {' '.join(cmd)}")
    return (result.stdout or "").strip()


def app_version() -> str:
    sys.path.insert(0, str(ROOT / "src"))
    from warestore import __version__  # noqa: E402
    return __version__


def gh_json(args: list[str]) -> object:
    return json.loads(run(["gh", "api", *args], capture=True) or "null")


def download_url(repo: str) -> str:
    # Stable alias: always resolves to the latest release's asset of this name.
    return f"https://github.com/{repo}/releases/latest/download/{ASSET_NAME}"


def current_manifest(repo: str) -> tuple[dict, str | None]:
    """Return (manifest, blob_sha). Empty manifest + None sha if absent."""
    try:
        data = gh_json(["-H", "Accept: application/vnd.github+json",
                        f"repos/{repo}/contents/version.json"])
    except SystemExit:
        return {}, None
    if not isinstance(data, dict) or "content" not in data:
        return {}, None
    raw = base64.b64decode(data["content"]).decode("utf-8")
    return json.loads(raw), data.get("sha")


def main() -> None:
    ap = argparse.ArgumentParser(description="Publish a WareStore release + version.json.")
    ap.add_argument("-c", "--changelog", default=None,
                    help="change_log text (default: auto-generate from commits since the last tag)")
    ap.add_argument("--repo", default=DEFAULT_REPO, help=f"target repo (default {DEFAULT_REPO})")
    ap.add_argument("--force-below", default=None,
                    help="force_update_below_version (default: keep existing)")
    ap.add_argument("--no-build", action="store_true", help="skip build; use existing installer")
    ap.add_argument("--dry-run", action="store_true", help="print the plan; change nothing")
    args = ap.parse_args()

    version = app_version()
    tag = f"v{version}"
    print(f"[*] App version (source of truth): {version}  ->  tag {tag}")

    # A hand-written changelog wins; otherwise auto-generate one scoped to this
    # release, grouped by type and filtered to user-facing changes.
    sys.path.insert(0, str(ROOT / "scripts"))
    from gen_changelog import generate  # noqa: E402

    changelog = args.changelog or generate()
    print("[*] Changelog:")
    print("\n".join("      " + ln for ln in changelog.splitlines()))

    # 1. Build if needed ------------------------------------------------------
    if not args.no_build and not args.dry_run:
        print("[*] Building installer...")
        os.environ.setdefault("CI", "1")  # make build.bat skip its trailing `pause`
        run(["cmd", "/c", str(ROOT / "scripts" / "build.bat")])
    if not ASSET_PATH.exists():
        die(f"installer not found: {ASSET_PATH} (build it, or drop --no-build)")
    print(f"[*] Installer: {ASSET_PATH} ({ASSET_PATH.stat().st_size / 1e6:.1f} MB)")

    # 2. Assemble the manifest ------------------------------------------------
    manifest, sha = current_manifest(args.repo)
    force_below = args.force_below or manifest.get("force_update_below_version", version)
    new_manifest = {
        "latest_version": version,
        "change_log": changelog,
        "download_url": download_url(args.repo),
        "force_update_below_version": force_below,
    }
    print("[*] version.json to publish:")
    print("\n".join("      " + ln for ln in json.dumps(new_manifest, indent=4).splitlines()))

    if args.dry_run:
        print("\n[dry-run] Would create release "
              f"{tag} on {args.repo} with {ASSET_NAME}, then commit version.json above.")
        return

    # 3. Publish the release (idempotent: create, else clobber the asset) -----
    print(f"[*] Publishing release {tag} on {args.repo}...")
    exists = subprocess.run(["gh", "release", "view", tag, "--repo", args.repo],
                            cwd=ROOT, capture_output=True, text=True).returncode == 0
    if exists:
        run(["gh", "release", "upload", tag, str(ASSET_PATH),
             "--repo", args.repo, "--clobber"])
        # Refresh the notes too, so the release page matches version.json's
        # change_log on a re-release (upload --clobber only touches the asset).
        run(["gh", "release", "edit", tag, "--repo", args.repo,
             "--notes", changelog])
    else:
        run(["gh", "release", "create", tag, str(ASSET_PATH),
             "--repo", args.repo, "--title", f"WareStore {version}",
             "--notes", changelog])

    # 4. Commit version.json --------------------------------------------------
    print("[*] Updating version.json...")
    content_b64 = base64.b64encode(
        (json.dumps(new_manifest, indent=4) + "\n").encode("utf-8")
    ).decode("ascii")
    put = ["-X", "PUT", f"repos/{args.repo}/contents/version.json",
           "-f", f"message=release: v{version}",
           "-f", f"content={content_b64}"]
    if sha:
        put += ["-f", f"sha={sha}"]
    run(["gh", "api", *put], capture=True)

    print(f"\n[OK] Released {version}. Update dialog now serves {download_url(args.repo)}")


if __name__ == "__main__":
    main()
