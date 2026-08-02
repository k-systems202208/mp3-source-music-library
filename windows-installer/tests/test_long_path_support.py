from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

from long_paths import (  # noqa: E402
    io_path,
    is_long_path,
    mkdir_path,
    open_path,
    path_length,
    stat_path,
    strip_extended_prefix,
    windows_extended_path,
    write_bytes_path,
)


def synchsafe(value: int) -> bytes:
    return bytes(
        (
            (value >> 21) & 0x7F,
            (value >> 14) & 0x7F,
            (value >> 7) & 0x7F,
            value & 0x7F,
        )
    )


def text_frame(frame_id: str, value: str) -> bytes:
    payload = b"\x03" + value.encode("utf-8")
    return frame_id.encode("ascii") + len(payload).to_bytes(4, "big") + b"\x00\x00" + payload


def id3_only_mp3(*, title: str, artist: str, album: str) -> bytes:
    frames = b"".join(
        (
            text_frame("TIT2", title),
            text_frame("TPE1", artist),
            text_frame("TALB", album),
            text_frame("TRCK", "1"),
        )
    )
    return b"ID3\x03\x00\x00" + synchsafe(len(frames)) + frames + (b"\x00" * 2048)


def make_deep_directory(root: Path) -> Path:
    current = root
    index = 0
    while path_length(current / "01-long-path-test.mp3") < 310:
        current = current / (f"segment-{index:02d}-" + ("x" * 38))
        index += 1
    mkdir_path(current, parents=True, exist_ok=True)
    return current


def test_prefix_conversion() -> None:
    drive = r"C:\Music\Artist\Album\song.mp3"
    extended_drive = windows_extended_path(drive, platform="nt")
    assert extended_drive == r"\\?\C:\Music\Artist\Album\song.mp3"
    assert windows_extended_path(extended_drive, platform="nt") == extended_drive
    assert strip_extended_prefix(extended_drive) == drive

    unc = r"\\server\share\Music\song.mp3"
    extended_unc = windows_extended_path(unc, platform="nt")
    assert extended_unc == r"\\?\UNC\server\share\Music\song.mp3"
    assert strip_extended_prefix(extended_unc) == unc


def test_generator_and_range_playback() -> None:
    temp_root = Path(tempfile.mkdtemp(prefix="music-library-long-path-"))
    try:
        data_root = temp_root / "data"
        music_root = temp_root / "music"
        data_root.mkdir()
        music_root.mkdir()
        deep = make_deep_directory(music_root)
        long_mp3 = deep / "01-long-path-test.mp3"
        short_mp3 = music_root / "short-test.mp3"
        folder_art = deep / "folder.jpg"

        write_bytes_path(
            long_mp3,
            id3_only_mp3(
                title="Long Path Test",
                artist="Long Path Artist",
                album="Long Path Album",
            ),
        )
        write_bytes_path(
            short_mp3,
            id3_only_mp3(
                title="Short Path Test",
                artist="Short Path Artist",
                album="Short Path Album",
            ),
        )
        write_bytes_path(folder_art, b"\xff\xd8\xff\xe0long-path-artwork")

        assert is_long_path(long_mp3), path_length(long_mp3)
        assert path_length(long_mp3) >= 310
        assert stat_path(long_mp3).st_size > 0
        with open_path(long_mp3, "rb") as file:
            assert file.read(3) == b"ID3"

        os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(data_root)
        os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)

        # Imports must occur after the isolated environment is configured.
        import generator  # noqa: E402

        assert generator.main() == 0

        database_path = data_root / "library.db"
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            rows = connection.execute(
                "SELECT t.title, t.relative_path, a.relative_path AS artwork_relative_path, "
                "t.is_available FROM tracks AS t "
                "LEFT JOIN artworks AS a ON a.id = t.artwork_id "
                "ORDER BY t.title"
            ).fetchall()
            assert len(rows) == 2, rows
            long_row = next(row for row in rows if row["title"] == "Long Path Test")
            assert long_row["is_available"] == 1
            assert str(long_row["relative_path"]).startswith("Music/")
            assert str(long_row["artwork_relative_path"]).endswith("folder.jpg")

            scan = connection.execute(
                "SELECT details_json, errors FROM scan_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
            details = json.loads(scan["details_json"])
            assert scan["errors"] == 0, details
            assert details["longPathFiles"] == 1, details
            assert details["longPathLoaded"] == 1, details
            assert details["longPathErrors"] == 0, details
            assert details["maxPathLength"] >= 310, details
        finally:
            connection.close()

        import server  # noqa: E402

        httpd = server.create_server(
            "127.0.0.1",
            0,
            owner_control_secret="long-path-test-secret-0123456789-abcdef",
        )
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            relative_url = "/" + urllib.parse.quote(
                str(long_row["relative_path"]),
                safe="/",
            )
            request = urllib.request.Request(
                f"http://127.0.0.1:{httpd.server_address[1]}{relative_url}",
                headers={"Range": "bytes=0-9"},
            )
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 206
                assert response.headers.get("Content-Range", "").startswith("bytes 0-9/")
                assert response.read() == id3_only_mp3(
                    title="Long Path Test",
                    artist="Long Path Artist",
                    album="Long Path Album",
                )[:10]
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
    finally:
        shutil.rmtree(io_path(temp_root), ignore_errors=True)


test_prefix_conversion()
test_generator_and_range_playback()
print("Windows long-path scan, metadata, artwork and range-playback tests passed.")
