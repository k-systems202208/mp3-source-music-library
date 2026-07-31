#!/usr/bin/env python3
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from email.header import decode_header
from typing import Any, Mapping
from urllib.parse import urlparse

TAILSCALE_LOGIN_HEADER = "Tailscale-User-Login"
TAILSCALE_NAME_HEADER = "Tailscale-User-Name"
TAILSCALE_PROFILE_HEADER = "Tailscale-User-Profile-Pic"

MAX_LOGIN_LENGTH = 512
MAX_DISPLAY_NAME_LENGTH = 200
MAX_PROFILE_URL_LENGTH = 2048


@dataclass(frozen=True)
class TailscaleIdentity:
    """Validated Tailscale Serve identity forwarded to the localhost backend."""

    subject: str
    login_name: str
    display_name: str
    profile_picture_url: str


def _single_header_value(headers: Any, name: str) -> str:
    """Return one header value and reject duplicates.

    ``http.client.HTTPMessage`` exposes ``get_all`` while unit-test mappings
    generally expose only ``get``. Tailscale Serve is expected to forward one
    value for each identity header. Duplicate login headers are ambiguous and
    therefore not trusted.
    """
    get_all = getattr(headers, "get_all", None)
    if callable(get_all):
        values = get_all(name)
        if values is None:
            return ""
        if len(values) != 1:
            return ""
        return str(values[0] or "")

    if isinstance(headers, Mapping):
        lowered_name = name.casefold()
        matches = [
            value
            for key, value in headers.items()
            if str(key).casefold() == lowered_name
        ]
        if len(matches) != 1:
            return ""
        return str(matches[0] or "")

    getter = getattr(headers, "get", None)
    if callable(getter):
        return str(getter(name, "") or "")
    return ""


def decode_identity_header(value: str) -> str:
    """Decode a plain or RFC 2047 encoded identity header safely."""
    raw = str(value or "").strip()
    if not raw:
        return ""

    try:
        parts = decode_header(raw)
    except Exception:
        parts = [(raw, None)]

    decoded_parts: list[str] = []
    for part, charset in parts:
        if isinstance(part, str):
            decoded_parts.append(part)
            continue

        encodings = []
        if charset:
            encodings.append(str(charset))
        encodings.extend(["utf-8", "latin-1"])

        decoded = None
        for encoding in encodings:
            try:
                decoded = part.decode(encoding)
                break
            except (LookupError, UnicodeDecodeError):
                continue
        if decoded is None:
            decoded = part.decode("utf-8", errors="replace")
        decoded_parts.append(decoded)

    return unicodedata.normalize("NFKC", "".join(decoded_parts)).strip()


def _contains_control_characters(value: str) -> bool:
    return any(unicodedata.category(char) == "Cc" for char in value)


def normalize_login(value: str) -> str:
    """Return the stable Tailscale identity subject.

    The login name is case-insensitive for this application. Display-name
    changes do not affect the subject.
    """
    decoded = decode_identity_header(value)
    if not decoded or len(decoded) > MAX_LOGIN_LENGTH:
        return ""
    if _contains_control_characters(decoded):
        return ""
    return decoded.casefold()


def normalize_display_name(value: str, *, fallback: str) -> str:
    decoded = decode_identity_header(value)
    if (
        not decoded
        or len(decoded) > MAX_DISPLAY_NAME_LENGTH
        or _contains_control_characters(decoded)
    ):
        decoded = decode_identity_header(fallback)
    if not decoded:
        decoded = "Tailscale利用者"
    return decoded[:MAX_DISPLAY_NAME_LENGTH]


def normalize_profile_picture_url(value: str) -> str:
    decoded = decode_identity_header(value)
    if not decoded:
        return ""
    if len(decoded) > MAX_PROFILE_URL_LENGTH or _contains_control_characters(decoded):
        return ""

    parsed = urlparse(decoded)
    if parsed.scheme.casefold() not in {"http", "https"}:
        return ""
    if not parsed.netloc or parsed.username or parsed.password:
        return ""
    return decoded


def parse_tailscale_identity(headers: Any) -> TailscaleIdentity | None:
    """Parse trusted identity headers supplied by Tailscale Serve.

    The application server must remain bound to localhost. Tailscale's proxy
    removes caller-supplied identity headers and then adds the authenticated
    user's values. Tagged devices do not receive these user identity headers,
    so a missing login always remains anonymous.
    """
    raw_login = _single_header_value(headers, TAILSCALE_LOGIN_HEADER)
    subject = normalize_login(raw_login)
    if not subject:
        return None

    login_name = decode_identity_header(raw_login)
    display_name = normalize_display_name(
        _single_header_value(headers, TAILSCALE_NAME_HEADER),
        fallback=login_name or subject,
    )
    profile_picture_url = normalize_profile_picture_url(
        _single_header_value(headers, TAILSCALE_PROFILE_HEADER)
    )

    return TailscaleIdentity(
        subject=subject,
        login_name=login_name or subject,
        display_name=display_name,
        profile_picture_url=profile_picture_url,
    )
