#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import unicodedata
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Sequence

ROOT = Path(__file__).resolve().parent
DATABASE_PATH = ROOT / "library.db"
BACKUP_DIR = ROOT / "Backups"
SCHEMA_VERSION = 4


def utc_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def normalized(value: Any) -> str:
    import re

    text = str(value or "").casefold()
    return re.sub(
        r"[\s\u3000\-‐‑‒–—―_・･·.,，。!！?？'\"“”()（）\[\]【】{}／/\\:：]",
        "",
        text,
    )


def stable_key(prefix: str, *parts: Any) -> str:
    source = "\u241f".join(str(part or "") for part in parts)
    digest = hashlib.sha256(source.encode("utf-8", errors="surrogatepass")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def _is_latin_only(value: Any) -> int:
    """Match the former browser filter: contains Latin letters and no Japanese text."""
    text = str(value or "")
    has_japanese = bool(re.search(r"[\u3040-\u30ff\u4e00-\u9fff]", text))
    has_latin = bool(re.search(r"[A-Za-z]", text))
    return int(has_latin and not has_japanese)


INDEX_KEYS = (
    "0-9",
    *tuple(chr(code) for code in range(ord("A"), ord("Z") + 1)),
    "あ", "か", "さ", "た", "な", "は", "ま", "や", "ら", "わ",
    "他",
)
INDEX_KEY_SET = frozenset(INDEX_KEYS)

_KANA_ROWS = {
    "あ": frozenset("ぁあぃいぅうぇえぉおゔ"),
    "か": frozenset("かがきぎくぐけげこごゕゖ"),
    "さ": frozenset("さざしじすずせぜそぞ"),
    "た": frozenset("ただちぢっつづてでとど"),
    "な": frozenset("なにぬねの"),
    "は": frozenset("はばぱひびぴふぶぷへべぺほぼぽ"),
    "ま": frozenset("まみむめも"),
    "や": frozenset("ゃやゅゆょよ"),
    "ら": frozenset("らりるれろ"),
    "わ": frozenset("ゎわゐゑをん"),
}


def _katakana_to_hiragana(value: str) -> str:
    chars: list[str] = []
    for char in value:
        code = ord(char)
        if 0x30A1 <= code <= 0x30F6:
            chars.append(chr(code - 0x60))
        else:
            chars.append(char)
    return "".join(chars)


def _catalog_source(value: Any) -> str:
    """Return text used for catalog ordering and index classification.

    ID3 sort fields are supplied by the caller when available. Leading symbols
    are ignored, and English articles are skipped so ``The Beatles`` appears
    under B rather than T.
    """
    text = unicodedata.normalize("NFKC", str(value or "")).strip()
    text = re.sub(r"^[\s\u3000\-‐‑‒–—―_・･·.,，。!！?？'\"“”()（）\[\]【】{}／/\\:：]+", "", text)
    article = re.match(r"^(?:the|an|a)\s+([A-Za-z0-9].*)$", text, re.IGNORECASE)
    if article:
        text = article.group(1).strip()
    return text


def _catalog_bucket(value: Any) -> str:
    text = _catalog_source(value)
    if not text:
        return "他"
    first = text[0]
    if first.isdigit():
        return "0-9"
    upper = first.upper()
    if "A" <= upper <= "Z":
        return upper
    hira = _katakana_to_hiragana(first)
    for label, characters in _KANA_ROWS.items():
        if hira in characters:
            return label
    return "他"


def _catalog_sort_key(value: Any) -> str:
    text = _katakana_to_hiragana(_catalog_source(value))
    return unicodedata.normalize("NFKC", text).casefold()


def connect_database(path: Path = DATABASE_PATH) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    connection.execute("PRAGMA busy_timeout = 30000")
    connection.create_function("is_latin_only", 1, _is_latin_only, deterministic=True)
    connection.create_function("catalog_bucket", 1, _catalog_bucket, deterministic=True)
    connection.create_function("catalog_sort_key", 1, _catalog_sort_key, deterministic=True)
    return connection


@contextmanager
def database(path: Path = DATABASE_PATH) -> Iterator[sqlite3.Connection]:
    connection = connect_database(path)
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_info (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artists (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL UNIQUE,
    sort_name TEXT NOT NULL DEFAULT '',
    display_name_override TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS artworks (
    id TEXT PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    source_type TEXT NOT NULL,
    source_mp3_path TEXT NOT NULL DEFAULT '',
    mime_type TEXT NOT NULL DEFAULT '',
    file_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS albums (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    album_artist TEXT NOT NULL DEFAULT '',
    normalized_album_artist TEXT NOT NULL DEFAULT '',
    sort_title TEXT NOT NULL DEFAULT '',
    year INTEGER,
    artwork_id TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(normalized_title, normalized_album_artist),
    FOREIGN KEY (artwork_id) REFERENCES artworks(id)
);

CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,

    title TEXT NOT NULL,
    normalized_title TEXT NOT NULL,
    sort_title TEXT NOT NULL DEFAULT '',
    artist_id TEXT,
    album_id TEXT,
    album_artist TEXT NOT NULL DEFAULT '',
    genre TEXT NOT NULL DEFAULT '',
    composer TEXT NOT NULL DEFAULT '',
    year INTEGER,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    track_number INTEGER,
    disc_number INTEGER,
    kind TEXT NOT NULL DEFAULT 'MP3オーディオファイル',

    file_size INTEGER NOT NULL,
    modified_time_ns INTEGER NOT NULL,
    content_signature TEXT NOT NULL DEFAULT '',
    audio_file TEXT NOT NULL,
    artwork_id TEXT,
    metadata_source_json TEXT NOT NULL DEFAULT '{}',

    play_count INTEGER NOT NULL DEFAULT 0 CHECK(play_count >= 0),
    date_added TEXT NOT NULL DEFAULT '',
    last_played_at TEXT NOT NULL DEFAULT '',
    favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite IN (0, 1)),
    rating INTEGER CHECK(rating IS NULL OR (rating >= 0 AND rating <= 5)),

    title_override TEXT,
    artist_override TEXT,
    album_override TEXT,

    legacy_id TEXT NOT NULL DEFAULT '',
    legacy_match_method TEXT NOT NULL DEFAULT '',
    last_scanned_at TEXT NOT NULL,
    is_available INTEGER NOT NULL DEFAULT 1 CHECK(is_available IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    FOREIGN KEY (artist_id) REFERENCES artists(id),
    FOREIGN KEY (album_id) REFERENCES albums(id),
    FOREIGN KEY (artwork_id) REFERENCES artworks(id)
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    status TEXT NOT NULL,
    mp3_files INTEGER NOT NULL DEFAULT 0,
    loaded INTEGER NOT NULL DEFAULT 0,
    errors INTEGER NOT NULL DEFAULT 0,
    cache_hits INTEGER NOT NULL DEFAULT 0,
    details_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS scan_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER,
    severity TEXT NOT NULL,
    category TEXT NOT NULL,
    relative_path TEXT NOT NULL DEFAULT '',
    message TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tracks_available
ON tracks(is_available);

CREATE INDEX IF NOT EXISTS idx_tracks_title
ON tracks(normalized_title);

CREATE INDEX IF NOT EXISTS idx_tracks_artist
ON tracks(artist_id);

CREATE INDEX IF NOT EXISTS idx_tracks_album
ON tracks(album_id);

CREATE INDEX IF NOT EXISTS idx_tracks_order
ON tracks(album_id, disc_number, track_number, normalized_title);

CREATE INDEX IF NOT EXISTS idx_tracks_signature
ON tracks(content_signature);

CREATE INDEX IF NOT EXISTS idx_tracks_modified
ON tracks(modified_time_ns);

CREATE INDEX IF NOT EXISTS idx_tracks_available_title
ON tracks(is_available, normalized_title);

CREATE INDEX IF NOT EXISTS idx_tracks_available_artist
ON tracks(is_available, artist_id);

CREATE INDEX IF NOT EXISTS idx_tracks_available_album
ON tracks(is_available, album_id);

CREATE INDEX IF NOT EXISTS idx_scan_errors_run
ON scan_errors(scan_run_id);
"""


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)

    # Additive migrations for databases created by earlier development builds.
    artist_columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(artists)").fetchall()
    }
    if "sort_name" not in artist_columns:
        connection.execute("ALTER TABLE artists ADD COLUMN sort_name TEXT NOT NULL DEFAULT ''")
    if "display_name_override" not in artist_columns:
        connection.execute("ALTER TABLE artists ADD COLUMN display_name_override TEXT")
        # Migrate group corrections from early development builds that stored
        # the same override redundantly on every track.
        rows = connection.execute(
            """
            SELECT artist_id, MIN(artist_override) AS value,
                   COUNT(DISTINCT artist_override) AS value_count
              FROM tracks
             WHERE artist_id IS NOT NULL
               AND artist_override IS NOT NULL
               AND artist_override <> ''
             GROUP BY artist_id
            """
        ).fetchall()
        for row in rows:
            if int(row["value_count"] or 0) == 1:
                connection.execute(
                    "UPDATE artists SET display_name_override = ? WHERE id = ?",
                    (row["value"], row["artist_id"]),
                )
        connection.execute("UPDATE tracks SET artist_override = NULL")

    track_columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(tracks)").fetchall()
    }
    if "sort_title" not in track_columns:
        connection.execute("ALTER TABLE tracks ADD COLUMN sort_title TEXT NOT NULL DEFAULT ''")

    album_columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(albums)").fetchall()
    }
    if "sort_title" not in album_columns:
        connection.execute("ALTER TABLE albums ADD COLUMN sort_title TEXT NOT NULL DEFAULT ''")

    connection.execute(
        "INSERT INTO schema_info(key, value) VALUES('schema_version', ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (str(SCHEMA_VERSION),),
    )
    connection.execute(
        "INSERT INTO schema_info(key, value) VALUES('created_by', 'MP3 Source Music Library') "
        "ON CONFLICT(key) DO NOTHING"
    )


def backup_database_if_needed(database_path: Path = DATABASE_PATH) -> Path | None:
    """Create at most one automatic backup per local calendar day."""
    if not database_path.exists() or database_path.stat().st_size == 0:
        return None

    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    destination = BACKUP_DIR / f"library-{stamp}.db"
    if destination.exists():
        return destination

    source = sqlite3.connect(database_path)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination


def create_scan_run(connection: sqlite3.Connection, started_at: str) -> int:
    cursor = connection.execute(
        "INSERT INTO scan_runs(started_at, status) VALUES(?, 'running')",
        (started_at,),
    )
    return int(cursor.lastrowid)


def complete_scan_run(
    connection: sqlite3.Connection,
    scan_run_id: int,
    *,
    status: str,
    completed_at: str,
    stats: dict[str, Any],
) -> None:
    connection.execute(
        """
        UPDATE scan_runs
           SET completed_at = ?,
               status = ?,
               mp3_files = ?,
               loaded = ?,
               errors = ?,
               cache_hits = ?,
               details_json = ?
         WHERE id = ?
        """,
        (
            completed_at,
            status,
            int(stats.get("mp3Files", 0)),
            int(stats.get("loaded", 0)),
            int(stats.get("errors", 0)),
            int(stats.get("cacheHits", 0)),
            json.dumps(stats, ensure_ascii=False),
            scan_run_id,
        ),
    )


def add_scan_error(
    connection: sqlite3.Connection,
    scan_run_id: int,
    *,
    severity: str,
    category: str,
    relative_path: str,
    message: str,
) -> None:
    connection.execute(
        """
        INSERT INTO scan_errors(
            scan_run_id, severity, category, relative_path, message, occurred_at
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (scan_run_id, severity, category, relative_path, message, utc_now()),
    )


def load_track_rows(connection: sqlite3.Connection) -> list[sqlite3.Row]:
    return connection.execute(
        """
        SELECT t.*, ar.name AS artist_name,
               ar.display_name_override AS artist_display_override,
               al.title AS album_title,
               aw.relative_path AS artwork_relative_path,
               aw.source_type AS artwork_source_type
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
          LEFT JOIN artworks aw ON aw.id = t.artwork_id
        """
    ).fetchall()


def row_to_track(row: sqlite3.Row) -> dict[str, Any]:
    metadata_source: dict[str, Any]
    try:
        parsed = json.loads(row["metadata_source_json"] or "{}")
        metadata_source = parsed if isinstance(parsed, dict) else {}
    except Exception:
        metadata_source = {}

    title = row["title_override"] or row["title"] or ""
    artist = (
        row["artist_override"]
        or row["artist_display_override"]
        or row["artist_name"]
        or ""
    )
    album = row["album_override"] or row["album_title"] or ""

    track: dict[str, Any] = {
        "id": str(row["id"]),
        "name": title,
        "originalName": row["title"] or "",
        "isCorrected": bool(row["title_override"]),
        "artist": artist,
        "originalArtist": row["artist_name"] or "",
        "artistDbId": row["artist_id"] or "",
        "isArtistCorrected": bool(
            row["artist_override"] or row["artist_display_override"]
        ),
        "albumArtist": row["album_artist"] or "",
        "album": album,
        "originalAlbum": row["album_title"] or "",
        "genre": row["genre"] or "",
        "composer": row["composer"] or "",
        "year": row["year"] if row["year"] is not None else "",
        "time": int(row["duration_ms"] or 0),
        "trackNumber": row["track_number"] if row["track_number"] is not None else "",
        "discNumber": row["disc_number"] if row["disc_number"] is not None else "",
        "playCount": int(row["play_count"] or 0),
        "dateAdded": row["date_added"] or "",
        "lastPlayedAt": row["last_played_at"] or "",
        "favorite": bool(row["favorite"]),
        "rating": row["rating"] if row["rating"] is not None else "",
        "kind": row["kind"] or "MP3オーディオファイル",
        "size": int(row["file_size"] or 0),
        "relativePath": row["relative_path"] or "",
        "audioFile": row["audio_file"] or row["relative_path"] or "",
        "artworkFile": row["artwork_relative_path"] or "",
        "artworkSource": row["artwork_source_type"] or "",
        "metadataSource": metadata_source,
    }
    if row["legacy_id"]:
        track["legacyId"] = row["legacy_id"]
    if row["legacy_match_method"]:
        track["legacyMatchMethod"] = row["legacy_match_method"]
    return track


def get_available_tracks(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT t.*, ar.name AS artist_name,
               ar.display_name_override AS artist_display_override,
               al.title AS album_title,
               aw.relative_path AS artwork_relative_path,
               aw.source_type AS artwork_source_type
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
          LEFT JOIN artworks aw ON aw.id = t.artwork_id
         WHERE t.is_available = 1
         ORDER BY COALESCE(t.artist_override, ar.display_name_override, ar.name, '') COLLATE NOCASE,
                  COALESCE(t.album_override, al.title, '') COLLATE NOCASE,
                  COALESCE(t.disc_number, 0),
                  COALESCE(t.track_number, 0),
                  COALESCE(t.title_override, t.title, '') COLLATE NOCASE,
                  t.relative_path COLLATE NOCASE
        """
    ).fetchall()
    return [row_to_track(row) for row in rows]



TITLE_EXPR = "COALESCE(NULLIF(t.title_override, ''), t.title, '')"
TITLE_SORT_EXPR = f"COALESCE(NULLIF(t.title_override, ''), NULLIF(t.sort_title, ''), {TITLE_EXPR})"
ARTIST_EXPR = (
    "COALESCE(NULLIF(t.artist_override, ''), "
    "NULLIF(ar.display_name_override, ''), ar.name, '')"
)
ALBUM_EXPR = "COALESCE(NULLIF(t.album_override, ''), al.title, '')"
ARTIST_SORT_EXPR = f"COALESCE(NULLIF(ar.sort_name, ''), {ARTIST_EXPR})"
ALBUM_SORT_EXPR = f"COALESCE(NULLIF(al.sort_title, ''), {ALBUM_EXPR})"
UNKNOWN_ARTIST_KEY = "__unknown_artist__"
UNKNOWN_ALBUM_KEY = "__unknown_album__"


def _bounded_page_size(value: int) -> int:
    return max(1, min(int(value), 200))


def _validated_index_key(value: str) -> str:
    key = str(value or "").strip()
    if not key:
        return ""
    if key not in INDEX_KEY_SET:
        raise ValueError(f"unsupported index key: {key}")
    return key


def _index_counts(rows: Sequence[sqlite3.Row]) -> dict[str, int]:
    counts = {key: 0 for key in INDEX_KEYS}
    for row in rows:
        key = str(row["bucket"] or "他")
        if key in counts:
            counts[key] = int(row["item_count"] or 0)
        else:
            counts["他"] += int(row["item_count"] or 0)
    return counts


def _like_conditions(
    query: str,
    *,
    include_title: bool = True,
    include_artist: bool = True,
    include_album: bool = True,
    include_composer: bool = False,
) -> tuple[list[str], list[Any]]:
    query = str(query or "").strip()
    if not query:
        return [], []

    visible_like = f"%{query}%"
    normalized_like = f"%{normalized(query)}%"
    pieces: list[str] = []
    params: list[Any] = []

    if include_title:
        pieces.extend([f"{TITLE_EXPR} LIKE ? COLLATE NOCASE", "t.normalized_title LIKE ?"])
        params.extend([visible_like, normalized_like])
    if include_artist:
        pieces.extend([f"{ARTIST_EXPR} LIKE ? COLLATE NOCASE", "ar.normalized_name LIKE ?"])
        params.extend([visible_like, normalized_like])
    if include_album:
        pieces.extend([f"{ALBUM_EXPR} LIKE ? COLLATE NOCASE", "al.normalized_title LIKE ?"])
        params.extend([visible_like, normalized_like])
    if include_composer:
        pieces.append("t.composer LIKE ? COLLATE NOCASE")
        params.append(visible_like)

    return (["(" + " OR ".join(pieces) + ")"] if pieces else []), params


def _scope_condition(column: str, value: str, unknown_key: str) -> tuple[str, list[Any]]:
    value = str(value or "")
    if value == unknown_key:
        return f"{column} IS NULL", []
    return f"{column} = ?", [value]


def _base_track_conditions(
    *,
    query: str,
    latin_only: bool,
    corrected_only: bool,
    artist_key: str = "",
    album_key: str = "",
    global_album_title: str = "",
) -> tuple[list[str], list[Any]]:
    conditions = ["t.is_available = 1"]
    params: list[Any] = []

    q_conditions, q_params = _like_conditions(
        query,
        include_title=True,
        include_artist=True,
        include_album=True,
        include_composer=True,
    )
    conditions.extend(q_conditions)
    params.extend(q_params)

    if latin_only:
        conditions.append(f"is_latin_only({TITLE_EXPR}) = 1")
    if corrected_only:
        conditions.append(
            "(NULLIF(t.title_override, '') IS NOT NULL "
            "OR NULLIF(t.artist_override, '') IS NOT NULL "
            "OR NULLIF(ar.display_name_override, '') IS NOT NULL)"
        )
    if artist_key:
        condition, values = _scope_condition("t.artist_id", artist_key, UNKNOWN_ARTIST_KEY)
        conditions.append(condition)
        params.extend(values)
    if album_key:
        condition, values = _scope_condition("t.album_id", album_key, UNKNOWN_ALBUM_KEY)
        conditions.append(condition)
        params.extend(values)
    if global_album_title:
        conditions.append(f"{ALBUM_EXPR} = ?")
        params.append(global_album_title)

    return conditions, params


def _track_order(sort: str, *, album_context: bool) -> str:
    if album_context and sort in {"album_order", ""}:
        return (
            "COALESCE(t.disc_number, 0), COALESCE(t.track_number, 0), "
            f"{TITLE_EXPR} COLLATE NOCASE, t.relative_path COLLATE NOCASE"
        )
    orders = {
        "artist": f"{ARTIST_EXPR} COLLATE NOCASE, {TITLE_EXPR} COLLATE NOCASE",
        "album": (
            f"{ALBUM_EXPR} COLLATE NOCASE, COALESCE(t.disc_number, 0), "
            f"COALESCE(t.track_number, 0), {TITLE_EXPR} COLLATE NOCASE"
        ),
        "plays": f"t.play_count DESC, {TITLE_EXPR} COLLATE NOCASE",
        "added": f"t.date_added DESC, {TITLE_EXPR} COLLATE NOCASE",
        "title": f"catalog_sort_key({TITLE_SORT_EXPR}) COLLATE NOCASE, {TITLE_EXPR} COLLATE NOCASE, {ARTIST_EXPR} COLLATE NOCASE",
    }
    return orders.get(sort, orders["title"])


def browse_tracks(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    limit: int = 80,
    offset: int = 0,
    latin_only: bool = False,
    corrected_only: bool = False,
    artist_key: str = "",
    album_key: str = "",
    global_album_title: str = "",
    sort: str = "title",
    index_key: str = "",
) -> dict[str, Any]:
    limit = _bounded_page_size(limit)
    offset = max(0, int(offset))
    index_key = _validated_index_key(index_key)
    album_context = bool(album_key or global_album_title)
    conditions, params = _base_track_conditions(
        query=query,
        latin_only=latin_only,
        corrected_only=corrected_only,
        artist_key=artist_key,
        album_key=album_key,
        global_album_title=global_album_title,
    )
    base_where_sql = " AND ".join(conditions)
    count_rows = connection.execute(
        f"""
        SELECT catalog_bucket({TITLE_SORT_EXPR}) AS bucket,
               COUNT(*) AS item_count
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
         WHERE {base_where_sql}
         GROUP BY bucket
        """,
        params,
    ).fetchall()
    index_counts = _index_counts(count_rows)

    filtered_conditions = list(conditions)
    filtered_params = list(params)
    if index_key:
        filtered_conditions.append(f"catalog_bucket({TITLE_SORT_EXPR}) = ?")
        filtered_params.append(index_key)
    where_sql = " AND ".join(filtered_conditions)

    aggregate = connection.execute(
        f"""
        SELECT COUNT(*) AS total, COALESCE(SUM(t.duration_ms), 0) AS duration_ms
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
         WHERE {where_sql}
        """,
        filtered_params,
    ).fetchone()

    rows = connection.execute(
        f"""
        SELECT t.*, ar.name AS artist_name,
               ar.display_name_override AS artist_display_override,
               al.title AS album_title,
               aw.relative_path AS artwork_relative_path,
               aw.source_type AS artwork_source_type
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
          LEFT JOIN artworks aw ON aw.id = t.artwork_id
         WHERE {where_sql}
         ORDER BY {_track_order(sort, album_context=album_context)}
         LIMIT ? OFFSET ?
        """,
        [*filtered_params, limit, offset],
    ).fetchall()
    total = int(aggregate["total"] or 0)
    return {
        "kind": "tracks",
        "items": [row_to_track(row) for row in rows],
        "total": total,
        "trackTotal": total,
        "totalDurationMs": int(aggregate["duration_ms"] or 0),
        "offset": offset,
        "limit": limit,
        "hasMore": offset + len(rows) < total,
        "indexKey": index_key,
        "indexCounts": index_counts,
    }


def browse_artists(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    limit: int = 80,
    offset: int = 0,
    index_key: str = "",
) -> dict[str, Any]:
    limit = _bounded_page_size(limit)
    offset = max(0, int(offset))
    index_key = _validated_index_key(index_key)
    conditions = ["t.is_available = 1"]
    params: list[Any] = []
    q_conditions, q_params = _like_conditions(
        query, include_title=False, include_artist=True, include_album=False
    )
    conditions.extend(q_conditions)
    params.extend(q_params)
    where_sql = " AND ".join(conditions)
    group_sql = f"COALESCE(t.artist_id, '{UNKNOWN_ARTIST_KEY}'), {ARTIST_EXPR}, COALESCE(ar.name, '')"
    grouped_cte = f"""
        WITH grouped AS (
            SELECT COALESCE(t.artist_id, '{UNKNOWN_ARTIST_KEY}') AS key,
                   {ARTIST_EXPR} AS display,
                   COALESCE(ar.name, '') AS original_artist,
                   MIN(catalog_sort_key({ARTIST_SORT_EXPR})) AS sort_key,
                   MIN(catalog_bucket({ARTIST_SORT_EXPR})) AS bucket,
                   COUNT(*) AS track_count,
                   COUNT(DISTINCT COALESCE(t.album_id, '{UNKNOWN_ALBUM_KEY}')) AS album_count,
                   MAX(CASE WHEN NULLIF(t.artist_override, '') IS NOT NULL
                              OR NULLIF(ar.display_name_override, '') IS NOT NULL
                            THEN 1 ELSE 0 END) AS corrected
              FROM tracks t
              LEFT JOIN artists ar ON ar.id = t.artist_id
              LEFT JOIN albums al ON al.id = t.album_id
             WHERE {where_sql}
             GROUP BY {group_sql}
        )
    """

    count_rows = connection.execute(
        grouped_cte + " SELECT bucket, COUNT(*) AS item_count FROM grouped GROUP BY bucket",
        params,
    ).fetchall()
    index_counts = _index_counts(count_rows)
    filter_sql = " WHERE bucket = ?" if index_key else ""
    filter_params: list[Any] = [index_key] if index_key else []

    totals = connection.execute(
        grouped_cte
        + f" SELECT COUNT(*) AS total, COALESCE(SUM(track_count), 0) AS track_total FROM grouped{filter_sql}",
        [*params, *filter_params],
    ).fetchone()
    rows = connection.execute(
        grouped_cte
        + f"""
          SELECT key, display, original_artist, bucket, track_count, album_count, corrected
            FROM grouped{filter_sql}
           ORDER BY sort_key COLLATE NOCASE, display COLLATE NOCASE
           LIMIT ? OFFSET ?
        """,
        [*params, *filter_params, limit, offset],
    ).fetchall()
    items = [
        {
            "key": str(row["key"]),
            "display": str(row["display"] or "(不明なアーティスト)"),
            "originalArtist": str(row["original_artist"] or ""),
            "indexKey": str(row["bucket"] or "他"),
            "count": int(row["track_count"] or 0),
            "albumCount": int(row["album_count"] or 0),
            "isCorrected": bool(row["corrected"]),
        }
        for row in rows
    ]
    total = int(totals["total"] or 0)
    return {
        "kind": "artists",
        "items": items,
        "total": total,
        "trackTotal": int(totals["track_total"] or 0),
        "totalDurationMs": 0,
        "offset": offset,
        "limit": limit,
        "hasMore": offset + len(items) < total,
        "indexKey": index_key,
        "indexCounts": index_counts,
    }

def browse_artist_albums(
    connection: sqlite3.Connection,
    *,
    artist_key: str,
    query: str = "",
    limit: int = 80,
    offset: int = 0,
) -> dict[str, Any]:
    limit = _bounded_page_size(limit)
    offset = max(0, int(offset))
    artist_condition, artist_params = _scope_condition(
        "t.artist_id", artist_key, UNKNOWN_ARTIST_KEY
    )
    conditions = ["t.is_available = 1", artist_condition]
    params: list[Any] = [*artist_params]
    q_conditions, q_params = _like_conditions(
        query, include_title=False, include_artist=False, include_album=True
    )
    conditions.extend(q_conditions)
    params.extend(q_params)
    where_sql = " AND ".join(conditions)
    album_key_expr = f"COALESCE(t.album_id, '{UNKNOWN_ALBUM_KEY}')"
    group_sql = f"{album_key_expr}, {ALBUM_EXPR}"

    totals = connection.execute(
        f"""
        SELECT COUNT(*) AS total, COALESCE(SUM(track_count), 0) AS track_total
          FROM (
            SELECT COUNT(*) AS track_count
              FROM tracks t
              LEFT JOIN artists ar ON ar.id = t.artist_id
              LEFT JOIN albums al ON al.id = t.album_id
             WHERE {where_sql}
             GROUP BY {group_sql}
          ) grouped
        """,
        params,
    ).fetchone()
    rows = connection.execute(
        f"""
        SELECT {album_key_expr} AS key,
               {ALBUM_EXPR} AS display,
               COUNT(*) AS track_count,
               MAX(t.year) AS year,
               MIN(CASE WHEN aw.relative_path IS NOT NULL AND aw.relative_path <> ''
                        THEN aw.relative_path END) AS artwork_file
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
          LEFT JOIN artworks aw ON aw.id = t.artwork_id
         WHERE {where_sql}
         GROUP BY {group_sql}
         ORDER BY display COLLATE NOCASE
         LIMIT ? OFFSET ?
        """,
        [*params, limit, offset],
    ).fetchall()
    items = [
        {
            "key": str(row["key"]),
            "display": str(row["display"] or "(不明なアルバム)"),
            "count": int(row["track_count"] or 0),
            "year": row["year"] if row["year"] is not None else "",
            "artworkFile": str(row["artwork_file"] or ""),
        }
        for row in rows
    ]
    total = int(totals["total"] or 0)
    return {
        "kind": "artist_albums",
        "items": items,
        "total": total,
        "trackTotal": int(totals["track_total"] or 0),
        "totalDurationMs": 0,
        "offset": offset,
        "limit": limit,
        "hasMore": offset + len(items) < total,
    }


def browse_albums(
    connection: sqlite3.Connection,
    *,
    query: str = "",
    limit: int = 80,
    offset: int = 0,
    index_key: str = "",
) -> dict[str, Any]:
    limit = _bounded_page_size(limit)
    offset = max(0, int(offset))
    index_key = _validated_index_key(index_key)
    conditions = ["t.is_available = 1"]
    params: list[Any] = []
    q_conditions, q_params = _like_conditions(
        query, include_title=False, include_artist=True, include_album=True
    )
    conditions.extend(q_conditions)
    params.extend(q_params)
    where_sql = " AND ".join(conditions)
    group_sql = ALBUM_EXPR
    grouped_cte = f"""
        WITH grouped AS (
            SELECT {ALBUM_EXPR} AS key,
                   MIN(catalog_sort_key({ALBUM_SORT_EXPR})) AS sort_key,
                   MIN(catalog_bucket({ALBUM_SORT_EXPR})) AS bucket,
                   COUNT(*) AS track_count,
                   GROUP_CONCAT(DISTINCT {ARTIST_EXPR}) AS artist_names,
                   MIN(CASE WHEN aw.relative_path IS NOT NULL AND aw.relative_path <> ''
                            THEN aw.relative_path END) AS artwork_file
              FROM tracks t
              LEFT JOIN artists ar ON ar.id = t.artist_id
              LEFT JOIN albums al ON al.id = t.album_id
              LEFT JOIN artworks aw ON aw.id = t.artwork_id
             WHERE {where_sql}
             GROUP BY {group_sql}
        )
    """

    count_rows = connection.execute(
        grouped_cte + " SELECT bucket, COUNT(*) AS item_count FROM grouped GROUP BY bucket",
        params,
    ).fetchall()
    index_counts = _index_counts(count_rows)
    filter_sql = " WHERE bucket = ?" if index_key else ""
    filter_params: list[Any] = [index_key] if index_key else []
    totals = connection.execute(
        grouped_cte
        + f" SELECT COUNT(*) AS total, COALESCE(SUM(track_count), 0) AS track_total FROM grouped{filter_sql}",
        [*params, *filter_params],
    ).fetchone()
    rows = connection.execute(
        grouped_cte
        + f"""
          SELECT key, bucket, track_count, artist_names, artwork_file
            FROM grouped{filter_sql}
           ORDER BY sort_key COLLATE NOCASE, key COLLATE NOCASE
           LIMIT ? OFFSET ?
        """,
        [*params, *filter_params, limit, offset],
    ).fetchall()
    items = []
    for row in rows:
        artists = [name for name in str(row["artist_names"] or "").split(",") if name]
        items.append(
            {
                "key": str(row["key"] or "(不明なアルバム)"),
                "display": str(row["key"] or "(不明なアルバム)"),
                "indexKey": str(row["bucket"] or "他"),
                "count": int(row["track_count"] or 0),
                "artists": artists,
                "artworkFile": str(row["artwork_file"] or ""),
            }
        )
    total = int(totals["total"] or 0)
    return {
        "kind": "albums",
        "items": items,
        "total": total,
        "trackTotal": int(totals["track_total"] or 0),
        "totalDurationMs": 0,
        "offset": offset,
        "limit": limit,
        "hasMore": offset + len(items) < total,
        "indexKey": index_key,
        "indexCounts": index_counts,
    }

def browse_library(
    connection: sqlite3.Connection,
    *,
    view: str,
    query: str = "",
    limit: int = 80,
    offset: int = 0,
    latin_only: bool = False,
    corrected_only: bool = False,
    artist_key: str = "",
    album_key: str = "",
    album_title: str = "",
    sort: str = "title",
    index_key: str = "",
) -> dict[str, Any]:
    if view == "artists":
        return browse_artists(
            connection, query=query, limit=limit, offset=offset, index_key=index_key
        )
    if view == "artist_albums":
        if not artist_key:
            raise ValueError("artistKey is required")
        return browse_artist_albums(
            connection,
            artist_key=artist_key,
            query=query,
            limit=limit,
            offset=offset,
        )
    if view == "albums":
        return browse_albums(
            connection, query=query, limit=limit, offset=offset, index_key=index_key
        )
    if view == "artist_tracks":
        if not artist_key or not album_key:
            raise ValueError("artistKey and albumKey are required")
        return browse_tracks(
            connection,
            query=query,
            limit=limit,
            offset=offset,
            latin_only=latin_only,
            corrected_only=corrected_only,
            artist_key=artist_key,
            album_key=album_key,
            sort=sort or "album_order",
            index_key=index_key,
        )
    if view == "album_tracks":
        if not album_title:
            raise ValueError("albumTitle is required")
        return browse_tracks(
            connection,
            query=query,
            limit=limit,
            offset=offset,
            latin_only=latin_only,
            corrected_only=corrected_only,
            global_album_title=album_title,
            sort=sort or "album_order",
            index_key=index_key,
        )
    if view != "songs":
        raise ValueError(f"unsupported view: {view}")
    return browse_tracks(
        connection,
        query=query,
        limit=limit,
        offset=offset,
        latin_only=latin_only,
        corrected_only=corrected_only,
        sort=sort,
        index_key=index_key,
    )


def get_track_by_path(connection: sqlite3.Connection, relative_path: str) -> sqlite3.Row | None:
    return connection.execute(
        "SELECT * FROM tracks WHERE relative_path = ?",
        (relative_path,),
    ).fetchone()


def upsert_artist(
    connection: sqlite3.Connection,
    name: str,
    timestamp: str,
    sort_name: str = "",
) -> str | None:
    name = str(name or "").strip()
    sort_name = str(sort_name or "").strip()
    if not name:
        return None
    normalized_name = normalized(name)
    artist_id = stable_key("artist", normalized_name)
    connection.execute(
        """
        INSERT INTO artists(id, name, normalized_name, sort_name, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_name) DO UPDATE SET
            name = excluded.name,
            sort_name = CASE
                WHEN excluded.sort_name <> '' THEN excluded.sort_name
                ELSE artists.sort_name
            END,
            updated_at = excluded.updated_at
        """,
        (artist_id, name, normalized_name, sort_name, timestamp, timestamp),
    )
    row = connection.execute(
        "SELECT id FROM artists WHERE normalized_name = ?",
        (normalized_name,),
    ).fetchone()
    return str(row["id"]) if row else artist_id


def upsert_artwork(
    connection: sqlite3.Connection,
    *,
    relative_path: str,
    source_type: str,
    source_mp3_path: str,
    mime_type: str,
    file_hash: str,
    timestamp: str,
) -> str | None:
    relative_path = str(relative_path or "").strip()
    if not relative_path:
        return None
    artwork_id = stable_key("art", source_type, relative_path)
    connection.execute(
        """
        INSERT INTO artworks(
            id, relative_path, source_type, source_mp3_path,
            mime_type, file_hash, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(relative_path) DO UPDATE SET
            source_type = excluded.source_type,
            source_mp3_path = excluded.source_mp3_path,
            mime_type = excluded.mime_type,
            file_hash = excluded.file_hash,
            updated_at = excluded.updated_at
        """,
        (
            artwork_id,
            relative_path,
            source_type,
            source_mp3_path,
            mime_type,
            file_hash,
            timestamp,
            timestamp,
        ),
    )
    row = connection.execute(
        "SELECT id FROM artworks WHERE relative_path = ?",
        (relative_path,),
    ).fetchone()
    return str(row["id"]) if row else artwork_id


def upsert_album(
    connection: sqlite3.Connection,
    *,
    title: str,
    album_artist: str,
    fallback_artist: str,
    sort_title: str,
    year: int | None,
    artwork_id: str | None,
    timestamp: str,
) -> str | None:
    title = str(title or "").strip()
    if not title:
        return None
    identity_artist = str(album_artist or fallback_artist or "").strip()
    sort_title = str(sort_title or "").strip()
    normalized_title = normalized(title)
    normalized_album_artist = normalized(identity_artist)
    album_id = stable_key("album", normalized_title, normalized_album_artist)
    connection.execute(
        """
        INSERT INTO albums(
            id, title, normalized_title, album_artist,
            normalized_album_artist, sort_title, year, artwork_id, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(normalized_title, normalized_album_artist) DO UPDATE SET
            title = excluded.title,
            album_artist = CASE
                WHEN excluded.album_artist <> '' THEN excluded.album_artist
                ELSE albums.album_artist
            END,
            sort_title = CASE
                WHEN excluded.sort_title <> '' THEN excluded.sort_title
                ELSE albums.sort_title
            END,
            year = COALESCE(excluded.year, albums.year),
            artwork_id = COALESCE(excluded.artwork_id, albums.artwork_id),
            updated_at = excluded.updated_at
        """,
        (
            album_id,
            title,
            normalized_title,
            identity_artist,
            normalized_album_artist,
            sort_title,
            year,
            artwork_id,
            timestamp,
            timestamp,
        ),
    )
    row = connection.execute(
        """
        SELECT id FROM albums
         WHERE normalized_title = ? AND normalized_album_artist = ?
        """,
        (normalized_title, normalized_album_artist),
    ).fetchone()
    return str(row["id"]) if row else album_id


def upsert_track(
    connection: sqlite3.Connection,
    *,
    track: dict[str, Any],
    artist_id: str | None,
    album_id: str | None,
    artwork_id: str | None,
    file_size: int,
    modified_time_ns: int,
    content_signature: str,
    timestamp: str,
    existing_row: sqlite3.Row | None,
) -> None:
    play_count = int(track.get("playCount") or 0)
    date_added = str(track.get("dateAdded") or "")
    favorite = 0
    rating: int | None = None
    last_played_at = ""
    title_override = None
    artist_override = None
    album_override = None
    created_at = timestamp

    if existing_row is not None:
        play_count = int(existing_row["play_count"] or 0)
        date_added = str(existing_row["date_added"] or date_added)
        favorite = int(existing_row["favorite"] or 0)
        rating = existing_row["rating"]
        last_played_at = str(existing_row["last_played_at"] or "")
        title_override = existing_row["title_override"]
        artist_override = existing_row["artist_override"]
        album_override = existing_row["album_override"]
        created_at = str(existing_row["created_at"] or timestamp)

    if not date_added:
        date_added = timestamp

    connection.execute(
        """
        INSERT INTO tracks(
            id, relative_path, filename,
            title, normalized_title, sort_title, artist_id, album_id,
            album_artist, genre, composer, year, duration_ms,
            track_number, disc_number, kind,
            file_size, modified_time_ns, content_signature,
            audio_file, artwork_id, metadata_source_json,
            play_count, date_added, last_played_at, favorite, rating,
            title_override, artist_override, album_override,
            legacy_id, legacy_match_method,
            last_scanned_at, is_available, created_at, updated_at
        ) VALUES (
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?,
            ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, ?,
            ?, 1, ?, ?
        )
        ON CONFLICT(id) DO UPDATE SET
            relative_path = excluded.relative_path,
            filename = excluded.filename,
            title = excluded.title,
            normalized_title = excluded.normalized_title,
            sort_title = excluded.sort_title,
            artist_id = excluded.artist_id,
            album_id = excluded.album_id,
            album_artist = excluded.album_artist,
            genre = excluded.genre,
            composer = excluded.composer,
            year = excluded.year,
            duration_ms = excluded.duration_ms,
            track_number = excluded.track_number,
            disc_number = excluded.disc_number,
            kind = excluded.kind,
            file_size = excluded.file_size,
            modified_time_ns = excluded.modified_time_ns,
            content_signature = excluded.content_signature,
            audio_file = excluded.audio_file,
            artwork_id = excluded.artwork_id,
            metadata_source_json = excluded.metadata_source_json,
            legacy_id = excluded.legacy_id,
            legacy_match_method = excluded.legacy_match_method,
            last_scanned_at = excluded.last_scanned_at,
            is_available = 1,
            updated_at = excluded.updated_at
        """,
        (
            str(track["id"]),
            str(track["relativePath"]),
            Path(str(track["relativePath"])).name,
            str(track.get("name") or ""),
            normalized(track.get("name")),
            str(track.get("sortTitle") or ""),
            artist_id,
            album_id,
            str(track.get("albumArtist") or ""),
            str(track.get("genre") or ""),
            str(track.get("composer") or ""),
            int(track["year"]) if str(track.get("year") or "").isdigit() else None,
            int(track.get("time") or 0),
            int(track["trackNumber"]) if str(track.get("trackNumber") or "").isdigit() else None,
            int(track["discNumber"]) if str(track.get("discNumber") or "").isdigit() else None,
            str(track.get("kind") or "MP3オーディオファイル"),
            int(file_size),
            int(modified_time_ns),
            content_signature,
            str(track.get("audioFile") or track["relativePath"]),
            artwork_id,
            json.dumps(track.get("metadataSource") or {}, ensure_ascii=False),
            play_count,
            date_added,
            last_played_at,
            favorite,
            rating,
            title_override,
            artist_override,
            album_override,
            str(track.get("legacyId") or ""),
            str(track.get("legacyMatchMethod") or ""),
            timestamp,
            created_at,
            timestamp,
        ),
    )


def mark_track_seen_without_reparse(
    connection: sqlite3.Connection,
    *,
    track_id: str,
    timestamp: str,
) -> None:
    connection.execute(
        """
        UPDATE tracks
           SET is_available = 1,
               last_scanned_at = ?,
               updated_at = ?
         WHERE id = ?
        """,
        (timestamp, timestamp, track_id),
    )


def increment_play_count(connection: sqlite3.Connection, track_id: str) -> int | None:
    timestamp = utc_now()
    cursor = connection.execute(
        """
        UPDATE tracks
           SET play_count = play_count + 1,
               last_played_at = ?,
               updated_at = ?
         WHERE id = ? AND is_available = 1
        """,
        (timestamp, timestamp, track_id),
    )
    if cursor.rowcount == 0:
        return None
    row = connection.execute(
        "SELECT play_count FROM tracks WHERE id = ?",
        (track_id,),
    ).fetchone()
    return int(row["play_count"]) if row else None



def set_title_override(
    connection: sqlite3.Connection, track_id: str, value: str | None
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT title FROM tracks WHERE id = ? AND is_available = 1",
        (track_id,),
    ).fetchone()
    if row is None:
        return None
    original = str(row["title"] or "")
    cleaned = str(value or "").strip()
    override = cleaned if cleaned and cleaned != original else None
    timestamp = utc_now()
    connection.execute(
        "UPDATE tracks SET title_override = ?, updated_at = ? WHERE id = ?",
        (override, timestamp, track_id),
    )
    return {
        "id": track_id,
        "name": override or original,
        "originalName": original,
        "isCorrected": bool(override),
    }


def set_artist_override(
    connection: sqlite3.Connection, artist_id: str, value: str | None
) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT name FROM artists WHERE id = ?",
        (artist_id,),
    ).fetchone()
    if row is None:
        return None
    original = str(row["name"] or "")
    cleaned = str(value or "").strip()
    override = cleaned if cleaned and cleaned != original else None
    timestamp = utc_now()
    connection.execute(
        """
        UPDATE artists
           SET display_name_override = ?, updated_at = ?
         WHERE id = ?
        """,
        (override, timestamp, artist_id),
    )
    # Clear the development-build per-track group override. A true per-track
    # override remains reserved for a future separate UI operation.
    connection.execute(
        "UPDATE tracks SET artist_override = NULL, updated_at = ? WHERE artist_id = ?",
        (timestamp, artist_id),
    )
    count_row = connection.execute(
        "SELECT COUNT(*) AS count FROM tracks WHERE artist_id = ?",
        (artist_id,),
    ).fetchone()
    return {
        "artistId": artist_id,
        "artist": override or original,
        "originalArtist": original,
        "isCorrected": bool(override),
        "updatedTracks": int(count_row["count"] or 0),
    }

def database_stats(connection: sqlite3.Connection) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT COUNT(*) AS total_rows,
               SUM(CASE WHEN is_available = 1 THEN 1 ELSE 0 END) AS available_tracks,
               SUM(CASE WHEN is_available = 0 THEN 1 ELSE 0 END) AS unavailable_tracks,
               SUM(CASE WHEN artwork_id IS NOT NULL THEN 1 ELSE 0 END) AS artwork_tracks,
               SUM(play_count) AS total_plays
          FROM tracks
        """
    ).fetchone()
    latest = connection.execute(
        """
        SELECT id, started_at, completed_at, status, mp3_files, loaded, errors, cache_hits
          FROM scan_runs
         ORDER BY id DESC LIMIT 1
        """
    ).fetchone()
    return {
        "database": DATABASE_PATH.name,
        "schemaVersion": SCHEMA_VERSION,
        "totalRows": int(row["total_rows"] or 0),
        "availableTracks": int(row["available_tracks"] or 0),
        "unavailableTracks": int(row["unavailable_tracks"] or 0),
        "artworkTracks": int(row["artwork_tracks"] or 0),
        "totalPlays": int(row["total_plays"] or 0),
        "latestScan": dict(latest) if latest else None,
    }


def manual_backup(destination: Path | None = None) -> Path:
    if not DATABASE_PATH.exists():
        raise FileNotFoundError("library.db がまだ作成されていません。先にライブラリを起動してください。")
    BACKUP_DIR.mkdir(exist_ok=True)
    if destination is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        destination = BACKUP_DIR / f"library-manual-{stamp}.db"
    source = sqlite3.connect(DATABASE_PATH)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
    finally:
        target.close()
        source.close()
    return destination
