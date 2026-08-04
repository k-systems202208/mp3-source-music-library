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

IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-user-ui-"))
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


def request(
    connection: http.client.HTTPConnection,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    value: dict | None = None,
) -> tuple[int, dict[str, str], dict | bytes]:
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
    if response_headers.get("content-type", "").startswith("application/json"):
        return response.status, response_headers, json.loads(payload.decode("utf-8"))
    return response.status, response_headers, payload


def get_owner_cookie(port: int, control_secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "U" * 43
        status, _, _ = request(
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
        assert response.status == 200
        set_cookie = dict(
            (key.casefold(), value) for key, value in response.getheaders()
        )["set-cookie"]
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        return set_cookie.split(";", 1)[0]
    finally:
        connection.close()


def test_database_user_listing() -> None:
    path = IMPORT_ROOT / "listing.db"
    connection = db.connect_database(path, prepare_migration_backup=False)
    try:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        member = db.get_or_create_tailscale_user(
            connection,
            subject="member@example.com",
            display_name="家族A",
        )

        timestamp = db.utc_now()
        connection.execute(
            """
            INSERT INTO tracks(
                id, relative_path, filename, title, normalized_title,
                file_size, modified_time_ns, audio_file,
                last_scanned_at, created_at, updated_at
            ) VALUES (
                'track_ui', 'Test/track_ui.mp3', 'track_ui.mp3',
                'Track UI', 'track ui', 1, 1, 'Music/Test/track_ui.mp3',
                ?, ?, ?
            )
            """,
            (timestamp, timestamp, timestamp),
        )
        connection.execute(
            """
            INSERT INTO user_track_state(
                user_id, track_id, favorite, rating,
                play_count, last_played_at, created_at, updated_at
            ) VALUES (?, 'track_ui', 1, NULL, 4, ?, ?, ?)
            """,
            (member["id"], timestamp, timestamp, timestamp),
        )
        connection.commit()

        users = db.list_users_for_management(connection)
        assert users[0]["isOwner"] is True
        listed_member = next(user for user in users if user["id"] == member["id"])
        assert listed_member["displayName"] == "家族A"
        assert listed_member["stateCount"] == 1
        assert listed_member["favoriteCount"] == 1
        assert listed_member["playCount"] == 4
        assert listed_member["canChangeActive"] is True
        assert listed_member["identities"][0]["provider"] == "tailscale"
        assert listed_member["identities"][0]["subject"] == "member@example.com"

        assert db.get_user_by_id(connection, member["id"])["id"] == member["id"]
        assert db.get_user_by_id(connection, "missing") is None
        renamed = db.set_user_display_name(
            connection,
            user_id=member["id"],
            display_name="  家族の表示名  ",
        )
        assert renamed is not None and renamed["displayName"] == "家族の表示名"
        resolved_again = db.get_or_create_tailscale_user(
            connection,
            subject="member@example.com",
            display_name="Tailscale側の新しい名前",
        )
        assert resolved_again["displayName"] == "家族の表示名"
        try:
            db.set_user_display_name(connection, user_id=member["id"], display_name=" ")
        except ValueError as exc:
            assert "表示名" in str(exc)
        else:
            raise AssertionError("blank display name was accepted")
    finally:
        connection.close()


def test_http_user_management() -> None:
    control_secret = "M" * 48
    music_server = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret=control_secret,
    )
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    with db.database() as db_connection:
        db.initialize_database(db_connection)
        timestamp = db.utc_now()
        artist_id = db.upsert_artist(
            db_connection,
            "Original Artist",
            timestamp,
        )
        assert artist_id is not None
        album_id = db.upsert_album(
            db_connection,
            title="Original Album",
            album_artist="Original Artist",
            fallback_artist="Original Artist",
            sort_title="",
            year=None,
            artwork_id=None,
            timestamp=timestamp,
        )
        assert album_id is not None
        db_connection.execute(
            """
            INSERT INTO tracks(
                id, relative_path, filename, title, normalized_title,
                artist_id, album_id, file_size, modified_time_ns, audio_file,
                last_scanned_at, created_at, updated_at
            ) VALUES (
                'track_metadata_permissions', 'Test/metadata.mp3', 'metadata.mp3',
                'Original Title', 'original title', ?, ?, 1, 1,
                'Music/Test/metadata.mp3', ?, ?, ?
            )
            """,
            (artist_id, album_id, timestamp, timestamp, timestamp),
        )
        db_connection.execute(
            """
            INSERT INTO tracks(
                id, relative_path, filename, title, normalized_title,
                artist_id, album_id, file_size, modified_time_ns, audio_file,
                last_scanned_at, created_at, updated_at
            ) VALUES (
                'track_album_permissions_2', 'Test/album2.mp3', 'album2.mp3',
                'Album Track 2', 'album track 2', ?, ?, 1, 1,
                'Music/Test/album2.mp3', ?, ?, ?
            )
            """,
            (artist_id, album_id, timestamp, timestamp, timestamp),
        )
        db_connection.commit()

    family_headers = {
        TAILSCALE_LOGIN_HEADER: "family@example.com",
        TAILSCALE_NAME_HEADER: "Family A",
    }
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, _, payload = request(
            connection,
            "POST",
            "/api/tracks/track_metadata_permissions/title-correction",
            value={"value": "Anonymous Title"},
        )
        assert status == 403
        assert payload["error"] == "owner authentication required"

        status, _, payload = request(connection, "GET", "/api/users")
        assert status == 403
        assert payload["error"] == "owner authentication required"

        status, _, payload = request(connection, "GET", "/api/diagnostics")
        assert status == 403
        assert payload["error"] == "owner authentication required"

        status, _, payload = request(
            connection,
            "PUT",
            "/api/me/profile",
            value={"displayName": "Anonymous"},
        )
        assert status == 401

        status, _, current = request(
            connection,
            "GET",
            "/api/current-user",
            headers=family_headers,
        )
        assert status == 200
        assert current["authenticated"] is True
        assert current["isOwner"] is False
        family_id = current["id"]

        status, _, payload = request(
            connection,
            "PUT",
            "/api/me/profile",
            headers=family_headers,
            value={"displayName": "わたしの表示名"},
        )
        assert status == 200
        assert payload["user"]["displayName"] == "わたしの表示名"
        status, _, current = request(
            connection,
            "GET",
            "/api/current-user",
            headers=family_headers,
        )
        assert status == 200 and current["displayName"] == "わたしの表示名"
        status, _, _ = request(
            connection,
            "PUT",
            "/api/me/profile",
            headers=family_headers,
            value={"displayName": " "},
        )
        assert status == 400

        # Metadata edits are owner-only even when a family user is authenticated.
        status, _, payload = request(
            connection,
            "POST",
            "/api/tracks/track_metadata_permissions/title-correction",
            headers=family_headers,
            value={"value": "Family Title"},
        )
        assert status == 403
        assert payload["error"] == "owner authentication required"

        status, _, payload = request(
            connection,
            "POST",
            f"/api/artists/{artist_id}/correction",
            headers=family_headers,
            value={"value": "Family Artist"},
        )
        assert status == 403
        assert payload["error"] == "owner authentication required"

        status, _, payload = request(
            connection,
            "POST",
            f"/api/albums/{album_id}/correction",
            headers=family_headers,
            value={"value": "Family Album"},
        )
        assert status == 403
        assert payload["error"] == "owner authentication required"

        with db.database() as db_connection:
            row = db_connection.execute(
                """
                SELECT t.title_override, ar.display_name_override
                  FROM tracks t
                  JOIN artists ar ON ar.id = t.artist_id
                 WHERE t.id = 'track_metadata_permissions'
                """
            ).fetchone()
            assert row["title_override"] is None
            assert row["display_name_override"] is None

        status, _, _ = request(
            connection,
            "GET",
            "/api/users",
            headers=family_headers,
        )
        assert status == 403

        status, _, _ = request(
            connection,
            "POST",
            f"/api/users/{family_id}/active",
            headers=family_headers,
            value={"active": False},
        )
        assert status == 403

        owner_cookie = get_owner_cookie(port, control_secret)
        owner_headers = {"Cookie": owner_cookie}

        status, _, payload = request(
            connection,
            "GET",
            "/api/users",
            headers=owner_headers,
        )
        assert status == 200
        users = payload["users"]
        owner = next(user for user in users if user["isOwner"])
        family = next(user for user in users if user["id"] == family_id)

        status, _, payload = request(
            connection,
            "POST",
            "/api/tracks/track_metadata_permissions/title-correction",
            headers=owner_headers,
            value={"value": "Owner Title"},
        )
        assert status == 200
        assert payload["name"] == "Owner Title"

        # A Tailscale identity already linked to the owner may view the list,
        # but sensitive enable/disable changes still require the local owner.
        owner_remote_subject = "owner-remote@example.com"
        with db.database() as db_connection:
            db.initialize_database(db_connection)
            db_connection.execute(
                """
                INSERT INTO user_identities(
                    id, user_id, provider, subject,
                    provider_display_name, profile_picture_url,
                    created_at, last_seen_at
                ) VALUES (?, ?, 'tailscale', ?, 'Owner Remote', '', ?, '')
                """,
                (
                    db.stable_key("idn", "tailscale", owner_remote_subject),
                    owner["id"],
                    owner_remote_subject,
                    db.utc_now(),
                ),
            )
            db_connection.commit()

        owner_remote_headers = {
            TAILSCALE_LOGIN_HEADER: owner_remote_subject,
            TAILSCALE_NAME_HEADER: "Owner Remote",
        }
        status, _, remote_payload = request(
            connection,
            "GET",
            "/api/users",
            headers=owner_remote_headers,
        )
        assert status == 200
        assert remote_payload["viewer"]["isOwner"] is True
        assert remote_payload["viewer"]["provider"] == "tailscale"

        status, _, payload = request(
            connection,
            "POST",
            f"/api/artists/{artist_id}/correction",
            headers=owner_remote_headers,
            value={"value": "Owner Artist"},
        )
        assert status == 200
        assert payload["artist"] == "Owner Artist"

        status, _, payload = request(
            connection,
            "POST",
            f"/api/albums/{album_id}/correction",
            headers=owner_remote_headers,
            value={"value": "Owner Album"},
        )
        assert status == 200
        assert payload["album"] == "Owner Album"
        assert payload["updatedTracks"] == 2

        status, _, albums_payload = request(
            connection,
            "GET",
            "/api/browse?view=albums&limit=20",
            headers=owner_remote_headers,
        )
        assert status == 200
        album_group = next(
            item for item in albums_payload["items"] if item["display"] == "Owner Album"
        )
        assert album_group["albumId"] == album_id
        assert album_group["count"] == 2

        status, _, diagnostics = request(
            connection,
            "GET",
            "/api/diagnostics",
            headers=owner_remote_headers,
        )
        assert status == 200
        assert diagnostics["application"]["version"] == "2.7.7"
        assert diagnostics["database"]["healthy"] is True
        assert diagnostics["database"]["schemaVersion"] == 7
        assert diagnostics["database"]["tracks"] == 2
        assert diagnostics["database"]["availableTracks"] == 2
        assert diagnostics["paths"]["music"]["exists"] is True

        status, _, _ = request(
            connection,
            "POST",
            f"/api/users/{family_id}/active",
            headers=owner_remote_headers,
            value={"active": False},
        )
        assert status == 403
        assert owner["canChangeActive"] is False
        assert family["canChangeActive"] is True
        assert family["isActive"] is True
        assert family["identities"][0]["subject"] == "family@example.com"

        status, _, payload = request(
            connection,
            "POST",
            f"/api/users/{owner['id']}/active",
            headers=owner_headers,
            value={"active": False},
        )
        assert status == 409
        assert "オーナー" in payload["error"]

        status, _, _ = request(
            connection,
            "POST",
            f"/api/users/{family_id}/active",
            headers=owner_headers,
            value={"active": "false"},
        )
        assert status == 400

        status, _, payload = request(
            connection,
            "POST",
            f"/api/users/{family_id}/active",
            headers=owner_headers,
            value={"active": False},
        )
        assert status == 200
        assert payload["user"]["isActive"] is False

        status, _, current = request(
            connection,
            "GET",
            "/api/current-user",
            headers=family_headers,
        )
        assert status == 200
        assert current["authenticated"] is False

        status, _, payload = request(
            connection,
            "POST",
            f"/api/users/{family_id}/active",
            headers=owner_headers,
            value={"active": True},
        )
        assert status == 200
        assert payload["user"]["isActive"] is True

        status, _, current = request(
            connection,
            "GET",
            "/api/current-user",
            headers=family_headers,
        )
        assert status == 200
        assert current["authenticated"] is True

        status, _, _ = request(
            connection,
            "POST",
            "/api/users/missing/active",
            headers=owner_headers,
            value={"active": False},
        )
        assert status == 404
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


def test_html_user_interface() -> None:
    html = (SRC / "music-library-search.html").read_text(encoding="utf-8")
    required = [
        'id="userMenuButton"',
        'id="userModal"',
        'id="currentUserName"',
        'id="profileSection"',
        'id="profileDisplayNameInput"',
        'id="profileSaveButton"',
        'id="tailscaleClaimSection"',
        'id="ownerLinkSection"',
        'id="userManagementSection"',
        'id="diagnosticsSection"',
        'id="diagnosticsDownloadButton"',
        "CURRENT_USER_API_URL",
        "CURRENT_USER_PROFILE_API_URL",
        "DIAGNOSTICS_API_URL",
        "USERS_API_URL",
        "OWNER_LINK_START_API_URL",
        "OWNER_LINK_CLAIM_API_URL",
        "OWNER_LINK_CONFIRM_API_URL",
        "OWNER_LINK_CANCEL_API_URL",
        "loadManagedUsers",
        "updateUserActive",
        "saveCurrentUserDisplayName",
        "loadDiagnostics",
        "downloadDiagnostics",
        "confirmed:true",
        "function canEditMetadata()",
        "const editable = canEditMetadata();",
        "const artistEdit = editable && track.artistDbId",
        "const edit = canEditMetadata() && group.key",
        "${editable ? '<button type=\"button\" class=\"icon-btn\" data-action=\"edit\"",
        "data-player-browse",
        "openTrackMetadataView",
        'data-action="edit-album"',
        "startEditAlbum",
        "renderPlayerMetadata(els.playerArtist, track)",
        "renderPlayerMetadata(els.playerModalArtist, currentPlayerTrack)",
    ]
    for marker in required:
        assert marker in html, marker

    assert "ユーザーを削除" not in html
    assert 'id="btnCorrectedOnly"' not in html
    assert "訂正済" not in html
    assert "利用を停止" in html
    assert "自宅PCの管理画面から" in html


test_database_user_listing()
test_http_user_management()
test_html_user_interface()
print("User management UI tests passed.")
