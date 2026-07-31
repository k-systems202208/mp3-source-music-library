from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

# paths.py resolves these settings at import time.
IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-schema-v5-import-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402


def raw_connection(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=30.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def create_v4_database(path: Path, *, precreate_v5_tables: bool = False) -> None:
    connection = raw_connection(path)
    try:
        connection.executescript(db.SCHEMA_SQL)
        if not precreate_v5_tables:
            connection.executescript(
                """
                DROP TABLE user_track_state;
                DROP TABLE user_identities;
                DROP TABLE users;
                """
            )
        connection.execute(
            "INSERT INTO schema_info(key, value) VALUES('schema_version', '4') "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
        )
        connection.execute(
            "INSERT INTO schema_info(key, value) VALUES('created_by', 'MP3 Source Music Library') "
            "ON CONFLICT(key) DO NOTHING"
        )
        connection.commit()
    finally:
        connection.close()


def insert_track(
    connection: sqlite3.Connection,
    track_id: str,
    *,
    play_count: int = 0,
    last_played_at: str = "",
    favorite: int = 0,
    rating: int | None = None,
    is_available: int = 1,
) -> None:
    stamp = "2026-07-31T09:00:00+00:00"
    relative_path = f"Artist/Album/{track_id}.mp3"
    connection.execute(
        """
        INSERT INTO tracks(
            id, relative_path, filename,
            title, normalized_title, sort_title,
            artist_id, album_id, album_artist, genre, composer,
            year, duration_ms, track_number, disc_number, kind,
            file_size, modified_time_ns, content_signature,
            audio_file, artwork_id, metadata_source_json,
            play_count, date_added, last_played_at, favorite, rating,
            title_override, artist_override, album_override,
            legacy_id, legacy_match_method, last_scanned_at,
            is_available, created_at, updated_at
        ) VALUES (
            ?, ?, ?,
            ?, ?, '',
            NULL, NULL, '', '', '',
            NULL, 0, NULL, NULL, 'MP3オーディオファイル',
            100, 1, ?,
            ?, NULL, '{}',
            ?, ?, ?, ?, ?,
            NULL, NULL, NULL,
            '', '', ?,
            ?, ?, ?
        )
        """,
        (
            track_id,
            relative_path,
            f"{track_id}.mp3",
            track_id,
            track_id,
            f"signature-{track_id}",
            f"Music/{relative_path}",
            play_count,
            stamp,
            last_played_at,
            favorite,
            rating,
            stamp,
            is_available,
            stamp,
            stamp,
        ),
    )


def seed_legacy_states(path: Path, *, precreate_v5_tables: bool = False) -> None:
    create_v4_database(path, precreate_v5_tables=precreate_v5_tables)
    connection = raw_connection(path)
    try:
        insert_track(
            connection,
            "track_a",
            play_count=12,
            last_played_at="2026-07-31T18:00:00+09:00",
            favorite=1,
        )
        insert_track(connection, "track_b")
        insert_track(connection, "track_c", rating=0)
        insert_track(
            connection,
            "track_d",
            play_count=3,
            last_played_at="2026-07-30T20:00:00+09:00",
            is_available=0,
        )
        connection.commit()
    finally:
        connection.close()


def schema_value(connection: sqlite3.Connection, key: str) -> str | None:
    row = connection.execute(
        "SELECT value FROM schema_info WHERE key = ?",
        (key,),
    ).fetchone()
    return str(row["value"]) if row else None


def test_dedicated_backup() -> None:
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        database_path = temp_root / "library.db"
        backup_dir = temp_root / "Backups"
        seed_legacy_states(database_path)

        fixed_time = datetime(
            2026,
            7,
            31,
            18,
            54,
            0,
            tzinfo=timezone(timedelta(hours=9)),
        )
        backup = db.create_pre_v27_migration_backup(
            database_path,
            backup_dir=backup_dir,
            now=fixed_time,
        )
        assert backup is not None
        assert backup.name == "library-pre-v2.7.0-20260731-185400.db"
        assert db.database_schema_version(backup) == 4

        backup_connection = raw_connection(backup)
        try:
            assert backup_connection.execute("PRAGMA quick_check").fetchone()[0] == "ok"
            assert backup_connection.execute("SELECT COUNT(*) FROM tracks").fetchone()[0] == 4
        finally:
            backup_connection.close()

        second = db.create_pre_v27_migration_backup(
            database_path,
            backup_dir=backup_dir,
            now=fixed_time,
        )
        assert second is not None
        assert second.name == "library-pre-v2.7.0-20260731-185400-01.db"


def test_connect_creates_backup_before_upgrade() -> None:
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        database_path = temp_root / "library.db"
        backup_dir = temp_root / "migration-backups"
        seed_legacy_states(database_path)

        connection = db.connect_database(
            database_path,
            migration_backup_dir=backup_dir,
        )
        try:
            # connect_database only prepares the backup. The schema is still v4
            # until initialize_database starts its transaction.
            assert db.read_schema_version(connection) == 4
        finally:
            connection.close()

        backups = list(backup_dir.glob("library-pre-v2.7.0-*.db"))
        assert len(backups) == 1
        assert db.database_schema_version(backups[0]) == 4


def test_schema_v5_migration() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        seed_legacy_states(database_path)

        connection = raw_connection(database_path)
        try:
            db.initialize_database(connection)

            assert db.read_schema_version(connection) == 5
            assert schema_value(connection, db.MIGRATION_V5_FLAG) == db.MIGRATION_V5_COMPLETED

            owners = connection.execute(
                "SELECT * FROM users WHERE is_owner = 1"
            ).fetchall()
            assert len(owners) == 1
            owner = owners[0]
            owner_id = str(owner["id"])
            assert owner["display_name"] == db.OWNER_DEFAULT_DISPLAY_NAME
            assert int(owner["is_active"]) == 1
            assert schema_value(connection, "owner_user_id") == owner_id

            identity = connection.execute(
                """
                SELECT * FROM user_identities
                 WHERE provider = ? AND subject = ?
                """,
                (db.OWNER_IDENTITY_PROVIDER, db.OWNER_IDENTITY_SUBJECT),
            ).fetchone()
            assert identity is not None
            assert identity["user_id"] == owner_id

            rows = connection.execute(
                """
                SELECT track_id, favorite, rating, play_count, last_played_at
                  FROM user_track_state
                 WHERE user_id = ?
                 ORDER BY track_id
                """,
                (owner_id,),
            ).fetchall()
            assert [row["track_id"] for row in rows] == [
                "track_a",
                "track_c",
                "track_d",
            ]

            values = {str(row["track_id"]): row for row in rows}
            assert int(values["track_a"]["favorite"]) == 1
            assert values["track_a"]["rating"] is None
            assert int(values["track_a"]["play_count"]) == 12
            assert values["track_a"]["last_played_at"] == "2026-07-31T18:00:00+09:00"

            # rating=0 is a real value and must not be treated as unset.
            assert values["track_c"]["rating"] == 0
            assert int(values["track_c"]["play_count"]) == 0

            # Unavailable tracks retain their user state.
            assert int(values["track_d"]["play_count"]) == 3
            available = connection.execute(
                "SELECT is_available FROM tracks WHERE id = 'track_d'"
            ).fetchone()
            assert int(available["is_available"]) == 0

            # Legacy columns remain unchanged during this development phase.
            legacy = connection.execute(
                """
                SELECT play_count, last_played_at, favorite, rating
                  FROM tracks WHERE id = 'track_a'
                """
            ).fetchone()
            assert int(legacy["play_count"]) == 12
            assert legacy["last_played_at"] == "2026-07-31T18:00:00+09:00"
            assert int(legacy["favorite"]) == 1
            assert legacy["rating"] is None

            assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        finally:
            connection.close()


def test_migration_is_idempotent() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        seed_legacy_states(database_path)

        connection = raw_connection(database_path)
        try:
            db.initialize_database(connection)
            owner_id_before = schema_value(connection, "owner_user_id")
            state_count_before = connection.execute(
                "SELECT COUNT(*) FROM user_track_state"
            ).fetchone()[0]

            db.initialize_database(connection)

            assert schema_value(connection, "owner_user_id") == owner_id_before
            assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM user_identities").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM user_track_state").fetchone()[0] == state_count_before
        finally:
            connection.close()


