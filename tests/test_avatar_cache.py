# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 bet3rd

import os

import warestore.presentation.account_manager.ui.avatars as av


def test_ensure_avatar_downloaded_caches_by_hash(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "_AVATAR_CACHE_DIR", str(tmp_path / "avatars"))
    calls = {"n": 0}

    def fake_retrieve(url, dest):
        calls["n"] += 1
        with open(dest, "wb") as f:
            f.write(b"img-bytes")

    monkeypatch.setattr(av.urllib.request, "urlretrieve", fake_retrieve)

    p1 = av.ensure_avatar_downloaded("https://x/abc_full.jpg", "abc")
    assert p1 and os.path.exists(p1) and calls["n"] == 1

    # second call for the same hash: served from cache, no re-download
    p2 = av.ensure_avatar_downloaded("https://x/abc_full.jpg", "abc")
    assert p2 == p1 and calls["n"] == 1

    # different hash: downloads again to a different file
    p3 = av.ensure_avatar_downloaded("https://x/def_full.jpg", "def")
    assert p3 != p1 and calls["n"] == 2


def test_ensure_avatar_downloaded_noop_without_inputs(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "_AVATAR_CACHE_DIR", str(tmp_path))
    assert av.ensure_avatar_downloaded("", "abc") is None
    assert av.ensure_avatar_downloaded("https://x/y", "") is None


def test_ensure_avatar_downloaded_cleans_up_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(av, "_AVATAR_CACHE_DIR", str(tmp_path / "avatars"))

    def boom(url, dest):
        raise OSError("network down")

    monkeypatch.setattr(av.urllib.request, "urlretrieve", boom)
    assert av.ensure_avatar_downloaded("https://x/z_full.jpg", "z") is None
    # no leftover .part file
    assert not os.path.exists(av.cached_avatar_path("z") + ".part")
