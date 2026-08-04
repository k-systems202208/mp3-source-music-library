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
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-home-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402
import server  # noqa: E402
from tailscale_identity import TAILSCALE_LOGIN_HEADER, TAILSCALE_NAME_HEADER  # noqa: E402


def insert_track(
    connection,
    track_id: str,
    *,
    title: str,
    date_added: str,
    artist: str = "Test Artist",
    album: str = "Test Album",
) -> None:
    timestamp = db.utc_now()
    artist_id = db.upsert_artist(connection, artist, timestamp)
    album_id = db.upsert_album(
        connection,
        title=album,
        album_artist=artist,
        fallback_artist=artist,
        sort_title="",
        year=None,
        artwork_id=None,
        timestamp=timestamp,
    )
    connection.execute(
        """
        INSERT INTO tracks(
            id, relative_path, filename, title, normalized_title,
            artist_id, album_id, date_added,
            file_size, modified_time_ns, audio_file, is_available,
            last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 1, ?, 1, ?, ?, ?)
        """,
        (
            track_id,
            f"Test/{track_id}.mp3",
            f"{track_id}.mp3",
            title,
            title.casefold(),
            artist_id,
            album_id,
            date_added,
            f"Music/Test/{track_id}.mp3",
            timestamp,
            timestamp,
            timestamp,
        ),
    )