def test_migration_rolls_back_on_failure() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        seed_legacy_states(database_path, precreate_v5_tables=True)

        connection = raw_connection(database_path)
        try:
            connection.execute(
                """
                CREATE TRIGGER force_state_migration_failure
                BEFORE INSERT ON user_track_state
                BEGIN
                    SELECT RAISE(ABORT, 'forced migration failure');
                END
                """
            )
            connection.commit()

            try:
                db.initialize_database(connection)
            except sqlite3.IntegrityError as exc:
                assert "forced migration failure" in str(exc)
            else:
                raise AssertionError("The forced migration failure did not occur")

            assert db.read_schema_version(connection) == 4
            assert connection.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM user_identities").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM user_track_state").fetchone()[0] == 0
            assert schema_value(connection, db.MIGRATION_V5_FLAG) is None
            assert schema_value(connection, "owner_user_id") is None
        finally:
            connection.close()


def test_foreign_key_restricts_state_track_deletion() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        seed_legacy_states(database_path)

        connection = raw_connection(database_path)
        try:
            db.initialize_database(connection)
            try:
                connection.execute("DELETE FROM tracks WHERE id = 'track_a'")
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
            else:
                raise AssertionError("State-bearing track deletion was not blocked")

            assert connection.execute(
                "SELECT COUNT(*) FROM tracks WHERE id = 'track_a'"
            ).fetchone()[0] == 1
        finally:
            connection.close()


