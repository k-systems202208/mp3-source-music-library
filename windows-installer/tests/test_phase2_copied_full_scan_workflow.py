from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from long_paths import mkdir_path, path_length, write_bytes_path


def synchsafe(value: int) -> bytes:
    return bytes(((value >> 21) & 0x7F, (value >> 14) & 0x7F, (value >> 7) & 0x7F, value & 0x7F))


def frame(frame_id: str, value: str) -> bytes:
    payload = b"\x03" + value.encode("utf-8")
    return frame_id.encode("ascii") + len(payload).to_bytes(4, "big") + b"\0\0" + payload


def mp3(title: str, artist: str, album: str) -> bytes:
    frames = frame("TIT2", title) + frame("TPE1", artist) + frame("TALB", album)
    return b"ID3\x03\0\0" + synchsafe(len(frames)) + frames + b"\0" * 8192


def deep_dir(root: Path, filename: str) -> Path:
    current = root
    index = 0
    while path_length(current / filename) < 300:
        current = current / (f"segment-{index:02d}-" + "x" * 36)
        index += 1
    mkdir_path(current, parents=True, exist_ok=True)
    return current


def run_generator(data: Path, music: Path) -> None:
    env = os.environ.copy()
    env["MUSIC_LIBRARY_DATA_DIR"] = str(data)
    env["MUSIC_LIBRARY_MUSIC_DIR"] = str(music)
    completed = subprocess.run([sys.executable, str(SRC / "generator.py")], env=env, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stdout + completed.stderr


def main() -> None:
    temp = Path(tempfile.mkdtemp(prefix="ml-phase2-full-scan-"))
    try:
        live = temp / "live"
        music = temp / "music"
        output = temp / "output"
        live.mkdir()
        music.mkdir()
        write_bytes_path(music / "short.mp3", mp3("Short", "Tester", "Album"))
        (live / "config.json").write_text(json.dumps({"musicRoot": str(music)}), encoding="utf-8")
        run_generator(live, music)

        connection = sqlite3.connect(live / "library.db")
        try:
            owner = connection.execute("SELECT id FROM users WHERE is_owner=1").fetchone()[0]
            track = connection.execute("SELECT id FROM tracks WHERE title='Short'").fetchone()[0]
            connection.execute(
                "INSERT INTO user_track_state(user_id,track_id,favorite,rating,play_count,last_played_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (owner, track, 1, None, 3, "2026-01-01T00:00:00+00:00", "2026-01-01", "2026-01-01"),
            )
            connection.commit()
        finally:
            connection.close()

        for index in range(2):
            name = f"long-{index}.mp3"
            target = deep_dir(music, name) / name
            write_bytes_path(target, mp3(f"Long {index}", "Tester", "Long Album"))

        command = [
            sys.executable,
            str(ROOT / "tests" / "run_phase2_copied_full_scan.py"),
            "--data-root",
            str(live),
            "--music-root",
            str(music),
            "--output-root",
            str(output),
            "--expected-added",
            "2",
            "--skip-artwork-copy",
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        assert completed.returncode == 0, completed.stdout + completed.stderr
        result_path = next(output.glob("*/PHASE2_COPIED_SCAN_RESULT.json"))
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        summary = payload["summary"]
        assert summary["liveAvailableTracks"] == 1, summary
        assert summary["copiedAvailableTracks"] == 3, summary
        assert summary["newlyAvailableTracks"] == 2, summary
        assert summary["longPathFiles"] == 2, summary
        assert summary["longPathsLoaded"] == 2, summary
        assert summary["longPathErrors"] == 0, summary
        assert summary["userStatePreserved"] is True, summary
        assert summary["liveDatabaseUnchanged"] is True, summary
        assert summary["musicFilesUnchanged"] is True, summary
        assert summary["httpRangeSamplesPassed"] >= 1, summary
        assert summary["passed"] is True, payload
    finally:
        shutil.rmtree(temp, ignore_errors=True)


main()
print("Copied full-scan workflow, state preservation and long-path range playback tests passed.")
