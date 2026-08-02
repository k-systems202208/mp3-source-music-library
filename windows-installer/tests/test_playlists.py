from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-playlists-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402
import server  # noqa: E402
from local_auth import SESSION_COOKIE_NAME  # noqa: E402
from tailscale_identity import TAILSCALE_LOGIN_HEADER, TAILSCALE_NAME_HEADER  # noqa: E402


def insert_track(connection, track_id: str, title: str) -> None:
    timestamp = db.utc_now()
    connection.execute(
        """
        INSERT INTO tracks(
            id, relative_path, filename, title, normalized_title,
            duration_ms, file_size, modified_time_ns, audio_file,
            last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?)
        """,
        (
            track_id,
            f"Test/{track_id}.mp3",
            f"{track_id}.mp3",
            title,
            title.casefold(),
            60000,
            f"Music/Test/{track_id}.mp3",
            timestamp,
            timestamp,
            timestamp,
        ),
    )


def request_json(connection, method, path, *, headers=None, value=None):
    body = None
    actual_headers = dict(headers or {})
    if value is not None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        actual_headers["Content-Type"] = "application/json"
        actual_headers["Content-Length"] = str(len(body))
    connection.request(method, path, body=body, headers=actual_headers)
    response = connection.getresponse()
    payload = response.read()
    return response.status, json.loads(payload.decode("utf-8"))


