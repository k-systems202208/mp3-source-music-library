from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
from email.header import Header
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-tailscale-identity-"))
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
    TAILSCALE_PROFILE_HEADER,
    decode_identity_header,
    normalize_login,
    parse_tailscale_identity,
)


class DuplicateHeaders:
    def __init__(self, values: dict[str, list[str]]) -> None:
        self.values = values

    def get_all(self, name: str):
        return self.values.get(name)


def encode_rfc2047(value: str) -> str:
    return Header(value, "utf-8").encode()


def request(
    connection: http.client.HTTPConnection,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    connection.request(method, path, body=body, headers=headers or {})
    response = connection.getresponse()
    payload = response.read()
    return (
        response.status,
        {key.casefold(): value for key, value in response.getheaders()},
        payload,
    )


def current_user(
    port: int,
    *,
    headers: dict[str, str] | None = None,
) -> dict:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, _, payload = request(
            connection,
            "GET",
            "/api/current-user",
            headers=headers,
        )
        assert status == 200, payload.decode("utf-8", errors="replace")
        return json.loads(payload.decode("utf-8"))
    finally:
        connection.close()


def get_owner_cookie(port: int, control_secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "O" * 43
        body = json.dumps(
            {"token": token, "expiresInSeconds": 60},
            separators=(",", ":"),
        ).encode("utf-8")
        status, _, _ = request(
            connection,
            "POST",
            "/api/local-auth/token",
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body)),
                "X-Music-Library-Control-Secret": control_secret,
            },
            body=body,
        )
        assert status == 201

        status, response_headers, _ = request(
            connection,
            "GET",
            f"/api/local-auth/exchange?token={token}",
        )
        assert status == 303
        set_cookie = response_headers["set-cookie"]
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        return set_cookie.split(";", 1)[0]
    finally:
        connection.close()


def test_header_parsing() -> None:
    assert decode_identity_header(" Alice@example.com ") == "Alice@example.com"
    assert normalize_login(" Alice@EXAMPLE.com ") == "alice@example.com"

    encoded_name = encode_rfc2047("戸島 康博")
    identity = parse_tailscale_identity(
        {
            TAILSCALE_LOGIN_HEADER: " User@Example.com ",
            TAILSCALE_NAME_HEADER: encoded_name,
            TAILSCALE_PROFILE_HEADER: "https://example.com/profile.jpg",
        }
    )
    assert identity is not None
    assert identity.subject == "user@example.com"
    assert identity.login_name == "User@Example.com"
    assert identity.display_name == "戸島 康博"
    assert identity.profile_picture_url == "https://example.com/profile.jpg"

    no_login = parse_tailscale_identity(
        {TAILSCALE_NAME_HEADER: encoded_name}
    )
    assert no_login is None

    duplicate = parse_tailscale_identity(
        DuplicateHeaders(
            {
                TAILSCALE_LOGIN_HEADER: [
                    "first@example.com",
                    "second@example.com",
                ]
            }
        )
    )
    assert duplicate is None

    invalid_profile = parse_tailscale_identity(
        {
            TAILSCALE_LOGIN_HEADER: "user@example.com",
            TAILSCALE_PROFILE_HEADER: "javascript:alert(1)",
        }
    )
    assert invalid_profile is not None
    assert invalid_profile.profile_picture_url == ""

    control_character = parse_tailscale_identity(
        {TAILSCALE_LOGIN_HEADER: "user@example.com\nadmin@example.com"}
    )
    assert control_character is None


