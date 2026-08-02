#!/usr/bin/env python3
from __future__ import annotations

import builtins
import os
import ntpath
import stat as stat_module
from pathlib import Path
from typing import Callable, Iterator

WINDOWS_MAX_PATH = 260
_EXTENDED_PREFIX = "\\\\?\\"
_EXTENDED_UNC_PREFIX = "\\\\?\\UNC\\"


def strip_extended_prefix(value: str | os.PathLike[str]) -> str:
    """Return a normal Windows path for display, database storage and URLs."""
    raw = os.fspath(value)
    if raw.startswith(_EXTENDED_UNC_PREFIX):
        return "\\\\" + raw[len(_EXTENDED_UNC_PREFIX) :]
    if raw.startswith(_EXTENDED_PREFIX):
        return raw[len(_EXTENDED_PREFIX) :]
    return raw


def windows_extended_path(
    value: str | os.PathLike[str],
    *,
    platform: str | None = None,
) -> str:
    """Return a Win32 extended-length path for filesystem I/O.

    The original, non-prefixed path remains the canonical value stored in
    SQLite and exposed to the browser. Only calls that touch the filesystem use
    this representation. ``platform`` exists so the conversion can be tested on
    non-Windows build hosts.
    """
    raw = os.fspath(value)
    target_platform = os.name if platform is None else platform
    if target_platform != "nt":
        return raw
    if raw.startswith(_EXTENDED_PREFIX):
        return raw

    absolute = (ntpath.normpath(raw) if ntpath.isabs(raw) else ntpath.abspath(raw)).replace("/", "\\")
    if absolute.startswith("\\\\"):
        return _EXTENDED_UNC_PREFIX + absolute[2:]
    if len(absolute) >= 3 and absolute[1:3] == ":\\":
        return _EXTENDED_PREFIX + absolute
    return absolute


def io_path(value: str | os.PathLike[str]) -> str:
    return windows_extended_path(value)


def display_path(value: str | os.PathLike[str]) -> str:
    return strip_extended_prefix(value)


def path_length(value: str | os.PathLike[str]) -> int:
    """Length of the user-visible absolute path, excluding the Win32 prefix."""
    raw = strip_extended_prefix(value)
    if os.name == "nt":
        absolute = ntpath.normpath(raw) if ntpath.isabs(raw) else ntpath.abspath(raw)
    else:
        absolute = os.path.abspath(raw)
    return len(absolute)


def is_long_path(value: str | os.PathLike[str]) -> bool:
    return path_length(value) >= WINDOWS_MAX_PATH


def open_path(
    value: str | os.PathLike[str],
    mode: str = "r",
    *args,
    **kwargs,
):
    return builtins.open(io_path(value), mode, *args, **kwargs)


def stat_path(value: str | os.PathLike[str]):
    return os.stat(io_path(value))


def exists_path(value: str | os.PathLike[str]) -> bool:
    try:
        stat_path(value)
        return True
    except (FileNotFoundError, NotADirectoryError, OSError):
        return False


def is_file_path(value: str | os.PathLike[str]) -> bool:
    try:
        return stat_module.S_ISREG(stat_path(value).st_mode)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return False


def is_dir_path(value: str | os.PathLike[str]) -> bool:
    try:
        return stat_module.S_ISDIR(stat_path(value).st_mode)
    except (FileNotFoundError, NotADirectoryError, OSError):
        return False


def mkdir_path(
    value: str | os.PathLike[str],
    *,
    parents: bool = False,
    exist_ok: bool = False,
) -> None:
    target = io_path(value)
    if parents:
        os.makedirs(target, exist_ok=exist_ok)
    else:
        try:
            os.mkdir(target)
        except FileExistsError:
            if not exist_ok:
                raise


def read_bytes_path(value: str | os.PathLike[str]) -> bytes:
    with open_path(value, "rb") as file:
        return file.read()


def write_bytes_path(value: str | os.PathLike[str], data: bytes) -> int:
    with open_path(value, "wb") as file:
        return file.write(data)


def unlink_path(value: str | os.PathLike[str], *, missing_ok: bool = False) -> None:
    try:
        os.unlink(io_path(value))
    except FileNotFoundError:
        if not missing_ok:
            raise


def walk_path(
    root: str | os.PathLike[str],
    *,
    onerror: Callable[[OSError], None] | None = None,
) -> Iterator[tuple[str, list[str], list[str]]]:
    """A non-symlink-following ``os.walk`` equivalent using long-path I/O.

    Yielded paths never contain ``\\?\\`` so database keys and diagnostics stay
    compatible with existing v2.7.x records.
    """
    raw_root = strip_extended_prefix(root)
    if os.name == "nt":
        absolute_root = ntpath.normpath(raw_root) if ntpath.isabs(raw_root) else ntpath.abspath(raw_root)
    else:
        absolute_root = os.path.abspath(raw_root)
    logical_root = Path(absolute_root)
    pending = [logical_root]
    while pending:
        directory = pending.pop()
        dirnames: list[str] = []
        filenames: list[str] = []
        try:
            with os.scandir(io_path(directory)) as entries:
                for entry in entries:
                    try:
                        if entry.is_dir(follow_symlinks=False):
                            dirnames.append(entry.name)
                        else:
                            # Match os.walk(followlinks=False): directory symlinks
                            # are not traversed, while file-like entries remain visible.
                            filenames.append(entry.name)
                    except OSError as exc:
                        if onerror is not None:
                            onerror(exc)
        except OSError as exc:
            if onerror is not None:
                onerror(exc)
            continue

        dirnames.sort(key=str.casefold)
        filenames.sort(key=str.casefold)
        yield str(directory), dirnames, filenames
        for name in reversed(dirnames):
            pending.append(directory / name)