def set_state(
    connection,
    user_id: str,
    track_id: str,
    *,
    plays: int = 0,
    last_played: str = "",
    favorite: bool = False,
    updated_at: str = "2026-08-01T00:00:00+00:00",
) -> None:
    connection.execute(
        """
        INSERT INTO user_track_state(
            user_id, track_id, favorite, rating,
            play_count, last_played_at, created_at, updated_at
        ) VALUES (?, ?, ?, NULL, ?, ?, ?, ?)
        """,
        (
            user_id,
            track_id,
            1 if favorite else 0,
            plays,
            last_played,
            updated_at,
            updated_at,
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
        token = "H" * 43
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


def populate(connection):
    owner = db.get_owner_user(connection)
    assert owner is not None
    family = db.get_or_create_tailscale_user(
        connection,
        subject="family-home@example.com",
        display_name="家族ホーム",
    )
    insert_track(connection, "track_a", title="Alpha", date_added="2026-07-01T00:00:00+00:00")
    insert_track(connection, "track_b", title="Bravo", date_added="2026-07-20T00:00:00+00:00")
    insert_track(connection, "track_c", title="Charlie", date_added="2026-07-31T00:00:00+00:00")
    insert_track(connection, "track_d", title="Delta", date_added="2026-06-01T00:00:00+00:00")

    set_state(
        connection,
        str(owner["id"]),
        "track_a",
        plays=4,
        last_played="2026-07-31T10:00:00+00:00",
        favorite=True,
    )
    set_state(
        connection,
        str(owner["id"]),
        "track_b",
        plays=8,
        last_played="2026-07-30T10:00:00+00:00",
    )
    set_state(
        connection,
        str(owner["id"]),
        "track_c",
        plays=2,
        last_played="2026-08-01T01:00:00+00:00",
        favorite=True,
    )
    set_state(
        connection,
        str(family["id"]),
        "track_d",
        plays=9,
        last_played="2026-08-01T02:00:00+00:00",
        favorite=True,
    )
    return owner, family


def ids(section):
    return [item["id"] for item in section["items"]]


def test_database_library_home() -> None:
    path = IMPORT_ROOT / "home.db"
    with db.database(path, prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        owner, family = populate(connection)

        home = db.library_home(connection, user_id=str(owner["id"]), section_limit=2)
        assert home["authenticated"] is True
        assert ids(home["recentlyPlayed"]) == ["track_c", "track_a"]
        assert home["recentlyPlayed"]["total"] == 3
        assert ids(home["mostPlayed"]) == ["track_b", "track_a"]
        assert ids(home["favorites"]) == ["track_a", "track_c"]
        assert ids(home["recentlyAdded"]) == ["track_c", "track_b"]
        assert all(item["id"] != "track_d" for item in home["recentlyPlayed"]["items"])

        family_home = db.library_home(
            connection,
            user_id=str(family["id"]),
            section_limit=8,
        )
        assert ids(family_home["recentlyPlayed"]) == ["track_d"]
        assert ids(family_home["favorites"]) == ["track_d"]
        assert ids(family_home["mostPlayed"]) == ["track_d"]

        anonymous = db.library_home(connection, user_id=None, section_limit=2)
        assert anonymous["authenticated"] is False
        assert anonymous["recentlyPlayed"]["items"] == []
        assert anonymous["favorites"]["items"] == []
        assert anonymous["mostPlayed"]["items"] == []
        assert ids(anonymous["recentlyAdded"]) == ["track_c", "track_b"]

        recent = db.browse_library(
            connection,
            view="songs",
            sort="recent",
            user_id=str(owner["id"]),
            played_only=True,
        )
        assert [item["id"] for item in recent["items"]] == ["track_c", "track_a", "track_b"]
        assert recent["playedOnly"] is True


def test_http_library_home() -> None:
    secret = "L" * 48
    music_server = server.create_server("127.0.0.1", 0, owner_control_secret=secret)
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    with db.database() as connection:
        db.initialize_database(connection)
        owner, family = populate(connection)

    owner_cookie = get_owner_cookie(port, secret)
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, payload = request_json(connection, "GET", "/api/home?limit=2")
        assert status == 200
        assert payload["authenticated"] is False
        assert payload["recentlyPlayed"]["items"] == []
        assert ids(payload["recentlyAdded"]) == ["track_c", "track_b"]

        status, payload = request_json(
            connection,
            "GET",
            "/api/home?limit=2",
            headers={"Cookie": owner_cookie},
        )
        assert status == 200
        assert payload["authenticated"] is True
        assert ids(payload["recentlyPlayed"]) == ["track_c", "track_a"]
        assert ids(payload["favorites"]) == ["track_a", "track_c"]

        status, payload = request_json(
            connection,
            "GET",
            "/api/home?limit=8",
            headers={
                TAILSCALE_LOGIN_HEADER: "family-home@example.com",
                TAILSCALE_NAME_HEADER: "Family Home",
            },
        )
        assert status == 200
        assert ids(payload["recentlyPlayed"]) == ["track_d"]
        assert ids(payload["favorites"]) == ["track_d"]

        status, payload = request_json(connection, "GET", "/api/home?limit=0")
        assert status == 400
        assert "limit" in payload["error"]

        # The client cannot select another user's state through query parameters.
        status, payload = request_json(
            connection,
            "GET",
            f"/api/home?limit=8&userId={family['id']}",
            headers={"Cookie": owner_cookie},
        )
        assert status == 200
        assert "track_d" not in ids(payload["recentlyPlayed"])
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


def test_library_home_ui_contract() -> None:
    html = (ROOT / "src" / "music-library-search.html").read_text(encoding="utf-8")
    server_text = (ROOT / "src" / "server.py").read_text(encoding="utf-8")
    database_text = (ROOT / "src" / "database.py").read_text(encoding="utf-8")
    paths_text = (ROOT / "src" / "paths.py").read_text(encoding="utf-8")
    launcher_text = (ROOT / "src" / "launcher.py").read_text(encoding="utf-8")

    assert 'APP_VERSION = "2.7.7"' in paths_text
    assert 'APP_VERSION = "2.7.7"' in launcher_text
    assert 'server_version = "MusicLibrary/SQLiteAPI2.7.7"' in server_text
    assert 'data-view="home"' in html
    assert "view: 'home'" in html
    assert "const HOME_API_URL = './api/home';" in html
    assert "最近再生した曲" in html
    assert "お気に入り" in html
    assert "よく聴く曲" in html
    assert "最近追加した曲" in html
    assert "function captureHomePlaybackContext" in html
    assert "section.playedOnly" in html
    assert "userId" not in html[html.index("async function loadHome"):html.index("function openBrowseView")]
    assert 'HOME_ROUTE = "/api/home"' in server_text
    assert "def handle_home(" in server_text
    assert "def library_home(" in database_text
    assert '"recent":' in database_text
    assert "played_only" in database_text
    assert ".home-panel{" in html
    assert "grid-template-columns:minmax(0,1fr);" in html
    assert "#homeSections{" in html
    assert ".home-track-row{\n    display:flex;" in html
    assert "flex:0 0 clamp(178px,23%,218px);" in html
    assert ".home-track-card{flex-basis:min(72vw,218px);}" in html
    assert "grid-auto-flow:column;" not in html


if __name__ == "__main__":
    test_database_library_home()
    test_http_library_home()
    test_library_home_ui_contract()
    print("Library home tests passed.")
