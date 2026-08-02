from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from long_paths import (  # noqa: E402
    is_long_path,
    open_path,
    path_length,
    stat_path,
    walk_path,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only Windows long-path probe")
    parser.add_argument("--data-root", default="", help="MusicLibrary data directory")
    parser.add_argument("--music-root", default="", help="Music directory override")
    parser.add_argument("--output-root", default=str(ROOT / "PHASE1_OUTPUT"))
    return parser.parse_args()


def default_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "MusicLibrary"
    return Path.home() / ".musiclibrary"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        return {}
    return value


def diagnostic_error_paths(data_root: Path) -> set[str]:
    payload = load_json(data_root / "library-diagnostics.json")
    values: set[str] = set()
    for item in payload.get("diagnostics", []):
        if not isinstance(item, dict) or item.get("category") != "mp3_read_error":
            continue
        value = str(item.get("path") or "").replace("\\", "/").lstrip("/")
        if value.casefold().startswith("music/"):
            values.add(value[6:])
    return values


def find_long_mp3_files(music_root: Path) -> tuple[list[Path], list[dict[str, str]]]:
    found: list[Path] = []
    scan_errors: list[dict[str, str]] = []

    def onerror(exc: OSError) -> None:
        scan_errors.append(
            {
                "path": str(getattr(exc, "filename", "") or ""),
                "error": f"{type(exc).__name__}: {exc}",
            }
        )

    for directory, _, filenames in walk_path(music_root, onerror=onerror):
        base = Path(directory)
        for name in filenames:
            path = base / name
            if path.suffix.casefold() == ".mp3" and is_long_path(path):
                found.append(path)
    found.sort(key=lambda value: str(value).casefold())
    return found, scan_errors


def probe_file(path: Path, music_root: Path, old_errors: set[str], generator: Any) -> dict[str, Any]:
    relative = path.relative_to(music_root).as_posix()
    result: dict[str, Any] = {
        "relativePath": relative,
        "absolutePathLength": path_length(path),
        "wasPreviousReadError": relative in old_errors,
        "fileSize": 0,
        "title": "",
        "metadataSource": "",
        "durationMs": 0,
        "parserNotes": [],
        "status": "failed",
        "error": "",
    }
    try:
        info = stat_path(path)
        result["fileSize"] = int(info.st_size)
        if info.st_size <= 0:
            raise RuntimeError("File is empty")

        # Exercise the same open/read/seek operations used by scanning and HTTP
        # byte-range playback without modifying the MP3.
        with open_path(path, "rb") as file:
            head = file.read(min(4096, info.st_size))
            if not head:
                raise RuntimeError("Could not read the beginning of the file")
            file.seek(max(0, info.st_size - min(4096, info.st_size)))
            tail = file.read()
            if not tail:
                raise RuntimeError("Could not read the end of the file")

        # Exercise the exact metadata path used by the patched generator.
        tags, _, duration, notes = generator.parse_with_mutagen(path)
        source = "mutagen"
        if not tags:
            fallback, _ = generator.parse_id3v2_fallback(path)
            tags.update(fallback)
            source = "fallback" if fallback else "filename"
        result["title"] = str(tags.get("TIT2") or path.stem)
        result["metadataSource"] = source
        result["durationMs"] = int(duration or generator.detect_audio_duration_ms_fallback(path))
        result["parserNotes"] = list(notes)

        # Exercise the head/tail hashing path used to recognize moved files.
        signature = generator.content_signature(path, int(info.st_size))
        if not signature:
            raise RuntimeError("Content signature was not generated")

        result["status"] = "passed"
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def main() -> int:
    args = parse_args()
    data_root = Path(args.data_root).expanduser() if args.data_root else default_data_root()
    config = load_json(data_root / "config.json")
    music_value = args.music_root or str(config.get("musicRoot") or "")
    if not music_value:
        print(f"ERROR: musicRoot was not found in {data_root / 'config.json'}")
        return 2

    music_root = Path(music_value).expanduser()
    os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(data_root)
    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)

    import generator  # noqa: E402

    old_errors = diagnostic_error_paths(data_root)
    print("Scanning for MP3 paths of 260 characters or more...")
    long_files, scan_errors = find_long_mp3_files(music_root)
    print(f"Long MP3 paths found   : {len(long_files):,}")
    print(f"Previous read errors   : {len(old_errors):,}")

    results: list[dict[str, Any]] = []
    for index, path in enumerate(long_files, 1):
        results.append(probe_file(path, music_root, old_errors, generator))
        if index % 25 == 0 or index == len(long_files):
            print(f"  {index:,} / {len(long_files):,}")

    passed = sum(item["status"] == "passed" for item in results)
    failed = len(results) - passed
    previous_targets = sum(bool(item["wasPreviousReadError"]) for item in results)
    previous_resolved = sum(
        item["status"] == "passed" and item["wasPreviousReadError"] for item in results
    )
    max_length = max((int(item["absolutePathLength"]) for item in results), default=0)

    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_root) / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "checkedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "dataRoot": str(data_root),
        "musicRoot": str(music_root),
        "longPathFiles": len(results),
        "passed": passed,
        "failed": failed,
        "previousReadErrors": len(old_errors),
        "previousErrorsFoundAmongLongPaths": previous_targets,
        "previousErrorsResolvedByProbe": previous_resolved,
        "maximumPathLength": max_length,
        "scanErrors": scan_errors,
        "readOnly": True,
    }
    (output_dir / "LONG_PATH_PROBE.json").write_text(
        json.dumps({"summary": summary, "files": results}, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    with (output_dir / "LONG_PATH_PROBE.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "status",
                "absolutePathLength",
                "wasPreviousReadError",
                "fileSize",
                "title",
                "metadataSource",
                "durationMs",
                "relativePath",
                "error",
            ],
        )
        writer.writeheader()
        for item in results:
            writer.writerow({key: item.get(key, "") for key in writer.fieldnames})

    lines = [
        "Music Library v2.7.4 Phase 1 Long Path Probe",
        "================================================",
        f"Long MP3 paths             : {len(results):,}",
        f"Readable and seekable      : {passed:,}",
        f"Failed                     : {failed:,}",
        f"Previous read errors       : {len(old_errors):,}",
        f"Previous errors resolved   : {previous_resolved:,}",
        f"Maximum path length        : {max_length:,}",
        "Live DB modified           : No",
        "Music files modified       : No",
        f"Detailed report            : {output_dir}",
    ]
    (output_dir / "LONG_PATH_PROBE_SUMMARY.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    print()
    for line in lines[2:]:
        print(line)

    if scan_errors or failed:
        print("LONG PATH PROBE FAILED")
        return 1
    print("LONG PATH PROBE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
