from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sqlite3
import subprocess
import sys
import time
import webbrowser
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEFAULT_PORT = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the v2.7.1 backup/restore preview against copied data."
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--output-root", default=str(ROOT / "PHASE2_OUTPUT"))
    return parser.parse_args()


def local_app_data() -> Path:
    value = os.environ.get("LOCALAPPDATA", "").strip()
    if not value:
        raise RuntimeError("LOCALAPPDATA is not available")
    return Path(value).expanduser().resolve()


def read_config(live_data_root: Path) -> dict:
    path = live_data_root / "config.json"
    if not path.exists():
        raise FileNotFoundError(f"Config was not found: {path}")
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("config.json must contain a JSON object")
    return value


def sqlite_backup(source_path: Path, destination_path: Path) -> None:
    if not source_path.exists():
        raise FileNotFoundError(f"Live database was not found: {source_path}")
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    source_uri = f"file:{source_path.as_posix()}?mode=ro"
    source = sqlite3.connect(source_uri, uri=True, timeout=30)
    destination = sqlite3.connect(destination_path)
    try:
        source.backup(destination)
    finally:
        destination.close()
        source.close()


def link_artwork(live_data_root: Path, preview_data_root: Path) -> str:
    source = live_data_root / ".artwork-cache"
    destination = preview_data_root / ".artwork-cache"
    if not source.exists():
        destination.mkdir(parents=True, exist_ok=True)
        return "Artwork cache did not exist; an empty preview cache was created."

    if destination.exists() or destination.is_symlink():
        if destination.is_dir() and not destination.is_symlink():
            shutil.rmtree(destination)
        else:
            destination.unlink()

    if os.name == "nt":
        result = subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(destination), str(source)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            destination.mkdir(parents=True, exist_ok=True)
            return (
                "Artwork junction could not be created; the preview will use "
                f"empty artwork. Details: {result.stdout} {result.stderr}"
            ).strip()
        return f"Artwork cache junction: {destination} -> {source}"

    destination.symlink_to(source, target_is_directory=True)
    return f"Artwork cache symlink: {destination} -> {source}"



def copy_backups(live_data_root: Path, preview_data_root: Path) -> tuple[int, int]:
    source = live_data_root / "Backups"
    destination = preview_data_root / "Backups"
    destination.mkdir(parents=True, exist_ok=True)
    copied = 0
    skipped = 0
    if not source.is_dir():
        return copied, skipped
    for path in source.glob("library-*.db"):
        if not path.is_file():
            continue
        try:
            shutil.copy2(path, destination / path.name)
            copied += 1
        except OSError:
            skipped += 1
    return copied, skipped

def prepare_preview(output_root: Path) -> tuple[Path, Path, str]:
    live_data_root = local_app_data() / "MusicLibrary"
    config = read_config(live_data_root)
    music_root_text = str(config.get("musicRoot") or "").strip()
    if not music_root_text:
        raise RuntimeError("musicRoot is not configured in config.json")
    music_root = Path(music_root_text).expanduser().resolve()
    if not music_root.exists():
        raise FileNotFoundError(f"Configured music folder was not found: {music_root}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    preview_root = output_root.resolve() / stamp
    preview_data_root = preview_root / "data"
    preview_data_root.mkdir(parents=True, exist_ok=False)

    sqlite_backup(live_data_root / "library.db", preview_data_root / "library.db")
    backup_count, backup_skipped = copy_backups(live_data_root, preview_data_root)
    artwork_note = link_artwork(live_data_root, preview_data_root)

    copied_config = {
        "musicRoot": str(music_root),
        "port": DEFAULT_PORT,
        "preview": True,
    }
    (preview_data_root / "config.json").write_text(
        json.dumps(copied_config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    info = [
        "Music Library v2.7.1 Phase 2 - Backup and Restore Preview",
        "========================================================",
        f"Created: {datetime.now().isoformat(timespec='seconds')}",
        f"Live data root (read only): {live_data_root}",
        f"Copied database: {preview_data_root / 'library.db'}",
        f"Music root (read only): {music_root}",
        f"Copied backups: {backup_count} (skipped: {backup_skipped})",
        artwork_note,
        "",
        "All backup, restore-reservation, favorite and playback changes made",
        "in this preview are written only below the preview folder.",
        "The live library.db and live Backups folder are not modified.",
    ]
    (preview_root / "PREVIEW_INFO.txt").write_text(
        "\n".join(info) + "\n",
        encoding="utf-8-sig",
    )
    return preview_root, preview_data_root, str(music_root)


def main() -> int:
    args = parse_args()
    output_root = Path(args.output_root)
    preview_root, preview_data_root, music_root = prepare_preview(output_root)
    print("=" * 72)
    print("Music Library v2.7.1 - Backup and Restore Preview")
    print("=" * 72)
    print(f"Preview folder : {preview_root}")
    print(f"Copied database: {preview_data_root / 'library.db'}")
    print(f"Music folder   : {music_root}")
    print("The live library.db and Backups folder will not be changed.")

    if args.prepare_only:
        print("Preview preparation completed.")
        return 0

    os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(preview_data_root)
    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = music_root
    sys.path.insert(0, str(SRC))

    import server  # noqa: E402

    control_secret = secrets.token_urlsafe(48)
    music_server = server.create_server(
        "127.0.0.1",
        int(args.port),
        owner_control_secret=control_secret,
    )
    token = secrets.token_urlsafe(36)
    music_server.local_owner_auth.register_one_time_token(token, ttl_seconds=120)
    actual_port = int(music_server.server_address[1])
    url = (
        f"http://127.0.0.1:{actual_port}"
        f"/api/local-auth/exchange?token={token}"
    )
    print(f"Preview URL    : http://127.0.0.1:{actual_port}/music-library-search.html")
    print("Close this console or press Ctrl+C to stop the preview.")
    print("Backup/restore reservations and personal changes remain inside the preview data.")
    if not args.no_browser:
        webbrowser.open(url)

    try:
        music_server.serve_forever()
    except KeyboardInterrupt:
        print("\nPreview stopped.")
    finally:
        music_server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
