from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from long_paths import io_path, mkdir_path, path_length, write_bytes_path  # noqa: E402


def synchsafe(value: int) -> bytes:
    return bytes(((value >> 21) & 0x7F, (value >> 14) & 0x7F, (value >> 7) & 0x7F, value & 0x7F))


def frame(frame_id: str, value: str) -> bytes:
    payload = b"\x03" + value.encode("utf-8")
    return frame_id.encode("ascii") + len(payload).to_bytes(4, "big") + b"\x00\x00" + payload


def mp3_bytes() -> bytes:
    frames = frame("TIT2", "Probe Test") + frame("TPE1", "Probe Artist") + frame("TALB", "Probe Album")
    return b"ID3\x03\x00\x00" + synchsafe(len(frames)) + frames + (b"\x00" * 1024)


temp_root = Path(tempfile.mkdtemp(prefix="music-library-live-probe-test-"))
try:
    data_root = temp_root / "data"
    music_root = temp_root / "music"
    output_root = temp_root / "output"
    data_root.mkdir()
    music_root.mkdir()

    deep = music_root
    counter = 0
    while path_length(deep / "probe.mp3") < 300:
        deep = deep / (f"deep-{counter:02d}-" + "z" * 42)
        counter += 1
    mkdir_path(deep, parents=True, exist_ok=True)
    target = deep / "probe.mp3"
    write_bytes_path(target, mp3_bytes())
    relative = target.relative_to(music_root).as_posix()

    (data_root / "config.json").write_text(
        json.dumps({"musicRoot": str(music_root)}), encoding="utf-8"
    )
    (data_root / "library-diagnostics.json").write_text(
        json.dumps(
            {
                "diagnostics": [
                    {
                        "severity": "error",
                        "category": "mp3_read_error",
                        "path": "Music/" + relative,
                        "message": "simulated previous MAX_PATH error",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    command = [
        sys.executable,
        str(ROOT / "tests" / "run_live_long_path_probe.py"),
        "--data-root",
        str(data_root),
        "--output-root",
        str(output_root),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, timeout=120)
    if completed.returncode != 0:
        print(completed.stdout)
        print(completed.stderr, file=sys.stderr)
        raise AssertionError(f"probe exited with {completed.returncode}")
    assert "LONG PATH PROBE PASSED" in completed.stdout

    reports = list(output_root.glob("*/LONG_PATH_PROBE.json"))
    assert len(reports) == 1, reports
    payload = json.loads(reports[0].read_text(encoding="utf-8"))
    summary = payload["summary"]
    assert summary["longPathFiles"] == 1, summary
    assert summary["passed"] == 1, summary
    assert summary["failed"] == 0, summary
    assert summary["previousErrorsResolvedByProbe"] == 1, summary
    assert summary["readOnly"] is True
finally:
    shutil.rmtree(io_path(temp_root), ignore_errors=True)

print("Read-only live long-path probe tests passed.")
