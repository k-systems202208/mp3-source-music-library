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
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-user-favorites-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402
import server  # noqa: E402
from local_auth import SESSION_COOKIE_NAME  # noqa: E402
from tailscale_identity import TAILSCALE_LOGIN_HEADER, TAILSCALE_NAME_HEADER  # noqa: E402


def insert_track(connection, track_id: str, *, available: int = 1) -> None:
    timestamp = db.utc_now()
    connection.execute(
        """
        INSERT INTO tracks(
            id, relative_path, filename, title, normalized_title,
            file_size, modified_time_ns, audio_file, is_available,
            last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?, ?)
        """,
        (
            track_id,
            f"Test/{track_id}.mp3",
            f"{track_id}.mp3",
            track_id,
            track_id.casefold(),
            f"Music/Test/{track_id}.mp3",
            available,
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
        token = "F" * 43
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
        set_cookie = dict((k.casefold(), v) for k, v in response.getheaders())["set-cookie"]
        return set_cookie.split(";", 1)[0]
    finally:
        connection.close()


def test_database_user_favorites() -> None:
    path = IMPORT_ROOT / "favorites.db"
    with db.database(path, prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        family = db.get_or_create_tailscale_user(
            connection,
            subject="family-favorite@example.com",
            display_name="家族A",
        )
        insert_track(connection, "track_a")
        insert_track(connection, "track_hidden", available=0)
        timestamp = db.utc_now()
        connection.execute(
            """
            INSERT INTO user_track_state(
                user_id, track_id, favorite, rating,
                play_count, last_played_at, created_at, updated_at
            ) VALUES (?, 'track_a', 0, 4, 7, '2026-07-31T12:00:00+09:00', ?, ?)
            """,
            (owner["id"], timestamp, timestamp),
        )

        result = db.set_user_favorite(
            connection, user_id=owner["id"], track_id="track_a", favorite=True
        )
        assert result == {
            "favorite": True,
            "rating": 4,
            "playCount": 7,
            "lastPlayedAt": "2026-07-31T12:00:00+09:00",
        }
        owner_track = {t["id"]: t for t in db.get_available_tracks(connection, user_id=owner["id"])}["track_a"]
        family_track = {t["id"]: t for t in db.get_available_tracks(connection, user_id=family["id"])}["track_a"]
        assert owner_track["favorite"] is True
        assert family_track["favorite"] is False

        # Explicit desired state is idempotent and preserves playback/rating.
        again = db.set_user_favorite(
            connection, user_id=owner["id"], track_id="track_a", favorite=True
        )
        assert again == result
        cleared = db.set_user_favorite(
            connection, user_id=owner["id"], track_id="track_a", favorite=False
        )
        assert cleared["favorite"] is False
        assert cleared["playCount"] == 7
        assert cleared["rating"] == 4

        # A favorite-only sparse row is removed after clearing.
        created = db.set_user_favorite(
            connection, user_id=family["id"], track_id="track_a", favorite=True
        )
        assert created["favorite"] is True
        removed = db.set_user_favorite(
            connection, user_id=family["id"], track_id="track_a", favorite=False
        )
        assert removed == {
            "favorite": False,
            "rating": None,
            "playCount": 0,
            "lastPlayedAt": "",
        }
        assert connection.execute(
            "SELECT COUNT(*) FROM user_track_state WHERE user_id = ? AND track_id = 'track_a'",
            (family["id"],),
        ).fetchone()[0] == 0

        assert db.set_user_favorite(
            connection, user_id=owner["id"], track_id="missing", favorite=True
        ) is None
        assert db.set_user_favorite(
            connection, user_id=owner["id"], track_id="track_hidden", favorite=True
        ) is None
        try:
            db.set_user_favorite(connection, user_id=None, track_id="track_a", favorite=True)
        except PermissionError:
            pass
        else:
            raise AssertionError("anonymous favorite update was accepted")

        db.set_user_active(connection, family["id"], False)
        try:
            db.set_user_favorite(
                connection, user_id=family["id"], track_id="track_a", favorite=True
            )
        except PermissionError:
            pass
        else:
            raise AssertionError("inactive user's favorite update was accepted")


def test_concurrent_idempotent_favorite_updates() -> None:
    path = IMPORT_ROOT / "favorites-concurrency.db"
    with db.database(path, prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        owner_id = str(owner["id"])
        insert_track(connection, "track_concurrent")

    def set_true(_: int) -> None:
        with db.database(path, prepare_migration_backup=False) as connection:
            db.initialize_database(connection)
            result = db.set_user_favorite(
                connection,
                user_id=owner_id,
                track_id="track_concurrent",
                favorite=True,
            )
            assert result and result["favorite"] is True

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(set_true, range(24)))

    with db.database(path, prepare_migration_backup=False) as connection:
        rows = connection.execute(
            "SELECT favorite FROM user_track_state WHERE user_id = ? AND track_id = 'track_concurrent'",
            (owner_id,),
        ).fetchall()
        assert len(rows) == 1
        assert int(rows[0]["favorite"]) == 1


def test_http_user_favorites() -> None:
    secret = "S" * 48
    music_server = server.create_server("127.0.0.1", 0, owner_control_secret=secret)
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    with db.database() as connection:
        db.initialize_database(connection)
        insert_track(connection, "http_favorite")

    owner_cookie = get_owner_cookie(port, secret)
    owner_headers = {"Cookie": owner_cookie}
    family_headers = {
        TAILSCALE_LOGIN_HEADER: "family-favorite-http@example.com",
        TAILSCALE_NAME_HEADER: "Family Favorite HTTP",
    }
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, payload = request_json(
            connection,
            "POST",
            "/api/tracks/http_favorite/favorite",
            value={"favorite": True},
        )
        assert status == 401
        assert payload["error"] == "authenticated user is required"

        status, payload = request_json(
            connection,
            "POST",
            "/api/tracks/http_favorite/favorite",
            headers=owner_headers,
            value={"favorite": True},
        )
        assert status == 200 and payload["favorite"] is True

        status, payload = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&limit=20&offset=0",
            headers=owner_headers,
        )
        assert status == 200
        assert payload["items"][0]["favorite"] is True

        status, payload = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&limit=20&offset=0",
            headers=family_headers,
        )
        assert status == 200
        assert payload["items"][0]["favorite"] is False

        status, payload = request_json(
            connection,
            "POST",
            "/api/tracks/http_favorite/favorite",
            headers=family_headers,
            value={"favorite": True},
        )
        assert status == 200 and payload["favorite"] is True

        status, payload = request_json(
            connection,
            "POST",
            "/api/tracks/http_favorite/favorite",
            headers=owner_headers,
            value={"favorite": "yes"},
        )
        assert status == 400
        assert payload["error"] == "favorite must be a boolean"

        status, payload = request_json(
            connection,
            "POST",
            "/api/tracks/not-found/favorite",
            headers=owner_headers,
            value={"favorite": True},
        )
        assert status == 404
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


def test_favorite_ui_contract() -> None:
    html = (SRC / "music-library-search.html").read_text(encoding="utf-8")
    assert 'data-action="favorite"' in html
    assert "async function setTrackFavorite" in html
    assert "updateFavoriteButtons" in html
    assert "JSON.stringify({favorite:Boolean(favorite)})" in html
    assert "利用者を確認できないためお気に入りを保存できません" in html
    assert "button.disabled = !authenticated" in html
    assert "track.favorite = Boolean(result.favorite)" in html
    assert "user_id" not in html[html.index("async function setTrackFavorite"):html.index("function updatePlayButtons")]


if __name__ == "__main__":
    test_database_user_favorites()
    test_concurrent_idempotent_favorite_updates()
    test_http_user_favorites()
    test_favorite_ui_contract()
    print("User-specific favorite tests passed.")
