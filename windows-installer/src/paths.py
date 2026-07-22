#!/usr/bin/env python3
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_ID = "MusicLibrary"
APP_VERSION = "2.6.2"


def resource_root() -> Path:
    """Return the read-only application resource directory."""
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        return Path(frozen_root).resolve()
    return Path(__file__).resolve().parent


def default_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / APP_ID
    return Path.home().resolve() / f".{APP_ID.casefold()}"


def configured_data_root() -> Path:
    value = os.environ.get("MUSIC_LIBRARY_DATA_DIR", "").strip()
    return Path(value).expanduser().resolve() if value else default_data_root()


def configured_music_root() -> Path:
    value = os.environ.get("MUSIC_LIBRARY_MUSIC_DIR", "").strip()
    if not value:
        raise RuntimeError("MUSIC_LIBRARY_MUSIC_DIR is not configured")
    return Path(value).expanduser().resolve()


RESOURCE_ROOT = resource_root()
DATA_ROOT = configured_data_root()
MUSIC_ROOT = configured_music_root()
ARTWORK_CACHE = DATA_ROOT / ".artwork-cache"
BACKUP_DIR = DATA_ROOT / "Backups"
EXPORT_DIR = DATA_ROOT / "Exports"
LOG_DIR = DATA_ROOT / "Logs"


def ensure_data_directories() -> None:
    for path in (DATA_ROOT, ARTWORK_CACHE, BACKUP_DIR, EXPORT_DIR, LOG_DIR):
        path.mkdir(parents=True, exist_ok=True)


def is_within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def media_relative_path(path: Path) -> str:
    """Map a physical media/cache path to a browser-visible virtual path."""
    resolved = path.resolve()
    music = MUSIC_ROOT.resolve()
    data = DATA_ROOT.resolve()
    if is_within(resolved, music):
        relative = resolved.relative_to(music).as_posix()
        return f"Music/{relative}" if relative else "Music"
    if is_within(resolved, data):
        return resolved.relative_to(data).as_posix()
    raise ValueError(f"Path is outside configured roots: {resolved}")


def resolve_virtual_path(virtual_path: str) -> Path | None:
    """Resolve a browser-visible path without allowing traversal."""
    normalized = virtual_path.replace("\\", "/").lstrip("/")
    if not normalized:
        return None

    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None

    if parts[0].casefold() == "music":
        candidate = MUSIC_ROOT.joinpath(*parts[1:]).resolve()
        return candidate if is_within(candidate, MUSIC_ROOT) else None

    if parts[0].casefold() == ".artwork-cache":
        candidate = ARTWORK_CACHE.joinpath(*parts[1:]).resolve()
        return candidate if is_within(candidate, ARTWORK_CACHE) else None

    candidate = RESOURCE_ROOT.joinpath(*parts).resolve()
    return candidate if is_within(candidate, RESOURCE_ROOT) else None
