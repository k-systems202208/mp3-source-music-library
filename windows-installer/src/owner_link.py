#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

DEFAULT_OWNER_LINK_TTL_SECONDS = 5 * 60
MIN_OWNER_LINK_TTL_SECONDS = 60
MAX_OWNER_LINK_TTL_SECONDS = 10 * 60
MIN_OWNER_LINK_CODE_LENGTH = 32


class OwnerLinkError(RuntimeError):
    """Base class for owner-link state errors."""


class OwnerLinkCodeInvalid(OwnerLinkError):
    pass


class OwnerLinkCodeExpired(OwnerLinkError):
    pass


class OwnerLinkConflict(OwnerLinkError):
    pass


class OwnerLinkNotReady(OwnerLinkError):
    pass


@dataclass(frozen=True)
class OwnerLinkCandidate:
    user_id: str
    subject: str
    display_name: str
    is_owner: bool
    state_count: int = 0
    play_count: int = 0
    favorite_count: int = 0
    rating_count: int = 0
    rating_conflict_count: int = 0
    identity_count: int = 1
    can_merge: bool = True


@dataclass
class _OwnerLinkChallenge:
    owner_user_id: str
    expires_at: float
    candidate: OwnerLinkCandidate | None = None
    confirming: bool = False


class OwnerLinkManager:
    """In-memory two-sided confirmation for linking one Tailscale identity.

    The raw pairing code is never stored. A newly created challenge replaces
    any older challenge for the same owner, preventing two browser windows
    from confirming different accounts by mistake.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], float] | None = None,
        default_ttl_seconds: int = DEFAULT_OWNER_LINK_TTL_SECONDS,
    ) -> None:
        self._clock = clock or time.monotonic
        self._default_ttl_seconds = self._clamp_ttl(default_ttl_seconds)
        self._lock = threading.RLock()
        self._challenges: dict[str, _OwnerLinkChallenge] = {}
        self._owner_codes: dict[str, str] = {}

    @staticmethod
    def _hash_code(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @staticmethod
    def _validate_code(code: str) -> str:
        value = str(code or "").strip()
        if len(value) < MIN_OWNER_LINK_CODE_LENGTH or len(value) > 256:
            raise OwnerLinkCodeInvalid("関連付けコードが正しくありません。")
        return value

    @staticmethod
    def _clamp_ttl(value: int) -> int:
        ttl = int(value)
        if ttl < MIN_OWNER_LINK_TTL_SECONDS:
            return MIN_OWNER_LINK_TTL_SECONDS
        if ttl > MAX_OWNER_LINK_TTL_SECONDS:
            return MAX_OWNER_LINK_TTL_SECONDS
        return ttl

    def _remove_locked(self, code_hash: str) -> None:
        challenge = self._challenges.pop(code_hash, None)
        if challenge is not None:
            current = self._owner_codes.get(challenge.owner_user_id)
            if current == code_hash:
                self._owner_codes.pop(challenge.owner_user_id, None)

    def _lookup_locked(self, code: str) -> tuple[str, _OwnerLinkChallenge]:
        code_hash = self._hash_code(self._validate_code(code))
        challenge = self._challenges.get(code_hash)
        if challenge is None:
            raise OwnerLinkCodeInvalid("関連付けコードが見つかりません。")
        if challenge.expires_at <= self._clock():
            self._remove_locked(code_hash)
            raise OwnerLinkCodeExpired("関連付けコードの有効期限が切れています。")
        return code_hash, challenge

    def create_challenge(
        self,
        owner_user_id: str,
        *,
        ttl_seconds: int | None = None,
    ) -> tuple[str, int]:
        owner_id = str(owner_user_id or "").strip()
        if not owner_id:
            raise ValueError("owner_user_id is required")
        effective_ttl = self._clamp_ttl(
            self._default_ttl_seconds if ttl_seconds is None else ttl_seconds
        )
        raw_code = secrets.token_urlsafe(32)
        code_hash = self._hash_code(raw_code)

        with self._lock:
            previous = self._owner_codes.get(owner_id)
            if previous:
                self._remove_locked(previous)
            self._challenges[code_hash] = _OwnerLinkChallenge(
                owner_user_id=owner_id,
                expires_at=self._clock() + effective_ttl,
            )
            self._owner_codes[owner_id] = code_hash

        return raw_code, effective_ttl

    def claim(self, code: str, candidate: OwnerLinkCandidate) -> dict[str, object]:
        if not candidate.user_id or not candidate.subject:
            raise ValueError("candidate identity is incomplete")

        with self._lock:
            _, challenge = self._lookup_locked(code)
            if challenge.confirming:
                raise OwnerLinkConflict("この関連付けは確認処理中です。")
            if challenge.candidate is None:
                challenge.candidate = candidate
            elif (
                challenge.candidate.user_id != candidate.user_id
                or challenge.candidate.subject != candidate.subject
            ):
                raise OwnerLinkConflict(
                    "このコードには別のTailscale利用者が確認待ちです。"
                )

            return self._status_payload_locked(challenge)

    def status(self, code: str, owner_user_id: str) -> dict[str, object]:
        with self._lock:
            _, challenge = self._lookup_locked(code)
            if challenge.owner_user_id != str(owner_user_id or ""):
                raise OwnerLinkConflict("このコードを確認する権限がありません。")
            return self._status_payload_locked(challenge)

    def begin_confirmation(
        self,
        code: str,
        owner_user_id: str,
        *,
        expected_user_id: str,
        expected_subject: str,
    ) -> OwnerLinkCandidate:
        with self._lock:
            _, challenge = self._lookup_locked(code)
            if challenge.owner_user_id != str(owner_user_id or ""):
                raise OwnerLinkConflict("このコードを確認する権限がありません。")
            if challenge.candidate is None:
                raise OwnerLinkNotReady("Tailscale利用者の確認がまだ完了していません。")
            if challenge.confirming:
                raise OwnerLinkConflict("この関連付けはすでに確認処理中です。")
            if (
                challenge.candidate.user_id != str(expected_user_id or "")
                or challenge.candidate.subject != str(expected_subject or "")
            ):
                raise OwnerLinkConflict(
                    "確認対象が現在のTailscale利用者と一致しません。"
                )
            challenge.confirming = True
            return challenge.candidate

    def release_confirmation(self, code: str) -> None:
        with self._lock:
            try:
                _, challenge = self._lookup_locked(code)
            except OwnerLinkError:
                return
            challenge.confirming = False

    def complete_confirmation(self, code: str) -> None:
        with self._lock:
            code_hash, _ = self._lookup_locked(code)
            self._remove_locked(code_hash)

    def cancel(self, code: str, owner_user_id: str) -> None:
        with self._lock:
            code_hash, challenge = self._lookup_locked(code)
            if challenge.owner_user_id != str(owner_user_id or ""):
                raise OwnerLinkConflict("このコードを取り消す権限がありません。")
            self._remove_locked(code_hash)

    def _status_payload_locked(
        self,
        challenge: _OwnerLinkChallenge,
    ) -> dict[str, object]:
        remaining = max(0, int(challenge.expires_at - self._clock()))
        candidate = challenge.candidate
        return {
            "status": (
                "confirming"
                if challenge.confirming
                else (
                    "awaiting_owner_confirmation"
                    if candidate is not None
                    else "waiting_for_tailscale"
                )
            ),
            "expiresInSeconds": remaining,
            "candidate": (
                None
                if candidate is None
                else {
                    "userId": candidate.user_id,
                    "subject": candidate.subject,
                    "displayName": candidate.display_name,
                    "alreadyOwner": candidate.is_owner,
                    "stateCount": candidate.state_count,
                    "playCount": candidate.play_count,
                    "favoriteCount": candidate.favorite_count,
                    "ratingCount": candidate.rating_count,
                    "ratingConflictCount": candidate.rating_conflict_count,
                    "identityCount": candidate.identity_count,
                    "canMerge": candidate.can_merge,
                }
            ),
        }
