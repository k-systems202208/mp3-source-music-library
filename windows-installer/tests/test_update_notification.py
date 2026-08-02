from __future__ import annotations

import http.client
import json
import os
import sys
import tempfile
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-update-notification-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import server  # noqa: E402
import update_check  # noqa: E402
from local_auth import SESSION_COOKIE_NAME  # noqa: E402
from tailscale_identity import TAILSCALE_LOGIN_HEADER, TAILSCALE_NAME_HEADER  # noqa: E402


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
    response_headers = {key.casefold(): val for key, val in response.getheaders()}
    if response_headers.get("content-type", "").startswith("application/json"):
        return response.status, json.loads(payload.decode("utf-8"))
    return response.status, payload


def owner_cookie(port: int, secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "U" * 43
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
        assert response.status == 200
        cookie = dict((key.casefold(), val) for key, val in response.getheaders())["set-cookie"]
        assert SESSION_COOKIE_NAME in cookie
        return cookie.split(";", 1)[0]
    finally:
        connection.close()


def fake_release(
    version: str = "2.8.0",
    *,
    prerelease: bool = False,
    draft: bool = False,
    published_at: str = "2026-08-02T00:00:00Z",
) -> dict:
    return {
        "tag_name": f"v{version}",
        "name": f"Music Library v{version}",
        "html_url": (
            "https://github.com/k-systems202208/"
            f"mp3-source-music-library/releases/tag/v{version}"
        ),
        "published_at": published_at,
        "draft": draft,
        "prerelease": prerelease,
    }


def release_list(latest: str = "2.8.0") -> list[dict]:
    return [
        fake_release(latest, prerelease=True),
        fake_release("2.7.0", prerelease=True, published_at="2026-07-31T00:00:00Z"),
    ]


def test_version_and_url_validation() -> None:
    assert update_check.CURRENT_VERSION == "2.7.3"
    assert update_check.GITHUB_API_URL.endswith("/releases?per_page=100")
    assert "/releases/latest" not in update_check.GITHUB_API_URL
    assert update_check.parse_version("v2.7.3") == (2, 7, 3)
    assert update_check.is_newer_version("2.8.0", "2.7.1") is True
    assert update_check.is_newer_version("2.7.1", "2.7.1") is False
    assert update_check.safe_release_url(fake_release()["html_url"])
    assert update_check.safe_release_url("http://github.com/example/release") == ""
    assert update_check.safe_release_url("https://evil.example/releases/v2.8.0") == ""


def test_release_selection_includes_prereleases_and_excludes_drafts() -> None:
    selected = update_check._select_latest_published_release(
        [
            fake_release("9.0.0", draft=True),
            {"tag_name": "nightly", "draft": False, "prerelease": True},
            fake_release("2.6.3", prerelease=True),
            fake_release("2.7.0", prerelease=True),
        ]
    )
    assert selected["tag_name"] == "v2.7.0"
    assert selected["prerelease"] is True

    # Selection is semantic-version based rather than relying on API list order.
    selected = update_check._select_latest_published_release(
        [fake_release("2.8.0", prerelease=True), fake_release("2.10.0", prerelease=True)]
    )
    assert selected["tag_name"] == "v2.10.0"

    # A full release wins over a prerelease when tags normalize to the same version.
    selected = update_check._select_latest_published_release(
        [
            fake_release("3.0.0-rc1", prerelease=True, published_at="2026-09-02T00:00:00Z"),
            fake_release("3.0.0", prerelease=False, published_at="2026-09-01T00:00:00Z"),
        ]
    )
    assert selected["tag_name"] == "v3.0.0"


def test_prerelease_only_repository_matches_real_release_policy() -> None:
    result = update_check.check_for_update(
        data_root=IMPORT_ROOT / "prerelease-only",
        current_version="2.7.1",
        fetch=lambda *_: [
            fake_release("2.7.0", prerelease=True),
            fake_release("2.6.3", prerelease=True),
            fake_release("2.6.2", prerelease=True),
            fake_release("2.6.1", prerelease=True),
        ],
        now=datetime(2026, 8, 1, 4, 20, tzinfo=timezone.utc),
    )
    assert result["source"] == "network"
    assert result["latestVersion"] == "2.7.0"
    assert result["isPrerelease"] is True
    assert result["updateAvailable"] is False


def test_network_result_and_cache() -> None:
    root = IMPORT_ROOT / "cache"
    calls: list[tuple[str, float]] = []

    def fetch(url: str, timeout: float) -> list[dict]:
        calls.append((url, timeout))
        return release_list("2.8.0")

    now = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
    result = update_check.check_for_update(
        data_root=root,
        current_version="2.7.1",
        fetch=fetch,
        now=now,
    )
    assert result["updateAvailable"] is True
    assert result["latestVersion"] == "2.8.0"
    assert result["isPrerelease"] is True
    assert result["source"] == "network"
    assert len(calls) == 1
    assert (root / update_check.CACHE_FILENAME).is_file()

    cached = update_check.check_for_update(
        data_root=root,
        current_version="2.7.1",
        fetch=lambda *_: (_ for _ in ()).throw(AssertionError("network must not run")),
        now=now + timedelta(hours=2),
    )
    assert cached["source"] == "cache"
    assert cached["updateAvailable"] is True
    assert cached["isPrerelease"] is True


def test_force_and_stale_cache_fallback() -> None:
    root = IMPORT_ROOT / "stale"
    now = datetime(2026, 8, 1, 1, 0, tzinfo=timezone.utc)
    update_check.check_for_update(
        data_root=root,
        current_version="2.7.1",
        fetch=lambda *_: release_list("2.8.0"),
        now=now,
    )

    def fail(*_args):
        raise update_check.UpdateCheckError("offline")

    stale = update_check.check_for_update(
        data_root=root,
        current_version="2.7.1",
        force=True,
        fetch=fail,
        now=now + timedelta(days=2),
    )
    assert stale["source"] == "stale-cache"
    assert stale["updateAvailable"] is True
    assert "offline" in stale["error"]


def test_no_cache_failure_is_non_fatal() -> None:
    result = update_check.check_for_update(
        data_root=IMPORT_ROOT / "offline",
        current_version="2.7.1",
        force=True,
        fetch=lambda *_: (_ for _ in ()).throw(update_check.UpdateCheckError("offline")),
        now=datetime(2026, 8, 1, tzinfo=timezone.utc),
    )
    assert result["source"] == "error"
    assert result["updateAvailable"] is False
    assert result["currentVersion"] == "2.7.1"


def test_preview_override() -> None:
    previous_version = os.environ.get("MUSIC_LIBRARY_UPDATE_PREVIEW_VERSION")
    previous_url = os.environ.get("MUSIC_LIBRARY_UPDATE_PREVIEW_URL")
    try:
        os.environ["MUSIC_LIBRARY_UPDATE_PREVIEW_VERSION"] = "2.8.0"
        os.environ["MUSIC_LIBRARY_UPDATE_PREVIEW_URL"] = update_check.GITHUB_RELEASES_URL
        result = update_check.check_for_update(
            data_root=IMPORT_ROOT / "preview",
            current_version="2.7.1",
        )
        assert result["source"] == "preview"
        assert result["updateAvailable"] is True
        assert result["latestVersion"] == "2.8.0"
    finally:
        if previous_version is None:
            os.environ.pop("MUSIC_LIBRARY_UPDATE_PREVIEW_VERSION", None)
        else:
            os.environ["MUSIC_LIBRARY_UPDATE_PREVIEW_VERSION"] = previous_version
        if previous_url is None:
            os.environ.pop("MUSIC_LIBRARY_UPDATE_PREVIEW_URL", None)
        else:
            os.environ["MUSIC_LIBRARY_UPDATE_PREVIEW_URL"] = previous_url


def test_http_route_requires_owner_and_honors_force() -> None:
    control_secret = "N" * 48
    original = server.update_check.check_for_update
    calls: list[bool] = []

    def fake_check(**kwargs):
        calls.append(bool(kwargs.get("force")))
        return {
            "currentVersion": "2.7.1",
            "latestVersion": "2.8.0",
            "latestTag": "v2.8.0",
            "releaseName": "Music Library v2.8.0",
            "releaseUrl": update_check.GITHUB_RELEASES_URL,
            "publishedAt": "2026-08-02T00:00:00Z",
            "checkedAt": "2026-08-02T01:00:00Z",
            "updateAvailable": True,
            "isPrerelease": True,
            "source": "network",
            "repository": update_check.GITHUB_REPOSITORY,
            "error": "",
        }

    server.update_check.check_for_update = fake_check
    httpd = server.create_server("127.0.0.1", 0, owner_control_secret=control_secret)
    port = int(httpd.server_address[1])
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, _ = request(connection, "GET", "/api/update-status")
        assert status == 403

        member_headers = {
            TAILSCALE_LOGIN_HEADER: "member@example.com",
            TAILSCALE_NAME_HEADER: "Member",
        }
        status, _ = request(
            connection,
            "GET",
            "/api/update-status",
            headers=member_headers,
        )
        assert status == 403

        cookie = owner_cookie(port, control_secret)
        status, payload = request(
            connection,
            "GET",
            "/api/update-status?force=1",
            headers={"Cookie": cookie},
        )
        assert status == 200
        assert payload["updateAvailable"] is True
        assert payload["viewer"]["isOwner"] is True
        assert calls == [True]
    finally:
        server.update_check.check_for_update = original
        connection.close()
        httpd.shutdown()
        httpd.server_close()
        thread.join(timeout=5)


def test_frontend_contains_owner_only_update_ui() -> None:
    html = (SRC / "music-library-search.html").read_text(encoding="utf-8")
    required = [
        'id="updateBanner"',
        'id="updateSection"',
        'id="updateCheckButton"',
        "./api/update-status",
        "loadUpdateStatus({force:true})",
        "els.updateSection.hidden = !owner",
        'rel="noopener noreferrer"',
        "music-library-dismissed-update-",
        "プレビュー用の模擬通知",
        "最新版情報を確認しました。",
        "updateCheckCompletedMessage",
        "renderUpdateStatus(payload, {manual:force})",
        "公開済みRelease（プレリリース設定を含む）",
        "公開済み最新版 v${latest} より新しい版です。",
        "GitHub上はプレリリース設定",
    ]
    for marker in required:
        assert marker in html, marker
    assert "api.github.com" not in html


def main() -> int:
    test_version_and_url_validation()
    test_release_selection_includes_prereleases_and_excludes_drafts()
    test_prerelease_only_repository_matches_real_release_policy()
    test_network_result_and_cache()
    test_force_and_stale_cache_fallback()
    test_no_cache_failure_is_non_fatal()
    test_preview_override()
    test_http_route_requires_owner_and_honors_force()
    test_frontend_contains_owner_only_update_ui()
    print("Update notification tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
