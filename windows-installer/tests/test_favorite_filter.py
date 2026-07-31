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
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-favorite-filter-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402
import server  # noqa: E402
from tailscale_identity import TAILSCALE_LOGIN_HEADER, TAILSCALE_NAME_HEADER  # noqa: E402


def insert_track(connection, track_id: str, title: str, *, available: int = 1) -> None:
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
            title,
            title.casefold(),
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


def test_database_favorite_filter() -> None:
    path = IMPORT_ROOT / "favorite-filter.db"
    with db.database(path, prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        family = db.get_or_create_tailscale_user(
            connection,
            subject="family-filter@example.com",
            display_name="家族フィルター",
        )
        insert_track(connection, "track_alpha", "Alpha")
        insert_track(connection, "track_beta", "Beta")
        insert_track(connection, "track_gamma", "Gamma")
        insert_track(connection, "track_hidden", "Hidden", available=0)

        db.set_user_favorite(connection, user_id=owner["id"], track_id="track_alpha", favorite=True)
        db.set_user_favorite(connection, user_id=owner["id"], track_id="track_gamma", favorite=True)
        db.set_user_favorite(connection, user_id=family["id"], track_id="track_beta", favorite=True)

        owner_result = db.browse_library(
            connection,
            view="songs",
            favorite_only=True,
            user_id=owner["id"],
            limit=20,
        )
        assert owner_result["favoriteOnly"] is True
        assert owner_result["total"] == 2
        assert [item["id"] for item in owner_result["items"]] == ["track_alpha", "track_gamma"]
        assert all(item["favorite"] is True for item in owner_result["items"])
        assert owner_result["indexCounts"]["A"] == 1
        assert owner_result["indexCounts"]["G"] == 1
        assert owner_result["indexCounts"]["B"] == 0

        # Favorite filter composes with search and index filtering.
        searched = db.browse_library(
            connection,
            view="songs",
            query="Gamma",
            favorite_only=True,
            user_id=owner["id"],
            limit=20,
        )
        assert searched["total"] == 1
        assert searched["items"][0]["id"] == "track_gamma"
        indexed = db.browse_library(
            connection,
            view="songs",
            favorite_only=True,
            user_id=owner["id"],
            index_key="A",
            limit=20,
        )
        assert indexed["total"] == 1
        assert indexed["items"][0]["id"] == "track_alpha"

        family_result = db.browse_library(
            connection,
            view="songs",
            favorite_only=True,
            user_id=family["id"],
            limit=20,
        )
        assert [item["id"] for item in family_result["items"]] == ["track_beta"]

        anonymous_result = db.browse_library(
            connection,
            view="songs",
            favorite_only=True,
            user_id=None,
            limit=20,
        )
        assert anonymous_result["total"] == 0
        assert anonymous_result["items"] == []

        owner_stats = db.database_stats(connection, user_id=owner["id"])
        family_stats = db.database_stats(connection, user_id=family["id"])
        anonymous_stats = db.database_stats(connection, user_id=None)
        assert owner_stats["favoriteTracks"] == 2
        assert family_stats["favoriteTracks"] == 1
        assert anonymous_stats["favoriteTracks"] == 0


def test_http_favorite_filter() -> None:
    music_server = server.create_server("127.0.0.1", 0)
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    owner_headers = {
        TAILSCALE_LOGIN_HEADER: "owner-filter@example.com",
        TAILSCALE_NAME_HEADER: "Owner Filter",
    }
    family_headers = {
        TAILSCALE_LOGIN_HEADER: "family-filter-http@example.com",
        TAILSCALE_NAME_HEADER: "Family Filter HTTP",
    }

    with db.database() as connection:
        db.initialize_database(connection)
        insert_track(connection, "http_alpha", "Alpha HTTP")
        insert_track(connection, "http_beta", "Beta HTTP")

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, payload = request_json(
            connection,
            "POST",
            "/api/tracks/http_alpha/favorite",
            headers=owner_headers,
            value={"favorite": True},
        )
        assert status == 200 and payload["favorite"] is True
        status, payload = request_json(
            connection,
            "POST",
            "/api/tracks/http_beta/favorite",
            headers=family_headers,
            value={"favorite": True},
        )
        assert status == 200 and payload["favorite"] is True

        status, payload = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&favoriteOnly=1&limit=20&offset=0",
            headers=owner_headers,
        )
        assert status == 200
        assert payload["favoriteOnly"] is True
        assert [item["id"] for item in payload["items"]] == ["http_alpha"]

        status, payload = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&favoriteOnly=1&limit=20&offset=0",
            headers=family_headers,
        )
        assert status == 200
        assert [item["id"] for item in payload["items"]] == ["http_beta"]

        status, payload = request_json(
            connection,
            "GET",
            "/api/browse?view=songs&favoriteOnly=1&limit=20&offset=0",
        )
        assert status == 200
        assert payload["items"] == []
        assert payload["total"] == 0

        status, payload = request_json(
            connection,
            "GET",
            "/api/stats",
            headers=owner_headers,
        )
        assert status == 200
        assert payload["favoriteTracks"] == 1
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


def test_favorite_filter_ui_contract() -> None:
    html = (SRC / "music-library-search.html").read_text(encoding="utf-8")
    assert 'id="btnFavoritesOnly"' in html
    assert "filterFavoritesOnly: false" in html
    assert "params.set('favoriteOnly', '1')" in html
    assert "state.filterFavoritesOnly = !state.filterFavoritesOnly" in html
    assert "els.btnFavoritesOnly.disabled = !authenticated || !songLevel" in html
    assert "stats.favoriteTracks" in html
    assert "if (state.filterFavoritesOnly && !track.favorite) await reloadBrowse();" in html
    assert "この条件に一致するお気に入りはありません" in html
    assert "user_id" not in html[
        html.index("function buildBrowseParams"):
        html.index("async function fetchJson")
    ]


if __name__ == "__main__":
    test_database_favorite_filter()
    test_http_favorite_filter()
    test_favorite_filter_ui_contract()
    print("Favorite-only filter tests passed.")
