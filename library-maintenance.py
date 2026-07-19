#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from database import (
    DATABASE_PATH,
    database,
    database_stats,
    get_available_tracks,
    initialize_database,
    manual_backup,
)


def command_stats() -> int:
    with database() as connection:
        initialize_database(connection)
        print(json.dumps(database_stats(connection), ensure_ascii=False, indent=2))
    return 0


def command_check() -> int:
    if not DATABASE_PATH.exists():
        print("library.db がまだありません。先に start-music-library.bat を実行してください。")
        return 1
    with sqlite3.connect(DATABASE_PATH) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()[0]
    print(f"SQLite integrity_check: {result}")
    return 0 if result == "ok" else 2


def command_backup() -> int:
    destination = manual_backup()
    print(f"バックアップを作成しました: {destination}")
    return 0


def command_vacuum() -> int:
    if not DATABASE_PATH.exists():
        print("library.db がまだありません。先に start-music-library.bat を実行してください。")
        return 1
    with sqlite3.connect(DATABASE_PATH, timeout=30) as connection:
        connection.execute("PRAGMA busy_timeout = 30000")
        connection.execute("VACUUM")
    print("SQLiteの最適化が完了しました。")
    return 0



def command_export() -> int:
    if not DATABASE_PATH.exists():
        print("library.db がまだありません。先に start-music-library.bat を実行してください。")
        return 1
    with database() as connection:
        initialize_database(connection)
        tracks = get_available_tracks(connection)
    export_dir = DATABASE_PATH.parent / "Exports"
    export_dir.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    destination = export_dir / f"music-library-data-{stamp}.json"
    destination.write_text(
        json.dumps(tracks, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    print(f"JSONエクスポートを作成しました: {destination}")
    print(f"曲数: {len(tracks):,}")
    return 0

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Music Library SQLite maintenance tool")
    parser.add_argument("command", choices=("stats", "check", "backup", "vacuum", "export"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    return {
        "stats": command_stats,
        "check": command_check,
        "backup": command_backup,
        "vacuum": command_vacuum,
        "export": command_export,
    }[args.command]()


if __name__ == "__main__":
    raise SystemExit(main())
