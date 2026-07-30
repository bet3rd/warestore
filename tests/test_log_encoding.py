"""Logging/console output must not crash on non-Latin-1 glyphs (e.g. the '→' in
`logger.info('Switched → ...')`). Windows consoles/pipes are cp1252 by default."""

import io
import logging
import sys

import pytest

from warestore.presentation.account_manager.main import (
    _TeeStdout,
    _make_streams_unicode_safe,
)

ARROW = "Switched → acc"


def _cp1252():
    # strict cp1252, like a real Windows console / captured pipe
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", newline="")


def test_baseline_cp1252_rejects_arrow():
    with pytest.raises(UnicodeEncodeError):
        _cp1252().write(ARROW)


def test_make_streams_unicode_safe(monkeypatch):
    out, err = _cp1252(), _cp1252()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    _make_streams_unicode_safe()
    out.write(ARROW)  # no longer raises
    err.write(ARROW)
    out.flush()
    assert b"Switched" in out.buffer.getvalue()


def test_make_streams_unicode_safe_handles_none(monkeypatch):
    # frozen windowed build: no console -> streams are None; must be a no-op
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    _make_streams_unicode_safe()  # must not raise


def test_tee_never_raises_on_arrow():
    stream = _cp1252()  # deliberately NOT reconfigured -> exercises tee's guard
    _TeeStdout(stream).write(ARROW + "\n")
    stream.flush()
    assert b"Switched" in stream.buffer.getvalue()


def test_logging_console_handler_arrow_safe():
    stream = _cp1252()
    stream.reconfigure(errors="backslashreplace")
    handler = logging.StreamHandler(stream)
    logger = logging.getLogger("warestore._arrow_test")
    logger.handlers[:] = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
    logger.info(ARROW)  # must not raise
    handler.flush()
    assert b"Switched" in stream.buffer.getvalue()
