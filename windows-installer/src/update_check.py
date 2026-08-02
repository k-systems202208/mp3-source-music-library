#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

CURRENT_VERSION = "2.7.2"
GITHUB_REPOSITORY = "k-systems202208/mp3-source-music-library"
GITHUB_API_URL = (
    f"https://api.github.com/repos/{GITHUB_REPOSITORY}/releases?per_page=100"
)
GITHUB_RELEASES_URL = f"https://github.com/{GITHUB_REPOSITORY}/releases"
CACHE_FILENAME = "update-status.json"
CACHE_TTL_SECONDS = 24 * 60 * 60
REQUEST_TIMEOUT_SECONDS = 5.0
VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:[-+].*)?$", re.IGNORECASE)


class UpdateCheckError(RuntimeError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def isoformat_utc(value: datetime) -> str:
    normalized = value.astimezone(timezone.utc).replace(microsecond=0)
    return normalized.isoformat().replace("+00:00", "Z")


def parse_version(value: str) -> tuple[int, int, int]:
    match = VERSION_PATTERN.fullmatch(str(value or "").strip())
    if not match:
        raise ValueError(f"invalid semantic version: {value!r}")
    return tuple(int(part) for part in match.groups())


def normalized_version(value: str) -> str:
    major, minor, patch = parse_version(value)
    return f"{major}.{minor}.{patch}"


def is_newer_version(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def safe_release_url(value: str, repository: str = GITHUB_REPOSITORY) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlparse(text)
    except ValueError:
        return ""
    expected_prefix = f"/{repository.casefold()}/releases"
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com":
        return ""
    if not parsed.path.casefold().startswith(expected_prefix):
        return ""
    return text


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, OSError, UnicodeDecodeError, json.JSONDecodeError):
        return {}


def _atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _parse_checked_at(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _cache_is_fresh(cache: dict[str, Any], now: datetime, ttl_seconds: int) -> bool:
    checked_at = _parse_checked_at(cache.get("checkedAt"))
    if checked_at is None:
        return False
    age = (now - checked_at).total_seconds()
    return 0 <= age < max(0, int(ttl_seconds))


def _default_fetch(url: str, timeout: float) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "MusicLibrary-UpdateChecker/2.7.2",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except urllib.error.HTTPError as exc:
        raise UpdateCheckError(f"GitHub returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise UpdateCheckError(f"GitHub could not be reached: {exc.reason}") from exc
    except OSError as exc:
        raise UpdateCheckError(f"network error: {exc}") from exc

    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdateCheckError("GitHub response was not valid JSON") from exc
    if not isinstance(value, list):
        raise UpdateCheckError("GitHub release list had an unexpected shape")
    return [item for item in value if isinstance(item, dict)]


def _select_latest_published_release(value: Any) -> dict[str, Any]:
    """Select the highest semantic-version Release, including prereleases.

    Drafts are excluded. When the same semantic version appears more than once,
    a full release is preferred over a prerelease, then the newest publication
    timestamp is preferred.
    """
    if not isinstance(value, list):
        raise UpdateCheckError("GitHub release list had an unexpected shape")

    candidates: list[tuple[tuple[int, int, int], bool, str, dict[str, Any]]] = []
    for item in value:
        if not isinstance(item, dict) or bool(item.get("draft")):
            continue
        tag = str(item.get("tag_name") or "").strip()
        try:
            version = parse_version(tag)
        except ValueError:
            continue
        published_at = str(item.get("published_at") or "")
        candidates.append((version, not bool(item.get("prerelease")), published_at, item))

    if not candidates:
        raise UpdateCheckError(
            "GitHub did not return a published semantic-version Release"
        )
    return max(candidates, key=lambda candidate: candidate[:3])[3]


def _preview_result(current_version: str, now: datetime) -> dict[str, Any] | None:
    preview_version = os.environ.get("MUSIC_LIBRARY_UPDATE_PREVIEW_VERSION", "").strip()
    if not preview_version:
        return None
    latest = normalized_version(preview_version)
    release_url = safe_release_url(
        os.environ.get("MUSIC_LIBRARY_UPDATE_PREVIEW_URL", GITHUB_RELEASES_URL)
    ) or GITHUB_RELEASES_URL
    return {
        "currentVersion": normalized_version(current_version),
        "latestVersion": latest,
        "latestTag": f"v{latest}",
        "releaseName": f"Music Library v{latest}",
        "releaseUrl": release_url,
        "publishedAt": isoformat_utc(now),
        "checkedAt": isoformat_utc(now),
        "updateAvailable": is_newer_version(latest, current_version),
        "isPrerelease": False,
        "source": "preview",
        "repository": GITHUB_REPOSITORY,
        "error": "",
    }


def _result_from_release(
    release: dict[str, Any],
    *,
    current_version: str,
    checked_at: datetime,
    repository: str,
) -> dict[str, Any]:
    tag = str(release.get("tag_name") or "").strip()
    latest = normalized_version(tag)
    url = safe_release_url(str(release.get("html_url") or ""), repository)
    if not url:
        raise UpdateCheckError("GitHub release URL did not match the configured repository")
    return {
        "currentVersion": normalized_version(current_version),
        "latestVersion": latest,
        "latestTag": tag or f"v{latest}",
        "releaseName": str(release.get("name") or tag or f"v{latest}"),
        "releaseUrl": url,
        "publishedAt": str(release.get("published_at") or ""),
        "checkedAt": isoformat_utc(checked_at),
        "updateAvailable": is_newer_version(latest, current_version),
        "isPrerelease": bool(release.get("prerelease")),
        "source": "network",
        "repository": repository,
        "error": "",
    }


def check_for_update(
    *,
    data_root: Path,
    current_version: str = CURRENT_VERSION,
    force: bool = False,
    ttl_seconds: int = CACHE_TTL_SECONDS,
    timeout: float = REQUEST_TIMEOUT_SECONDS,
    repository: str = GITHUB_REPOSITORY,
    api_url: str = GITHUB_API_URL,
    fetch: Callable[[str, float], Any] | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return the newest published GitHub Release without making startup depend on GitHub.

    The repository's release process publishes Releases with GitHub's prerelease flag,
    so the checker reads the published Release list instead of the full-release-only endpoint. Drafts
    are ignored and the highest valid semantic version is selected.

    Successful responses are cached under the application data directory. A failed
    network request returns the most recent successful cache when one exists; otherwise
    it returns a non-fatal error payload.
    """
    checked_at = (now or utc_now()).astimezone(timezone.utc)
    preview = _preview_result(current_version, checked_at)
    if preview is not None:
        return preview

    cache_path = Path(data_root) / CACHE_FILENAME
    cache = _read_json(cache_path)
    if not force and cache and _cache_is_fresh(cache, checked_at, ttl_seconds):
        result = dict(cache)
        result["source"] = "cache"
        result["error"] = ""
        result["currentVersion"] = normalized_version(current_version)
        latest = str(result.get("latestVersion") or "")
        result["updateAvailable"] = bool(latest) and is_newer_version(latest, current_version)
        result["isPrerelease"] = bool(result.get("isPrerelease"))
        return result

    actual_fetch = fetch or _default_fetch
    try:
        releases = actual_fetch(api_url, timeout)
        release = _select_latest_published_release(releases)
        result = _result_from_release(
            release,
            current_version=current_version,
            checked_at=checked_at,
            repository=repository,
        )
        _atomic_write_json(cache_path, result)
        return result
    except (UpdateCheckError, ValueError, TypeError, OSError) as exc:
        message = f"{type(exc).__name__}: {exc}"
        if cache:
            result = dict(cache)
            result["source"] = "stale-cache"
            result["error"] = message
            result["currentVersion"] = normalized_version(current_version)
            result["isPrerelease"] = bool(result.get("isPrerelease"))
            latest = str(result.get("latestVersion") or "")
            try:
                result["updateAvailable"] = bool(latest) and is_newer_version(
                    latest, current_version
                )
            except ValueError:
                result["updateAvailable"] = False
            return result
        return {
            "currentVersion": normalized_version(current_version),
            "latestVersion": "",
            "latestTag": "",
            "releaseName": "",
            "releaseUrl": GITHUB_RELEASES_URL,
            "publishedAt": "",
            "checkedAt": isoformat_utc(checked_at),
            "updateAvailable": False,
            "isPrerelease": False,
            "source": "error",
            "repository": repository,
            "error": message,
        }
