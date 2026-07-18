from __future__ import annotations

import os
import traceback
from typing import Any, Dict, List, Optional

SOURCE_CONTEXT_RADIUS = 6
MAX_SOURCE_LINE_CHARS = 400


def parse_backtrace(exc: BaseException, root_directory: str) -> List[Dict[str, Any]]:
    frames: List[Dict[str, Any]] = []
    # traceback.extract_tb returns oldest -> newest. Errorgap frame index 0 is
    # the innermost frame where the exception was raised.
    tb_frames = reversed(traceback.extract_tb(exc.__traceback__))

    for index, frame in enumerate(tb_frames):
        file = frame.filename
        in_app = _is_in_app(file, root_directory)
        normalized: Dict[str, Any] = {
            "file": _relative_file(file, root_directory),
            "line": frame.lineno,
            "function": frame.name,
            "in_app": in_app,
            "index": index,
        }
        source = _source_excerpt(file, frame.lineno)
        if source is not None:
            normalized["source"] = source
        frames.append(normalized)

    return frames


def _relative_file(file: Optional[str], root: str) -> Optional[str]:
    if not file:
        return file
    if not root:
        return file
    normalized = root if root.endswith(os.sep) else root + os.sep
    if file.startswith(normalized):
        return file[len(normalized):]
    return file


def _is_in_app(file: Optional[str], root: str) -> bool:
    if not file or not root:
        return False
    if "site-packages" in file:
        return False
    if file.startswith("<"):
        return False
    return file.startswith(root)


def _source_excerpt(file: str, line: int) -> Optional[Dict[str, Any]]:
    if line < 1:
        return None
    start_line = max(1, line - SOURCE_CONTEXT_RADIUS)
    end_line = line + SOURCE_CONTEXT_RADIUS
    lines: List[str] = []
    target_found = False

    try:
        with open(file, encoding="utf-8", errors="replace") as source_file:
            for number, text in enumerate(source_file, start=1):
                if number < start_line:
                    continue
                if number > end_line:
                    break
                lines.append(text.rstrip("\r\n")[:MAX_SOURCE_LINE_CHARS])
                if number == line:
                    target_found = True
    except OSError:
        return None

    if not lines or not target_found:
        return None
    return {"start_line": start_line, "lines": lines}
