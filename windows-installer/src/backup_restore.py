#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from paths import BACKUP_DIR, DATA_ROOT

DATABASE_FILENAME = "library.db"
RESTORE_REQUEST_FILENAME = "restore-request.json"
RESTORE_STATUS_FILENAME = "restore-status.json"
SUPPORTED_SCHEMA_VERSIONS = frozenset({5, 6, 7})
BACKUP_NAME_PATTERN = re.compile(r"^library-[A-Za-z0-9._-]+\.db$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


def _schema_version(connection: sqlite3.Connection) -> int:
    if not _table_exists(connection, "schema_info"):
        return 0
    row = connection.execute(
        "SELECT value FROM schema_info WHERE key='schema_version'"
    ).fetchone()
    try:
        return int(row[0]) if row else 0
    except (TypeError, ValueError):
        return 0


def _count_rows(connection: sqlite3.Connection, table: str) -> int:
    if not _table_exists(connection, table):
        return 0
    return int(connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0])


def inspect_database(path: Path) -> dict[str, Any]:
    resolved = Path(path)
    result: dict[str, Any] = {
        "exists": resolved.is_file(),
        "valid": False,
        "quickCheck": "missing",
        "schemaVersion": 0,
        "trackCount": 0,
        "userCount": 0,
        "error": "",
    }
    if not resolved.is_file() or resolved.stat().st_size <= 0:
        result["error"] = "ファイルが存在しないか、空です。"
        return result

    connection: sqlite3.Connection | None = None
    try:
        connection = sqlite3.connect(f"file:{resolved.as_posix()}?mode=ro", uri=True, timeout=15.0)
        quick = connection.execute("PRAGMA quick_check").fetchone()
        quick_text = str(quick[0] if quick else "unknown")
        schema = _schema_version(connection)
        result.update(
            {
                "quickCheck": quick_text,
                "schemaVersion": schema,
                "trackCount": _count_rows(connection, "tracks"),
                "userCount": _count_rows(connection, "users"),
                "valid": quick_text.casefold() == "ok" and schema in SUPPORTED_SCHEMA_VERSIONS,
            }
        )
        if quick_text.casefold() != "ok":
            result["error"] = f"SQLite整合性検査: {quick_text}"
        elif schema not in SUPPORTED_SCHEMA_VERSIONS:
            result["error"] = f"対応外のDBスキーマです: {schema}"
    except sqlite3.Error as exc:
        result["quickCheck"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        if connection is not None:
            connection.close()
    return result


def _backup_kind(name: str) -> str:
    lowered = name.casefold()
    if lowered.startswith("library-manual-"):
        return "manual"
    if lowered.startswith("library-pre-restore-"):
        return "pre_restore"
    if lowered.startswith("library-pre-owner-link-"):
        return "pre_owner_link"
    if lowered.startswith("library-pre-v2.7.0-"):
        return "pre_migration"
    if re.fullmatch(r"library-\d{8}\.db", lowered):
        return "daily"
    return "other"


def _safe_backup_path(name: str, backup_dir: Path = BACKUP_DIR) -> Path:
    text = str(name or "").strip()
    if not BACKUP_NAME_PATTERN.fullmatch(text):
        raise ValueError("バックアップ名が不正です。")
    candidate = (Path(backup_dir) / text).resolve()
    root = Path(backup_dir).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("バックアップ保存先の外は指定できません。") from exc
    return candidate


def _backup_item(path: Path, *, include_inspection: bool = True) -> dict[str, Any]:
    stat = path.stat()
    inspection = inspect_database(path) if include_inspection else {}
    return {
        "name": path.name,
        "kind": _backup_kind(path.name),
        "sizeBytes": int(stat.st_size),
        "modifiedAt": datetime.fromtimestamp(stat.st_mtime, timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        **inspection,
    }


def list_backups(backup_dir: Path = BACKUP_DIR) -> list[dict[str, Any]]:
    root = Path(backup_dir)
    root.mkdir(parents=True, exist_ok=True)
    paths = [path for path in root.glob("library-*.db") if path.is_file()]
    paths.sort(key=lambda path: (path.stat().st_mtime_ns, path.name), reverse=True)
    return [_backup_item(path) for path in paths]


def create_manual_backup(
    *,
    database_path: Path | None = None,
    backup_dir: Path = BACKUP_DIR,
) -> dict[str, Any]:
    source_path = Path(database_path or (DATA_ROOT / DATABASE_FILENAME))
    if not source_path.is_file():
        raise FileNotFoundError("library.db が見つかりません。")

    root = Path(backup_dir)
    root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = root / f"library-manual-{stamp}.db"
    sequence = 1
    while destination.exists():
        destination = root / f"library-manual-{stamp}-{sequence:02d}.db"
        sequence += 1

    source = sqlite3.connect(source_path, timeout=30.0)
    target = sqlite3.connect(destination, timeout=30.0)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()

    item = _backup_item(destination)
    if not bool(item.get("valid")):
        try:
            destination.unlink()
        except OSError:
            pass
        raise RuntimeError(f"作成したバックアップの検証に失敗しました: {item.get('error')}")
    return item


def pending_restore(data_root: Path = DATA_ROOT) -> dict[str, Any] | None:
    request_path = Path(data_root) / RESTORE_REQUEST_FILENAME
    value = _read_json(request_path)
    if not value:
        return None
    name = str(value.get("backupName") or "")
    return {
        "backupName": name,
        "requestedAt": str(value.get("requestedAt") or ""),
    }


def restore_status(data_root: Path = DATA_ROOT) -> dict[str, Any] | None:
    value = _read_json(Path(data_root) / RESTORE_STATUS_FILENAME)
    return value or None


def schedule_restore(
    backup_name: str,
    *,
    data_root: Path = DATA_ROOT,
    backup_dir: Path = BACKUP_DIR,
) -> dict[str, Any]:
    backup_path = _safe_backup_path(backup_name, backup_dir)
    if not backup_path.is_file():
        raise FileNotFoundError("選択したバックアップが見つかりません。")
    inspection = inspect_database(backup_path)
    if not bool(inspection.get("valid")):
        raise ValueError(f"復元できないバックアップです: {inspection.get('error')}")

    request = {
        "formatVersion": 1,
        "backupName": backup_path.name,
        "requestedAt": _utc_now_iso(),
        "schemaVersion": inspection["schemaVersion"],
        "trackCount": inspection["trackCount"],
    }
    _atomic_write_json(Path(data_root) / RESTORE_REQUEST_FILENAME, request)
    return request


def cancel_restore(data_root: Path = DATA_ROOT) -> bool:
    request_path = Path(data_root) / RESTORE_REQUEST_FILENAME
    try:
        request_path.unlink()
        return True
    except FileNotFoundError:
        return False


def _next_pre_restore_path(backup_dir: Path) -> Path:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = backup_dir / f"library-pre-restore-{stamp}.db"
    number = 1
    while candidate.exists():
        candidate = backup_dir / f"library-pre-restore-{stamp}-{number:02d}.db"
        number += 1
    return candidate


def _sqlite_backup(source_path: Path, destination_path: Path) -> None:
    source = sqlite3.connect(source_path, timeout=30.0)
    target = sqlite3.connect(destination_path, timeout=30.0)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()


def apply_pending_restore(data_root: Path) -> dict[str, Any] | None:
    root = Path(data_root).expanduser().resolve()
    request_path = root / RESTORE_REQUEST_FILENAME
    request = _read_json(request_path)
    if not request:
        return None

    backup_dir = root / "Backups"
    database_path = root / DATABASE_FILENAME
    status_path = root / RESTORE_STATUS_FILENAME
    started_at = _utc_now_iso()
    backup_name = str(request.get("backupName") or "")
    try:
        selected = _safe_backup_path(backup_name, backup_dir)
        if not selected.is_file():
            raise FileNotFoundError("復元対象のバックアップが見つかりません。")
        selected_inspection = inspect_database(selected)
        if not bool(selected_inspection.get("valid")):
            raise ValueError(f"復元対象が無効です: {selected_inspection.get('error')}")

        backup_dir.mkdir(parents=True, exist_ok=True)
        pre_restore_path: Path | None = None
        if database_path.is_file():
            pre_restore_path = _next_pre_restore_path(backup_dir)
            _sqlite_backup(database_path, pre_restore_path)
            pre_inspection = inspect_database(pre_restore_path)
            if not bool(pre_inspection.get("valid")):
                raise RuntimeError("復元前バックアップの検証に失敗しました。")

        temp_path = root / "library.restore.tmp.db"
        for candidate in (temp_path, Path(str(temp_path) + "-wal"), Path(str(temp_path) + "-shm")):
            try:
                candidate.unlink()
            except FileNotFoundError:
                pass
        _sqlite_backup(selected, temp_path)
        temp_inspection = inspect_database(temp_path)
        if not bool(temp_inspection.get("valid")):
            raise RuntimeError("復元用DBの検証に失敗しました。")

        for suffix in ("-wal", "-shm"):
            try:
                Path(str(database_path) + suffix).unlink()
            except FileNotFoundError:
                pass
        os.replace(temp_path, database_path)

        restored_inspection = inspect_database(database_path)
        if not bool(restored_inspection.get("valid")):
            raise RuntimeError("復元後DBの検証に失敗しました。")

        status = {
            "state": "restored",
            "backupName": selected.name,
            "preRestoreBackupName": pre_restore_path.name if pre_restore_path else "",
            "requestedAt": str(request.get("requestedAt") or ""),
            "startedAt": started_at,
            "finishedAt": _utc_now_iso(),
            "trackCount": restored_inspection["trackCount"],
            "schemaVersion": restored_inspection["schemaVersion"],
        }
        _atomic_write_json(status_path, status)
        request_path.unlink(missing_ok=True)
        return status
    except Exception as exc:
        rolled_back = False
        rollback_error = ""
        try:
            pre_restore_name = locals().get("pre_restore_path")
            if isinstance(pre_restore_name, Path) and pre_restore_name.is_file():
                rollback_temp = root / "library.rollback.tmp.db"
                try:
                    rollback_temp.unlink()
                except FileNotFoundError:
                    pass
                _sqlite_backup(pre_restore_name, rollback_temp)
                rollback_inspection = inspect_database(rollback_temp)
                if bool(rollback_inspection.get("valid")):
                    for suffix in ("-wal", "-shm"):
                        try:
                            Path(str(database_path) + suffix).unlink()
                        except FileNotFoundError:
                            pass
                    os.replace(rollback_temp, database_path)
                    rolled_back = True
                else:
                    rollback_error = str(rollback_inspection.get("error") or "rollback validation failed")
        except Exception as rollback_exc:
            rollback_error = f"{type(rollback_exc).__name__}: {rollback_exc}"

        status = {
            "state": "error",
            "backupName": backup_name,
            "requestedAt": str(request.get("requestedAt") or ""),
            "startedAt": started_at,
            "finishedAt": _utc_now_iso(),
            "error": f"{type(exc).__name__}: {exc}",
            "rolledBack": rolled_back,
            "rollbackError": rollback_error,
        }
        _atomic_write_json(status_path, status)
        request_path.unlink(missing_ok=True)
        return status