def test_fresh_database() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        connection = raw_connection(database_path)
        try:
            db.initialize_database(connection)
            assert db.read_schema_version(connection) == 5
            assert connection.execute("SELECT COUNT(*) FROM users WHERE is_owner = 1").fetchone()[0] == 1
            assert connection.execute("SELECT COUNT(*) FROM user_track_state").fetchone()[0] == 0
            assert schema_value(connection, db.MIGRATION_V5_FLAG) == db.MIGRATION_V5_COMPLETED
        finally:
            connection.close()



def test_wal_backup_contains_committed_changes() -> None:
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        database_path = temp_root / "library.db"
        backup_dir = temp_root / "Backups"
        seed_legacy_states(database_path)

        writer = raw_connection(database_path)
        try:
            writer.execute("PRAGMA journal_mode = WAL")
            writer.execute(
                "UPDATE tracks SET play_count = 21 WHERE id = 'track_a'"
            )
            writer.commit()

            backup = db.create_pre_v27_migration_backup(
                database_path,
                backup_dir=backup_dir,
            )
            assert backup is not None

            copied = raw_connection(backup)
            try:
                row = copied.execute(
                    "SELECT play_count FROM tracks WHERE id = 'track_a'"
                ).fetchone()
                assert int(row["play_count"]) == 21
            finally:
                copied.close()
        finally:
            writer.close()


def test_backup_failure_blocks_connection() -> None:
    with tempfile.TemporaryDirectory() as temp:
        temp_root = Path(temp)
        database_path = temp_root / "library.db"
        seed_legacy_states(database_path)

        invalid_backup_dir = temp_root / "not-a-directory"
        invalid_backup_dir.write_text("file", encoding="utf-8")

        try:
            db.connect_database(
                database_path,
                migration_backup_dir=invalid_backup_dir,
            )
        except OSError:
            pass
        else:
            raise AssertionError("Connection continued after backup failure")

        assert db.database_schema_version(database_path) == 4


