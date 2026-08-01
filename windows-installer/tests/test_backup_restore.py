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
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-backup-restore-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import backup_restore  # noqa: E402
import database as db  # noqa: E402
import server  # noqa: E402
from local_auth import SESSION_COOKIE_NAME  # noqa: E402
from tailscale_identity import TAILSCALE_LOGIN_HEADER, TAILSCALE_NAME_HEADER  # noqa: E402


def add_track(path: Path, track_id: str, title: str) -> None:
    connection = db.connect_database(path, prepare_migration_backup=False)
    try:
        db.initialize_database(connection)
        now = db.utc_now()
        connection.execute(
            """
            INSERT OR REPLACE INTO tracks(
                id, relative_path, filename, title, normalized_title,
                file_size, modified_time_ns, audio_file,
                last_scanned_at, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?)
            """,
            (
                track_id,
                f"Test/{track_id}.mp3",
                f"{track_id}.mp3",
                title,
                title.casefold(),
                f"Music/Test/{track_id}.mp3",
                now,
                now,
                now,
            ),
        )
        connection.commit()
    finally:
        connection.close()


def request(
    connection: http.client.HTTPConnection,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    value: dict | None = None,
):
    actual_headers = dict(headers or {})
    body = None
    if value is not None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        actual_headers["Content-Type"] = "application/json"
        actual_headers["Content-Length"] = str(len(body))
    connection.request(method, path, body=body, headers=actual_headers)
    response = connection.getresponse()
    payload = response.read()
    response_headers = {key.casefold(): value for key, value in response.getheaders()}
    if response_headers.get("content-type", "").startswith("application/json"):
        return response.status, json.loads(payload.decode("utf-8"))
    return response.status, payload