def test_database_identity_resolution() -> None:
    database_path = IMPORT_ROOT / "database-test.db"
    connection = db.connect_database(
        database_path,
        prepare_migration_backup=False,
    )
    try:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None

        first = db.get_or_create_tailscale_user(
            connection,
            subject="family@example.com",
            display_name="Family A",
            profile_picture_url="https://example.com/a.jpg",
        )
        connection.commit()
        assert first["isOwner"] is False
        assert first["isActive"] is True
        first_id = first["id"]

        # A provider display-name update must not overwrite a future manual
        # profile name.
        connection.execute(
            "UPDATE users SET display_name = ? WHERE id = ?",
            ("家族A", first_id),
        )
        connection.commit()

        second = db.get_or_create_tailscale_user(
            connection,
            subject="FAMILY@example.com",
            display_name="Family A New",
            profile_picture_url="https://example.com/new.jpg",
        )
        connection.commit()
        assert second["id"] == first_id
        assert second["displayName"] == "家族A"

        # An optional profile header may be absent on later requests. The
        # last known valid provider picture must not be erased.
        third = db.get_or_create_tailscale_user(
            connection,
            subject="family@example.com",
            display_name="Family A New",
            profile_picture_url="",
        )
        connection.commit()
        assert third["id"] == first_id

        counts = connection.execute(
            """
            SELECT
              (SELECT COUNT(*) FROM users WHERE is_owner = 1) AS owners,
              (SELECT COUNT(*) FROM users WHERE is_owner = 0) AS members,
              (SELECT COUNT(*) FROM user_identities
                WHERE provider = 'tailscale'
                  AND subject = 'family@example.com') AS identities
            """
        ).fetchone()
        assert counts is not None
        assert int(counts["owners"]) == 1
        assert int(counts["members"]) == 1
        assert int(counts["identities"]) == 1

        metadata = connection.execute(
            """
            SELECT provider_display_name, profile_picture_url
              FROM user_identities
             WHERE provider = 'tailscale'
               AND subject = 'family@example.com'
            """
        ).fetchone()
        assert metadata is not None
        assert metadata["provider_display_name"] == "Family A New"
        assert metadata["profile_picture_url"] == "https://example.com/new.jpg"

        assert db.set_user_active(connection, first_id, False)
        connection.commit()
        disabled = db.get_or_create_tailscale_user(
            connection,
            subject="family@example.com",
            display_name="Family A New",
        )
        connection.commit()
        assert disabled["isActive"] is False

        # The database resolver is compatible with a future owner-linking
        # operation: an existing Tailscale identity may point to the owner.
        linked_subject = "owner@example.com"
        connection.execute(
            """
            INSERT INTO user_identities(
                id, user_id, provider, subject,
                provider_display_name, profile_picture_url,
                created_at, last_seen_at
            ) VALUES (?, ?, 'tailscale', ?, ?, '', ?, '')
            """,
            (
                db.stable_key("idn", "tailscale", linked_subject),
                owner["id"],
                linked_subject,
                "Owner via Tailscale",
                db.utc_now(),
            ),
        )
        connection.commit()

        linked = db.get_or_create_tailscale_user(
            connection,
            subject=linked_subject,
            display_name="Owner via Tailscale",
        )
        connection.commit()
        assert linked["id"] == owner["id"]
        assert linked["isOwner"] is True
    finally:
        connection.close()


def test_http_identity_flow() -> None:
    control_secret = "S" * 48
    music_server = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret=control_secret,
    )
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    try:
        anonymous = current_user(port)
        assert anonymous == {
            "authenticated": False,
            "id": None,
            "displayName": "",
            "isOwner": False,
            "provider": "",
            "skinId": "library",
        }

        tagged_device = current_user(
            port,
            headers={
                TAILSCALE_NAME_HEADER: encode_rfc2047("タグ付き端末"),
            },
        )
        assert tagged_device["authenticated"] is False

        encoded_name = encode_rfc2047("家族 A")
        tailscale_headers = {
            TAILSCALE_LOGIN_HEADER: "Family@Example.com",
            TAILSCALE_NAME_HEADER: encoded_name,
            TAILSCALE_PROFILE_HEADER: "https://example.com/family.jpg",
        }
        family = current_user(port, headers=tailscale_headers)
        assert family["authenticated"] is True
        assert family["provider"] == "tailscale"
        assert family["displayName"] == "家族 A"
        assert family["isOwner"] is False
        family_id = family["id"]

        same_family = current_user(
            port,
            headers={
                TAILSCALE_LOGIN_HEADER: "family@example.com",
                TAILSCALE_NAME_HEADER: "Changed provider name",
            },
        )
        assert same_family["id"] == family_id
        assert same_family["displayName"] == "家族 A"

        # Tailscale identity takes precedence over a local-owner cookie.
        owner_cookie = get_owner_cookie(port, control_secret)
        both = current_user(
            port,
            headers={
                "Cookie": owner_cookie,
                TAILSCALE_LOGIN_HEADER: "other@example.com",
                TAILSCALE_NAME_HEADER: "Other User",
            },
        )
        assert both["provider"] == "tailscale"
        assert both["isOwner"] is False
        assert both["id"] != family_id

        with db.database() as connection:
            db.initialize_database(connection)
            assert db.set_user_active(connection, family_id, False)

        disabled = current_user(port, headers=tailscale_headers)
        assert disabled["authenticated"] is False

        # Concurrent first access must produce one profile and one identity.
        concurrent_headers = {
            TAILSCALE_LOGIN_HEADER: "concurrent@example.com",
            TAILSCALE_NAME_HEADER: "Concurrent User",
        }
        results: list[dict] = []
        errors: list[BaseException] = []
        lock = threading.Lock()

        def worker() -> None:
            try:
                value = current_user(port, headers=concurrent_headers)
                with lock:
                    results.append(value)
            except BaseException as exc:  # pragma: no cover - diagnostic path
                with lock:
                    errors.append(exc)

        workers = [threading.Thread(target=worker) for _ in range(8)]
        for worker_thread in workers:
            worker_thread.start()
        for worker_thread in workers:
            worker_thread.join(timeout=15)

        assert not errors, errors
        assert len(results) == 8
        concurrent_ids = {value["id"] for value in results}
        assert len(concurrent_ids) == 1

        with db.database() as connection:
            db.initialize_database(connection)
            count = connection.execute(
                """
                SELECT COUNT(*)
                  FROM user_identities
                 WHERE provider = 'tailscale'
                   AND subject = 'concurrent@example.com'
                """
            ).fetchone()
            assert count is not None
            assert int(count[0]) == 1
    finally:
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


test_header_parsing()
test_database_identity_resolution()
test_http_identity_flow()
print("Tailscale identity tests passed.")
