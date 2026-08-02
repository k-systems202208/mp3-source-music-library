#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import unicodedata
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

from paths import BACKUP_DIR, DATA_ROOT, ensure_data_directories
from typing import Any, Iterator, Sequence

ensure_data_directories()
DATABASE_PATH = DATA_ROOT / "library.db"
SCHEMA_VERSION = 6
DEFAULT_SKIN_ID = "library"
ALLOWED_SKIN_IDS = frozenset({
    "library",
    "midnight",
    "neon",
    "cyberpunk",
    "candy",
    "monochrome",
})
MIGRATION_V5_FLAG = "user_state_migration_v5"
MIGRATION_V5_COMPLETED = "completed"
OWNER_IDENTITY_PROVIDER = "local_owner"
OWNER_IDENTITY_SUBJECT = "local-owner"
OWNER_DEFAULT_DISPLAY_NAME = "オーナー"
TAILSCALE_IDENTITY_PROVIDER = "tailscale"


class OwnerIdentityLinkError(RuntimeError):
    """Raised when an owner/Tailscale identity link cannot be completed safely."""


class OwnerIdentityLinkNotFound(OwnerIdentityLinkError):
    pass


class OwnerIdentityLinkConflict(OwnerIdentityLinkError):
    pass


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


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    row = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def read_schema_version(connection: sqlite3.Connection) -> int:
    if not _table_exists(connection, "schema_info"):
        return 0
    row = connection.execute(
        "SELECT value FROM schema_info WHERE key = 'schema_version'"
    ).fetchone()
    if row is None:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def database_schema_version(path: Path) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    connection = sqlite3.connect(path, timeout=30.0)
    try:
        return read_schema_version(connection)
    finally:
        connection.close()


def _next_available_backup_path(
    backup_dir: Path,
    stamp: str,
    *,
    release_label: str,
) -> Path:
    candidate = backup_dir / f"library-pre-{release_label}-{stamp}.db"
    if not candidate.exists():
        return candidate
    for number in range(1, 1000):
        candidate = backup_dir / f"library-pre-{release_label}-{stamp}-{number:02d}.db"
        if not candidate.exists():
            return candidate
    raise RuntimeError("移行前バックアップの保存名を確保できませんでした。")


def _track_count(connection: sqlite3.Connection) -> int | None:
    if not _table_exists(connection, "tracks"):
        return None
    row = connection.execute("SELECT COUNT(*) FROM tracks").fetchone()
    return int(row[0]) if row is not None else 0


def verify_sqlite_backup(
    source_path: Path,
    backup_path: Path,
    *,
    expected_schema_version: int,
) -> None:
    if not backup_path.exists() or backup_path.stat().st_size == 0:
        raise RuntimeError("移行前バックアップが空です。")

    source = sqlite3.connect(source_path, timeout=30.0)
    backup = sqlite3.connect(backup_path, timeout=30.0)
    try:
        check = backup.execute("PRAGMA quick_check").fetchone()
        if check is None or str(check[0]).casefold() != "ok":
            raise RuntimeError(f"移行前バックアップの整合性確認に失敗しました: {check}")

        backup_version = read_schema_version(backup)
        if backup_version != expected_schema_version:
            raise RuntimeError(
                "移行前バックアップのスキーマバージョンが一致しません。"
            )

        source_track_count = _track_count(source)
        backup_track_count = _track_count(backup)
        if source_track_count != backup_track_count:
            raise RuntimeError("移行前バックアップの曲数が元データと一致しません。")
    finally:
        backup.close()
        source.close()


