from __future__ import annotations

import os
import traceback
from typing import Any, Dict, List, Optional


def parse_backtrace(exc: BaseException, root_directory: str) -> List[Dict[str, Any]]:
    frames: List[Dict[str, Any]] = []
    tb_frames = traceback.extract_tb(exc.__traceback__)

    for index, frame in enumerate(tb_frames):
        file = frame.filename
        frames.append(
            {
                "file": _relative_file(file, root_directory),
                "line": frame.lineno,
                "function": frame.name,
                "in_app": _is_in_app(file, root_directory),
                "index": index,
            }
        )

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
