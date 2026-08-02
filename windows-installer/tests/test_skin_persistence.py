from __future__ import annotations

import http.client
import json
import os
import sqlite3
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-skin-persistence-import-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import backup_restore  # noqa: E402
import database as db  # noqa: E402
import server  # noqa: E402
from local_auth import SESSION_COOKIE_NAME  # noqa: E402
from tailscale_identity import (  # noqa: E402
    TAILSCALE_LOGIN_HEADER,
    TAILSCALE_NAME_HEADER,
)


def raw_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def request_json(
    connection: http.client.HTTPConnection,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    value: object | None = None,
) -> tuple[int, dict]:
    body = None
    request_headers = dict(headers or {})
    if value is not None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
        request_headers["Content-Length"] = str(len(body))
    connection.request(method, path, body=body, headers=request_headers)
    response = connection.getresponse()
    payload = response.read()
    decoded = json.loads(payload.decode("utf-8")) if payload else {}
    return response.status, decoded


def get_owner_cookie(port: int, control_secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "K" * 43
        status, _ = request_json(
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
        set_cookie = response.getheader("Set-Cookie") or ""
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        return set_cookie.split(";", 1)[0]
    finally:
        connection.close()


def start_server(control_secret: str) -> tuple[object, int, threading.Thread]:
    music_server = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret=control_secret,
    )
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()
    return music_server, port, thread


def stop_server(music_server: object, thread: threading.Thread) -> None:
    music_server.shutdown()
    music_server.server_close()
    thread.join(timeout=5)


def test_schema_v7_and_database_functions() -> None:
    with db.database(prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        assert db.read_schema_version(connection) == 7
        owner = db.get_owner_user(connection)
        assert owner is not None
        owner_id = str(owner["id"])
        assert db.get_user_skin(connection, owner_id) == "library"

        saved = db.set_user_skin(
            connection,
            user_id=owner_id,
            skin_id="NeOn",
        )
        assert saved["skinId"] == "neon"
        assert db.get_user_skin(connection, owner_id) == "neon"

        try:
            db.set_user_skin(connection, user_id=owner_id, skin_id="unknown")
        except ValueError as exc:
            assert "not supported" in str(exc)
        else:
            raise AssertionError("Unsupported skin was accepted")

        connection.execute("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            "UPDATE user_preferences SET skin_id = 'broken' WHERE user_id = ?",
            (owner_id,),
        )
        assert db.get_user_skin(connection, owner_id) == "library"
        connection.execute("PRAGMA ignore_check_constraints = OFF")
        connection.execute(
            "UPDATE user_preferences SET skin_id = 'neon' WHERE user_id = ?",
            (owner_id,),
        )


def test_schema_v5_migration_and_backup() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)
        database_path = root / "library.db"
        backup_dir = root / "Backups"
        connection = raw_connection(database_path)
        try:
            db.initialize_database(connection)
            connection.execute("DROP TABLE user_preferences")
            connection.execute(
                "UPDATE schema_info SET value = '5' WHERE key = 'schema_version'"
            )
            connection.commit()
        finally:
            connection.close()

        backup = db.create_pre_v272_migration_backup(
            database_path,
            backup_dir=backup_dir,
        )
        assert backup is not None
        assert backup.name.startswith("library-pre-v2.7.2-")
        assert db.database_schema_version(backup) == 5
        inspected = backup_restore.inspect_database(backup)
        assert inspected["valid"] is True
        assert inspected["schemaVersion"] == 5

        connection = raw_connection(database_path)
        try:
            db.initialize_database(connection)
            assert db.read_schema_version(connection) == 7
            row = connection.execute(
                "SELECT skin_id FROM user_preferences"
            ).fetchone()
            assert row is not None and row["skin_id"] == "library"
        finally:
            connection.close()


def test_user_separation_and_owner_link() -> None:
    with db.database(prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        owner_id = str(owner["id"])
        db.set_user_skin(connection, user_id=owner_id, skin_id="midnight")

        family = db.get_or_create_tailscale_user(
            connection,
            subject="skin-family@example.com",
            display_name="Skin Family",
        )
        family_id = str(family["id"])
        assert family_id != owner_id
        assert db.get_user_skin(connection, family_id) == "library"
        db.set_user_skin(connection, user_id=family_id, skin_id="candy")

        assert db.get_user_skin(connection, owner_id) == "midnight"
        assert db.get_user_skin(connection, family_id) == "candy"

        linked = db.link_tailscale_identity_to_owner(
            connection,
            subject="skin-family@example.com",
            expected_candidate_user_id=family_id,
        )
        assert linked["id"] == owner_id
        assert db.get_user_skin(connection, owner_id) == "midnight"
        assert connection.execute(
            "SELECT COUNT(*) FROM users WHERE id = ?",
            (family_id,),
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM user_preferences WHERE user_id = ?",
            (family_id,),
        ).fetchone()[0] == 0

        resolved = db.get_or_create_tailscale_user(
            connection,
            subject="skin-family@example.com",
            display_name="Skin Family",
        )
        assert resolved["id"] == owner_id
        assert db.get_user_skin(connection, str(resolved["id"])) == "midnight"


def test_http_persistence_and_restart() -> None:
    with db.database(prepare_migration_backup=False) as connection:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        db.set_user_skin(connection, user_id=str(owner["id"]), skin_id="library")

    secret = "S" * 48
    music_server, port, thread = start_server(secret)
    owner_cookie = get_owner_cookie(port, secret)
    owner_headers = {"Cookie": owner_cookie}
    family_headers = {
        TAILSCALE_LOGIN_HEADER: "skin-http-family@example.com",
        TAILSCALE_NAME_HEADER: "Skin HTTP Family",
    }

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, anonymous = request_json(connection, "GET", "/api/current-user")
        assert status == 200
        assert anonymous["authenticated"] is False
        assert anonymous["skinId"] == "library"

        status, payload = request_json(
            connection,
            "PUT",
            "/api/me/skin",
            value={"skinId": "neon"},
        )
        assert status == 401
        assert payload["error"] == "authenticated user is required"

        status, owner = request_json(
            connection,
            "GET",
            "/api/current-user",
            headers=owner_headers,
        )
        assert status == 200 and owner["skinId"] == "library"

        status, saved = request_json(
            connection,
            "PUT",
            "/api/me/skin",
            headers=owner_headers,
            value={"skinId": "candy"},
        )
        assert status == 200 and saved["skinId"] == "candy"

        status, family = request_json(
            connection,
            "GET",
            "/api/current-user",
            headers=family_headers,
        )
        assert status == 200 and family["skinId"] == "library"

        status, saved = request_json(
            connection,
            "PUT",
            "/api/me/skin",
            headers=family_headers,
            value={"skinId": "monochrome"},
        )
        assert status == 200 and saved["skinId"] == "monochrome"

        status, owner = request_json(
            connection,
            "GET",
            "/api/current-user",
            headers=owner_headers,
        )
        assert status == 200 and owner["skinId"] == "candy"

        status, payload = request_json(
            connection,
            "PUT",
            "/api/me/skin",
            headers=owner_headers,
            value={"skinId": "javascript:alert(1)"},
        )
        assert status == 400
        assert "not supported" in payload["error"]
    finally:
        connection.close()
        stop_server(music_server, thread)

    restarted, restarted_port, restarted_thread = start_server(secret)
    restarted_owner_cookie = get_owner_cookie(restarted_port, secret)
    connection = http.client.HTTPConnection("127.0.0.1", restarted_port, timeout=10)
    try:
        status, owner = request_json(
            connection,
            "GET",
            "/api/current-user",
            headers={"Cookie": restarted_owner_cookie},
        )
        assert status == 200 and owner["skinId"] == "candy"

        status, family = request_json(
            connection,
            "GET",
            "/api/current-user",
            headers=family_headers,
        )
        assert status == 200 and family["skinId"] == "monochrome"
    finally:
        connection.close()
        stop_server(restarted, restarted_thread)


test_schema_v7_and_database_functions()
test_schema_v5_migration_and_backup()
test_user_separation_and_owner_link()
test_http_persistence_and_restart()
print("Skin persistence tests passed.")