def get_owner_cookie(port: int, secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "P" * 43
        status, _ = request_json(
            connection,
            "POST",
            "/api/local-auth/token",
            headers={"X-Music-Library-Control-Secret": secret},
            value={"token": token, "expiresInSeconds": 60},
        )
        assert status == 201
        connection.request("GET", f"/api/local-auth/exchange?token={token}")
        response = connection.getresponse()
        response.read()
        assert response.status == 200
        headers = {key.casefold(): value for key, value in response.getheaders()}
        return headers["set-cookie"].split(";", 1)[0]
    finally:
        connection.close()


def test_schema_v6_to_v7_backup_and_database_operations() -> None:
    root = IMPORT_ROOT / "migration"
    root.mkdir(parents=True, exist_ok=True)
    path = root / "library.db"
    backup_dir = root / "Backups"

    with db.database(path, prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        connection.execute("DROP TABLE playlist_tracks")
        connection.execute("DROP TABLE playlists")
        connection.execute(
            "UPDATE schema_info SET value='6' WHERE key='schema_version'"
        )

    obsolete_backup = db.create_pre_v272_migration_backup(
        path, backup_dir=backup_dir
    )
    assert obsolete_backup is None

    connection = db.connect_database(
        path,
        prepare_migration_backup=True,
        migration_backup_dir=backup_dir,
    )
    try:
        db.initialize_database(connection)
        assert db.read_schema_version(connection) == 7
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='playlists'"
        ).fetchone()
        owner = db.get_owner_user(connection)
        assert owner is not None
        family = db.get_or_create_tailscale_user(
            connection,
            subject="playlist-family@example.com",
            display_name="家族A",
        )
        for index in range(3):
            insert_track(connection, f"track_{index}", f"曲 {index}")

        created = db.create_user_playlist(
            connection, user_id=owner["id"], name="ドライブ"
        )
        for index in range(3):
            db.add_track_to_user_playlist(
                connection,
                user_id=owner["id"],
                playlist_id=created["id"],
                track_id=f"track_{index}",
            )
        detail = db.get_user_playlist(
            connection, user_id=owner["id"], playlist_id=created["id"]
        )
        assert [track["id"] for track in detail["tracks"]] == [
            "track_0", "track_1", "track_2"
        ]
        assert detail["durationMs"] == 180000

        db.reorder_user_playlist_tracks(
            connection,
            user_id=owner["id"],
            playlist_id=created["id"],
            track_ids=["track_2", "track_0", "track_1"],
        )
        detail = db.get_user_playlist(
            connection, user_id=owner["id"], playlist_id=created["id"]
        )
        assert [track["id"] for track in detail["tracks"]] == [
            "track_2", "track_0", "track_1"
        ]

        connection.execute("UPDATE tracks SET is_available=0 WHERE id='track_1'")
        reordered = db.reorder_user_playlist_tracks(
            connection,
            user_id=owner["id"],
            playlist_id=created["id"],
            track_ids=["track_0", "track_2"],
        )
        assert reordered["unavailableTrackCount"] == 1
        stored_order = [
            str(row[0])
            for row in connection.execute(
                "SELECT track_id FROM playlist_tracks WHERE playlist_id=? ORDER BY position",
                (created["id"],),
            ).fetchall()
        ]
        assert stored_order == ["track_0", "track_2", "track_1"]
        connection.execute("UPDATE tracks SET is_available=1 WHERE id='track_1'")

        db.remove_track_from_user_playlist(
            connection,
            user_id=owner["id"],
            playlist_id=created["id"],
            track_id="track_0",
        )
        assert db.list_user_playlists(connection, user_id=owner["id"])[0][
            "trackCount"
        ] == 2
        assert db.list_user_playlists(connection, user_id=family["id"]) == []
        try:
            db.get_user_playlist(
                connection, user_id=family["id"], playlist_id=created["id"]
            )
        except db.PlaylistNotFound:
            pass
        else:
            raise AssertionError("another user's playlist was readable")
    finally:
        connection.close()

    backups = list(backup_dir.glob("library-pre-v2.7.5-*.db"))
    assert len(backups) == 1
    assert db.database_schema_version(backups[0]) == 6


def test_http_playlist_crud_and_user_isolation() -> None:
    secret = "L" * 48
    music_server = server.create_server("127.0.0.1", 0, owner_control_secret=secret)
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    with db.database() as connection:
        db.initialize_database(connection)
        insert_track(connection, "http_track_a", "HTTP曲A")
        insert_track(connection, "http_track_b", "HTTP曲B")

    owner_cookie = get_owner_cookie(port, secret)
    owner_headers = {"Cookie": owner_cookie}
    family_headers = {
        TAILSCALE_LOGIN_HEADER: "playlist-family-http@example.com",
        TAILSCALE_NAME_HEADER: "Playlist Family HTTP",
    }
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, payload = request_json(connection, "GET", "/api/playlists")
        assert status == 401
        assert payload["error"] == "authenticated user is required"

        status, payload = request_json(
            connection,
            "POST",
            "/api/playlists",
            headers=owner_headers,
            value={"name": "夜に聴く"},
        )
        assert status == 201
        playlist_id = payload["playlist"]["id"]

        for track_id in ("http_track_a", "http_track_b"):
            status, _ = request_json(
                connection,
                "POST",
                f"/api/playlists/{playlist_id}/tracks",
                headers=owner_headers,
                value={"trackId": track_id},
            )
            assert status == 201

        status, payload = request_json(
            connection,
            "GET",
            f"/api/playlists/{playlist_id}",
            headers=owner_headers,
        )
        assert status == 200
        assert [item["id"] for item in payload["playlist"]["tracks"]] == [
            "http_track_a", "http_track_b"
        ]

        status, payload = request_json(
            connection,
            "PUT",
            f"/api/playlists/{playlist_id}/tracks/order",
            headers=owner_headers,
            value={"trackIds": ["http_track_b", "http_track_a"]},
        )
        assert status == 200 and payload["reordered"] is True

        status, _ = request_json(
            connection,
            "GET",
            f"/api/playlists/{playlist_id}",
            headers=family_headers,
        )
        assert status == 404

        status, payload = request_json(
            connection,
            "PUT",
            f"/api/playlists/{playlist_id}",
            headers=owner_headers,
            value={"name": "夜ドライブ"},
        )
        assert status == 200 and payload["playlist"]["name"] == "夜ドライブ"

        status, payload = request_json(
            connection,
            "DELETE",
            f"/api/playlists/{playlist_id}/tracks/http_track_a",
            headers=owner_headers,
        )
        assert status == 200 and payload["removed"] is True

        status, payload = request_json(
            connection,
            "DELETE",
            f"/api/playlists/{playlist_id}",
            headers=owner_headers,
        )
        assert status == 200 and payload["deleted"] is True
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


def test_playlist_ui_contract() -> None:
    html = (SRC / "music-library-search.html").read_text(encoding="utf-8")
    required = [
        'data-view="playlists"',
        'id="playlistPanel"',
        'id="playlistCreateButton"',
        'id="playlistAddModal"',
        'data-action="playlist-add"',
        "PLAYLISTS_API_URL",
        "loadPlaylists",
        "createPlaylistAndAdd",
        "reorderPlaylistTrack",
        "trackIds",
        "PERSONAL PLAYLISTS",
    ]
    for token in required:
        assert token in html, token
    assert "現在の利用者だけの曲リスト" in html
    assert "曲ファイルは削除されません" in html


test_schema_v6_to_v7_backup_and_database_operations()
test_http_playlist_crud_and_user_isolation()
test_playlist_ui_contract()
print("Per-user playlist database, API and UI contract tests passed.")