def owner_cookie(port: int, secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "B" * 43
        status, _ = request(
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
        assert response.status == 303
        value = dict((key.casefold(), value) for key, value in response.getheaders())["set-cookie"]
        assert SESSION_COOKIE_NAME in value
        return value.split(";", 1)[0]
    finally:
        connection.close()


def test_backup_functions_and_restore_on_next_start() -> None:
    data_root = IMPORT_ROOT / "functional"
    backup_dir = data_root / "Backups"
    database_path = data_root / "library.db"
    data_root.mkdir(parents=True, exist_ok=True)

    add_track(database_path, "current_track", "Current")
    manual = backup_restore.create_manual_backup(
        database_path=database_path,
        backup_dir=backup_dir,
    )
    assert manual["valid"] is True
    assert manual["trackCount"] == 1
    assert manual["kind"] == "manual"

    add_track(database_path, "new_track", "New")
    assert backup_restore.inspect_database(database_path)["trackCount"] == 2

    backups = backup_restore.list_backups(backup_dir)
    assert backups[0]["name"] == manual["name"]
    assert backups[0]["valid"] is True

    request_value = backup_restore.schedule_restore(
        manual["name"], data_root=data_root, backup_dir=backup_dir
    )
    assert request_value["backupName"] == manual["name"]
    assert backup_restore.pending_restore(data_root)["backupName"] == manual["name"]

    restored = backup_restore.apply_pending_restore(data_root)
    assert restored is not None
    assert restored["state"] == "restored"
    assert restored["backupName"] == manual["name"]
    assert restored["preRestoreBackupName"].startswith("library-pre-restore-")
    assert backup_restore.inspect_database(database_path)["trackCount"] == 1
    assert backup_restore.pending_restore(data_root) is None
    assert backup_restore.restore_status(data_root)["state"] == "restored"
    assert (backup_dir / restored["preRestoreBackupName"]).is_file()

    try:
        backup_restore.schedule_restore(
            "../library.db", data_root=data_root, backup_dir=backup_dir
        )
    except ValueError:
        pass
    else:
        raise AssertionError("path traversal must be rejected")


def test_restore_cancel() -> None:
    data_root = IMPORT_ROOT / "cancel"
    backup_dir = data_root / "Backups"
    database_path = data_root / "library.db"
    data_root.mkdir(parents=True, exist_ok=True)
    add_track(database_path, "track", "Track")
    item = backup_restore.create_manual_backup(database_path=database_path, backup_dir=backup_dir)
    backup_restore.schedule_restore(item["name"], data_root=data_root, backup_dir=backup_dir)
    assert backup_restore.cancel_restore(data_root) is True
    assert backup_restore.cancel_restore(data_root) is False



def test_failed_restore_does_not_loop_startup() -> None:
    data_root = IMPORT_ROOT / "failed"
    data_root.mkdir(parents=True, exist_ok=True)
    database_path = data_root / "library.db"
    add_track(database_path, "safe_track", "Safe")
    (data_root / backup_restore.RESTORE_REQUEST_FILENAME).write_text(
        json.dumps({"backupName": "library-missing.db", "requestedAt": "test"}),
        encoding="utf-8",
    )
    result = backup_restore.apply_pending_restore(data_root)
    assert result is not None
    assert result["state"] == "error"
    assert backup_restore.pending_restore(data_root) is None
    assert backup_restore.inspect_database(database_path)["trackCount"] == 1


def test_http_requires_local_owner() -> None:
    # The imported database module uses IMPORT_ROOT/data.
    add_track(db.DATABASE_PATH, "http_track", "HTTP Track")
    control_secret = "R" * 48
    httpd = server.create_server("127.0.0.1", 0, owner_control_secret=control_secret)
    port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, _ = request(connection, "GET", "/api/backups")
        assert status == 403

        tailscale_headers = {
            TAILSCALE_LOGIN_HEADER: "member@example.com",
            TAILSCALE_NAME_HEADER: "Member",
        }
        status, _ = request(
            connection,
            "POST",
            "/api/backups/create",
            headers=tailscale_headers,
            value={},
        )
        assert status == 403

        cookie = owner_cookie(port, control_secret)
        owner_headers = {"Cookie": cookie}
        status, payload = request(connection, "GET", "/api/backups", headers=owner_headers)
        assert status == 200
        assert payload["database"]["valid"] is True

        status, payload = request(
            connection,
            "POST",
            "/api/backups/create",
            headers=owner_headers,
            value={},
        )
        assert status == 201
        backup_name = payload["backup"]["name"]

        status, _ = request(
            connection,
            "POST",
            "/api/backups/restore",
            headers=owner_headers,
            value={"backupName": backup_name, "confirmation": "WRONG"},
        )
        assert status == 400

        status, payload = request(
            connection,
            "POST",
            "/api/backups/restore",
            headers=owner_headers,
            value={"backupName": backup_name, "confirmation": "RESTORE"},
        )
        assert status == 202
        assert payload["scheduled"] is True

        status, payload = request(connection, "GET", "/api/backups", headers=owner_headers)
        assert status == 200
        assert payload["pendingRestore"]["backupName"] == backup_name

        status, payload = request(
            connection,
            "POST",
            "/api/backups/restore/cancel",
            headers=owner_headers,
            value={},
        )
        assert status == 200
        assert payload["cancelled"] is True
    finally:
        connection.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_frontend_contains_backup_screen() -> None:
    html = (SRC / "music-library-search.html").read_text(encoding="utf-8")
    required = [
        'id="backupSection"',
        'id="backupCreateButton"',
        'id="backupList"',
        "BACKUPS_API_URL",
        "scheduleBackupRestore",
        "confirmation:'RESTORE'",
        "currentUser.provider === 'local_owner'",
    ]
    for fragment in required:
        assert fragment in html, fragment


if __name__ == "__main__":
    test_backup_functions_and_restore_on_next_start()
    test_restore_cancel()
    test_failed_restore_does_not_loop_startup()
    test_http_requires_local_owner()
    test_frontend_contains_backup_screen()
    print("Backup and restore tests passed.")
