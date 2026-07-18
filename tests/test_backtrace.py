from __future__ import annotations

import os

from errorgap.backtrace import (
    MAX_SOURCE_LINE_CHARS,
    SOURCE_CONTEXT_RADIUS,
    _source_excerpt,
    parse_backtrace,
)


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


def _inner_failure() -> None:
    raise RuntimeError("inner boom")


def _outer_failure() -> None:
    _inner_failure()


def test_innermost_frame_is_first_and_includes_source_context():
    try:
        _outer_failure()
    except RuntimeError as exc:
        frames = parse_backtrace(exc, os.getcwd())

    assert frames[0]["function"] == "_inner_failure"
    assert frames[1]["function"] == "_outer_failure"
    source = frames[0]["source"]
    target_offset = frames[0]["line"] - source["start_line"]
    assert 'raise RuntimeError("inner boom")' in source["lines"][target_offset]


def test_attaches_source_to_readable_vendor_frames():
    exc = _raise_and_capture()
    frames = parse_backtrace(exc, "/path/that/does/not/contain/tests")
    assert frames[0]["in_app"] is False
    source = frames[0]["source"]
    target_offset = frames[0]["line"] - source["start_line"]
    assert 'raise ValueError("boom")' in source["lines"][target_offset]


def test_source_excerpt_is_bounded(tmp_path):
    source_file = tmp_path / "app.py"
    source_file.write_text("\n".join(["x" * 500] * 30), encoding="utf-8")

    source = _source_excerpt(str(source_file), 15)

    assert source is not None
    assert source["start_line"] == 15 - SOURCE_CONTEXT_RADIUS
    assert len(source["lines"]) == SOURCE_CONTEXT_RADIUS * 2 + 1
    assert all(len(line) == MAX_SOURCE_LINE_CHARS for line in source["lines"])