def create_pre_v27_migration_backup(
    database_path: Path = DATABASE_PATH,
    *,
    backup_dir: Path = BACKUP_DIR,
    now: datetime | None = None,
) -> Path | None:
    """Create and verify a dedicated backup before the schema-v5 migration."""
    if not database_path.exists() or database_path.stat().st_size == 0:
        return None

    current_version = database_schema_version(database_path)
    if current_version >= 5:
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now or datetime.now().astimezone()
    destination = _next_available_backup_path(
        backup_dir,
        timestamp.strftime("%Y%m%d-%H%M%S"),
        release_label="v2.7.0",
    )

    source = sqlite3.connect(database_path, timeout=30.0)
    target = sqlite3.connect(destination, timeout=30.0)
    try:
        source.backup(target)
        target.commit()
    except Exception:
        target.close()
        source.close()
        destination.unlink(missing_ok=True)
        raise
    else:
        target.close()
        source.close()

    try:
        verify_sqlite_backup(
            database_path,
            destination,
            expected_schema_version=current_version,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return destination


def create_pre_v272_migration_backup(
    database_path: Path = DATABASE_PATH,
    *,
    backup_dir: Path = BACKUP_DIR,
    now: datetime | None = None,
) -> Path | None:
    """Create and verify a dedicated backup before the schema-v6 migration."""
    if not database_path.exists() or database_path.stat().st_size == 0:
        return None

    current_version = database_schema_version(database_path)
    if current_version >= SCHEMA_VERSION:
        return None

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now or datetime.now().astimezone()
    destination = _next_available_backup_path(
        backup_dir,
        timestamp.strftime("%Y%m%d-%H%M%S"),
        release_label="v2.7.2",
    )

    source = sqlite3.connect(database_path, timeout=30.0)
    target = sqlite3.connect(destination, timeout=30.0)
    try:
        source.backup(target)
        target.commit()
    except Exception:
        target.close()
        source.close()
        destination.unlink(missing_ok=True)
        raise
    else:
        target.close()
        source.close()

    try:
        verify_sqlite_backup(
            database_path,
            destination,
            expected_schema_version=current_version,
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return destination


def create_pre_owner_link_backup(
    database_path: Path = DATABASE_PATH,
    *,
    backup_dir: Path = BACKUP_DIR,
    now: datetime | None = None,
) -> Path:
    """Create a verified backup immediately before linking an identity.

    Owner linking deletes an empty duplicate profile after moving its single
    Tailscale identity. The backup is separate from daily and migration
    backups so that this explicit identity operation always has a recovery
    point.
    """
    if not database_path.exists() or database_path.stat().st_size == 0:
        raise FileNotFoundError("library.dbが見つかりません。")

    backup_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now or datetime.now().astimezone()
    stamp = timestamp.strftime("%Y%m%d-%H%M%S")
    destination = backup_dir / f"library-pre-owner-link-{stamp}.db"
    for number in range(1, 1000):
        if not destination.exists():
            break
        destination = backup_dir / (
            f"library-pre-owner-link-{stamp}-{number:02d}.db"
        )
    else:
        raise RuntimeError("関連付け前バックアップの保存名を確保できませんでした。")

    source = sqlite3.connect(database_path, timeout=30.0)
    target = sqlite3.connect(destination, timeout=30.0)
    try:
        source.backup(target)
        target.commit()
    except Exception:
        target.close()
        source.close()
        destination.unlink(missing_ok=True)
        raise
    else:
        target.close()
        source.close()

    try:
        verify_sqlite_backup(
            database_path,
            destination,
            expected_schema_version=database_schema_version(database_path),
        )
    except Exception:
        destination.unlink(missing_ok=True)
        raise

    return destination


def connect_database(
    path: Path = DATABASE_PATH,
    *,
    prepare_migration_backup: bool = True,
    migration_backup_dir: Path | None = None,
) -> sqlite3.Connection:
    if prepare_migration_backup:
        create_pre_v272_migration_backup(
            path,
            backup_dir=migration_backup_dir or (path.parent / "Backups"),
        )

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
def database(
    path: Path = DATABASE_PATH,
    *,
    prepare_migration_backup: bool = True,
    migration_backup_dir: Path | None = None,
) -> Iterator[sqlite3.Connection]:
    connection = connect_database(
        path,
        prepare_migration_backup=prepare_migration_backup,
        migration_backup_dir=migration_backup_dir,
    )
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

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    is_owner INTEGER NOT NULL DEFAULT 0 CHECK(is_owner IN (0, 1)),
    is_active INTEGER NOT NULL DEFAULT 1 CHECK(is_active IN (0, 1)),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT ''
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_single_owner
ON users(is_owner)
WHERE is_owner = 1;

CREATE TABLE IF NOT EXISTS user_identities (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    subject TEXT NOT NULL,
    provider_display_name TEXT NOT NULL DEFAULT '',
    profile_picture_url TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL DEFAULT '',
    UNIQUE(provider, subject),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_user_identities_user
ON user_identities(user_id);

CREATE TABLE IF NOT EXISTS user_track_state (
    user_id TEXT NOT NULL,
    track_id TEXT NOT NULL,
    favorite INTEGER NOT NULL DEFAULT 0 CHECK(favorite IN (0, 1)),
    rating INTEGER CHECK(rating IS NULL OR (rating >= 0 AND rating <= 5)),
    play_count INTEGER NOT NULL DEFAULT 0 CHECK(play_count >= 0),
    last_played_at TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY(user_id, track_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE RESTRICT,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_user_track_state_plays
ON user_track_state(user_id, play_count DESC);

CREATE INDEX IF NOT EXISTS idx_user_track_state_last_played
ON user_track_state(user_id, last_played_at DESC);

CREATE INDEX IF NOT EXISTS idx_user_track_state_favorite
ON user_track_state(user_id, favorite);

CREATE TABLE IF NOT EXISTS user_preferences (
    user_id TEXT PRIMARY KEY,
    skin_id TEXT NOT NULL DEFAULT 'library'
        CHECK(skin_id IN ('library', 'midnight', 'neon', 'cyberpunk', 'candy', 'monochrome')),
    updated_at TEXT NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
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


def _run_additive_schema_migrations(connection: sqlite3.Connection) -> None:
    # Additive migrations for databases created by earlier development builds.
    artist_columns = {
        str(row["name"]) for row in connection.execute("PRAGMA table_info(artists)").fetchall()
    }
    if "sort_name" not in artist_columns:
        connection.execute("ALTER TABLE artists ADD COLUMN sort_name TEXT NOT NULL DEFAULT ''")
    if "display_name_override" not in artist_columns:
        connection.execute("ALTER TABLE artists ADD COLUMN display_name_override TEXT")
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


def _new_user_id() -> str:
    return f"usr_{uuid.uuid4().hex}"


def _ensure_owner_user(connection: sqlite3.Connection, timestamp: str) -> str:
    owners = connection.execute(
        "SELECT id FROM users WHERE is_owner = 1 ORDER BY created_at, id"
    ).fetchall()
    if len(owners) > 1:
        raise RuntimeError("オーナーが複数登録されているため移行できません。")

    if owners:
        owner_id = str(owners[0]["id"])
    else:
        owner_id = _new_user_id()
        connection.execute(
            """
            INSERT INTO users(
                id, display_name, is_owner, is_active,
                created_at, updated_at, last_seen_at
            ) VALUES (?, ?, 1, 1, ?, ?, '')
            """,
            (owner_id, OWNER_DEFAULT_DISPLAY_NAME, timestamp, timestamp),
        )

    identity = connection.execute(
        """
        SELECT id, user_id
          FROM user_identities
         WHERE provider = ? AND subject = ?
        """,
        (OWNER_IDENTITY_PROVIDER, OWNER_IDENTITY_SUBJECT),
    ).fetchone()

    if identity is None:
        connection.execute(
            """
            INSERT INTO user_identities(
                id, user_id, provider, subject,
                provider_display_name, profile_picture_url,
                created_at, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, '', ?, '')
            """,
            (
                stable_key("idn", OWNER_IDENTITY_PROVIDER, OWNER_IDENTITY_SUBJECT),
                owner_id,
                OWNER_IDENTITY_PROVIDER,
                OWNER_IDENTITY_SUBJECT,
                OWNER_DEFAULT_DISPLAY_NAME,
                timestamp,
            ),
        )
    elif str(identity["user_id"]) != owner_id:
        raise RuntimeError("ローカルオーナー識別情報が別ユーザーへ関連付けられています。")

    connection.execute(
        """
        INSERT INTO schema_info(key, value) VALUES('owner_user_id', ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (owner_id,),
    )
    return owner_id


def _legacy_user_state_count(connection: sqlite3.Connection) -> int:
    row = connection.execute(
        """
        SELECT COUNT(*)
          FROM tracks
         WHERE play_count <> 0
            OR last_played_at <> ''
            OR favorite <> 0
            OR rating IS NOT NULL
        """
    ).fetchone()
    return int(row[0]) if row else 0


def _migrate_legacy_user_state(
    connection: sqlite3.Connection,
    owner_id: str,
    timestamp: str,
) -> None:
    migration = connection.execute(
        "SELECT value FROM schema_info WHERE key = ?",
        (MIGRATION_V5_FLAG,),
    ).fetchone()
    initial_migration = not (
        migration is not None
        and str(migration["value"]) == MIGRATION_V5_COMPLETED
    )
    expected_count = _legacy_user_state_count(connection)

    # Keep this insert idempotent even after the initial migration. A fresh
    # database can be initialized before the first scan imports legacy play
    # counts. The next initialization must add only the missing owner rows.
    connection.execute(
        """
        INSERT INTO user_track_state(
            user_id, track_id, favorite, rating,
            play_count, last_played_at, created_at, updated_at
        )
        SELECT ?, id, favorite, rating,
               play_count, last_played_at, ?, ?
          FROM tracks
         WHERE (play_count <> 0
             OR last_played_at <> ''
             OR favorite <> 0
             OR rating IS NOT NULL)
           AND NOT EXISTS (
                SELECT 1
                  FROM user_track_state AS existing
                 WHERE existing.user_id = ?
                   AND existing.track_id = tracks.id
           )
        """,
        (owner_id, timestamp, timestamp, owner_id),
    )

    missing_row = connection.execute(
        """
        SELECT COUNT(*)
          FROM tracks AS t
         WHERE (t.play_count <> 0
             OR t.last_played_at <> ''
             OR t.favorite <> 0
             OR t.rating IS NOT NULL)
           AND NOT EXISTS (
                SELECT 1
                  FROM user_track_state AS uts
                 WHERE uts.user_id = ?
                   AND uts.track_id = t.id
           )
        """,
        (owner_id,),
    ).fetchone()
    if missing_row and int(missing_row[0]) != 0:
        raise RuntimeError("既存の曲状態に対応するオーナー行が不足しています。")

    if initial_migration:
        state_count_row = connection.execute(
            "SELECT COUNT(*) FROM user_track_state WHERE user_id = ?",
            (owner_id,),
        ).fetchone()
        state_count = int(state_count_row[0]) if state_count_row else 0
        if state_count != expected_count:
            raise RuntimeError(
                "既存の曲状態をオーナーへ移行した件数が一致しません。"
            )

        mismatch_row = connection.execute(
            """
            SELECT COUNT(*)
              FROM tracks AS t
              JOIN user_track_state AS uts
                ON uts.user_id = ?
               AND uts.track_id = t.id
             WHERE (t.play_count <> 0
                 OR t.last_played_at <> ''
                 OR t.favorite <> 0
                 OR t.rating IS NOT NULL)
               AND (
                    uts.favorite <> t.favorite
                 OR NOT (uts.rating IS t.rating)
                 OR uts.play_count <> t.play_count
                 OR uts.last_played_at <> t.last_played_at
               )
            """,
            (owner_id,),
        ).fetchone()
        if mismatch_row and int(mismatch_row[0]) != 0:
            raise RuntimeError("移行後の曲状態が既存データと一致しません。")

        connection.execute(
            """
            INSERT INTO schema_info(key, value) VALUES(?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (MIGRATION_V5_FLAG, MIGRATION_V5_COMPLETED),
        )


def _ensure_user_preferences(connection: sqlite3.Connection, timestamp: str) -> None:
    connection.execute(
        """
        INSERT INTO user_preferences(user_id, skin_id, updated_at)
        SELECT id, ?, ?
          FROM users
         WHERE NOT EXISTS (
             SELECT 1 FROM user_preferences AS p WHERE p.user_id = users.id
         )
        """,
        (DEFAULT_SKIN_ID, timestamp),
    )


def _verify_schema_v5(connection: sqlite3.Connection, owner_id: str) -> None:
    required_tables = {"users", "user_identities", "user_track_state"}
    actual_tables = {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    missing = required_tables - actual_tables
    if missing:
        raise RuntimeError(f"スキーマ5のテーブルが不足しています: {sorted(missing)}")

    owner_count = connection.execute(
        "SELECT COUNT(*) FROM users WHERE is_owner = 1"
    ).fetchone()
    if owner_count is None or int(owner_count[0]) != 1:
        raise RuntimeError("オーナーが正しく1人登録されていません。")

    identity = connection.execute(
        """
        SELECT user_id
          FROM user_identities
         WHERE provider = ? AND subject = ?
        """,
        (OWNER_IDENTITY_PROVIDER, OWNER_IDENTITY_SUBJECT),
    ).fetchone()
    if identity is None or str(identity["user_id"]) != owner_id:
        raise RuntimeError("ローカルオーナー識別情報を確認できません。")

    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError("スキーマ5の外部キー整合性確認に失敗しました。")


def _verify_schema_v6(connection: sqlite3.Connection, owner_id: str) -> None:
    _verify_schema_v5(connection, owner_id)
    if not _table_exists(connection, "user_preferences"):
        raise RuntimeError("スキーマ6の利用者設定テーブルが不足しています。")

    missing = connection.execute(
        """
        SELECT COUNT(*)
          FROM users AS u
         WHERE NOT EXISTS (
             SELECT 1 FROM user_preferences AS p WHERE p.user_id = u.id
         )
        """
    ).fetchone()
    if missing is None or int(missing[0]) != 0:
        raise RuntimeError("利用者スキンの初期設定が不足しています。")

    invalid = connection.execute(
        """
        SELECT COUNT(*) FROM user_preferences
         WHERE skin_id NOT IN ('library', 'midnight', 'neon', 'cyberpunk', 'candy', 'monochrome')
        """
    ).fetchone()
    if invalid is None or int(invalid[0]) != 0:
        raise RuntimeError("未対応のスキン設定が保存されています。")

    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise RuntimeError("スキーマ6の外部キー整合性確認に失敗しました。")


def initialize_database(connection: sqlite3.Connection) -> None:
    if connection.in_transaction:
        raise RuntimeError("データベース初期化は未処理の更新がない状態で実行してください。")

    current_version = read_schema_version(connection)
    if current_version > SCHEMA_VERSION:
        raise RuntimeError(
            f"このアプリより新しいデータベース形式です: {current_version}"
        )

    # executescript commits pending work before execution. Beginning the
    # transaction inside the script keeps table creation and data migration
    # within the same rollback boundary.
    connection.executescript("BEGIN IMMEDIATE;\n" + SCHEMA_SQL)
    try:
        _run_additive_schema_migrations(connection)
        timestamp = utc_now()
        owner_id = _ensure_owner_user(connection, timestamp)
        _migrate_legacy_user_state(connection, owner_id, timestamp)
        _ensure_user_preferences(connection, timestamp)
        _verify_schema_v6(connection, owner_id)

        connection.execute(
            """
            INSERT INTO schema_info(key, value) VALUES('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """,
            (str(SCHEMA_VERSION),),
        )
        connection.execute(
            """
            INSERT INTO schema_info(key, value)
            VALUES('created_by', 'MP3 Source Music Library')
            ON CONFLICT(key) DO NOTHING
            """
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise


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
    row_keys = set(row.keys())

    def state_value(alias: str, legacy: str) -> Any:
        if alias in row_keys:
            return row[alias]
        return row[legacy]
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
        "playCount": int(state_value("user_play_count", "play_count") or 0),
        "dateAdded": row["date_added"] or "",
        "lastPlayedAt": state_value("user_last_played_at", "last_played_at") or "",
        "favorite": bool(state_value("user_favorite", "favorite")),
        "rating": (
            state_value("user_rating", "rating")
            if state_value("user_rating", "rating") is not None
            else ""
        ),
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


def get_available_tracks(
    connection: sqlite3.Connection,
    *,
    user_id: str | None = None,
) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT t.*, ar.name AS artist_name,
               ar.display_name_override AS artist_display_override,
               al.title AS album_title,
               aw.relative_path AS artwork_relative_path,
               aw.source_type AS artwork_source_type,
               COALESCE(uts.play_count, 0) AS user_play_count,
               COALESCE(uts.last_played_at, '') AS user_last_played_at,
               COALESCE(uts.favorite, 0) AS user_favorite,
               uts.rating AS user_rating
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
          LEFT JOIN artworks aw ON aw.id = t.artwork_id
          LEFT JOIN user_track_state uts
            ON uts.track_id = t.id AND uts.user_id = ?
         WHERE t.is_available = 1
         ORDER BY COALESCE(t.artist_override, ar.display_name_override, ar.name, '') COLLATE NOCASE,
                  COALESCE(t.album_override, al.title, '') COLLATE NOCASE,
                  COALESCE(t.disc_number, 0),
                  COALESCE(t.track_number, 0),
                  COALESCE(t.title_override, t.title, '') COLLATE NOCASE,
                  t.relative_path COLLATE NOCASE
        """,
        (str(user_id or ""),),
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
    favorite_only: bool = False,
    played_only: bool = False,
    user_id: str | None = None,
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
    if favorite_only:
        conditions.append(
            "EXISTS ("
            "SELECT 1 FROM user_track_state favorite_state "
            "WHERE favorite_state.user_id = ? "
            "AND favorite_state.track_id = t.id "
            "AND favorite_state.favorite = 1"
            ")"
        )
        params.append(str(user_id or ""))
    if played_only:
        conditions.append(
            "EXISTS ("
            "SELECT 1 FROM user_track_state played_state "
            "WHERE played_state.user_id = ? "
            "AND played_state.track_id = t.id "
            "AND played_state.play_count > 0"
            ")"
        )
        params.append(str(user_id or ""))

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
        "plays": f"COALESCE(uts.play_count, 0) DESC, COALESCE(uts.last_played_at, '') DESC, {TITLE_EXPR} COLLATE NOCASE",
        "recent": f"COALESCE(uts.last_played_at, '') DESC, COALESCE(uts.play_count, 0) DESC, {TITLE_EXPR} COLLATE NOCASE",
        "added": f"COALESCE(NULLIF(t.date_added, ''), t.created_at) DESC, {TITLE_EXPR} COLLATE NOCASE",
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
    user_id: str | None = None,
    favorite_only: bool = False,
    played_only: bool = False,
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
        favorite_only=favorite_only,
        played_only=played_only,
        user_id=user_id,
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
               aw.source_type AS artwork_source_type,
               COALESCE(uts.play_count, 0) AS user_play_count,
               COALESCE(uts.last_played_at, '') AS user_last_played_at,
               COALESCE(uts.favorite, 0) AS user_favorite,
               uts.rating AS user_rating
          FROM tracks t
          LEFT JOIN artists ar ON ar.id = t.artist_id
          LEFT JOIN albums al ON al.id = t.album_id
          LEFT JOIN artworks aw ON aw.id = t.artwork_id
          LEFT JOIN user_track_state uts
            ON uts.track_id = t.id AND uts.user_id = ?
         WHERE {where_sql}
         ORDER BY {_track_order(sort, album_context=album_context)}
         LIMIT ? OFFSET ?
        """,
        [str(user_id or ""), *filtered_params, limit, offset],
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
        "favoriteOnly": bool(favorite_only),
        "playedOnly": bool(played_only),
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
    user_id: str | None = None,
    favorite_only: bool = False,
    played_only: bool = False,
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
            user_id=user_id,
            favorite_only=favorite_only,
            played_only=played_only,
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
            user_id=user_id,
            favorite_only=favorite_only,
            played_only=played_only,
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
        user_id=user_id,
        favorite_only=favorite_only,
        played_only=played_only,
    )



def library_home(
    connection: sqlite3.Connection,
    *,
    user_id: str | None = None,
    section_limit: int = 8,
) -> dict[str, Any]:
    """Return the small, user-aware collections used by the library home.

    The server resolves ``user_id`` from the local-owner session or Tailscale
    identity. Anonymous clients receive only the shared recently-added section;
    personal playback and favorite state is never inferred from request input.
    """
    section_limit = max(1, min(int(section_limit), 24))
    normalized_user_id = str(user_id or "").strip()
    authenticated = bool(normalized_user_id)

    def section(
        *,
        sort: str,
        favorite_only: bool = False,
        played_only: bool = False,
    ) -> dict[str, Any]:
        if (favorite_only or played_only) and not authenticated:
            return {
                "items": [],
                "total": 0,
                "sort": sort,
                "favoriteOnly": bool(favorite_only),
                "playedOnly": bool(played_only),
            }
        result = browse_tracks(
            connection,
            limit=section_limit,
            offset=0,
            sort=sort,
            user_id=normalized_user_id or None,
            favorite_only=favorite_only,
            played_only=played_only,
        )
        return {
            "items": result["items"],
            "total": int(result["total"]),
            "sort": sort,
            "favoriteOnly": bool(favorite_only),
            "playedOnly": bool(played_only),
        }

    return {
        "authenticated": authenticated,
        "sectionLimit": section_limit,
        "recentlyPlayed": section(sort="recent", played_only=True),
        "favorites": section(sort="title", favorite_only=True),
        "mostPlayed": section(sort="plays", played_only=True),
        "recentlyAdded": section(sort="added"),
    }


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


def record_user_playback(
    connection: sqlite3.Connection,
    *,
    user_id: str | None,
    track_id: str,
) -> dict[str, Any] | None:
    """Record one completed playback for the authenticated user.

    Anonymous requests may still play audio, but they do not create or update
    personal state. Legacy columns in ``tracks`` remain as migration fallback
    data and are intentionally not updated after schema version 5.
    """
    track = connection.execute(
        "SELECT id FROM tracks WHERE id = ? AND is_available = 1",
        (track_id,),
    ).fetchone()
    if track is None:
        return None

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        return {
            "playCount": 0,
            "lastPlayedAt": "",
            "recorded": False,
        }

    user = connection.execute(
        "SELECT is_active FROM users WHERE id = ?",
        (normalized_user_id,),
    ).fetchone()
    if user is None or not bool(user["is_active"]):
        raise PermissionError("active user authentication is required")

    timestamp = utc_now()
    connection.execute(
        """
        INSERT INTO user_track_state(
            user_id, track_id, favorite, rating,
            play_count, last_played_at, created_at, updated_at
        ) VALUES (?, ?, 0, NULL, 1, ?, ?, ?)
        ON CONFLICT(user_id, track_id) DO UPDATE SET
            play_count = user_track_state.play_count + 1,
            last_played_at = excluded.last_played_at,
            updated_at = excluded.updated_at
        """,
        (normalized_user_id, track_id, timestamp, timestamp, timestamp),
    )
    state = connection.execute(
        """
        SELECT play_count, last_played_at
          FROM user_track_state
         WHERE user_id = ? AND track_id = ?
        """,
        (normalized_user_id, track_id),
    ).fetchone()
    if state is None:
        raise RuntimeError("user playback state was not created")
    return {
        "playCount": int(state["play_count"] or 0),
        "lastPlayedAt": str(state["last_played_at"] or ""),
        "recorded": True,
    }


def set_user_favorite(
    connection: sqlite3.Connection,
    *,
    user_id: str | None,
    track_id: str,
    favorite: bool,
) -> dict[str, Any] | None:
    """Set one authenticated user's favorite state for an available track.

    The requested state is explicit rather than a server-side toggle, making
    retries idempotent. Existing rating/playback fields are preserved. When a
    cleared favorite would leave an otherwise empty state row, that row is
    removed to keep ``user_track_state`` sparse.
    """
    if type(favorite) is not bool:
        raise ValueError("favorite must be a boolean")

    track = connection.execute(
        "SELECT id FROM tracks WHERE id = ? AND is_available = 1",
        (track_id,),
    ).fetchone()
    if track is None:
        return None

    normalized_user_id = str(user_id or "").strip()
    if not normalized_user_id:
        raise PermissionError("authenticated user is required")

    user = connection.execute(
        "SELECT id FROM users WHERE id = ? AND is_active = 1",
        (normalized_user_id,),
    ).fetchone()
    if user is None:
        raise PermissionError("active user is required")

    timestamp = utc_now()
    if bool(favorite):
        connection.execute(
            """
            INSERT INTO user_track_state(
                user_id, track_id, favorite, rating,
                play_count, last_played_at, created_at, updated_at
            ) VALUES (?, ?, 1, NULL, 0, '', ?, ?)
            ON CONFLICT(user_id, track_id) DO UPDATE SET
                favorite = 1,
                updated_at = excluded.updated_at
            """,
            (normalized_user_id, track_id, timestamp, timestamp),
        )
    else:
        connection.execute(
            """
            UPDATE user_track_state
               SET favorite = 0,
                   updated_at = ?
             WHERE user_id = ? AND track_id = ?
            """,
            (timestamp, normalized_user_id, track_id),
        )
        connection.execute(
            """
            DELETE FROM user_track_state
             WHERE user_id = ?
               AND track_id = ?
               AND favorite = 0
               AND rating IS NULL
               AND play_count = 0
               AND last_played_at = ''
            """,
            (normalized_user_id, track_id),
        )

    state = connection.execute(
        """
        SELECT favorite, rating, play_count, last_played_at
          FROM user_track_state
         WHERE user_id = ? AND track_id = ?
        """,
        (normalized_user_id, track_id),
    ).fetchone()
    return {
        "favorite": bool(state["favorite"]) if state is not None else False,
        "rating": state["rating"] if state is not None else None,
        "playCount": int(state["play_count"] or 0) if state is not None else 0,
        "lastPlayedAt": str(state["last_played_at"] or "") if state is not None else "",
    }


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

def database_stats(
    connection: sqlite3.Connection,
    *,
    user_id: str | None = None,
) -> dict[str, Any]:
    row = connection.execute(
        """
        SELECT COUNT(*) AS total_rows,
               SUM(CASE WHEN is_available = 1 THEN 1 ELSE 0 END) AS available_tracks,
               SUM(CASE WHEN is_available = 0 THEN 1 ELSE 0 END) AS unavailable_tracks,
               SUM(CASE WHEN artwork_id IS NOT NULL THEN 1 ELSE 0 END) AS artwork_tracks
          FROM tracks
        """
    ).fetchone()
    plays_row = connection.execute(
        """
        SELECT COALESCE(SUM(play_count), 0) AS total_plays
          FROM user_track_state
         WHERE user_id = ?
        """,
        (str(user_id or ""),),
    ).fetchone()
    favorite_row = connection.execute(
        """
        SELECT COUNT(*) AS favorite_tracks
          FROM user_track_state AS uts
          JOIN tracks AS t ON t.id = uts.track_id
         WHERE uts.user_id = ?
           AND uts.favorite = 1
           AND t.is_available = 1
        """,
        (str(user_id or ""),),
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
        "totalPlays": int(plays_row["total_plays"] or 0),
        "favoriteTracks": int(favorite_row["favorite_tracks"] or 0),
        "latestScan": dict(latest) if latest else None,
    }




def _user_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "displayName": str(row["display_name"]),
        "isOwner": bool(row["is_owner"]),
        "isActive": bool(row["is_active"]),
        "createdAt": str(row["created_at"]),
        "updatedAt": str(row["updated_at"]),
        "lastSeenAt": str(row["last_seen_at"]),
    }


def get_or_create_tailscale_user(
    connection: sqlite3.Connection,
    *,
    subject: str,
    display_name: str,
    profile_picture_url: str = "",
) -> dict[str, Any]:
    """Resolve one Tailscale identity and update its last-seen metadata.

    ``subject`` must already be normalized by ``tailscale_identity``. The
    identity table, rather than the current display name, is the stable link
    to the user profile. Existing user display names are not overwritten,
    which preserves future manual profile-name edits.
    """
    normalized_subject = unicodedata.normalize(
        "NFKC",
        str(subject or ""),
    ).strip().casefold()
    if not normalized_subject:
        raise ValueError("Tailscale login subject is required")
    if len(normalized_subject) > 512:
        raise ValueError("Tailscale login subject is too long")

    provider_name = str(display_name or "").strip() or normalized_subject
    provider_name = provider_name[:200]
    profile_url = str(profile_picture_url or "").strip()[:2048]
    timestamp = utc_now()

    started_transaction = not connection.in_transaction
    if started_transaction:
        connection.execute("BEGIN IMMEDIATE")

    try:
        row = connection.execute(
            """
            SELECT u.id, u.display_name, u.is_owner, u.is_active,
                   u.created_at, u.updated_at, u.last_seen_at,
                   i.id AS identity_id
              FROM user_identities AS i
              JOIN users AS u ON u.id = i.user_id
             WHERE i.provider = ?
               AND i.subject = ?
            """,
            (TAILSCALE_IDENTITY_PROVIDER, normalized_subject),
        ).fetchone()

        if row is None:
            user_id = _new_user_id()
            connection.execute(
                """
                INSERT INTO users(
                    id, display_name, is_owner, is_active,
                    created_at, updated_at, last_seen_at
                ) VALUES (?, ?, 0, 1, ?, ?, ?)
                """,
                (
                    user_id,
                    provider_name,
                    timestamp,
                    timestamp,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO user_identities(
                    id, user_id, provider, subject,
                    provider_display_name, profile_picture_url,
                    created_at, last_seen_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stable_key(
                        "idn",
                        TAILSCALE_IDENTITY_PROVIDER,
                        normalized_subject,
                    ),
                    user_id,
                    TAILSCALE_IDENTITY_PROVIDER,
                    normalized_subject,
                    provider_name,
                    profile_url,
                    timestamp,
                    timestamp,
                ),
            )
        else:
            user_id = str(row["id"])
            connection.execute(
                """
                UPDATE user_identities
                   SET provider_display_name = ?,
                       profile_picture_url = CASE
                           WHEN ? <> '' THEN ?
                           ELSE profile_picture_url
                       END,
                       last_seen_at = ?
                 WHERE provider = ?
                   AND subject = ?
                """,
                (
                    provider_name,
                    profile_url,
                    profile_url,
                    timestamp,
                    TAILSCALE_IDENTITY_PROVIDER,
                    normalized_subject,
                ),
            )
            connection.execute(
                """
                UPDATE users
                   SET last_seen_at = ?
                 WHERE id = ?
                """,
                (timestamp, user_id),
            )

        connection.execute(
            """
            INSERT INTO user_preferences(user_id, skin_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO NOTHING
            """,
            (user_id, DEFAULT_SKIN_ID, timestamp),
        )

        user_row = connection.execute(
            """
            SELECT id, display_name, is_owner, is_active,
                   created_at, updated_at, last_seen_at
              FROM users
             WHERE id = ?
            """,
            (user_id,),
        ).fetchone()
        if user_row is None:
            raise RuntimeError("Tailscale利用者を取得できませんでした。")

        result = _user_row_to_dict(user_row)
        result.update(
            {
                "provider": TAILSCALE_IDENTITY_PROVIDER,
                "subject": normalized_subject,
                "providerDisplayName": provider_name,
                "profilePictureUrl": profile_url,
            }
        )
        return result
    except Exception:
        if started_transaction:
            connection.rollback()
        raise




def get_user_state_summary(
    connection: sqlite3.Connection,
    user_id: str,
) -> dict[str, int]:
    """Return a compact personal-state summary for one user profile."""
    row = connection.execute(
        """
        SELECT COUNT(*) AS state_count,
               COALESCE(SUM(play_count), 0) AS play_count,
               COALESCE(SUM(favorite), 0) AS favorite_count,
               COALESCE(SUM(CASE WHEN rating IS NOT NULL THEN 1 ELSE 0 END), 0)
                   AS rating_count
          FROM user_track_state
         WHERE user_id = ?
        """,
        (str(user_id or ""),),
    ).fetchone()
    return {
        "stateCount": int(row["state_count"] or 0),
        "playCount": int(row["play_count"] or 0),
        "favoriteCount": int(row["favorite_count"] or 0),
        "ratingCount": int(row["rating_count"] or 0),
    }


def get_owner_link_merge_preview(
    connection: sqlite3.Connection,
    candidate_user_id: str,
) -> dict[str, Any]:
    """Describe the candidate state that would be merged into the owner."""
    candidate_id = str(candidate_user_id or "").strip()
    if not candidate_id:
        raise ValueError("candidate_user_id is required")

    candidate = connection.execute(
        "SELECT id, is_owner, is_active FROM users WHERE id = ?",
        (candidate_id,),
    ).fetchone()
    if candidate is None:
        raise OwnerIdentityLinkNotFound("確認対象の利用者が見つかりません。")

    summary = get_user_state_summary(connection, candidate_id)
    identity_row = connection.execute(
        "SELECT COUNT(*) AS count FROM user_identities WHERE user_id = ?",
        (candidate_id,),
    ).fetchone()
    identity_count = int(identity_row["count"] or 0) if identity_row else 0

    conflict_row = connection.execute(
        """
        SELECT COUNT(*) AS count
          FROM user_track_state AS candidate_state
          JOIN users AS owner_user
            ON owner_user.is_owner = 1
          JOIN user_track_state AS owner_state
            ON owner_state.user_id = owner_user.id
           AND owner_state.track_id = candidate_state.track_id
         WHERE candidate_state.user_id = ?
           AND candidate_state.rating IS NOT NULL
           AND owner_state.rating IS NOT NULL
           AND candidate_state.rating <> owner_state.rating
        """,
        (candidate_id,),
    ).fetchone()
    rating_conflict_count = int(conflict_row["count"] or 0) if conflict_row else 0

    result: dict[str, Any] = dict(summary)
    result.update(
        {
            "identityCount": identity_count,
            "ratingConflictCount": rating_conflict_count,
            "canMerge": bool(candidate["is_owner"]) or (
                bool(candidate["is_active"])
                and identity_count == 1
                and rating_conflict_count == 0
            ),
        }
    )
    return result


def _parse_owner_link_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise OwnerIdentityLinkConflict(
            "最終再生日時を安全に比較できない曲があるため関連付けを中止しました。"
        ) from exc
    if parsed.tzinfo is None:
        raise OwnerIdentityLinkConflict(
            "タイムゾーンのない最終再生日時があるため関連付けを中止しました。"
        )
    return parsed.astimezone(timezone.utc)


def _latest_owner_link_timestamp(left: str, right: str) -> str:
    left_value = str(left or "")
    right_value = str(right or "")
    if not left_value:
        return right_value
    if not right_value:
        return left_value
    left_time = _parse_owner_link_timestamp(left_value)
    right_time = _parse_owner_link_timestamp(right_value)
    return left_value if left_time >= right_time else right_value


def _merge_user_track_state_into_owner(
    connection: sqlite3.Connection,
    *,
    owner_user_id: str,
    candidate_user_id: str,
    timestamp: str,
) -> dict[str, int]:
    """Merge all candidate personal state without discarding conflicting data."""
    candidate_rows = connection.execute(
        """
        SELECT track_id, favorite, rating, play_count,
               last_played_at, created_at, updated_at
          FROM user_track_state
         WHERE user_id = ?
         ORDER BY track_id
        """,
        (candidate_user_id,),
    ).fetchall()
    owner_rows = {
        str(row["track_id"]): row
        for row in connection.execute(
            """
            SELECT track_id, favorite, rating, play_count,
                   last_played_at, created_at, updated_at
              FROM user_track_state
             WHERE user_id = ?
            """,
            (owner_user_id,),
        ).fetchall()
    }

    # Detect every lossy or ambiguous condition before modifying any row.
    rating_conflicts: list[str] = []
    for candidate in candidate_rows:
        track_id = str(candidate["track_id"])
        owner = owner_rows.get(track_id)
        if owner is None:
            continue
        owner_rating = owner["rating"]
        candidate_rating = candidate["rating"]
        if (
            owner_rating is not None
            and candidate_rating is not None
            and int(owner_rating) != int(candidate_rating)
        ):
            rating_conflicts.append(track_id)
        _latest_owner_link_timestamp(
            str(owner["last_played_at"] or ""),
            str(candidate["last_played_at"] or ""),
        )

    if rating_conflicts:
        raise OwnerIdentityLinkConflict(
            "評価が異なる曲が"
            f"{len(rating_conflicts)}件あるため、データを推測せず関連付けを中止しました。"
        )

    summary = {
        "candidateStateCount": len(candidate_rows),
        "movedStateCount": 0,
        "combinedStateCount": 0,
        "playCountAdded": 0,
        "favoriteAddedCount": 0,
        "ratingInheritedCount": 0,
    }

    for candidate in candidate_rows:
        track_id = str(candidate["track_id"])
        owner = owner_rows.get(track_id)
        candidate_favorite = int(candidate["favorite"] or 0)
        candidate_rating = candidate["rating"]
        candidate_plays = int(candidate["play_count"] or 0)
        summary["playCountAdded"] += candidate_plays

        if owner is None:
            connection.execute(
                """
                UPDATE user_track_state
                   SET user_id = ?, updated_at = ?
                 WHERE user_id = ? AND track_id = ?
                """,
                (owner_user_id, timestamp, candidate_user_id, track_id),
            )
            summary["movedStateCount"] += 1
            summary["favoriteAddedCount"] += candidate_favorite
            if candidate_rating is not None:
                summary["ratingInheritedCount"] += 1
            continue

        owner_favorite = int(owner["favorite"] or 0)
        owner_rating = owner["rating"]
        merged_favorite = 1 if owner_favorite or candidate_favorite else 0
        if candidate_favorite and not owner_favorite:
            summary["favoriteAddedCount"] += 1

        merged_rating = owner_rating
        if owner_rating is None and candidate_rating is not None:
            merged_rating = int(candidate_rating)
            summary["ratingInheritedCount"] += 1

        merged_last_played = _latest_owner_link_timestamp(
            str(owner["last_played_at"] or ""),
            str(candidate["last_played_at"] or ""),
        )
        merged_plays = int(owner["play_count"] or 0) + candidate_plays

        connection.execute(
            """
            UPDATE user_track_state
               SET favorite = ?,
                   rating = ?,
                   play_count = ?,
                   last_played_at = ?,
                   updated_at = ?
             WHERE user_id = ? AND track_id = ?
            """,
            (
                merged_favorite,
                merged_rating,
                merged_plays,
                merged_last_played,
                timestamp,
                owner_user_id,
                track_id,
            ),
        )
        connection.execute(
            "DELETE FROM user_track_state WHERE user_id = ? AND track_id = ?",
            (candidate_user_id, track_id),
        )
        summary["combinedStateCount"] += 1

    remaining = connection.execute(
        "SELECT COUNT(*) AS count FROM user_track_state WHERE user_id = ?",
        (candidate_user_id,),
    ).fetchone()
    if remaining is not None and int(remaining["count"] or 0) != 0:
        raise OwnerIdentityLinkConflict(
            "利用者データの統合後に未処理の状態が残ったため中止しました。"
        )

    return summary


def link_tailscale_identity_to_owner(
    connection: sqlite3.Connection,
    *,
    subject: str,
    expected_candidate_user_id: str,
) -> dict[str, Any]:
    """Merge one confirmed Tailscale profile into the local owner.

    Personal state is merged transactionally. Play counts are added, the
    newest last-played timestamp is retained, favorites use logical OR, and
    ratings are inherited only when they do not conflict.
    """
    normalized_subject = unicodedata.normalize(
        "NFKC",
        str(subject or ""),
    ).strip().casefold()
    expected_user_id = str(expected_candidate_user_id or "").strip()
    if not normalized_subject or not expected_user_id:
        raise ValueError("確認対象のTailscale利用者が不足しています。")

    started_transaction = not connection.in_transaction
    if started_transaction:
        connection.execute("BEGIN IMMEDIATE")

    try:
        owner_row = connection.execute(
            """
            SELECT id, display_name, is_owner, is_active,
                   created_at, updated_at, last_seen_at
              FROM users
             WHERE is_owner = 1
             ORDER BY created_at, id
             LIMIT 1
            """
        ).fetchone()
        if owner_row is None:
            raise OwnerIdentityLinkNotFound("オーナーを確認できませんでした。")
        if not bool(owner_row["is_active"]):
            raise OwnerIdentityLinkConflict("オーナーが無効化されています。")

        identity_row = connection.execute(
            """
            SELECT i.id AS identity_id, i.user_id,
                   i.provider_display_name, i.profile_picture_url,
                   u.display_name, u.is_owner, u.is_active
              FROM user_identities AS i
              JOIN users AS u ON u.id = i.user_id
             WHERE i.provider = ?
               AND i.subject = ?
            """,
            (TAILSCALE_IDENTITY_PROVIDER, normalized_subject),
        ).fetchone()
        if identity_row is None:
            raise OwnerIdentityLinkNotFound(
                "確認対象のTailscale識別情報が見つかりません。"
            )

        actual_user_id = str(identity_row["user_id"])
        if actual_user_id != expected_user_id:
            raise OwnerIdentityLinkConflict(
                "確認中にTailscale利用者が変更されたため中止しました。"
            )

        owner_id = str(owner_row["id"])
        if actual_user_id == owner_id:
            result = _user_row_to_dict(owner_row)
            result.update(
                {
                    "provider": TAILSCALE_IDENTITY_PROVIDER,
                    "subject": normalized_subject,
                    "alreadyLinked": True,
                    "removedDuplicateUserId": None,
                    "mergedPersonalState": {
                        "candidateStateCount": 0,
                        "movedStateCount": 0,
                        "combinedStateCount": 0,
                        "playCountAdded": 0,
                        "favoriteAddedCount": 0,
                        "ratingInheritedCount": 0,
                    },
                }
            )
            return result

        if bool(identity_row["is_owner"]):
            raise OwnerIdentityLinkConflict(
                "別のオーナープロフィールが関連付けられています。"
            )
        if not bool(identity_row["is_active"]):
            raise OwnerIdentityLinkConflict(
                "無効化された利用者はオーナーへ関連付けできません。"
            )

        identity_count_row = connection.execute(
            "SELECT COUNT(*) FROM user_identities WHERE user_id = ?",
            (actual_user_id,),
        ).fetchone()
        identity_count = int(identity_count_row[0]) if identity_count_row else 0
        if identity_count != 1:
            raise OwnerIdentityLinkConflict(
                "複数の識別情報を持つ利用者は自動統合できません。"
            )

        timestamp = utc_now()
        merge_summary = _merge_user_track_state_into_owner(
            connection,
            owner_user_id=owner_id,
            candidate_user_id=actual_user_id,
            timestamp=timestamp,
        )
        connection.execute(
            """
            UPDATE user_identities
               SET user_id = ?,
                   last_seen_at = ?
             WHERE id = ?
               AND user_id = ?
            """,
            (
                owner_id,
                timestamp,
                str(identity_row["identity_id"]),
                actual_user_id,
            ),
        )
        connection.execute(
            "DELETE FROM users WHERE id = ? AND is_owner = 0",
            (actual_user_id,),
        )
        connection.execute(
            """
            UPDATE users
               SET updated_at = ?,
                   last_seen_at = ?
             WHERE id = ?
            """,
            (timestamp, timestamp, owner_id),
        )

        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if foreign_key_errors:
            raise OwnerIdentityLinkConflict(
                "関連付け後のデータ整合性確認に失敗しました。"
            )

        updated_owner = connection.execute(
            """
            SELECT id, display_name, is_owner, is_active,
                   created_at, updated_at, last_seen_at
              FROM users
             WHERE id = ?
            """,
            (owner_id,),
        ).fetchone()
        if updated_owner is None:
            raise OwnerIdentityLinkNotFound("関連付け後のオーナーを取得できません。")

        result = _user_row_to_dict(updated_owner)
        result.update(
            {
                "provider": TAILSCALE_IDENTITY_PROVIDER,
                "subject": normalized_subject,
                "alreadyLinked": False,
                "removedDuplicateUserId": actual_user_id,
                "mergedPersonalState": merge_summary,
            }
        )
        return result
    except Exception:
        if started_transaction:
            connection.rollback()
        raise



def normalize_skin_id(value: Any) -> str:
    skin_id = str(value or "").strip().casefold()
    if skin_id not in ALLOWED_SKIN_IDS:
        return DEFAULT_SKIN_ID
    return skin_id


def get_user_skin(connection: sqlite3.Connection, user_id: str | None) -> str:
    if not user_id:
        return DEFAULT_SKIN_ID
    row = connection.execute(
        "SELECT skin_id FROM user_preferences WHERE user_id = ?",
        (str(user_id),),
    ).fetchone()
    if row is None:
        return DEFAULT_SKIN_ID
    return normalize_skin_id(row["skin_id"])


def set_user_skin(
    connection: sqlite3.Connection,
    *,
    user_id: str,
    skin_id: str,
) -> dict[str, str]:
    normalized_skin = str(skin_id or "").strip().casefold()
    if normalized_skin not in ALLOWED_SKIN_IDS:
        raise ValueError("skinId is not supported")

    user = connection.execute(
        "SELECT id, is_active FROM users WHERE id = ?",
        (str(user_id or ""),),
    ).fetchone()
    if user is None:
        raise PermissionError("authenticated user was not found")
    if not bool(user["is_active"]):
        raise PermissionError("inactive user cannot change skin")

    timestamp = utc_now()
    connection.execute(
        """
        INSERT INTO user_preferences(user_id, skin_id, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            skin_id = excluded.skin_id,
            updated_at = excluded.updated_at
        """,
        (str(user_id), normalized_skin, timestamp),
    )
    return {"skinId": normalized_skin, "updatedAt": timestamp}


def get_user_by_id(
    connection: sqlite3.Connection,
    user_id: str,
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, display_name, is_owner, is_active,
               created_at, updated_at, last_seen_at
          FROM users
         WHERE id = ?
        """,
        (str(user_id or ""),),
    ).fetchone()
    if row is None:
        return None
    return _user_row_to_dict(row)


def list_users_for_management(
    connection: sqlite3.Connection,
) -> list[dict[str, Any]]:
    """Return owner-visible profiles with identities and state totals."""
    rows = connection.execute(
        """
        SELECT u.id, u.display_name, u.is_owner, u.is_active,
               u.created_at, u.updated_at, u.last_seen_at,
               COUNT(uts.track_id) AS state_count,
               COALESCE(SUM(uts.favorite), 0) AS favorite_count,
               COALESCE(SUM(uts.play_count), 0) AS play_count
          FROM users AS u
          LEFT JOIN user_track_state AS uts
                 ON uts.user_id = u.id
         GROUP BY u.id
         ORDER BY u.is_owner DESC,
                  u.is_active DESC,
                  u.display_name COLLATE NOCASE,
                  u.id
        """
    ).fetchall()

    identity_rows = connection.execute(
        """
        SELECT user_id, provider, subject,
               provider_display_name, profile_picture_url,
               created_at, last_seen_at
          FROM user_identities
         ORDER BY user_id, provider, subject
        """
    ).fetchall()

    identities_by_user: dict[str, list[dict[str, Any]]] = {}
    for identity in identity_rows:
        user_id = str(identity["user_id"])
        identities_by_user.setdefault(user_id, []).append(
            {
                "provider": str(identity["provider"]),
                "subject": str(identity["subject"]),
                "providerDisplayName": str(
                    identity["provider_display_name"]
                ),
                "profilePictureUrl": str(
                    identity["profile_picture_url"]
                ),
                "createdAt": str(identity["created_at"]),
                "lastSeenAt": str(identity["last_seen_at"]),
            }
        )

    users: list[dict[str, Any]] = []
    for row in rows:
        user = _user_row_to_dict(row)
        user.update(
            {
                "identities": identities_by_user.get(user["id"], []),
                "stateCount": int(row["state_count"] or 0),
                "favoriteCount": int(row["favorite_count"] or 0),
                "playCount": int(row["play_count"] or 0),
                "canChangeActive": not bool(row["is_owner"]),
            }
        )
        users.append(user)
    return users


def set_user_active(
    connection: sqlite3.Connection,
    user_id: str,
    is_active: bool,
) -> bool:
    """Testable foundation for the later owner-only user management screen."""
    timestamp = utc_now()
    cursor = connection.execute(
        """
        UPDATE users
           SET is_active = ?,
               updated_at = ?
         WHERE id = ?
           AND is_owner = 0
        """,
        (1 if is_active else 0, timestamp, str(user_id or "")),
    )
    return cursor.rowcount == 1
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


def get_owner_user(connection: sqlite3.Connection) -> dict[str, Any] | None:
    """Return the single owner profile used by local authenticated sessions."""
    row = connection.execute(
        """
        SELECT id, display_name, is_owner, is_active,
               created_at, updated_at, last_seen_at
          FROM users
         WHERE is_owner = 1
         ORDER BY created_at, id
         LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None
    return _user_row_to_dict(row)
