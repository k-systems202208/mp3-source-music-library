#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import errno
import shutil
import sys
import secrets
from http.cookies import SimpleCookie
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from paths import RESOURCE_ROOT, resolve_virtual_path
from typing import Any, BinaryIO
from urllib.parse import parse_qs, unquote, urlparse

from tailscale_identity import parse_tailscale_identity

from owner_link import (
    DEFAULT_OWNER_LINK_TTL_SECONDS,
    OwnerLinkCandidate,
    OwnerLinkCodeExpired,
    OwnerLinkCodeInvalid,
    OwnerLinkConflict,
    OwnerLinkManager,
    OwnerLinkNotReady,
)

from local_auth import (
    DEFAULT_ONE_TIME_TOKEN_TTL_SECONDS,
    LocalOwnerAuth,
    SESSION_COOKIE_NAME,
)

from database import (
    DATABASE_PATH,
    database,
    browse_library,
    database_stats,
    get_available_tracks,
    record_user_playback,
    set_user_favorite,
    set_artist_override,
    set_title_override,
    initialize_database,
    get_owner_user,
    get_user_by_id,
    list_users_for_management,
    set_user_active,
    get_or_create_tailscale_user,
    get_owner_link_merge_preview,
    create_pre_owner_link_backup,
    link_tailscale_identity_to_owner,
    OwnerIdentityLinkConflict,
    OwnerIdentityLinkNotFound,
)

RANGE_PATTERN = re.compile(r"bytes=(\d*)-(\d*)$")
EXPECTED_CLIENT_DISCONNECT_ERRNOS = {
    errno.EPIPE,
    errno.ECONNRESET,
    errno.ECONNABORTED,
}
EXPECTED_CLIENT_DISCONNECT_WINERRORS = {10053, 10054, 10058}


def is_expected_client_disconnect(exc: BaseException) -> bool:
    """Return True when a browser intentionally stopped receiving a response."""
    if isinstance(exc, (BrokenPipeError, ConnectionResetError, ConnectionAbortedError)):
        return True
    if isinstance(exc, OSError):
        if getattr(exc, "errno", None) in EXPECTED_CLIENT_DISCONNECT_ERRNOS:
            return True
        if getattr(exc, "winerror", None) in EXPECTED_CLIENT_DISCONNECT_WINERRORS:
            return True
    return False


PLAYED_ROUTE = re.compile(r"^/api/tracks/([^/]+)/played$")
FAVORITE_ROUTE = re.compile(r"^/api/tracks/([^/]+)/favorite$")
TITLE_CORRECTION_ROUTE = re.compile(r"^/api/tracks/([^/]+)/title-correction$")
ARTIST_CORRECTION_ROUTE = re.compile(r"^/api/artists/([^/]+)/correction$")
USER_ACTIVE_ROUTE = re.compile(r"^/api/users/([^/]+)/active$")
LOCAL_OWNER_TOKEN_ROUTE = "/api/local-auth/token"
LOCAL_OWNER_EXCHANGE_ROUTE = "/api/local-auth/exchange"
CURRENT_USER_ROUTE = "/api/current-user"
USERS_ROUTE = "/api/users"
OWNER_LINK_START_ROUTE = "/api/owner-link/start"
OWNER_LINK_CLAIM_ROUTE = "/api/owner-link/claim"
OWNER_LINK_STATUS_ROUTE = "/api/owner-link/status"
OWNER_LINK_CONFIRM_ROUTE = "/api/owner-link/confirm"
OWNER_LINK_CANCEL_ROUTE = "/api/owner-link/cancel"
CONTROL_SECRET_HEADER = "X-Music-Library-Control-Secret"
OWNER_SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
BLOCKED_STATIC_NAMES = {
    "library.db",
    "library.db-wal",
    "library.db-shm",
    "legacy-library-data.json",
    "database.py",
    "generate-library.py",
    "serve-library.py",
}


