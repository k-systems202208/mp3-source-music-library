from __future__ import annotations

import http.client
import io
import json
import os
import sys
import tempfile
import threading
from email.message import Message
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-local-auth-import-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402
import server  # noqa: E402
from local_auth import LocalOwnerAuth, SESSION_COOKIE_NAME  # noqa: E402


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def test_in_memory_auth_manager() -> None:
    secret = "C" * 48
    clock = FakeClock()
    auth = LocalOwnerAuth(secret, clock=clock, session_ttl_seconds=60)

    assert auth.control_secret_matches(secret)
    assert not auth.control_secret_matches("wrong")

    token = "T" * 43
    assert auth.register_one_time_token(token, ttl_seconds=10) == 10
    assert auth.consume_one_time_token(token)
    assert not auth.consume_one_time_token(token)

    expired = "E" * 43
    auth.register_one_time_token(expired, ttl_seconds=10)
    clock.advance(11)
    assert not auth.consume_one_time_token(expired)

    issue = auth.issue_session()
    assert issue.max_age == 60
    assert auth.validate_session(issue.value)

    restarted = LocalOwnerAuth(secret, clock=clock, session_ttl_seconds=60)
    assert not restarted.validate_session(issue.value)

    clock.advance(61)
    assert not auth.validate_session(issue.value)


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
    return response.status, {key.casefold(): value for key, value in response.getheaders()}, payload



def test_rejected_post_consumes_request_body() -> None:
    """A rejected POST must not leave unread bytes in the TCP receive buffer."""
    control_secret = "S" * 48
    body = json.dumps(
        {"token": "A" * 43, "expiresInSeconds": 60},
        separators=(",", ":"),
    ).encode("utf-8")

    handler = object.__new__(server.MusicLibraryHandler)
    handler.path = "/api/local-auth/token"
    handler.headers = Message()
    handler.headers["Content-Type"] = "application/json"
    handler.headers["Content-Length"] = str(len(body))
    handler.rfile = io.BytesIO(body)
    handler._request_body_cache = None
    handler.server = SimpleNamespace(
        local_owner_auth=LocalOwnerAuth(control_secret)
    )

    captured: dict[str, object] = {}

    def capture_json(value: object, status: object = 200) -> None:
        captured["value"] = value
        captured["status"] = status

    handler.send_json = capture_json
    handler.do_POST()

    assert handler.rfile.tell() == len(body)
    assert int(captured["status"]) == 403
    assert captured["value"] == {"error": "forbidden"}


def test_http_flow() -> None:
    control_secret = "S" * 48
    music_server = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret=control_secret,
    )
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        status, _, payload = request(connection, "GET", "/api/current-user")
        assert status == 200
        current = json.loads(payload.decode("utf-8"))
        assert current == {
            "authenticated": False,
            "id": None,
            "displayName": "",
            "isOwner": False,
            "provider": "",
        }

        token = "A" * 43
        body = json.dumps(
            {"token": token, "expiresInSeconds": 60},
            separators=(",", ":"),
        ).encode("utf-8")

        status, _, _ = request(
            connection,
            "POST",
            "/api/local-auth/token",
            headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            body=body,
        )
        assert status == 403

        status, _, payload = request(
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
        registered = json.loads(payload.decode("utf-8"))
        assert registered == {"registered": True, "expiresInSeconds": 60}

        status, headers, payload = request(
            connection,
            "GET",
            f"/api/local-auth/exchange?token={token}",
        )
        assert status == 303
        assert payload == b""
        assert headers["location"] == "/music-library-search.html"
        set_cookie = headers["set-cookie"]
        assert f"{SESSION_COOKIE_NAME}=" in set_cookie
        assert "Path=/" in set_cookie
        assert "HttpOnly" in set_cookie
        assert "SameSite=Strict" in set_cookie
        assert "Max-Age=43200" in set_cookie
        cookie_pair = set_cookie.split(";", 1)[0]

        status, _, payload = request(
            connection,
            "GET",
            "/api/current-user",
            headers={"Cookie": cookie_pair},
        )
        assert status == 200
        current = json.loads(payload.decode("utf-8"))
        assert current["authenticated"] is True
        assert current["isOwner"] is True
        assert current["provider"] == "local_owner"
        assert current["displayName"] == db.OWNER_DEFAULT_DISPLAY_NAME
        assert str(current["id"]).startswith("usr_")

        status, _, _ = request(
            connection,
            "GET",
            f"/api/local-auth/exchange?token={token}",
        )
        assert status == 401
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)

    # Sessions are intentionally process-memory only. A fresh server rejects
    # a cookie issued by the previous server even when the control secret is the same.
    restarted = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret=control_secret,
    )
    restarted_port = int(restarted.server_address[1])
    restarted_thread = threading.Thread(target=restarted.serve_forever, daemon=True)
    restarted_thread.start()
    restarted_connection = http.client.HTTPConnection(
        "127.0.0.1", restarted_port, timeout=5
    )
    try:
        status, _, payload = request(
            restarted_connection,
            "GET",
            "/api/current-user",
            headers={"Cookie": cookie_pair},
        )
        assert status == 200
        current = json.loads(payload.decode("utf-8"))
        assert current["authenticated"] is False
    finally:
        restarted_connection.close()
        restarted.shutdown()
        restarted.server_close()
        restarted_thread.join(timeout=5)


test_in_memory_auth_manager()
test_rejected_post_consumes_request_body()
test_http_flow()
print("Local owner authentication tests passed.")
