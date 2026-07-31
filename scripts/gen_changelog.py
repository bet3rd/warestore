#!/usr/bin/env python
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd
"""Turn conventional-commit subjects into a user-facing, categorized changelog.

Only user-facing types (feat / fix / perf) are shown, grouped into sections.
Internal commits -- docs, ci, chore, test, refactor, build, style, version
bumps, merges, and any non-conventional subject ("Update README.md") -- are
dropped, so the notes describe the *release*, not the repo's plumbing.

CLI::

    python scripts/gen_changelog.py [<git-range>]
      # no range  -> commits since the latest v* tag
      # explicit  -> python scripts/gen_changelog.py v3.2..HEAD

Prints markdown to stdout.
"""

from __future__ import annotations

import re
import subprocess
import sys

# (conventional type, section heading), in display order.
_SECTIONS: list[tuple[str, str]] = [
    ("feat", "New features"),
    ("fix", "Bug fixes"),
    ("perf", "Performance"),
]
_USER_FACING = {t for t, _ in _SECTIONS}
_CONVENTIONAL = re.compile(
    r"^(?P<type>[a-z]+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<desc>.+)$",
    re.IGNORECASE,
)


def _humanize(desc: str) -> str:
    desc = desc.strip()
    return desc[:1].upper() + desc[1:] if desc else desc


def render(subjects: list[str]) -> str:
    """Render commit subjects into grouped markdown. Pure -- takes no git."""
    groups: dict[str, list[str]] = {t: [] for t, _ in _SECTIONS}
    breaking: list[str] = []
    for subject in subjects:
        m = _CONVENTIONAL.match(subject.strip())
        if not m:
            continue  # non-conventional ("Update README.md", "Bump version") -> drop
        typ = m.group("type").lower()
        scope = (m.group("scope") or "").strip()
        desc = _humanize(m.group("desc"))
        line = f"- **{scope}:** {desc}" if scope else f"- {desc}"
        if m.group("bang"):
            breaking.append(line)  # a breaking change is filed once, under Breaking
        elif typ in _USER_FACING:
            groups[typ].append(line)

    blocks: list[str] = []
    if breaking:
        blocks.append("**⚠️ Breaking changes**\n" + "\n".join(breaking))
    for typ, heading in _SECTIONS:
        if groups[typ]:
            blocks.append(f"**{heading}**\n" + "\n".join(groups[typ]))
    return "\n\n".join(blocks) if blocks else "- Maintenance and internal improvements."


def _git_subjects(rng: str) -> list[str]:
    cmd = ["git", "log", "--no-merges", "--pretty=format:%s"]
    if rng:
        cmd.insert(2, rng)
    out = subprocess.run(cmd, text=True, capture_output=True, check=True).stdout
    return [ln for ln in out.splitlines() if ln.strip()]


def _latest_tag() -> str:
    out = subprocess.run(
        ["git", "tag", "--list", "v*", "--sort=-v:refname"],
        text=True,
        capture_output=True,
    ).stdout.split()
    return out[0] if out else ""


def generate(rng: str = "") -> str:
    """Categorized changelog for a git range (default: since the latest v* tag)."""
    if not rng:
        tag = _latest_tag()
        rng = f"{tag}..HEAD" if tag else ""
    return render(_git_subjects(rng))


def main(argv: list[str]) -> None:
    print(generate(argv[1] if len(argv) > 1 else ""))


if __name__ == "__main__":
    main(sys.argv)
