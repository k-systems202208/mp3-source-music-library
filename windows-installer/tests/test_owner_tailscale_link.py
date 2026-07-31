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

IMPORT_ROOT = Path(tempfile.mkdtemp(prefix="music-library-owner-link-"))
os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(IMPORT_ROOT / "data")
os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(IMPORT_ROOT / "music")
(IMPORT_ROOT / "music").mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(SRC))

import database as db  # noqa: E402
import server  # noqa: E402
from local_auth import SESSION_COOKIE_NAME  # noqa: E402
from owner_link import (  # noqa: E402
    OwnerLinkCandidate,
    OwnerLinkCodeExpired,
    OwnerLinkCodeInvalid,
    OwnerLinkConflict,
    OwnerLinkManager,
    OwnerLinkNotReady,
)
from tailscale_identity import (  # noqa: E402
    TAILSCALE_LOGIN_HEADER,
    TAILSCALE_NAME_HEADER,
)


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0

    def __call__(self) -> float:
        return self.value

    def advance(self, seconds: float) -> None:
        self.value += seconds


def expect_exception(exc_type, callback) -> None:
    try:
        callback()
    except exc_type:
        return
    raise AssertionError(f"{exc_type.__name__} was not raised")


def test_manager() -> None:
    clock = FakeClock()
    manager = OwnerLinkManager(clock=clock, default_ttl_seconds=120)
    code, ttl = manager.create_challenge("usr_owner")
    assert ttl == 120
    assert len(code) >= 32
    assert code not in repr(manager.__dict__)

    waiting = manager.status(code, "usr_owner")
    assert waiting["status"] == "waiting_for_tailscale"
    assert waiting["candidate"] is None

    candidate = OwnerLinkCandidate(
        user_id="usr_candidate",
        subject="owner@example.com",
        display_name="Owner Remote",
        is_owner=False,
    )
    claimed = manager.claim(code, candidate)
    assert claimed["status"] == "awaiting_owner_confirmation"
    assert claimed["candidate"]["subject"] == "owner@example.com"

    # Repeating the same claim is idempotent; replacing it is not.
    manager.claim(code, candidate)
    expect_exception(
        OwnerLinkConflict,
        lambda: manager.claim(
            code,
            OwnerLinkCandidate(
                user_id="usr_other",
                subject="other@example.com",
                display_name="Other",
                is_owner=False,
            ),
        ),
    )

    expect_exception(
        OwnerLinkNotReady,
        lambda: manager.begin_confirmation(
            manager.create_challenge("usr_second")[0],
            "usr_second",
            expected_user_id="usr_candidate",
            expected_subject="owner@example.com",
        ),
    )
    expect_exception(
        OwnerLinkConflict,
        lambda: manager.begin_confirmation(
            code,
            "usr_owner",
            expected_user_id="usr_candidate",
            expected_subject="wrong@example.com",
        ),
    )

    selected = manager.begin_confirmation(
        code,
        "usr_owner",
        expected_user_id="usr_candidate",
        expected_subject="owner@example.com",
    )
    assert selected == candidate
    expect_exception(
        OwnerLinkConflict,
        lambda: manager.begin_confirmation(
            code,
            "usr_owner",
            expected_user_id="usr_candidate",
            expected_subject="owner@example.com",
        ),
    )
    manager.release_confirmation(code)
    manager.begin_confirmation(
        code,
        "usr_owner",
        expected_user_id="usr_candidate",
        expected_subject="owner@example.com",
    )
    manager.complete_confirmation(code)
    expect_exception(OwnerLinkCodeInvalid, lambda: manager.status(code, "usr_owner"))

    expiring, _ = manager.create_challenge("usr_expiring", ttl_seconds=60)
    clock.advance(61)
    expect_exception(
        OwnerLinkCodeExpired,
        lambda: manager.status(expiring, "usr_expiring"),
    )


