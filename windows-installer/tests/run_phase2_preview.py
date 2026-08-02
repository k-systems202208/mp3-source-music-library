from __future__ import annotations

import json
import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def latest_result() -> tuple[Path, dict]:
    candidates = sorted(
        (ROOT / "PHASE2_OUTPUT").glob("*/PHASE2_COPIED_SCAN_RESULT.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise RuntimeError("PHASE2_COPIED_SCAN_RESULT.json was not found. Run 01_scan_copied_library.bat first.")
    path = candidates[0]
    payload = json.loads(path.read_text(encoding="utf-8"))
    return path, payload


def main() -> int:
    result_path, payload = latest_result()
    summary = payload.get("summary", {})
    if not summary.get("passed"):
        raise RuntimeError("The latest copied full scan did not pass.")
    copied_data = Path(str(summary["copiedDataRoot"]))
    music_root = Path(str(summary["musicRoot"]))
    os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(copied_data)
    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)
    sys.path.insert(0, str(SRC))
    import server

    httpd = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret="phase2-preview-secret-0123456789abcdef",
    )
    url = f"http://127.0.0.1:{httpd.server_address[1]}/music-library-search.html"
    print("Copied-library preview")
    print("======================")
    print(f"Database : {copied_data / 'library.db'}")
    print(f"Music    : {music_root} (read only)")
    print(f"URL      : {url}")
    print()
    print("Long-path playback samples:")
    for item in payload.get("playbackSamples", []):
        print(f"- {item.get('title')} ({item.get('absolutePathLength')} characters)")
    print()
    print("Favorite/play-count changes made here affect only the copied database.")
    print("Press Ctrl+C to stop the preview.")
    webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