class MusicLibraryHandler(SimpleHTTPRequestHandler):
    """SQLite API and UTF-8 static server with MP3 byte-range support."""

    server_version = "MusicLibrary/SQLiteAPI2.7.0"
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".htm": "text/html; charset=utf-8",
        ".json": "application/json; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".txt": "text/plain; charset=utf-8",
        ".mp3": "audio/mpeg",
    }

    def __init__(self, *args, **kwargs):
        self._range_start: int | None = None
        self._range_length: int | None = None
        self._request_body_cache: bytes | None = None
        super().__init__(*args, directory=str(RESOURCE_ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the launcher log focused on scan and startup information."""
        return

    @property
    def local_owner_auth(self) -> LocalOwnerAuth:
        return self.server.local_owner_auth  # type: ignore[attr-defined]

    @property
    def owner_link_manager(self) -> OwnerLinkManager:
        return self.server.owner_link_manager  # type: ignore[attr-defined]

    def _owner_session_value(self) -> str:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return ""
        cookie = SimpleCookie()
        try:
            cookie.load(raw)
        except Exception:
            return ""
        morsel = cookie.get(SESSION_COOKIE_NAME)
        return str(morsel.value) if morsel is not None else ""

    def _has_valid_owner_session(self) -> bool:
        value = self._owner_session_value()
        return bool(value and self.local_owner_auth.validate_session(value))

    @staticmethod
    def _anonymous_current_user() -> dict[str, Any]:
        return {
            "authenticated": False,
            "id": None,
            "displayName": "",
            "isOwner": False,
            "provider": "",
        }

    def _resolve_current_user(self) -> dict[str, Any]:
        """Resolve Tailscale identity first, then the local-owner session.

        Tailscale Serve forwards the authenticated tailnet user's identity
        headers to this localhost-only backend. Tagged devices have no user
        login header and therefore remain anonymous.
        """
        tailscale_identity = parse_tailscale_identity(self.headers)
        if tailscale_identity is not None:
            with database() as connection:
                initialize_database(connection)
                user = get_or_create_tailscale_user(
                    connection,
                    subject=tailscale_identity.subject,
                    display_name=tailscale_identity.display_name,
                    profile_picture_url=(
                        tailscale_identity.profile_picture_url
                    ),
                )

            if not bool(user.get("isActive")):
                return self._anonymous_current_user()

            return {
                "authenticated": True,
                "id": user["id"],
                "displayName": user["displayName"],
                "isOwner": bool(user["isOwner"]),
                "provider": "tailscale",
            }

        if not self._has_valid_owner_session():
            return self._anonymous_current_user()

        with database() as connection:
            initialize_database(connection)
            owner = get_owner_user(connection)

        if owner is None or not bool(owner.get("isActive")):
            return self._anonymous_current_user()

        return {
            "authenticated": True,
            "id": owner["id"],
            "displayName": owner["displayName"],
            "isOwner": True,
            "provider": "local_owner",
        }

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        parsed_path = urlparse(self.path).path.casefold()
        if parsed_path.startswith("/api/") or parsed_path.endswith((".json", ".html", ".htm")):
            self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path in {"", "/"}:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", "/music-library-search.html")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "database": DATABASE_PATH.name})
            return
        if parsed.path == LOCAL_OWNER_EXCHANGE_ROUTE:
            self.handle_local_owner_exchange(parsed.query)
            return
        if parsed.path == CURRENT_USER_ROUTE:
            self.handle_current_user()
            return
        if parsed.path == USERS_ROUTE:
            self.handle_users()
            return
        if parsed.path == OWNER_LINK_STATUS_ROUTE:
            self.handle_owner_link_status(parsed.query)
            return
        if parsed.path == "/api/browse":
            self.handle_browse(parsed.query)
            return
        if parsed.path == "/api/tracks":
            self.handle_tracks()
            return
        if parsed.path == "/api/stats":
            self.handle_stats()
            return
        super().do_GET()

    def do_POST(self) -> None:
        # Read the complete request body before any authorization check.
        #
        # On Windows, closing a TCP connection while unread POST bytes remain
        # can reset the connection (WinError 10053) before the client receives
        # an otherwise valid 401/403 response. Caching the body here also means
        # every handler reads the same bytes exactly once.
        try:
            self.read_request_body_bytes()
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        parsed = urlparse(self.path)
        if parsed.path == LOCAL_OWNER_TOKEN_ROUTE:
            self.handle_local_owner_token_registration()
            return
        if parsed.path == OWNER_LINK_START_ROUTE:
            self.handle_owner_link_start()
            return
        if parsed.path == OWNER_LINK_CLAIM_ROUTE:
            self.handle_owner_link_claim()
            return
        if parsed.path == OWNER_LINK_CONFIRM_ROUTE:
            self.handle_owner_link_confirm()
            return
        if parsed.path == OWNER_LINK_CANCEL_ROUTE:
            self.handle_owner_link_cancel()
            return
        match = USER_ACTIVE_ROUTE.fullmatch(parsed.path)
        if match:
            self.handle_user_active(unquote(match.group(1)))
            return
        match = PLAYED_ROUTE.fullmatch(parsed.path)
        if match:
            self.handle_played(unquote(match.group(1)))
            return
        match = FAVORITE_ROUTE.fullmatch(parsed.path)
        if match:
            self.handle_favorite(unquote(match.group(1)))
            return
        match = TITLE_CORRECTION_ROUTE.fullmatch(parsed.path)
        if match:
            self.handle_title_correction(unquote(match.group(1)))
            return
        match = ARTIST_CORRECTION_ROUTE.fullmatch(parsed.path)
        if match:
            self.handle_artist_correction(unquote(match.group(1)))
            return
        self.send_json({"error": "API endpoint not found"}, HTTPStatus.NOT_FOUND)

    @staticmethod
    def _query_value(parameters: dict[str, list[str]], name: str, default: str = "") -> str:
        values = parameters.get(name)
        return str(values[0]) if values else default

    @staticmethod
    def _query_int(
        parameters: dict[str, list[str]],
        name: str,
        default: int,
        *,
        minimum: int = 0,
        maximum: int = 1000000,
    ) -> int:
        text = MusicLibraryHandler._query_value(parameters, name, str(default))
        try:
            value = int(text)
        except ValueError as exc:
            raise ValueError(f"{name} must be an integer") from exc
        if value < minimum or value > maximum:
            raise ValueError(f"{name} must be between {minimum} and {maximum}")
        return value

    @staticmethod
    def _query_bool(parameters: dict[str, list[str]], name: str) -> bool:
        value = MusicLibraryHandler._query_value(parameters, name, "").casefold()
        return value in {"1", "true", "yes", "on"}

    def handle_local_owner_token_registration(self) -> None:
        supplied_secret = self.headers.get(CONTROL_SECRET_HEADER, "")
        if not self.local_owner_auth.control_secret_matches(supplied_secret):
            self.send_json({"error": "forbidden"}, HTTPStatus.FORBIDDEN)
            return

        try:
            body = self.read_json_body()
            token = str(body.get("token") or "")
            ttl_value = body.get(
                "expiresInSeconds",
                DEFAULT_ONE_TIME_TOKEN_TTL_SECONDS,
            )
            if isinstance(ttl_value, bool):
                raise ValueError("expiresInSeconds must be an integer")
            ttl_seconds = int(ttl_value)
            effective_ttl = self.local_owner_auth.register_one_time_token(
                token,
                ttl_seconds=ttl_seconds,
            )
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        self.send_json(
            {
                "registered": True,
                "expiresInSeconds": effective_ttl,
            },
            HTTPStatus.CREATED,
        )

    def handle_local_owner_exchange(self, query_string: str) -> None:
        parameters = parse_qs(query_string, keep_blank_values=True)
        token_values = parameters.get("token") or []
        token = str(token_values[0]) if len(token_values) == 1 else ""

        if not self.local_owner_auth.consume_one_time_token(token):
            self.send_html_error(
                HTTPStatus.UNAUTHORIZED,
                "ローカルオーナー確認に失敗しました。管理画面からもう一度開いてください。",
            )
            return

        session = self.local_owner_auth.issue_session()
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", "/music-library-search.html")
        self.send_header(
            "Set-Cookie",
            (
                f"{SESSION_COOKIE_NAME}={session.value}; "
                f"Path=/; Max-Age={session.max_age}; "
                "HttpOnly; SameSite=Strict"
            ),
        )
        self.send_header("Content-Length", "0")
        self.end_headers()

    def handle_current_user(self) -> None:
        try:
            self.send_json(self._resolve_current_user())
        except Exception as exc:
            self.send_json(
                {
                    "error": (
                        "利用者情報を取得できませんでした: "
                        f"{type(exc).__name__}: {exc}"
                    )
                },
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )


    def _require_owner(self) -> dict[str, Any] | None:
        current = self._resolve_current_user()
        if (
            not bool(current.get("authenticated"))
            or not bool(current.get("isOwner"))
        ):
            self.send_json(
                {"error": "owner authentication required"},
                HTTPStatus.FORBIDDEN,
            )
            return None
        return current

    def _require_local_owner(self) -> dict[str, Any] | None:
        current = self._require_owner()
        if current is None:
            return None
        if current.get("provider") != "local_owner":
            self.send_json(
                {"error": "local owner authentication required"},
                HTTPStatus.FORBIDDEN,
            )
            return None
        return current

    def handle_users(self) -> None:
        viewer = self._require_owner()
        if viewer is None:
            return

        with database() as connection:
            initialize_database(connection)
            users = list_users_for_management(connection)

        self.send_json(
            {
                "viewer": viewer,
                "users": users,
            }
        )

    def handle_user_active(self, user_id: str) -> None:
        owner = self._require_local_owner()
        if owner is None:
            return

        try:
            body = self.read_json_body()
            active = body.get("active")
            if not isinstance(active, bool):
                raise ValueError("active must be true or false")
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        with database() as connection:
            initialize_database(connection)
            target = get_user_by_id(connection, user_id)
            if target is None:
                self.send_json(
                    {"error": "利用者が見つかりません。"},
                    HTTPStatus.NOT_FOUND,
                )
                return
            if bool(target.get("isOwner")):
                self.send_json(
                    {"error": "オーナーを無効化することはできません。"},
                    HTTPStatus.CONFLICT,
                )
                return

            updated = set_user_active(connection, user_id, active)
            if not updated:
                self.send_json(
                    {"error": "利用者の状態を更新できませんでした。"},
                    HTTPStatus.CONFLICT,
                )
                return
            connection.commit()
            result = get_user_by_id(connection, user_id)

        self.send_json(
            {
                "updated": True,
                "user": result,
            }
        )

    def _require_tailscale_candidate(self) -> tuple[dict[str, Any], str] | None:
        identity = parse_tailscale_identity(self.headers)
        if identity is None:
            self.send_json({"error": "Tailscale user authentication required"}, HTTPStatus.FORBIDDEN)
            return None

        with database() as connection:
            initialize_database(connection)
            user = get_or_create_tailscale_user(
                connection,
                subject=identity.subject,
                display_name=identity.display_name,
                profile_picture_url=identity.profile_picture_url,
            )

        if not bool(user.get("isActive")):
            self.send_json({"error": "Tailscale user is disabled"}, HTTPStatus.FORBIDDEN)
            return None
        return user, identity.subject

    @staticmethod
    def _owner_link_error_status(exc: Exception) -> HTTPStatus:
        if isinstance(exc, OwnerLinkCodeExpired):
            return HTTPStatus.GONE
        if isinstance(exc, OwnerLinkCodeInvalid):
            return HTTPStatus.NOT_FOUND
        if isinstance(exc, OwnerLinkNotReady):
            return HTTPStatus.CONFLICT
        if isinstance(exc, OwnerLinkConflict):
            return HTTPStatus.CONFLICT
        return HTTPStatus.BAD_REQUEST

    def handle_owner_link_start(self) -> None:
        owner = self._require_local_owner()
        if owner is None:
            return
        try:
            body = self.read_json_body()
            ttl_value = body.get("expiresInSeconds", DEFAULT_OWNER_LINK_TTL_SECONDS)
            if isinstance(ttl_value, bool):
                raise ValueError("expiresInSeconds must be an integer")
            code, effective_ttl = self.owner_link_manager.create_challenge(
                str(owner["id"]),
                ttl_seconds=int(ttl_value),
            )
        except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return

        self.send_json(
            {
                "code": code,
                "expiresInSeconds": effective_ttl,
                "status": "waiting_for_tailscale",
            },
            HTTPStatus.CREATED,
        )

    def handle_owner_link_claim(self) -> None:
        candidate_context = self._require_tailscale_candidate()
        if candidate_context is None:
            return
        user, subject = candidate_context
        try:
            body = self.read_json_body()
            code = str(body.get("code") or "")
            with database() as connection:
                initialize_database(connection)
                preview = get_owner_link_merge_preview(
                    connection,
                    str(user["id"]),
                )
            status = self.owner_link_manager.claim(
                code,
                OwnerLinkCandidate(
                    user_id=str(user["id"]),
                    subject=subject,
                    display_name=str(user["displayName"]),
                    is_owner=bool(user["isOwner"]),
                    state_count=int(preview["stateCount"]),
                    play_count=int(preview["playCount"]),
                    favorite_count=int(preview["favoriteCount"]),
                    rating_count=int(preview["ratingCount"]),
                    rating_conflict_count=int(preview["ratingConflictCount"]),
                    identity_count=int(preview["identityCount"]),
                    can_merge=bool(preview["canMerge"]),
                ),
            )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except (OwnerLinkCodeInvalid, OwnerLinkCodeExpired, OwnerLinkConflict) as exc:
            self.send_json({"error": str(exc)}, self._owner_link_error_status(exc))
            return

        self.send_json(
            {
                "claimed": True,
                "status": status["status"],
                "expiresInSeconds": status["expiresInSeconds"],
                "displayName": str(user["displayName"]),
                "subject": subject,
                "alreadyOwner": bool(user["isOwner"]),
                "mergePreview": preview,
            },
            HTTPStatus.ACCEPTED,
        )

    def handle_owner_link_status(self, query_string: str) -> None:
        owner = self._require_local_owner()
        if owner is None:
            return
        parameters = parse_qs(query_string, keep_blank_values=True)
        code_values = parameters.get("code") or []
        code = str(code_values[0]) if len(code_values) == 1 else ""
        try:
            status = self.owner_link_manager.status(code, str(owner["id"]))
        except (OwnerLinkCodeInvalid, OwnerLinkCodeExpired, OwnerLinkConflict) as exc:
            self.send_json({"error": str(exc)}, self._owner_link_error_status(exc))
            return
        self.send_json(status)

    def handle_owner_link_confirm(self) -> None:
        owner = self._require_local_owner()
        if owner is None:
            return
        code = ""
        try:
            body = self.read_json_body()
            code = str(body.get("code") or "")
            if body.get("confirmed") is not True:
                raise ValueError("confirmed must be true")
            expected_user_id = str(body.get("userId") or "")
            expected_subject = str(body.get("subject") or "")
            candidate = self.owner_link_manager.begin_confirmation(
                code,
                str(owner["id"]),
                expected_user_id=expected_user_id,
                expected_subject=expected_subject,
            )

            if not candidate.is_owner:
                create_pre_owner_link_backup()

            with database() as connection:
                initialize_database(connection)
                linked_owner = link_tailscale_identity_to_owner(
                    connection,
                    subject=candidate.subject,
                    expected_candidate_user_id=candidate.user_id,
                )
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            if code:
                self.owner_link_manager.release_confirmation(code)
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except (OwnerLinkCodeInvalid, OwnerLinkCodeExpired, OwnerLinkConflict, OwnerLinkNotReady) as exc:
            if code:
                self.owner_link_manager.release_confirmation(code)
            self.send_json({"error": str(exc)}, self._owner_link_error_status(exc))
            return
        except (OwnerIdentityLinkConflict, OwnerIdentityLinkNotFound) as exc:
            self.owner_link_manager.release_confirmation(code)
            self.send_json({"error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except Exception as exc:
            if code:
                self.owner_link_manager.release_confirmation(code)
            self.send_json(
                {"error": f"関連付けを完了できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return

        self.owner_link_manager.complete_confirmation(code)
        self.send_json(
            {
                "linked": True,
                "alreadyLinked": bool(linked_owner.get("alreadyLinked")),
                "owner": {
                    "id": linked_owner["id"],
                    "displayName": linked_owner["displayName"],
                    "isOwner": True,
                },
                "subject": linked_owner["subject"],
                "mergedPersonalState": linked_owner.get("mergedPersonalState", {}),
            }
        )

    def handle_owner_link_cancel(self) -> None:
        owner = self._require_local_owner()
        if owner is None:
            return
        try:
            body = self.read_json_body()
            code = str(body.get("code") or "")
            self.owner_link_manager.cancel(code, str(owner["id"]))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except (OwnerLinkCodeInvalid, OwnerLinkCodeExpired, OwnerLinkConflict) as exc:
            self.send_json({"error": str(exc)}, self._owner_link_error_status(exc))
            return
        self.send_json({"cancelled": True})

    def send_html_error(self, status: HTTPStatus, message: str) -> None:
        escaped = (
            str(message)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
        )
        body = (
            "<!doctype html><html lang=\"ja\"><meta charset=\"utf-8\">"
            "<title>自宅音楽ライブラリ</title>"
            f"<body><h1>{status.value}</h1><p>{escaped}</p></body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def handle_browse(self, query_string: str) -> None:
        try:
            parameters = parse_qs(query_string, keep_blank_values=True)
            view = self._query_value(parameters, "view", "songs")
            query = self._query_value(parameters, "q", "").strip()
            limit = self._query_int(parameters, "limit", 80, minimum=1, maximum=200)
            offset = self._query_int(parameters, "offset", 0, minimum=0)
            sort = self._query_value(parameters, "sort", "title")
            artist_key = self._query_value(parameters, "artistKey", "")
            album_key = self._query_value(parameters, "albumKey", "")
            album_title = self._query_value(parameters, "albumTitle", "")
            index_key = self._query_value(parameters, "indexKey", "")

            current_user = self._resolve_current_user()
            user_id = (
                str(current_user["id"])
                if bool(current_user.get("authenticated"))
                else None
            )
            with database() as connection:
                initialize_database(connection)
                result = browse_library(
                    connection,
                    view=view,
                    query=query,
                    limit=limit,
                    offset=offset,
                    latin_only=self._query_bool(parameters, "latinOnly"),
                    corrected_only=self._query_bool(parameters, "correctedOnly"),
                    artist_key=artist_key,
                    album_key=album_key,
                    album_title=album_title,
                    sort=sort,
                    index_key=index_key,
                    user_id=user_id,
                    favorite_only=self._query_bool(parameters, "favoriteOnly"),
                )
            self.send_json(result)
        except ValueError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json(
                {"error": f"SQLite検索に失敗しました: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def handle_tracks(self) -> None:
        try:
            current_user = self._resolve_current_user()
            user_id = (
                str(current_user["id"])
                if bool(current_user.get("authenticated"))
                else None
            )
            with database() as connection:
                initialize_database(connection)
                tracks = get_available_tracks(connection, user_id=user_id)
            self.send_json(tracks)
        except Exception as exc:
            self.send_json(
                {"error": f"SQLiteから曲データを取得できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def handle_stats(self) -> None:
        try:
            current_user = self._resolve_current_user()
            user_id = (
                str(current_user["id"])
                if bool(current_user.get("authenticated"))
                else None
            )
            with database() as connection:
                initialize_database(connection)
                stats = database_stats(connection, user_id=user_id)
            self.send_json(stats)
        except Exception as exc:
            self.send_json(
                {"error": f"SQLite統計を取得できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def handle_played(self, track_id: str) -> None:
        if not track_id:
            self.send_json({"error": "track id is required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            current_user = self._resolve_current_user()
            user_id = (
                str(current_user["id"])
                if bool(current_user.get("authenticated"))
                else None
            )
            with database() as connection:
                initialize_database(connection)
                playback = record_user_playback(
                    connection,
                    user_id=user_id,
                    track_id=track_id,
                )
            if playback is None:
                self.send_json({"error": "track not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"id": track_id, **playback})
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except Exception as exc:
            self.send_json(
                {"error": f"再生回数を保存できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )


    def handle_favorite(self, track_id: str) -> None:
        if not track_id:
            self.send_json({"error": "track id is required"}, HTTPStatus.BAD_REQUEST)
            return
        try:
            current_user = self._resolve_current_user()
            if not bool(current_user.get("authenticated")):
                self.send_json(
                    {"error": "authenticated user is required"},
                    HTTPStatus.UNAUTHORIZED,
                )
                return

            body = self.read_json_body()
            favorite = body.get("favorite")
            if type(favorite) is not bool:
                raise ValueError("favorite must be a boolean")

            with database() as connection:
                initialize_database(connection)
                result = set_user_favorite(
                    connection,
                    user_id=str(current_user["id"]),
                    track_id=track_id,
                    favorite=favorite,
                )
            if result is None:
                self.send_json({"error": "track not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"id": track_id, **result})
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except PermissionError as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.FORBIDDEN)
        except Exception as exc:
            self.send_json(
                {"error": f"お気に入りを保存できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def read_request_body_bytes(self) -> bytes:
        if self._request_body_cache is not None:
            return self._request_body_cache

        length_text = self.headers.get("Content-Length", "0")
        try:
            length = int(length_text)
        except ValueError as exc:
            raise ValueError("Content-Length is invalid") from exc
        if length < 0 or length > 64 * 1024:
            raise ValueError("Request body is too large")

        raw = self.rfile.read(length) if length else b"{}"
        if length and len(raw) != length:
            raise ValueError("Request body is incomplete")

        self._request_body_cache = raw
        return raw

    def read_json_body(self) -> dict[str, Any]:
        raw = self.read_request_body_bytes()
        value = json.loads(raw.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON body must be an object")
        return value

    def handle_title_correction(self, track_id: str) -> None:
        try:
            body = self.read_json_body()
            value = body.get("value")
            if value is not None and not isinstance(value, str):
                raise ValueError("value must be a string or null")
            with database() as connection:
                initialize_database(connection)
                result = set_title_override(connection, track_id, value)
            if result is None:
                self.send_json({"error": "track not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(result)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json(
                {"error": f"曲名補正を保存できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def handle_artist_correction(self, artist_id: str) -> None:
        try:
            body = self.read_json_body()
            value = body.get("value")
            if value is not None and not isinstance(value, str):
                raise ValueError("value must be a string or null")
            with database() as connection:
                initialize_database(connection)
                result = set_artist_override(connection, artist_id, value)
            if result is None:
                self.send_json({"error": "artist not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json(result)
        except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self.send_json(
                {"error": f"アーティスト名補正を保存できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def send_json(self, value: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_head(self) -> BinaryIO | None:
        parsed_path = urlparse(self.path).path
        decoded_path = unquote(parsed_path)
        requested = Path(decoded_path)
        requested_name = requested.name.casefold()
        requested_parts = {part.casefold() for part in requested.parts}
        blocked_suffix = requested.suffix.casefold() in {".db", ".sqlite", ".py", ".bat"}
        if (
            requested_name in BLOCKED_STATIC_NAMES
            or requested_name.startswith("library.db-")
            or blocked_suffix
            or "backups" in requested_parts
            or "exports" in requested_parts
        ):
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        resolved = resolve_virtual_path(decoded_path)
        path = str(resolved) if resolved is not None else ""
        if os.path.isdir(path):
            return super().send_head()

        try:
            file = open(path, "rb")
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND, "File not found")
            return None

        try:
            stat = os.fstat(file.fileno())
            size = stat.st_size
            content_type = self.guess_type(path)
            range_header = self.headers.get("Range", "").strip()
            parsed_range = self._parse_range(range_header, size) if range_header else None

            self._range_start = None
            self._range_length = None

            if parsed_range is not None:
                start, end = parsed_range
                length = end - start + 1
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Type", content_type)
                self.send_header("Accept-Ranges", "bytes")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
                self.end_headers()
                file.seek(start)
                self._range_start = start
                self._range_length = length
                return file

            if range_header:
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                file.close()
                return None

            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(size))
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Last-Modified", self.date_time_string(stat.st_mtime))
            self.end_headers()
            return file
        except Exception:
            file.close()
            raise

    @staticmethod
    def _parse_range(value: str, size: int) -> tuple[int, int] | None:
        match = RANGE_PATTERN.fullmatch(value)
        if not match or size <= 0:
            return None
        start_text, end_text = match.groups()
        if not start_text and not end_text:
            return None

        if start_text:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
            if start >= size or start > end:
                return None
            return start, min(end, size - 1)

        suffix_length = int(end_text)
        if suffix_length <= 0:
            return None
        suffix_length = min(suffix_length, size)
        return size - suffix_length, size - 1

    def copyfile(self, source: BinaryIO, outputfile: BinaryIO) -> None:
        """Send a file while treating browser-side cancellation as normal."""
        try:
            if self._range_length is None:
                shutil.copyfileobj(source, outputfile)
                return

            remaining = self._range_length
            while remaining > 0:
                chunk = source.read(min(64 * 1024, remaining))
                if not chunk:
                    break
                outputfile.write(chunk)
                remaining -= len(chunk)
        except OSError as exc:
            # Browsers routinely cancel image/audio requests during reload, seek,
            # track changes, and page navigation. This is not an application error.
            if is_expected_client_disconnect(exc):
                return
            raise


class MusicLibraryHTTPServer(ThreadingHTTPServer):
    """Threaded local server that hides expected browser disconnect tracebacks."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        server_address: tuple[str, int],
        handler_class: type[MusicLibraryHandler],
        *,
        local_owner_auth: LocalOwnerAuth,
        owner_link_manager: OwnerLinkManager,
    ) -> None:
        self.local_owner_auth = local_owner_auth
        self.owner_link_manager = owner_link_manager
        super().__init__(server_address, handler_class)

    def handle_error(self, request: object, client_address: object) -> None:
        exc = sys.exc_info()[1]
        if exc is not None and is_expected_client_disconnect(exc):
            return
        super().handle_error(request, client_address)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the SQLite MP3 music library locally.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    return parser.parse_args()


def create_server(
    host: str = "127.0.0.1",
    port: int = 8000,
    *,
    owner_control_secret: str | None = None,
    auth_clock: Any | None = None,
    owner_link_clock: Any | None = None,
) -> MusicLibraryHTTPServer:
    with database() as connection:
        initialize_database(connection)

    control_secret = owner_control_secret or secrets.token_urlsafe(48)
    auth = LocalOwnerAuth(control_secret, clock=auth_clock)
    owner_link_manager = OwnerLinkManager(clock=owner_link_clock)
    return MusicLibraryHTTPServer(
        (host, port),
        MusicLibraryHandler,
        local_owner_auth=auth,
        owner_link_manager=owner_link_manager,
    )


def main() -> None:
    args = parse_args()
    server = create_server(args.host, args.port)
    print(f"Music Library: http://{args.host}:{args.port}/music-library-search.html")
    print(f"SQLite       : {DATABASE_PATH}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nMusic Library stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