def insert_test_track(connection, track_id: str) -> None:
    timestamp = db.utc_now()
    connection.execute(
        """
        INSERT INTO tracks(
            id, relative_path, filename,
            title, normalized_title,
            file_size, modified_time_ns, audio_file,
            last_scanned_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, 1, 1, ?, ?, ?, ?)
        """,
        (
            track_id,
            f"Test/{track_id}.mp3",
            f"{track_id}.mp3",
            track_id,
            track_id.casefold(),
            f"Music/Test/{track_id}.mp3",
            timestamp,
            timestamp,
            timestamp,
        ),
    )



def insert_user_state(
    connection,
    *,
    user_id: str,
    track_id: str,
    favorite: int = 0,
    rating: int | None = None,
    play_count: int = 0,
    last_played_at: str = "",
    created_at: str | None = None,
) -> None:
    timestamp = created_at or db.utc_now()
    connection.execute(
        """
        INSERT INTO user_track_state(
            user_id, track_id, favorite, rating,
            play_count, last_played_at, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            track_id,
            favorite,
            rating,
            play_count,
            last_played_at,
            timestamp,
            timestamp,
        ),
    )


def get_state(connection, user_id: str, track_id: str):
    return connection.execute(
        """
        SELECT favorite, rating, play_count, last_played_at,
               created_at, updated_at
          FROM user_track_state
         WHERE user_id = ? AND track_id = ?
        """,
        (user_id, track_id),
    ).fetchone()


def test_database_link_safety() -> None:
    path = IMPORT_ROOT / "database-link-test.db"
    connection = db.connect_database(path, prepare_migration_backup=False)
    try:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None

        candidate = db.get_or_create_tailscale_user(
            connection,
            subject="owner@example.com",
            display_name="Owner Remote",
        )
        connection.commit()
        candidate_id = candidate["id"]

        linked = db.link_tailscale_identity_to_owner(
            connection,
            subject="OWNER@example.com",
            expected_candidate_user_id=candidate_id,
        )
        connection.commit()
        assert linked["id"] == owner["id"]
        assert linked["alreadyLinked"] is False
        assert linked["removedDuplicateUserId"] == candidate_id

        identity = connection.execute(
            """
            SELECT user_id FROM user_identities
             WHERE provider = 'tailscale' AND subject = 'owner@example.com'
            """
        ).fetchone()
        assert identity is not None
        assert identity["user_id"] == owner["id"]
        removed = connection.execute(
            "SELECT 1 FROM users WHERE id = ?",
            (candidate_id,),
        ).fetchone()
        assert removed is None

        linked_again = db.link_tailscale_identity_to_owner(
            connection,
            subject="owner@example.com",
            expected_candidate_user_id=owner["id"],
        )
        connection.commit()
        assert linked_again["alreadyLinked"] is True

        # A profile with personal state is merged without data loss.
        state_user = db.get_or_create_tailscale_user(
            connection,
            subject="state@example.com",
            display_name="State User",
        )
        insert_test_track(connection, "track_state")
        insert_user_state(
            connection,
            user_id=state_user["id"],
            track_id="track_state",
            favorite=1,
            rating=4,
            play_count=3,
            last_played_at="2026-07-31T21:00:00+09:00",
        )
        connection.commit()
        preview = db.get_owner_link_merge_preview(connection, state_user["id"])
        assert preview == {
            "stateCount": 1,
            "playCount": 3,
            "favoriteCount": 1,
            "ratingCount": 1,
            "identityCount": 1,
            "ratingConflictCount": 0,
            "canMerge": True,
        }
        merged = db.link_tailscale_identity_to_owner(
            connection,
            subject="state@example.com",
            expected_candidate_user_id=state_user["id"],
        )
        connection.commit()
        assert merged["mergedPersonalState"] == {
            "candidateStateCount": 1,
            "movedStateCount": 1,
            "combinedStateCount": 0,
            "playCountAdded": 3,
            "favoriteAddedCount": 1,
            "ratingInheritedCount": 1,
        }
        owner_state = get_state(connection, owner["id"], "track_state")
        assert owner_state is not None
        assert owner_state["favorite"] == 1
        assert owner_state["rating"] == 4
        assert owner_state["play_count"] == 3
        assert owner_state["last_played_at"] == "2026-07-31T21:00:00+09:00"
        removed_state_user = connection.execute(
            "SELECT 1 FROM users WHERE id = ?",
            (state_user["id"],),
        ).fetchone()
        assert removed_state_user is None

        # A profile with another identity must also be left untouched.
        multi = db.get_or_create_tailscale_user(
            connection,
            subject="multi@example.com",
            display_name="Multi",
        )
        connection.execute(
            """
            INSERT INTO user_identities(
                id, user_id, provider, subject,
                provider_display_name, profile_picture_url,
                created_at, last_seen_at
            ) VALUES (?, ?, 'future-provider', 'future-subject', '', '', ?, '')
            """,
            ("idn_future", multi["id"], db.utc_now()),
        )
        connection.commit()
        expect_exception(
            db.OwnerIdentityLinkConflict,
            lambda: db.link_tailscale_identity_to_owner(
                connection,
                subject="multi@example.com",
                expected_candidate_user_id=multi["id"],
            ),
        )
        connection.rollback()
    finally:
        connection.close()



def test_database_state_merge_rules() -> None:
    path = IMPORT_ROOT / "database-state-merge-test.db"
    connection = db.connect_database(path, prepare_migration_backup=False)
    try:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        assert owner is not None
        candidate = db.get_or_create_tailscale_user(
            connection,
            subject="merge@example.com",
            display_name="Merge Candidate",
        )

        for track_id in (
            "overlap",
            "candidate_only",
            "owner_rating_only",
            "candidate_rating_only",
            "same_rating",
        ):
            insert_test_track(connection, track_id)

        insert_user_state(
            connection,
            user_id=owner["id"],
            track_id="overlap",
            favorite=0,
            rating=None,
            play_count=5,
            last_played_at="2026-07-30T20:00:00+09:00",
        )
        insert_user_state(
            connection,
            user_id=candidate["id"],
            track_id="overlap",
            favorite=1,
            rating=None,
            play_count=3,
            last_played_at="2026-07-31T20:00:00+09:00",
        )
        insert_user_state(
            connection,
            user_id=candidate["id"],
            track_id="candidate_only",
            favorite=1,
            rating=5,
            play_count=2,
            last_played_at="2026-07-29T20:00:00+09:00",
        )
        insert_user_state(
            connection,
            user_id=owner["id"],
            track_id="owner_rating_only",
            rating=2,
            play_count=1,
        )
        insert_user_state(
            connection,
            user_id=candidate["id"],
            track_id="owner_rating_only",
            rating=None,
            play_count=4,
        )
        insert_user_state(
            connection,
            user_id=owner["id"],
            track_id="candidate_rating_only",
            rating=None,
            play_count=1,
        )
        insert_user_state(
            connection,
            user_id=candidate["id"],
            track_id="candidate_rating_only",
            rating=3,
            play_count=2,
        )
        insert_user_state(
            connection,
            user_id=owner["id"],
            track_id="same_rating",
            rating=4,
            play_count=7,
        )
        insert_user_state(
            connection,
            user_id=candidate["id"],
            track_id="same_rating",
            rating=4,
            play_count=6,
        )
        connection.commit()

        preview = db.get_owner_link_merge_preview(connection, candidate["id"])
        assert preview["stateCount"] == 5
        assert preview["playCount"] == 17
        assert preview["favoriteCount"] == 2
        assert preview["ratingCount"] == 3
        assert preview["ratingConflictCount"] == 0
        assert preview["canMerge"] is True

        result = db.link_tailscale_identity_to_owner(
            connection,
            subject="merge@example.com",
            expected_candidate_user_id=candidate["id"],
        )
        connection.commit()
        summary = result["mergedPersonalState"]
        assert summary["candidateStateCount"] == 5
        assert summary["movedStateCount"] == 1
        assert summary["combinedStateCount"] == 4
        assert summary["playCountAdded"] == 17
        assert summary["favoriteAddedCount"] == 2
        assert summary["ratingInheritedCount"] == 2

        overlap = get_state(connection, owner["id"], "overlap")
        assert overlap["favorite"] == 1
        assert overlap["play_count"] == 8
        assert overlap["last_played_at"] == "2026-07-31T20:00:00+09:00"

        candidate_only = get_state(connection, owner["id"], "candidate_only")
        assert candidate_only["favorite"] == 1
        assert candidate_only["rating"] == 5
        assert candidate_only["play_count"] == 2

        owner_rating = get_state(connection, owner["id"], "owner_rating_only")
        assert owner_rating["rating"] == 2
        assert owner_rating["play_count"] == 5

        candidate_rating = get_state(
            connection,
            owner["id"],
            "candidate_rating_only",
        )
        assert candidate_rating["rating"] == 3
        assert candidate_rating["play_count"] == 3

        same_rating = get_state(connection, owner["id"], "same_rating")
        assert same_rating["rating"] == 4
        assert same_rating["play_count"] == 13

        candidate_states = connection.execute(
            "SELECT COUNT(*) FROM user_track_state WHERE user_id = ?",
            (candidate["id"],),
        ).fetchone()[0]
        assert candidate_states == 0
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        connection.close()


def test_rating_conflict_rolls_back_everything() -> None:
    path = IMPORT_ROOT / "database-rating-conflict-test.db"
    connection = db.connect_database(path, prepare_migration_backup=False)
    try:
        db.initialize_database(connection)
        owner = db.get_owner_user(connection)
        candidate = db.get_or_create_tailscale_user(
            connection,
            subject="rating-conflict@example.com",
            display_name="Rating Conflict",
        )
        insert_test_track(connection, "rating_conflict")
        insert_user_state(
            connection,
            user_id=owner["id"],
            track_id="rating_conflict",
            favorite=0,
            rating=2,
            play_count=5,
        )
        insert_user_state(
            connection,
            user_id=candidate["id"],
            track_id="rating_conflict",
            favorite=1,
            rating=5,
            play_count=3,
        )
        connection.commit()

        preview = db.get_owner_link_merge_preview(connection, candidate["id"])
        assert preview["ratingConflictCount"] == 1
        assert preview["canMerge"] is False

        expect_exception(
            db.OwnerIdentityLinkConflict,
            lambda: db.link_tailscale_identity_to_owner(
                connection,
                subject="rating-conflict@example.com",
                expected_candidate_user_id=candidate["id"],
            ),
        )

        owner_state = get_state(connection, owner["id"], "rating_conflict")
        candidate_state = get_state(
            connection,
            candidate["id"],
            "rating_conflict",
        )
        assert owner_state["rating"] == 2
        assert owner_state["play_count"] == 5
        assert candidate_state["rating"] == 5
        assert candidate_state["play_count"] == 3
        identity = connection.execute(
            """
            SELECT user_id FROM user_identities
             WHERE provider = 'tailscale'
               AND subject = 'rating-conflict@example.com'
            """
        ).fetchone()
        assert identity["user_id"] == candidate["id"]
        assert connection.execute(
            "SELECT 1 FROM users WHERE id = ?",
            (candidate["id"],),
        ).fetchone() is not None
    finally:
        connection.close()


def request(
    connection: http.client.HTTPConnection,
    method: str,
    path: str,
    *,
    headers: dict[str, str] | None = None,
    value: dict | None = None,
) -> tuple[int, dict[str, str], dict | bytes]:
    body = None
    actual_headers = dict(headers or {})
    if value is not None:
        body = json.dumps(value, separators=(",", ":")).encode("utf-8")
        actual_headers["Content-Type"] = "application/json"
        actual_headers["Content-Length"] = str(len(body))
    connection.request(method, path, body=body, headers=actual_headers)
    response = connection.getresponse()
    payload = response.read()
    response_headers = {
        key.casefold(): value for key, value in response.getheaders()
    }
    if response_headers.get("content-type", "").startswith("application/json"):
        return response.status, response_headers, json.loads(payload.decode("utf-8"))
    return response.status, response_headers, payload


def get_owner_cookie(port: int, control_secret: str) -> str:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        token = "L" * 43
        status, _, _ = request(
            connection,
            "POST",
            "/api/local-auth/token",
            headers={"X-Music-Library-Control-Secret": control_secret},
            value={"token": token, "expiresInSeconds": 60},
        )
        assert status == 201
        status, headers, _ = request(
            connection,
            "GET",
            f"/api/local-auth/exchange?token={token}",
        )
        assert status == 303
        return headers["set-cookie"].split(";", 1)[0]
    finally:
        connection.close()


def tailscale_headers(login: str, name: str) -> dict[str, str]:
    return {
        TAILSCALE_LOGIN_HEADER: login,
        TAILSCALE_NAME_HEADER: name,
    }


def test_http_link_flow() -> None:
    control_secret = "S" * 48
    music_server = server.create_server(
        "127.0.0.1",
        0,
        owner_control_secret=control_secret,
    )
    port = int(music_server.server_address[1])
    thread = threading.Thread(target=music_server.serve_forever, daemon=True)
    thread.start()
    owner_cookie = get_owner_cookie(port, control_secret)
    owner_headers = {"Cookie": owner_cookie}

    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=10)
    try:
        status, _, _ = request(
            connection,
            "POST",
            "/api/owner-link/start",
            value={},
        )
        assert status == 403

        status, _, started = request(
            connection,
            "POST",
            "/api/owner-link/start",
            headers=owner_headers,
            value={"expiresInSeconds": 300},
        )
        assert status == 201
        code = started["code"]
        assert started["status"] == "waiting_for_tailscale"

        status, _, _ = request(
            connection,
            "GET",
            f"/api/owner-link/status?code={code}",
        )
        assert status == 403

        status, _, _ = request(
            connection,
            "POST",
            "/api/owner-link/claim",
            value={"code": code},
        )
        assert status == 403

        candidate_headers = tailscale_headers(
            "Owner@Example.com",
            "Owner Remote",
        )
        status, _, candidate_current = request(
            connection,
            "GET",
            "/api/current-user",
            headers=candidate_headers,
        )
        assert status == 200
        with db.database() as state_connection:
            db.initialize_database(state_connection)
            insert_test_track(state_connection, "http_merge_track")
            insert_user_state(
                state_connection,
                user_id=candidate_current["id"],
                track_id="http_merge_track",
                favorite=1,
                play_count=3,
                last_played_at="2026-07-31T22:00:00+09:00",
            )

        status, _, claimed = request(
            connection,
            "POST",
            "/api/owner-link/claim",
            headers=candidate_headers,
            value={"code": code},
        )
        assert status == 202
        assert claimed["subject"] == "owner@example.com"
        assert claimed["alreadyOwner"] is False
        assert claimed["mergePreview"]["stateCount"] == 1
        assert claimed["mergePreview"]["playCount"] == 3
        assert claimed["mergePreview"]["favoriteCount"] == 1
        assert claimed["mergePreview"]["canMerge"] is True

        status, _, status_value = request(
            connection,
            "GET",
            f"/api/owner-link/status?code={code}",
            headers=owner_headers,
        )
        assert status == 200
        candidate = status_value["candidate"]
        assert candidate["subject"] == "owner@example.com"
        assert candidate["displayName"] == "Owner Remote"
        assert candidate["stateCount"] == 1
        assert candidate["playCount"] == 3
        assert candidate["favoriteCount"] == 1
        assert candidate["ratingConflictCount"] == 0
        assert candidate["canMerge"] is True

        status, _, _ = request(
            connection,
            "POST",
            "/api/owner-link/confirm",
            headers=owner_headers,
            value={
                "code": code,
                "confirmed": False,
                "userId": candidate["userId"],
                "subject": candidate["subject"],
            },
        )
        assert status == 400

        status, _, _ = request(
            connection,
            "POST",
            "/api/owner-link/confirm",
            headers=owner_headers,
            value={
                "code": code,
                "confirmed": True,
                "userId": candidate["userId"],
                "subject": "wrong@example.com",
            },
        )
        assert status == 409

        status, _, confirmed = request(
            connection,
            "POST",
            "/api/owner-link/confirm",
            headers=owner_headers,
            value={
                "code": code,
                "confirmed": True,
                "userId": candidate["userId"],
                "subject": candidate["subject"],
            },
        )
        assert status == 200
        assert confirmed["linked"] is True
        assert confirmed["alreadyLinked"] is False
        assert confirmed["mergedPersonalState"]["candidateStateCount"] == 1
        assert confirmed["mergedPersonalState"]["playCountAdded"] == 3
        assert confirmed["mergedPersonalState"]["favoriteAddedCount"] == 1

        status, _, remote_owner = request(
            connection,
            "GET",
            "/api/current-user",
            headers=candidate_headers,
        )
        assert status == 200
        assert remote_owner["authenticated"] is True
        assert remote_owner["isOwner"] is True
        assert remote_owner["provider"] == "tailscale"
        assert remote_owner["id"] == confirmed["owner"]["id"]
        with db.database() as state_connection:
            db.initialize_database(state_connection)
            merged_http_state = get_state(
                state_connection,
                remote_owner["id"],
                "http_merge_track",
            )
            assert merged_http_state is not None
            assert merged_http_state["favorite"] == 1
            assert merged_http_state["play_count"] == 3

        backups = sorted((db.BACKUP_DIR).glob("library-pre-owner-link-*.db"))
        assert backups
        check = db.sqlite3.connect(backups[-1]).execute("PRAGMA quick_check").fetchone()
        assert check is not None and check[0] == "ok"

        # Already-linked identity is idempotent but still requires both sides.
        status, _, second_started = request(
            connection,
            "POST",
            "/api/owner-link/start",
            headers=owner_headers,
            value={},
        )
        assert status == 201
        second_code = second_started["code"]
        status, _, second_claim = request(
            connection,
            "POST",
            "/api/owner-link/claim",
            headers=candidate_headers,
            value={"code": second_code},
        )
        assert status == 202
        assert second_claim["alreadyOwner"] is True
        status, _, second_status = request(
            connection,
            "GET",
            f"/api/owner-link/status?code={second_code}",
            headers=owner_headers,
        )
        assert status == 200
        second_candidate = second_status["candidate"]
        status, _, second_confirm = request(
            connection,
            "POST",
            "/api/owner-link/confirm",
            headers=owner_headers,
            value={
                "code": second_code,
                "confirmed": True,
                "userId": second_candidate["userId"],
                "subject": second_candidate["subject"],
            },
        )
        assert status == 200
        assert second_confirm["alreadyLinked"] is True

        # A wrong claimant remains a normal member when the owner cancels.
        status, _, cancel_started = request(
            connection,
            "POST",
            "/api/owner-link/start",
            headers=owner_headers,
            value={},
        )
        cancel_code = cancel_started["code"]
        family_headers = tailscale_headers("family@example.com", "Family")
        status, _, _ = request(
            connection,
            "POST",
            "/api/owner-link/claim",
            headers=family_headers,
            value={"code": cancel_code},
        )
        assert status == 202
        status, _, cancelled = request(
            connection,
            "POST",
            "/api/owner-link/cancel",
            headers=owner_headers,
            value={"code": cancel_code},
        )
        assert status == 200 and cancelled["cancelled"] is True
        status, _, family = request(
            connection,
            "GET",
            "/api/current-user",
            headers=family_headers,
        )
        assert status == 200
        assert family["authenticated"] is True
        assert family["isOwner"] is False
    finally:
        connection.close()
        music_server.shutdown()
        music_server.server_close()
        thread.join(timeout=5)


test_manager()
test_database_link_safety()
test_database_state_merge_rules()
test_rating_conflict_rolls_back_everything()
test_http_link_flow()

html_text = (SRC / "music-library-search.html").read_text(encoding="utf-8")
assert 'id="ownerLinkCandidateState"' in html_text
assert "個人状態 ${stateCount}曲・再生 ${playCount}回" in html_text
assert "mergedPersonalState" in html_text

print("Owner and Tailscale identity linking tests passed.")
