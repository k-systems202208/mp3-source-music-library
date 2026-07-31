from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-user-playback-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402
import server  # noqa: E402
from local_auth import SESSION_COOKIE_NAME  # noqa: E402
from tailscale_identity import (  # noqa: E402
    TAILSCALE_LOGIN_HEADER,
    TAILSCALE_NAME_HEADER,
)


def insert_track(
    connection,
    track_id: str,
    title: str,
    *,
    legacy_play_count: int = 0,
    legacy_last_played_at: str = "",
    available: int = 1,
) -> None:
    timestamp = db.utc_now()
    connection.execute(
        """
        INSERT INTO tracks(
            id, relative_path, filename, title, normalized_title,
            file_size, modified_time_ns, audio_file,
            play_count, last_played_at, is_available,
            last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            f"Test/{track_id}.mp3",
            f"{track_id}.mp3",
            title,
            title.casefold(),
            f"Music/Test/{track_id}.mp3",
            legacy_play_count,
            legacy_last_played_at,
            available,
            timestamp,
            timestamp,
            timestamp,
        ),
    )


def request_json(
    connection: http.client.HTTPConnection,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    value: dict | None = None,
) -> tuple[int, dict[str, str], dict]:
    body = None
    actual_headers = dict(headers or {})
    if value is not None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        actual_headers["Content-Type"] = "application/json"
        actual_headers["Content-Length"] = str(len(body))
    connection.request(method, path, body=body, headers=actual_headers)
    response = connection.getresponse()
    payload = response.read()
    response_headers = {
        key.casefold(): value for key, value in response.getheaders()
    }
    return response.status, response_headers, json.loads(payload.decode("utf-8"))


def get_owner_cookie(port: int, control_secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "P" * 43
        status, _, _ = request_json(
            connection,
            "POST",
            "/api/local-auth/token",
            headers={"X-Music-Library-Control-Secret": control_secret},
            value={"token": token, "expiresInSeconds": 60},
        )
        assert status == 201
        connection.request("GET", f"/api/local-auth/exchange?token={token}")
        response = connection.getresponse()
        response.read()
        assert response.status == 303
        set_cookie = dict(
            (key.casefold(), value) for key, value in response.getheaders()
        )["set-cookie"]
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        return set_cookie.split(";", 1)[0]
    finally:
        connection.close()


def track_items(payload: dict) -> dict[str, dict]:
    assert payload["kind"] == "tracks"
    return {item["id"]: item for item in payload["items"]}


def test_database_user_playback_state() -> None:
    path = IMPORT_ROOT / "playback-database.db"
    connection = db.connect_database(path, prepare_migration_backup=False)
    try:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        family = db.get_or_create_tailscale_user(
            connection,
            subject="family@example.com",
            display_name="家族A",
        )
        insert_track(
            connection,
            "track_a",
            "Alpha",
            legacy_play_count=99,
            legacy_last_played_at="2026-01-01T00:00:00+09:00",
        )
        insert_track(connection, "track_b", "Beta", legacy_play_count=77)
        insert_track(connection, "track_c", "Charlie")
        insert_track(connection, "track_hidden", "Hidden", available=0)
        connection.commit()
        # The schema-5 compatibility backfill copies legacy personal state to
        # the owner exactly once before new user-specific increments begin.
        db.initialize_database(connection)
        timestamp = db.utc_now()
        connection.execute(
            """
            INSERT INTO user_track_state(
                user_id, track_id, favorite, rating,
                play_count, last_played_at, created_at, updated_at
            ) VALUES (?, 'track_c', 1, 5, 0, '', ?, ?)
            """,
            (owner["id"], timestamp, timestamp),
        )

        first = db.record_user_playback(
            connection,
            user_id=owner["id"],
            track_id="track_a",
        )
        second = db.record_user_playback(
            connection,
            user_id=owner["id"],
            track_id="track_a",
        )
        family_play = db.record_user_playback(
            connection,
            user_id=family["id"],
            track_id="track_a",
        )
        owner_b = db.record_user_playback(
            connection,
            user_id=owner["id"],
            track_id="track_b",
        )
        owner_c = db.record_user_playback(
            connection,
            user_id=owner["id"],
            track_id="track_c",
        )
        anonymous = db.record_user_playback(
            connection,
            user_id=None,
            track_id="track_a",
        )
        connection.commit()

        assert first and first["playCount"] == 100 and first["recorded"] is True
        assert second and second["playCount"] == 101
        assert second["lastPlayedAt"]
        assert family_play and family_play["playCount"] == 1
        assert owner_b and owner_b["playCount"] == 78
        assert owner_c and owner_c["playCount"] == 1
        assert anonymous == {
            "playCount": 0,
            "lastPlayedAt": "",
            "recorded": False,
        }
        assert db.record_user_playback(
            connection,
            user_id=owner["id"],
            track_id="track_hidden",
        ) is None
        assert db.record_user_playback(
            connection,
            user_id=owner["id"],
            track_id="missing",
        ) is None

        # Legacy migration columns must remain untouched after schema 5.
        legacy = connection.execute(
            "SELECT play_count, last_played_at FROM tracks WHERE id = 'track_a'"
        ).fetchone()
        assert int(legacy["play_count"]) == 99
        assert legacy["last_played_at"] == "2026-01-01T00:00:00+09:00"

        owner_result = db.browse_library(
            connection,
            view="songs",
            sort="plays",
            user_id=owner["id"],
        )
        owner_items = owner_result["items"]
        assert [item["id"] for item in owner_items[:3]] == [
            "track_a",
            "track_b",
            "track_c",
        ]
        assert owner_items[0]["playCount"] == 101
        assert owner_items[1]["playCount"] == 78
        assert owner_items[2]["playCount"] == 1
        assert owner_items[2]["favorite"] is True
        assert owner_items[2]["rating"] == 5

        family_items = track_items(
            db.browse_library(
                connection,
                view="songs",
                sort="plays",
                user_id=family["id"],
            )
        )
        assert family_items["track_a"]["playCount"] == 1
        assert family_items["track_b"]["playCount"] == 0

        anonymous_items = track_items(
            db.browse_library(connection, view="songs", sort="plays")
        )
        assert all(item["playCount"] == 0 for item in anonymous_items.values())
        assert all(item["lastPlayedAt"] == "" for item in anonymous_items.values())

        owner_tracks = {
            item["id"]: item
            for item in db.get_available_tracks(connection, user_id=owner["id"])
        }
        assert owner_tracks["track_a"]["playCount"] == 101
        assert owner_tracks["track_a"]["lastPlayedAt"]

        assert db.database_stats(
            connection,
            user_id=owner["id"],
        )["totalPlays"] == 180
        assert db.database_stats(
            connection,
            user_id=family["id"],
        )["totalPlays"] == 1
        assert db.database_stats(connection)["totalPlays"] == 0

        preserved = connection.execute(
            """
            SELECT favorite, rating, play_count
              FROM user_track_state
             WHERE user_id = ? AND track_id = 'track_c'
            """,
            (owner["id"],),
        ).fetchone()
        assert int(preserved["favorite"]) == 1
        assert int(preserved["rating"]) == 5
        assert int(preserved["play_count"]) == 1

        db.set_user_active(connection, family["id"], False)
        try:
            db.record_user_playback(
                connection,
                user_id=family["id"],
                track_id="track_a",
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("inactive user playback was accepted")
    finally:
        connection.close()


def test_concurrent_user_playback_updates() -> None:
    path = IMPORT_ROOT / "playback-concurrency.db"
    with db.database(path, prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        owner_id = str(owner["id"])
        insert_track(connection, "track_concurrent", "Concurrent")

    def record_once(_: int) -> None:
        with db.database(path, prepare_migration_backup=False) as connection:
            db.initialize_database(connection)
            result = db.record_user_playback(
                connection,
                user_id=owner_id,
                track_id="track_concurrent",
            )
            assert result is not None and result["recorded"] is True

    increments = 24
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(record_once, range(increments)))

    with db.database(path, prepare_migration_backup=False) as connection:
        state = connection.execute(
            """
            SELECT play_count, last_played_at
              FROM user_track_state
             WHERE user_id = ? AND track_id = 'track_concurrent'
            """,
            (owner_id,),
        ).fetchone()
        assert state is not None
        assert int(state["play_count"]) == increments
        assert state["last_played_at"]
        legacy = connection.execute(
            "SELECT play_count FROM tracks WHERE id = 'track_concurrent'"
        ).fetchone()
        assert int(legacy["play_count"]) == 0


def test_http_user_playback_state() -> None:
    control_secret = "R" * 48
    music_server = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret=control_secret,
    )
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    with db.database() as connection:
        db.initialize_database(connection)
        insert_track(connection, "http_a", "Alpha")
        insert_track(connection, "http_b", "Beta")

    owner_cookie = get_owner_cookie(port, control_secret)
    owner_headers = {"Cookie": owner_cookie}
    family_headers = {
        TAILSCALE_LOGIN_HEADER: "family-http@example.com",
        TAILSCALE_NAME_HEADER: "Family HTTP",
    }
    both_headers = {**owner_headers, **family_headers}

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, _, anonymous_play = request_json(
            connection,
            "POST",
            "/api/tracks/http_a/played",
            value={},
        )
        assert status == 200
        assert anonymous_play["recorded"] is False
        assert anonymous_play["playCount"] == 0

        status, _, owner_first = request_json(
            connection,
            "POST",
            "/api/tracks/http_a/played",
            headers=owner_headers,
            value={},
        )
        assert status == 200
        assert owner_first["recorded"] is True
        assert owner_first["playCount"] == 1
        assert owner_first["lastPlayedAt"]

        status, _, owner_second = request_json(
            connection,
            "POST",
            "/api/tracks/http_a/played",
            headers=owner_headers,
            value={},
        )
        assert status == 200
        assert owner_second["playCount"] == 2

        status, _, family_first = request_json(
            connection,
            "POST",
            "/api/tracks/http_b/played",
            headers=family_headers,
            value={},
        )
        assert status == 200
        assert family_first["playCount"] == 1

        # Tailscale identity takes precedence over a local owner cookie.
        status, _, family_second = request_json(
            connection,
            "POST",
            "/api/tracks/http_b/played",
            headers=both_headers,
            value={},
        )
        assert status == 200
        assert family_second["playCount"] == 2

        status, _, owner_browse = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&sort=plays&limit=20&offset=0",
            headers=owner_headers,
        )
        assert status == 200
        owner_items = track_items(owner_browse)
        assert owner_items["http_a"]["playCount"] == 2
        assert owner_items["http_b"]["playCount"] == 0

        status, _, family_browse = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&sort=plays&limit=20&offset=0",
            headers=family_headers,
        )
        assert status == 200
        family_items = track_items(family_browse)
        assert family_items["http_a"]["playCount"] == 0
        assert family_items["http_b"]["playCount"] == 2

        status, _, anonymous_browse = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&sort=plays&limit=20&offset=0",
        )
        assert status == 200
        assert all(
            item["playCount"] == 0
            for item in anonymous_browse["items"]
        )

        status, _, owner_stats = request_json(
            connection,
            "GET",
            "/api/stats",
            headers=owner_headers,
        )
        assert status == 200
        assert owner_stats["totalPlays"] == 2

        status, _, family_stats = request_json(
            connection,
            "GET",
            "/api/stats",
            headers=family_headers,
        )
        assert status == 200
        assert family_stats["totalPlays"] == 2

        status, _, missing = request_json(
            connection,
            "POST",
            "/api/tracks/not-found/played",
            headers=owner_headers,
            value={},
        )
        assert status == 404
        assert missing["error"] == "track not found"

        with db.database() as connection_db:
            legacy = connection_db.execute(
                "SELECT id, play_count FROM tracks ORDER BY id"
            ).fetchall()
            assert {row["id"]: int(row["play_count"]) for row in legacy} == {
                "http_a": 0,
                "http_b": 0,
            }
            rows = connection_db.execute(
                """
                SELECT u.display_name, uts.track_id, uts.play_count
                  FROM user_track_state uts
                  JOIN users u ON u.id = uts.user_id
                 ORDER BY u.is_owner DESC, u.display_name, uts.track_id
                """
            ).fetchall()
            assert len(rows) == 2
            assert sorted(int(row["play_count"]) for row in rows) == [2, 2]
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


if __name__ == "__main__":
    test_database_user_playback_state()
    test_concurrent_user_playback_updates()
    test_http_user_playback_state()
    print("User-specific playback state tests passed.")
