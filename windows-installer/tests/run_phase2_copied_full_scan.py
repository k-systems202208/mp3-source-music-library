from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from long_paths import path_length, stat_path, walk_path  # noqa: E402

STATE_TABLES = ("users", "user_identities", "user_track_state", "user_preferences")
COPY_FILES = (
    "config.json",
    "legacy-library-data.json",
    "library-diagnostics.json",
    "library-diagnostics.csv",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a full v2.7.4 scan against a copied MusicLibrary database"
    )
    parser.add_argument("--data-root", default="", help="Live MusicLibrary data root")
    parser.add_argument("--music-root", default="", help="Music directory override")
    parser.add_argument("--output-root", default=str(ROOT / "PHASE2_OUTPUT"))
    parser.add_argument(
        "--expected-added",
        type=int,
        default=-1,
        help="Optional exact number of newly available tracks",
    )
    parser.add_argument(
        "--skip-artwork-copy",
        action="store_true",
        help="Do not copy the live embedded-artwork cache (test use only)",
    )
    return parser.parse_args()


def default_data_root() -> Path:
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "MusicLibrary"
    return Path.home() / ".musiclibrary"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        return {}
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def table_digest(connection: sqlite3.Connection, table: str) -> dict[str, Any]:
    if not table_exists(connection, table):
        return {"exists": False, "rows": 0, "sha256": ""}
    columns = [
        str(row[1])
        for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    ]
    quoted = ", ".join(f'"{name}"' for name in columns)
    order = ", ".join(f'"{name}"' for name in columns)
    rows = connection.execute(
        f'SELECT {quoted} FROM "{table}" ORDER BY {order}'
    ).fetchall()
    payload = json.dumps(
        [list(row) for row in rows],
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return {
        "exists": True,
        "rows": len(rows),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def database_snapshot(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()
        quick_value = str(quick[0]) if quick else ""
        available = int(
            connection.execute(
                "SELECT COUNT(*) FROM tracks WHERE is_available=1"
            ).fetchone()[0]
        )
        total = int(connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0])
        track_ids = {
            str(row[0])
            for row in connection.execute("SELECT id FROM tracks").fetchall()
        }
        return {
            "quickCheck": quick_value,
            "availableTracks": available,
            "totalTracks": total,
            "trackIds": track_ids,
            "stateTables": {
                table: table_digest(connection, table) for table in STATE_TABLES
            },
        }
    finally:
        connection.close()


def backup_sqlite(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(source, timeout=30.0)
    dst = sqlite3.connect(destination, timeout=30.0)
    try:
        src.backup(dst)
        dst.commit()
    finally:
        dst.close()
        src.close()


def discover_mp3s(music_root: Path) -> tuple[list[Path], list[dict[str, str]]]:
    files: list[Path] = []
    errors: list[dict[str, str]] = []

    def onerror(exc: OSError) -> None:
        errors.append(
            {
                "path": str(getattr(exc, "filename", "") or ""),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )

    for directory, _, filenames in walk_path(music_root, onerror=onerror):
        base = Path(directory)
        for name in filenames:
            path = base / name
            if path.suffix.casefold() == ".mp3":
                files.append(path)
    files.sort(key=lambda value: str(value).casefold())
    return files, errors


def music_fingerprint(files: Iterable[Path], music_root: Path) -> str:
    digest = hashlib.sha256()
    for path in files:
        info = stat_path(path)
        relative = path.relative_to(music_root).as_posix()
        digest.update(relative.encode("utf-8", errors="surrogatepass"))
        digest.update(b"\0")
        digest.update(str(int(info.st_size)).encode("ascii"))
        digest.update(b"\0")
        digest.update(str(int(info.st_mtime_ns)).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def previous_error_paths(data_root: Path) -> set[str]:
    payload = load_json(data_root / "library-diagnostics.json")
    found: set[str] = set()
    for item in payload.get("diagnostics", []):
        if not isinstance(item, dict) or item.get("category") != "mp3_read_error":
            continue
        value = str(item.get("path") or "").replace("\\", "/").lstrip("/")
        if value.casefold().startswith("music/"):
            found.add(value)
    return found


def copy_regular_files(live_root: Path, copied_root: Path) -> None:
    for name in COPY_FILES:
        source = live_root / name
        if source.is_file():
            destination = copied_root / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)


def referenced_embedded_artwork(database_path: Path) -> list[str]:
    connection = sqlite3.connect(database_path, timeout=30.0)
    try:
        rows = connection.execute(
            """
            SELECT DISTINCT aw.relative_path
              FROM tracks AS t
              JOIN artworks AS aw ON aw.id=t.artwork_id
             WHERE t.is_available=1
               AND aw.source_type='embedded'
               AND aw.relative_path <> ''
            """
        ).fetchall()
        return sorted({str(row[0]) for row in rows}, key=str.casefold)
    finally:
        connection.close()


def copy_artwork_cache(live_root: Path, copied_root: Path, database_path: Path) -> dict[str, int]:
    paths = referenced_embedded_artwork(database_path)
    copied = 0
    missing = 0
    for index, relative in enumerate(paths, 1):
        source = live_root / Path(relative)
        destination = copied_root / Path(relative)
        if not source.is_file():
            missing += 1
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied += 1
        if index % 500 == 0 or index == len(paths):
            print(f"  Artwork cache: {index:,} / {len(paths):,}", flush=True)
    return {"referenced": len(paths), "copied": copied, "missing": missing}


def stream_subprocess(command: list[str], *, env: dict[str, str], log_path: Path) -> int:
    with log_path.open("w", encoding="utf-8", newline="\n") as log:
        process = subprocess.Popen(
            command,
            cwd=str(ROOT),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line)
        return process.wait()


def latest_scan(database_path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(database_path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return {}
        value = dict(row)
        try:
            value["details"] = json.loads(str(value.get("details_json") or "{}"))
        except json.JSONDecodeError:
            value["details"] = {}
        error_count = int(
            connection.execute(
                "SELECT COUNT(*) FROM scan_errors WHERE scan_run_id=? AND severity='error'",
                (row["id"],),
            ).fetchone()[0]
        )
        value["errorRows"] = error_count
        return value
    finally:
        connection.close()


def available_paths(database_path: Path) -> set[str]:
    connection = sqlite3.connect(database_path, timeout=30.0)
    try:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT relative_path FROM tracks WHERE is_available=1"
            ).fetchall()
        }
    finally:
        connection.close()


def playback_sample_rows(database_path: Path, music_root: Path) -> list[dict[str, Any]]:
    connection = sqlite3.connect(database_path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    try:
        candidates: list[dict[str, Any]] = []
        for row in connection.execute(
            "SELECT id, title, relative_path FROM tracks WHERE is_available=1"
        ).fetchall():
            relative = str(row["relative_path"])
            if not relative.casefold().startswith("music/"):
                continue
            physical = music_root / Path(relative[6:])
            length = path_length(physical)
            if length < 260:
                continue
            candidates.append(
                {
                    "id": str(row["id"]),
                    "title": str(row["title"]),
                    "relativePath": relative,
                    "absolutePathLength": length,
                    "fileSize": int(stat_path(physical).st_size),
                }
            )
        candidates.sort(key=lambda item: int(item["absolutePathLength"]))
        if not candidates:
            return []
        indexes = sorted({0, len(candidates) // 2, len(candidates) - 1})
        return [candidates[index] for index in indexes]
    finally:
        connection.close()


def verify_http_ranges(copied_data: Path, music_root: Path, samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not samples:
        raise RuntimeError("No long-path playback samples were found in the copied database")

    os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(copied_data)
    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)
    import server  # noqa: E402

    httpd = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret="phase2-long-path-check-secret-0123456789abcdef",
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    results: list[dict[str, Any]] = []
    try:
        base = f"http://127.0.0.1:{httpd.server_address[1]}"
        with urllib.request.urlopen(f"{base}/api/stats", timeout=20) as response:
            stats = json.loads(response.read().decode("utf-8"))
            if int(stats.get("availableTracks", -1)) <= 0:
                raise RuntimeError(f"/api/stats returned an invalid count: {stats}")

        for sample in samples:
            size = int(sample["fileSize"])
            starts = [0, max(0, size // 2)]
            checked_ranges: list[str] = []
            encoded = urllib.parse.quote(str(sample["relativePath"]), safe="/")
            for start in starts:
                end = min(size - 1, start + 1023)
                request = urllib.request.Request(
                    f"{base}/{encoded}",
                    headers={"Range": f"bytes={start}-{end}"},
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    body = response.read()
                    expected = end - start + 1
                    if response.status != 206 or len(body) != expected:
                        raise RuntimeError(
                            f"Range playback failed for {sample['relativePath']}: "
                            f"status={response.status} bytes={len(body)} expected={expected}"
                        )
                    if response.headers.get("Accept-Ranges", "").casefold() != "bytes":
                        raise RuntimeError("Accept-Ranges: bytes was not returned")
                    checked_ranges.append(f"{start}-{end}")
            results.append({**sample, "ranges": checked_ranges, "status": "passed"})
    finally:
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=10)
    return results


def write_outputs(output_dir: Path, result: dict[str, Any]) -> None:
    (output_dir / "PHASE2_COPIED_SCAN_RESULT.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    summary = result["summary"]
    lines = [
        "Music Library v2.7.4 Phase 2 Copied Full Scan",
        "=================================================",
        f"Live available tracks       : {summary['liveAvailableTracks']:,}",
        f"MP3 files discovered        : {summary['mp3FilesDiscovered']:,}",
        f"Copied DB available tracks  : {summary['copiedAvailableTracks']:,}",
        f"Newly available tracks      : {summary['newlyAvailableTracks']:,}",
        f"Long MP3 paths              : {summary['longPathFiles']:,}",
        f"Long paths loaded           : {summary['longPathsLoaded']:,}",
        f"Long path errors            : {summary['longPathErrors']:,}",
        f"Previous read errors        : {summary['previousReadErrors']:,}",
        f"Previous errors resolved    : {summary['previousErrorsResolved']:,}",
        f"Maximum path length         : {summary['maximumPathLength']:,}",
        f"Scan errors                 : {summary['scanErrors']:,}",
        f"User state preserved        : {'Yes' if summary['userStatePreserved'] else 'No'}",
        f"Existing track IDs preserved: {'Yes' if summary['existingTrackIdsPreserved'] else 'No'}",
        f"HTTP range samples passed   : {summary['httpRangeSamplesPassed']:,}",
        f"Live DB modified            : {'No' if summary['liveDatabaseUnchanged'] else 'YES'}",
        f"Music files modified        : {'No' if summary['musicFilesUnchanged'] else 'YES'}",
        f"Copied data                 : {summary['copiedDataRoot']}",
        f"Detailed report             : {output_dir}",
        "",
        "Playback samples:",
    ]
    for sample in result.get("playbackSamples", []):
        lines.append(
            f"- {sample['title']} | {sample['absolutePathLength']} chars | "
            f"ranges {', '.join(sample['ranges'])}"
        )
    lines.extend(
        [
            "",
            "This test used a copied SQLite database.",
            "The live database and MP3 files were not written by this workflow.",
        ]
    )
    (output_dir / "PHASE2_COPIED_SCAN_SUMMARY.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    (output_dir / "PHASE2_PLAYBACK_SAMPLES.txt").write_text(
        "\n".join(
            f"{item['title']}\t{item['relativePath']}" for item in result.get("playbackSamples", [])
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    args = parse_args()
    live_data = Path(args.data_root).expanduser() if args.data_root else default_data_root()
    config = load_json(live_data / "config.json")
    music_value = args.music_root or str(config.get("musicRoot") or "")
    if not music_value:
        print(f"ERROR: musicRoot was not found in {live_data / 'config.json'}")
        return 2
    music_root = Path(music_value).expanduser()
    live_db = live_data / "library.db"
    if not live_db.is_file():
        print(f"ERROR: live database was not found: {live_db}")
        return 2

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_root) / timestamp
    copied_data = output_dir / "data"
    copied_data.mkdir(parents=True, exist_ok=False)

    print("Preparing a copied database full-scan test...")
    print(f"Live data  : {live_data}")
    print(f"Music root : {music_root}")
    print(f"Output     : {output_dir}")

    live_hash_before = sha256_file(live_db)
    live_snapshot = database_snapshot(live_db)
    if live_snapshot["quickCheck"].casefold() != "ok":
        raise RuntimeError(f"Live database quick_check failed: {live_snapshot['quickCheck']}")

    print("Discovering MP3 files without modifying them...")
    mp3_before, discovery_errors = discover_mp3s(music_root)
    if discovery_errors:
        raise RuntimeError(f"Music traversal errors were found: {discovery_errors[:3]}")
    fingerprint_before = music_fingerprint(mp3_before, music_root)
    long_files = [path for path in mp3_before if path_length(path) >= 260]
    max_length = max((path_length(path) for path in mp3_before), default=0)
    old_errors = previous_error_paths(live_data)

    print("Copying live SQLite database with the SQLite backup API...")
    copied_db = copied_data / "library.db"
    backup_sqlite(live_db, copied_db)
    copy_regular_files(live_data, copied_data)

    artwork_copy = {"referenced": 0, "copied": 0, "missing": 0}
    if not args.skip_artwork_copy:
        print("Copying the referenced embedded-artwork cache...")
        artwork_copy = copy_artwork_cache(live_data, copied_data, copied_db)

    copied_before = database_snapshot(copied_db)
    if copied_before["quickCheck"].casefold() != "ok":
        raise RuntimeError("Copied database quick_check failed before scan")
    if copied_before["stateTables"] != live_snapshot["stateTables"]:
        raise RuntimeError("User state differs immediately after SQLite backup")

    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["MUSIC_LIBRARY_DATA_DIR"] = str(copied_data)
    env["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)
    print("Running the complete library scan against the copied database...")
    return_code = stream_subprocess(
        [sys.executable, str(SRC / "generator.py")],
        env=env,
        log_path=output_dir / "PHASE2_FULL_SCAN_LOG.txt",
    )
    if return_code != 0:
        raise RuntimeError(f"Copied full scan failed with exit code {return_code}")

    copied_after = database_snapshot(copied_db)
    scan = latest_scan(copied_db)
    details = dict(scan.get("details") or {})
    available = available_paths(copied_db)
    expected_paths = {"Music/" + path.relative_to(music_root).as_posix() for path in mp3_before}
    long_expected = {"Music/" + path.relative_to(music_root).as_posix() for path in long_files}
    unresolved = sorted(old_errors - available)
    missing_all = sorted(expected_paths - available)

    state_preserved = copied_after["stateTables"] == live_snapshot["stateTables"]
    ids_preserved = live_snapshot["trackIds"].issubset(copied_after["trackIds"])
    copied_available = int(copied_after["availableTracks"])
    newly_available = copied_available - int(live_snapshot["availableTracks"])

    samples = playback_sample_rows(copied_db, music_root)
    playback_results = verify_http_ranges(copied_data, music_root, samples)

    mp3_after, discovery_errors_after = discover_mp3s(music_root)
    fingerprint_after = music_fingerprint(mp3_after, music_root)
    live_hash_after = sha256_file(live_db)

    checks = {
        "scanStatusCompleted": str(scan.get("status")) == "completed",
        "scanErrorsZero": int(scan.get("errors", -1)) == 0 and int(scan.get("errorRows", 0)) == 0,
        "allDiscoveredAvailable": not missing_all and copied_available == len(mp3_before),
        "allLongPathsAvailable": long_expected.issubset(available),
        "longPathCountsMatch": int(details.get("longPathFiles", -1)) == len(long_files)
        and int(details.get("longPathLoaded", -1)) == len(long_files)
        and int(details.get("longPathErrors", -1)) == 0,
        "previousErrorsResolved": not unresolved,
        "userStatePreserved": state_preserved,
        "existingTrackIdsPreserved": ids_preserved,
        "liveDatabaseUnchanged": live_hash_before == live_hash_after,
        "musicFilesUnchanged": fingerprint_before == fingerprint_after
        and len(mp3_before) == len(mp3_after)
        and not discovery_errors_after,
        "httpRangePlaybackPassed": len(playback_results) == len(samples) and bool(samples),
    }
    if args.expected_added >= 0:
        checks["expectedAddedTracks"] = newly_available == args.expected_added

    result = {
        "summary": {
            "checkedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
            "liveDataRoot": str(live_data),
            "copiedDataRoot": str(copied_data),
            "musicRoot": str(music_root),
            "liveAvailableTracks": int(live_snapshot["availableTracks"]),
            "mp3FilesDiscovered": len(mp3_before),
            "copiedAvailableTracks": copied_available,
            "newlyAvailableTracks": newly_available,
            "longPathFiles": len(long_files),
            "longPathsLoaded": int(details.get("longPathLoaded", 0)),
            "longPathErrors": int(details.get("longPathErrors", 0)),
            "previousReadErrors": len(old_errors),
            "previousErrorsResolved": len(old_errors) - len(unresolved),
            "maximumPathLength": max_length,
            "scanErrors": int(scan.get("errors") or 0),
            "userStatePreserved": state_preserved,
            "existingTrackIdsPreserved": ids_preserved,
            "httpRangeSamplesPassed": len(playback_results),
            "liveDatabaseUnchanged": live_hash_before == live_hash_after,
            "musicFilesUnchanged": checks["musicFilesUnchanged"],
            "artworkCacheCopy": artwork_copy,
            "passed": all(checks.values()),
        },
        "checks": checks,
        "latestScan": scan,
        "unresolvedPreviousErrors": unresolved,
        "missingDiscoveredTracks": missing_all,
        "playbackSamples": playback_results,
        "liveStateTables": live_snapshot["stateTables"],
        "copiedStateTables": copied_after["stateTables"],
    }
    write_outputs(output_dir, result)

    print()
    print((output_dir / "PHASE2_COPIED_SCAN_SUMMARY.txt").read_text(encoding="utf-8"))
    if not result["summary"]["passed"]:
        print("COPIED FULL SCAN FAILED")
        return 1
    print("COPIED FULL SCAN PASSED")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Cancelled.")
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}")
        raise
