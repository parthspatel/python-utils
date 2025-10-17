from __future__ import annotations

import inspect
import os
from pathlib import Path
from types import FrameType
from typing import Iterable, Optional

from pyutils.fileapi import FileAPI

_PROJECT_MARKERS: tuple[str, ...] = (
    "pyproject.toml",
    "setup.cfg",
    "setup.py",
    "requirements.txt",
    ".git",
)

_PROJECT_ENV_VARS: tuple[str, ...] = (
    "UV_PROJECT_ROOT",
    "POETRY_PROJECT_ROOT",
    "PROJECT_ROOT"
)


def _get_current_dir() -> Path:
    """Return the directory of the first caller outside this module."""

    frame: Optional[FrameType] = inspect.currentframe()
    if frame is None:
        raise RuntimeError("Unable to determine caller; current frame unavailable.")

    try:
        caller = frame.f_back
        utils_file = Path(__file__).resolve()

        while caller is not None:
            caller_path = Path(caller.f_code.co_filename).resolve()
            if caller_path != utils_file:
                return caller_path.parent
            caller = caller.f_back

        raise RuntimeError("Unable to determine caller directory from stack frames.")
    finally:
        # Break the reference cycle (frame ↔ locals) to avoid leaking stack frames.
        del frame

def get_current_dir() -> FileAPI:
    path = str(_get_current_dir().resolve())
    return FileAPI(path)

def _get_project_dir(markers: Iterable[str] | None = None) -> Path:
    """Return the project root for the caller using UV env or filesystem markers."""

    # try to use env vars first to resolve the project root
    for env_var in _PROJECT_ENV_VARS:
        env_root = os.environ.get(env_var)
        if env_root:
            return Path(env_root).resolve()

    # search the filesystem upwards to find the project root, looking for key files that indicate a project root
    caller_dir = _get_current_dir()
    marker_names = tuple(markers) if markers is not None else _PROJECT_MARKERS

    project_root = _find_project_root(caller_dir, marker_names)
    if project_root is None:
        raise RuntimeError(
            f"Unable to locate project root from {caller_dir} using markers {marker_names}."
        )

    return project_root

def get_project_dir() -> FileAPI:
    path = str(_get_project_dir().resolve())
    return FileAPI(path)

def _get_data_dir(src_dir_path: str = "src", data_dir_path: str = "data") -> Path:
    """Return the data directory mirroring the caller's path under the src tree."""

    project_dir = _get_project_dir()
    caller_dir = _get_current_dir()

    src_dir = project_dir / src_dir_path
    try:
        relative_path = caller_dir.resolve().relative_to(src_dir.resolve())
    except ValueError as exc:
        raise RuntimeError(
            f"Caller directory {caller_dir} is not located within the src tree {src_dir}."
        ) from exc

    return (project_dir / data_dir_path / relative_path).resolve()

def get_data_dir() -> FileAPI:
    path = str(_get_data_dir().resolve())
    return FileAPI(path)

def _find_project_root(start_path: Path, markers: Iterable[str]) -> Optional[Path]:
    """Return the project root directory by searching upwards from the given start path."""
    current = start_path.resolve()

    while True:
        if any((current / marker).exists() for marker in markers):
            return current

        parent = current.parent
        if parent == current:
            return None

        current = parent
