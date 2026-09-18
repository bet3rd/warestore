"""Crash-safety of file replacement: a failed write must never corrupt the target."""

import json
import os

import pytest

from warestore.infrastructure.persistence.atomic_write import (
    atomic_write_bytes,
    atomic_write_text,
)
from warestore.infrastructure.persistence.json_store import JsonStore


def test_writes_content(tmp_path):
    p = tmp_path / "a.json"
    atomic_write_text(str(p), '{"k": 1}')
    assert p.read_text(encoding="utf-8") == '{"k": 1}'


def test_creates_parent_dirs(tmp_path):
    p = tmp_path / "deep" / "nested" / "a.json"
    atomic_write_bytes(str(p), b"hi")
    assert p.read_bytes() == b"hi"


def test_replaces_existing(tmp_path):
    p = tmp_path / "a.json"
    p.write_text("old" * 500, encoding="utf-8")
    atomic_write_text(str(p), "new")
    assert p.read_text(encoding="utf-8") == "new"  # fully replaced, no leftovers


def test_leaves_no_temp_files(tmp_path):
    p = tmp_path / "a.json"
    atomic_write_text(str(p), "x")
    assert [f.name for f in tmp_path.iterdir()] == ["a.json"]


def test_failed_write_preserves_original(tmp_path, monkeypatch):
    """The whole point: a crash mid-write must leave the old file intact."""
    p = tmp_path / "tokens.json"
    original = json.dumps({"76561198000000001": {"token": "keep-me"}})
    p.write_text(original, encoding="utf-8")

    real_write = os.write

    def boom(*a, **k):
        raise OSError("simulated disk full")

    # Fail during the temp-file write, before any replace happens.
    monkeypatch.setattr("os.fsync", boom)
    with pytest.raises(OSError):
        atomic_write_text(str(p), json.dumps({"wiped": True}))

    assert p.read_text(encoding="utf-8") == original  # untouched
    monkeypatch.undo()
    # and no temp litter left behind
    assert [f.name for f in tmp_path.iterdir()] == ["tokens.json"]


def test_json_store_survives_serialization_failure(tmp_path):
    """A value that can't be serialized must not destroy the existing file."""
    p = tmp_path / "settings.json"
    store = JsonStore(str(p))
    store.write({"good": 1})
    assert json.loads(p.read_text(encoding="utf-8")) == {"good": 1}

    with pytest.raises(TypeError):
        store.write({"bad": object()})  # json.dumps raises before any file I/O

    assert json.loads(p.read_text(encoding="utf-8")) == {"good": 1}


def test_json_store_roundtrip(tmp_path):
    store = JsonStore(str(tmp_path / "s.json"))
    store.write({"a": [1, 2], "b": "x"})
    assert store.read() == {"a": [1, 2], "b": "x"}
