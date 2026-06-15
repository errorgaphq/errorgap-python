from __future__ import annotations

import os

from errorgap.backtrace import parse_backtrace


def _raise_and_capture() -> Exception:
    try:
        raise ValueError("boom")
    except Exception as exc:
        return exc


def test_parses_frames():
    exc = _raise_and_capture()
    frames = parse_backtrace(exc, os.getcwd())
    assert len(frames) >= 1
    top = frames[0]
    assert top["function"] == "_raise_and_capture"
    assert top["line"] > 0
    assert "test_backtrace" in (top["file"] or "")
    assert top["index"] == 0


def test_in_app_marks_files_under_root():
    exc = _raise_and_capture()
    frames = parse_backtrace(exc, os.getcwd())
    assert frames[0]["in_app"] is True


def test_empty_for_exception_without_traceback():
    exc = ValueError("no tb")
    assert parse_backtrace(exc, os.getcwd()) == []
