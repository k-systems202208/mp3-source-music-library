#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import errno
import shutil
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from paths import RESOURCE_ROOT, resolve_virtual_path
from typing import Any, BinaryIO
from urllib.parse import parse_qs, unquote, urlparse

from database import (
    DATABASE_PATH,
    database,
    browse_library,
    database_stats,
    get_available_tracks,
    increment_play_count,
    set_artist_override,
    set_title_override,
    initialize_database,
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
TITLE_CORRECTION_ROUTE = re.compile(r"^/api/tracks/([^/]+)/title-correction$")
ARTIST_CORRECTION_ROUTE = re.compile(r"^/api/artists/([^/]+)/correction$")
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

    server_version = "MusicLibrary/SQLiteAPI2.6.2"
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
        super().__init__(*args, directory=str(RESOURCE_ROOT), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep the launcher log focused on scan and startup information."""
        return

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
        parsed = urlparse(self.path)
        match = PLAYED_ROUTE.fullmatch(parsed.path)
        if match:
            self.handle_played(unquote(match.group(1)))
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
            with database() as connection:
                initialize_database(connection)
                tracks = get_available_tracks(connection)
            self.send_json(tracks)
        except Exception as exc:
            self.send_json(
                {"error": f"SQLiteから曲データを取得できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def handle_stats(self) -> None:
        try:
            with database() as connection:
                initialize_database(connection)
                stats = database_stats(connection)
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
            with database() as connection:
                initialize_database(connection)
                play_count = increment_play_count(connection, track_id)
            if play_count is None:
                self.send_json({"error": "track not found"}, HTTPStatus.NOT_FOUND)
                return
            self.send_json({"id": track_id, "playCount": play_count})
        except Exception as exc:
            self.send_json(
                {"error": f"再生回数を保存できませんでした: {type(exc).__name__}: {exc}"},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def read_json_body(self) -> dict[str, Any]:
        length_text = self.headers.get("Content-Length", "0")
        try:
            length = int(length_text)
        except ValueError as exc:
            raise ValueError("Content-Length is invalid") from exc
        if length < 0 or length > 64 * 1024:
            raise ValueError("Request body is too large")
        raw = self.rfile.read(length) if length else b"{}"
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


def create_server(host: str = "127.0.0.1", port: int = 8000) -> MusicLibraryHTTPServer:
    with database() as connection:
        initialize_database(connection)
    return MusicLibraryHTTPServer((host, port), MusicLibraryHandler)


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
