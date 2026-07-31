from scripts.gen_changelog import render


def test_groups_user_facing_and_drops_internal():
    subjects = [
        "feat(accounts): refresh + persist persona name and avatar",
        "feat(cs2): apply source launch options on every switch",
        "fix(login): handle non-latin persona names",
        "perf(grid): lazy-load avatars",
        "docs: add project README",
        "ci: mirror main + tags to GitLab on push",
        "chore(license): GPL-3.0-only -> GPL-3.0-or-later",
        "refactor(core): tidy imports",
        "test: add coverage",
        "Update README.md",
        "Bump version to 3.2.1",
        "release: v3.2",
    ]
    out = render(subjects)

    # grouped under real section headings
    assert "**New features**" in out
    assert "**Bug fixes**" in out
    assert "**Performance**" in out

    # user-facing kept, prefix stripped, scope bolded, description capitalized
    assert "- **accounts:** Refresh + persist persona name and avatar" in out
    assert "- **login:** Handle non-latin persona names" in out

    # internal noise dropped entirely
    for noise in ("README", "GitLab", "SPDX", "GPL", "refactor", "Bump version", "release:", "test"):
        assert noise not in out


def test_section_order_is_features_fixes_perf():
    out = render(["perf: x speedup", "fix: y crash", "feat: z thing"])
    assert out.index("New features") < out.index("Bug fixes") < out.index("Performance")


def test_breaking_change_filed_once_under_breaking():
    out = render(["feat(api)!: drop legacy token format"])
    assert "**⚠️ Breaking changes**" in out
    assert "- **api:** Drop legacy token format" in out
    assert "New features" not in out  # not also duplicated under its type
    assert out.count("Drop legacy token format") == 1


def test_scopeless_commit_has_no_empty_bold():
    out = render(["feat: add dark mode"])
    assert "- Add dark mode" in out
    assert "****" not in out


def test_nothing_user_facing_falls_back():
    assert render(["docs: x", "ci: y", "Update README"]).startswith("- Maintenance")