def test_late_legacy_import_is_backfilled() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        connection = raw_connection(database_path)
        try:
            # A fresh database is initialized before the first scan.
            db.initialize_database(connection)
            owner_id = schema_value(connection, "owner_user_id")
            assert owner_id
            assert connection.execute(
                "SELECT COUNT(*) FROM user_track_state"
            ).fetchone()[0] == 0

            # The first scan can then import a legacy play count.
            insert_track(
                connection,
                "late_import",
                play_count=9,
                last_played_at="2026-07-31T19:00:00+09:00",
            )
            connection.commit()

            db.initialize_database(connection)
            state = connection.execute(
                """
                SELECT play_count, last_played_at
                  FROM user_track_state
                 WHERE user_id = ? AND track_id = 'late_import'
                """,
                (owner_id,),
            ).fetchone()
            assert state is not None
            assert int(state["play_count"]) == 9
            assert state["last_played_at"] == "2026-07-31T19:00:00+09:00"

            # Once the row exists, compatibility backfill never overwrites it.
            connection.execute(
                """
                UPDATE user_track_state
                   SET play_count = 15
                 WHERE user_id = ? AND track_id = 'late_import'
                """,
                (owner_id,),
            )
            connection.commit()
            db.initialize_database(connection)
            assert connection.execute(
                """
                SELECT play_count FROM user_track_state
                 WHERE user_id = ? AND track_id = 'late_import'
                """,
                (owner_id,),
            ).fetchone()[0] == 15
        finally:
            connection.close()


def test_new_schema_objects_roll_back_on_failure() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        seed_legacy_states(database_path)

        connection = raw_connection(database_path)
        try:
            def deny_state_insert(
                action_code: int,
                parameter1: str | None,
                parameter2: str | None,
                database_name: str | None,
                trigger_name: str | None,
            ) -> int:
                del parameter2, database_name, trigger_name
                if (
                    action_code == sqlite3.SQLITE_INSERT
                    and parameter1 == "user_track_state"
                ):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK

            connection.set_authorizer(deny_state_insert)
            try:
                db.initialize_database(connection)
            except sqlite3.DatabaseError:
                pass
            else:
                raise AssertionError("The authorizer did not stop migration")
            finally:
                connection.set_authorizer(None)

            assert db.read_schema_version(connection) == 4
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "users" not in tables
            assert "user_identities" not in tables
            assert "user_track_state" not in tables
        finally:
            connection.close()


def test_single_owner_constraint() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        connection = raw_connection(database_path)
        try:
            db.initialize_database(connection)
            stamp = "2026-07-31T10:00:00+00:00"
            try:
                connection.execute(
                    """
                    INSERT INTO users(
                        id, display_name, is_owner, is_active,
                        created_at, updated_at, last_seen_at
                    ) VALUES ('usr_second', 'Second', 1, 1, ?, ?, '')
                    """,
                    (stamp, stamp),
                )
                connection.commit()
            except sqlite3.IntegrityError:
                connection.rollback()
            else:
                raise AssertionError("A second owner was accepted")

            assert connection.execute(
                "SELECT COUNT(*) FROM users WHERE is_owner = 1"
            ).fetchone()[0] == 1
        finally:
            connection.close()


def test_future_schema_is_refused() -> None:
    with tempfile.TemporaryDirectory() as temp:
        database_path = Path(temp) / "library.db"
        create_v4_database(database_path)
        connection = raw_connection(database_path)
        try:
            connection.execute(
                "UPDATE schema_info SET value = '6' WHERE key = 'schema_version'"
            )
            connection.commit()

            try:
                db.initialize_database(connection)
            except RuntimeError as exc:
                assert "新しいデータベース形式" in str(exc)
            else:
                raise AssertionError("A future schema version was accepted")

            assert db.read_schema_version(connection) == 6
            tables = {
                str(row[0])
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            assert "users" not in tables
        finally:
            connection.close()

def main() -> None:
    test_dedicated_backup()
    test_wal_backup_contains_committed_changes()
    test_backup_failure_blocks_connection()
    test_connect_creates_backup_before_upgrade()
    test_schema_v5_migration()
    test_migration_is_idempotent()
    test_late_legacy_import_is_backfilled()
    test_migration_rolls_back_on_failure()
    test_new_schema_objects_roll_back_on_failure()
    test_foreign_key_restricts_state_track_deletion()
    test_single_owner_constraint()
    test_future_schema_is_refused()
    test_fresh_database()
    print("Schema v5 migration tests passed.")


if __name__ == "__main__":
    main()
