#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import struct
import sys
import sqlite3
import traceback
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from database import (
    DATABASE_PATH,
    add_scan_error,
    backup_database_if_needed,
    complete_scan_run,
    connect_database,
    create_scan_run,
    initialize_database,
    load_track_rows,
    mark_track_seen_without_reparse,
    row_to_track,
    upsert_album,
    upsert_artist,
    upsert_artwork,
    upsert_track,
    utc_now,
)

from paths import (
    ARTWORK_CACHE,
    DATA_ROOT,
    MUSIC_ROOT,
    RESOURCE_ROOT,
    ensure_data_directories,
    media_relative_path,
    resolve_virtual_path,
)

ensure_data_directories()
VENDOR_DIR = RESOURCE_ROOT / "vendor"
if VENDOR_DIR.is_dir():
    sys.path.insert(0, str(VENDOR_DIR))

try:
    from mutagen.id3 import ID3, ID3NoHeaderError
    from mutagen.mp3 import MP3
except Exception:
    ID3 = None
    ID3NoHeaderError = Exception
    MP3 = None

LEGACY_JSON = DATA_ROOT / "legacy-library-data.json"
OUTPUT_JSON = DATA_ROOT / "music-library-data.json"
CACHE_JSON = DATA_ROOT / "library-cache.json"  # 旧版互換。SQLite版では読み書きしません。
DIAG_JSON = DATA_ROOT / "library-diagnostics.json"
DIAG_CSV = DATA_ROOT / "library-diagnostics.csv"
MP3_INDEX_JSON = DATA_ROOT / "mp3-index.json"
ARTWORK_INDEX_JSON = DATA_ROOT / "artwork-index.json"

CACHE_VERSION = 2  # 旧JSONキャッシュの最終版。
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
PREFERRED_ARTWORK_NAMES = ["folder", "cover", "front", "albumart", "small"]
MOJIBAKE_MARKERS = set("ÃÂâã¤¦ƒ‚„‰ŠŒŽ�")


@dataclass
class DiagnosticRow:
    severity: str
    category: str
    path: str
    message: str


def safe_rel(path: Path) -> str:
    """Return the browser-visible virtual path for music and cache files."""
    return media_relative_path(path)


def atomic_write_text(path: Path, text: str) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8", newline="\n")
    temp.replace(path)


def write_json(path: Path, obj: Any) -> None:
    atomic_write_text(path, json.dumps(obj, ensure_ascii=False, indent=2))


def synchsafe_to_int(data: bytes) -> int:
    if len(data) != 4:
        return 0
    return (
        ((data[0] & 0x7F) << 21)
        | ((data[1] & 0x7F) << 14)
        | ((data[2] & 0x7F) << 7)
        | (data[3] & 0x7F)
    )


def is_japanese_character(char: str) -> bool:
    code = ord(char)
    return (
        0x3040 <= code <= 0x30FF
        or 0x3400 <= code <= 0x4DBF
        or 0x4E00 <= code <= 0x9FFF
        or 0xFF66 <= code <= 0xFF9F
    )


def text_quality(value: str) -> float:
    """Score text so correctly decoded Japanese/Latin text beats mojibake."""
    if not value:
        return -1000.0

    score = 0.0
    for char in value:
        code = ord(char)
        category = unicodedata.category(char)
        if char == "\ufffd":
            score -= 20
        elif code < 32 and char not in "\t\r\n":
            score -= 12
        elif 0x7F <= code <= 0x9F:
            score -= 10
        elif is_japanese_character(char):
            score += 3
        elif char.isalnum():
            score += 1
        elif char.isspace() or category.startswith("P"):
            score += 0.1
        elif category.startswith("S"):
            score -= 0.4

        if char in MOJIBAKE_MARKERS:
            score -= 3

    for marker in ("ã€", "ã", "ã‚", "â€™", "â€œ", "â€", "Â ", "ƒ", "‚"):
        score -= value.count(marker) * 5
    return score


def repair_mojibake(value: Any) -> tuple[str, str]:
    """Repair common UTF-8/CP932 bytes that were decoded as Latin-1/CP1252."""
    original = str(value or "").replace("\x00", " / ").strip()
    if not original:
        return "", ""

    candidates: list[tuple[str, str]] = [(original, "")]
    seen = {original}
    for source_encoding in ("latin1", "cp1252"):
        try:
            raw = original.encode(source_encoding)
        except (UnicodeEncodeError, LookupError):
            continue
        for target_encoding in ("utf-8", "cp932"):
            try:
                candidate = raw.decode(target_encoding).replace("\x00", " / ").strip()
            except (UnicodeDecodeError, LookupError):
                continue
            if candidate and candidate not in seen:
                seen.add(candidate)
                candidates.append((candidate, f"{source_encoding}_to_{target_encoding}"))

    best_text, best_method = max(candidates, key=lambda pair: text_quality(pair[0]))
    if best_method and text_quality(best_text) >= text_quality(original) + 2:
        return best_text, best_method
    return original, ""


def decode_single_byte_id3(raw: bytes) -> str:
    """Decode ID3 encoding byte 0, including non-standard Japanese CP932 tags."""
    if not raw:
        return ""

    candidates: list[str] = []
    for encoding in ("utf-8", "cp932", "latin1"):
        try:
            decoded = raw.decode(encoding).rstrip("\x00").strip()
        except UnicodeDecodeError:
            continue
        if decoded:
            candidates.append(decoded)

    if not candidates:
        return raw.decode("latin1", errors="replace").rstrip("\x00").strip()

    best = max(candidates, key=text_quality)
    return repair_mojibake(best)[0]


def decode_text_payload(payload: bytes) -> str:
    if not payload:
        return ""
    encoding_byte = payload[0]
    raw = payload[1:]
    try:
        if encoding_byte == 0:
            return decode_single_byte_id3(raw)
        if encoding_byte == 1:
            text = raw.decode("utf-16", errors="replace").rstrip("\x00")
        elif encoding_byte == 2:
            text = raw.decode("utf-16-be", errors="replace").rstrip("\x00")
        elif encoding_byte == 3:
            text = raw.decode("utf-8", errors="replace").rstrip("\x00")
        else:
            text = raw.decode("utf-8", errors="replace").rstrip("\x00")
    except Exception:
        text = raw.decode("utf-8", errors="replace").rstrip("\x00")
    return repair_mojibake(text)[0]


def parse_id3v2_fallback(path: Path) -> tuple[dict[str, Any], tuple[bytes, str] | None]:
    """Small dependency-free fallback for files Mutagen cannot parse."""
    tags: dict[str, Any] = {}
    artwork: tuple[bytes, str] | None = None
    with path.open("rb") as file:
        header = file.read(10)
        if len(header) < 10 or header[:3] != b"ID3":
            return tags, artwork
        version = header[3]
        tag_size = synchsafe_to_int(header[6:10])
        data = file.read(tag_size)

    pos = 0
    while pos + 10 <= len(data):
        frame_id = data[pos : pos + 4].decode("latin1", errors="ignore")
        if not frame_id.strip("\x00"):
            break
        frame_size = (
            synchsafe_to_int(data[pos + 4 : pos + 8])
            if version == 4
            else int.from_bytes(data[pos + 4 : pos + 8], "big")
        )
        if frame_size <= 0 or pos + 10 + frame_size > len(data):
            break
        payload = data[pos + 10 : pos + 10 + frame_size]
        pos += 10 + frame_size

        if frame_id.startswith("T") and frame_id != "TXXX":
            value = decode_text_payload(payload)
            if value:
                tags[frame_id] = value
        elif frame_id == "APIC" and artwork is None and payload:
            text_encoding = payload[0]
            rest = payload[1:]
            mime_end = rest.find(b"\x00")
            if mime_end < 0:
                continue
            mime = rest[:mime_end].decode("latin1", errors="ignore") or "image/jpeg"
            rest = rest[mime_end + 1 :]
            if not rest:
                continue
            rest = rest[1:]  # picture type
            if text_encoding in (0, 3):
                description_end = rest.find(b"\x00")
                image_data = rest[description_end + 1 :] if description_end >= 0 else rest
            else:
                description_end = rest.find(b"\x00\x00")
                image_data = rest[description_end + 2 :] if description_end >= 0 else rest
            if image_data:
                artwork = (image_data, mime)
    return tags, artwork


def parse_id3v1(path: Path) -> dict[str, str]:
    try:
        with path.open("rb") as file:
            file.seek(-128, os.SEEK_END)
            block = file.read(128)
        if block[:3] != b"TAG":
            return {}

        def decode(part: bytes) -> str:
            raw = part.rstrip(b"\x00 ")
            return decode_single_byte_id3(raw)

        return {
            "title": decode(block[3:33]),
            "artist": decode(block[33:63]),
            "album": decode(block[63:93]),
            "year": decode(block[93:97]),
        }
    except Exception:
        return {}


def frame_text(tags: Any, frame_id: str) -> str:
    if tags is None:
        return ""
    frame = tags.get(frame_id)
    if frame is None:
        return ""
    values = getattr(frame, "text", None)
    if values is not None:
        text = " / ".join(str(item) for item in values if str(item).strip())
    else:
        text = str(frame)
    return repair_mojibake(text)[0]


def parse_with_mutagen(path: Path) -> tuple[dict[str, Any], tuple[bytes, str] | None, int, list[str]]:
    """Read ID3 metadata, embedded artwork and duration with bundled Mutagen."""
    if ID3 is None or MP3 is None:
        return {}, None, 0, ["Bundled Mutagen could not be imported; fallback parser was used."]

    notes: list[str] = []
    tags = None
    try:
        tags = ID3(path)
    except ID3NoHeaderError:
        tags = None
    except Exception as exc:
        notes.append(f"ID3 parser: {type(exc).__name__}: {exc}")

    values: dict[str, Any] = {}
    if tags is not None:
        for frame_id in (
            "TIT2", "TPE1", "TPE2", "TALB", "TCON", "TCOM", "TRCK", "TPOS",
            "TDRC", "TYER", "TSOT", "TSOP", "TSOA",
        ):
            value = frame_text(tags, frame_id)
            if value:
                values[frame_id] = value

    artwork: tuple[bytes, str] | None = None
    if tags is not None:
        try:
            pictures = list(tags.getall("APIC"))
            if pictures:
                pictures.sort(key=lambda picture: 0 if getattr(picture, "type", None) == 3 else 1)
                selected = pictures[0]
                if getattr(selected, "data", b""):
                    artwork = (bytes(selected.data), getattr(selected, "mime", "image/jpeg") or "image/jpeg")
        except Exception as exc:
            notes.append(f"Artwork parser: {type(exc).__name__}: {exc}")

    duration_ms = 0
    try:
        audio = MP3(path)
        if audio.info and audio.info.length:
            duration_ms = int(round(float(audio.info.length) * 1000))
    except Exception as exc:
        notes.append(f"Audio header: {type(exc).__name__}: {exc}")

    return values, artwork, duration_ms, notes


def detect_audio_duration_ms_fallback(path: Path) -> int:
    """Estimate duration from the first MPEG frame when Mutagen cannot read it."""
    try:
        size = path.stat().st_size
        with path.open("rb") as file:
            head = file.read(min(size, 256 * 1024))
        start = 0
        if head[:3] == b"ID3" and len(head) >= 10:
            start = 10 + synchsafe_to_int(head[6:10])
        bitrate_table = {
            (3, 1): [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
            (2, 1): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
            (0, 1): [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
        }
        for index in range(start, len(head) - 4):
            byte1, byte2, byte3, _ = head[index : index + 4]
            if byte1 != 0xFF or (byte2 & 0xE0) != 0xE0:
                continue
            version_bits = (byte2 >> 3) & 0x03
            layer_bits = (byte2 >> 1) & 0x03
            if layer_bits != 1 or version_bits == 1:
                continue
            bitrate_index = (byte3 >> 4) & 0x0F
            kbps = bitrate_table.get((version_bits, 1), [0] * 16)[bitrate_index]
            if kbps:
                audio_bytes = max(0, size - start)
                return int(audio_bytes * 8 / (kbps * 1000) * 1000)
    except Exception:
        pass
    return 0


def parse_number(value: Any) -> int | str:
    if value in (None, ""):
        return ""
    match = re.search(r"\d+", str(value))
    return int(match.group()) if match else ""


def clean_stem(stem: str) -> tuple[str, int | str]:
    value = stem.strip()
    track_number: int | str = ""
    match = re.match(
        r"^(?:disc\s*\d+\s*[-_. ]*)?(?:track\s*)?(\d{1,3})\s*[-_.：: ]+\s*(.+)$",
        value,
        re.I,
    )
    if match:
        track_number = int(match.group(1))
        value = match.group(2).strip()
    return value, track_number


def infer_from_filename(path: Path, known_artist: str = "") -> tuple[str, str, int | str]:
    stem, track_number = clean_stem(path.stem)
    artist = known_artist.strip()
    title = stem
    if not artist and " - " in stem:
        left, right = stem.split(" - ", 1)
        if left.strip() and right.strip():
            artist, title = left.strip(), right.strip()
    elif artist and stem.casefold().startswith((artist + " - ").casefold()):
        title = stem[len(artist) + 3 :].strip()
    return title, artist, track_number


def infer_disc_from_path(path: Path) -> int | str:
    for parent in path.parents:
        match = re.search(r"(?:disc|disk|cd)\s*[-_. ]*(\d+)", parent.name, re.I)
        if match:
            return int(match.group(1))
        if parent == MUSIC_ROOT:
            break
    return ""


def stable_id(relative_path: str) -> str:
    digest = hashlib.sha256(relative_path.encode("utf-8", errors="surrogatepass")).hexdigest()[:20]
    return f"mp3_{digest}"


def normalized(value: Any) -> str:
    text = str(value or "").casefold()
    return re.sub(r"[\s\u3000\-‐‑‒–—―_・･·.,，。!！?？'\"“”()（）\[\]【】{}／/\\:：]", "", text)


def legacy_key(item: dict[str, Any]) -> tuple[str, str, str]:
    return normalized(item.get("artist")), normalized(item.get("album")), normalized(item.get("name"))


def build_legacy_indexes(
    items: list[dict[str, Any]],
) -> tuple[
    dict[tuple[str, str, str], list[dict[str, Any]]],
    dict[tuple[str, str], list[dict[str, Any]]],
    dict[int, list[dict[str, Any]]],
]:
    exact: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
    album_track: dict[tuple[str, str], list[dict[str, Any]]] = {}
    by_size: dict[int, list[dict[str, Any]]] = {}
    for item in items:
        exact.setdefault(legacy_key(item), []).append(item)
        album = normalized(item.get("album"))
        track = str(parse_number(item.get("trackNumber", "")))
        if album and track:
            album_track.setdefault((album, track), []).append(item)
        size = parse_number(item.get("size", ""))
        if isinstance(size, int) and size > 0:
            by_size.setdefault(size, []).append(item)
    return exact, album_track, by_size


def duration_difference(item: dict[str, Any], duration_ms: int) -> int:
    legacy_duration = int(item.get("time") or 0)
    if not legacy_duration or not duration_ms:
        return 0
    return abs(legacy_duration - duration_ms)


def choose_legacy(
    track: dict[str, Any],
    exact_index: dict[Any, list[dict[str, Any]]],
    album_track_index: dict[Any, list[dict[str, Any]]],
    size_index: dict[int, list[dict[str, Any]]],
) -> tuple[dict[str, Any] | None, str]:
    candidates = exact_index.get(legacy_key(track), [])
    if len(candidates) == 1:
        return candidates[0], "exact_artist_album_title"
    if len(candidates) > 1:
        duration = int(track.get("time") or 0)
        ranked = sorted(candidates, key=lambda item: duration_difference(item, duration))
        if len(ranked) == 1 or duration_difference(ranked[0], duration) < duration_difference(ranked[1], duration):
            return ranked[0], "exact_with_duration"

    album = normalized(track.get("album"))
    track_number = str(track.get("trackNumber") or "")
    if album and track_number:
        candidates = album_track_index.get((album, track_number), [])
        duration = int(track.get("time") or 0)
        close = [
            item
            for item in candidates
            if not duration or not item.get("time") or duration_difference(item, duration) <= 4000
        ]
        if len(close) == 1:
            return close[0], "album_track_duration"

    size = int(track.get("size") or 0)
    if size:
        candidates = size_index.get(size, [])
        if len(candidates) == 1:
            candidate = candidates[0]
            if duration_difference(candidate, int(track.get("time") or 0)) <= 4000:
                return candidate, "unique_size_duration"
    return None, ""


def artwork_extension(mime: str, data: bytes) -> str:
    lowered = mime.casefold()
    if "png" in lowered or data.startswith(b"\x89PNG"):
        return ".png"
    if "webp" in lowered or data.startswith(b"RIFF"):
        return ".webp"
    if "gif" in lowered or data.startswith(b"GIF"):
        return ".gif"
    return ".jpg"


def find_external_artwork(mp3_path: Path, all_images_by_dir: dict[Path, list[Path]]) -> Path | None:
    current = mp3_path.parent
    while True:
        files = all_images_by_dir.get(current, [])
        if files:
            def score(path: Path) -> tuple[int, str]:
                stem = path.stem.casefold()
                rank = 0
                for index, preferred in enumerate(PREFERRED_ARTWORK_NAMES):
                    if stem == preferred or stem.startswith(preferred):
                        rank = 100 - index * 10
                        break
                return -rank, path.name.casefold()

            return sorted(files, key=score)[0]
        if current == MUSIC_ROOT or MUSIC_ROOT not in current.parents:
            break
        current = current.parent
    return None


def scan_files() -> tuple[list[Path], list[Path], list[DiagnosticRow]]:
    mp3_files: list[Path] = []
    image_files: list[Path] = []
    diagnostics: list[DiagnosticRow] = []
    if not MUSIC_ROOT.exists():
        MUSIC_ROOT.mkdir(parents=True, exist_ok=True)
        diagnostics.append(
            DiagnosticRow(
                "warning",
                "music_root_missing",
                "Music",
                "Musicフォルダを作成しました。MP3を入れて再実行してください。",
            )
        )
        return mp3_files, image_files, diagnostics

    def onerror(error: OSError) -> None:
        diagnostics.append(
            DiagnosticRow("error", "scan_error", getattr(error, "filename", "") or "", str(error))
        )

    for dirpath, _, filenames in os.walk(MUSIC_ROOT, onerror=onerror, followlinks=False):
        directory = Path(dirpath)
        for filename in filenames:
            path = directory / filename
            extension = path.suffix.casefold()
            if extension == ".mp3":
                mp3_files.append(path)
            elif extension in IMAGE_EXTENSIONS:
                image_files.append(path)

    mp3_files.sort(key=lambda path: safe_rel(path).casefold())
    image_files.sort(key=lambda path: safe_rel(path).casefold())
    return mp3_files, image_files, diagnostics


def metadata_value(tag_value: str, fallback_value: str, fallback_source: str) -> tuple[str, str]:
    repaired, method = repair_mojibake(tag_value)
    if repaired and text_quality(repaired) >= 0:
        return repaired, "tag_repaired" if method else "tag"
    return fallback_value, fallback_source


def update_stats_from_track(stats: dict[str, int], track: dict[str, Any]) -> None:
    metadata_source = track.get("metadataSource") or {}
    if str(metadata_source.get("title", "")).startswith("tag"):
        stats["tagTitle"] += 1
    else:
        stats["filenameTitle"] += 1
        stats["missingTitleTag"] += 1
    if not str(metadata_source.get("artist", "")).startswith("tag"):
        stats["missingArtistTag"] += 1
    if not str(metadata_source.get("album", "")).startswith("tag"):
        stats["missingAlbumTag"] += 1
    if any(str(source).endswith("repaired") for source in metadata_source.values()):
        stats["mojibakeRepaired"] += 1


def content_signature(path: Path, file_size: int) -> str:
    """Create a lightweight content signature used to recognize moved MP3 files.

    It intentionally avoids hashing the entire library. The file size plus the
    first and last 64 KiB are sufficient for move detection in normal use. A
    match is accepted only when it points to exactly one missing old record.
    """
    digest = hashlib.sha256()
    digest.update(str(file_size).encode("ascii"))
    with path.open("rb") as file:
        head = file.read(64 * 1024)
        digest.update(head)
        if file_size > 64 * 1024:
            file.seek(max(0, file_size - 64 * 1024))
            digest.update(file.read(64 * 1024))
    return digest.hexdigest()


def load_legacy_items(diagnostics: list[DiagnosticRow]) -> list[dict[str, Any]]:
    """Load supplemental data from the old library and the previous export.

    SQLite remains authoritative. These JSON files are consulted only during
    first registration when a database row does not already exist.
    """
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source in (LEGACY_JSON, OUTPUT_JSON):
        if not source.exists():
            continue
        try:
            data = json.loads(source.read_text(encoding="utf-8-sig"))
            if not isinstance(data, list):
                continue
            for item in data:
                if not isinstance(item, dict):
                    continue
                key = str(item.get("id") or item.get("relativePath") or "")
                if key and key in seen:
                    continue
                if key:
                    seen.add(key)
                merged.append(item)
        except Exception as exc:
            diagnostics.append(
                DiagnosticRow("error", "legacy_json_error", safe_rel(source), str(exc))
            )
    return merged


def artwork_file_hash(path: Path) -> str:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while True:
                block = file.read(1024 * 1024)
                if not block:
                    break
                digest.update(block)
        return digest.hexdigest()
    except OSError:
        return ""


def main() -> int:
    print("Scanning MP3 files and artwork...")
    ARTWORK_CACHE.mkdir(exist_ok=True)
    backup_path = backup_database_if_needed()
    if backup_path:
        print(f"SQLite backup          : {backup_path.relative_to(DATA_ROOT)}")

    mp3_files, image_files, diagnostics = scan_files()
    current_paths = {safe_rel(path) for path in mp3_files}
    legacy_items = load_legacy_items(diagnostics)
    exact_index, album_track_index, size_index = build_legacy_indexes(legacy_items)

    images_by_dir: dict[Path, list[Path]] = {}
    for image_file in image_files:
        images_by_dir.setdefault(image_file.parent, []).append(image_file)

    stats: dict[str, int] = {
        "mp3Files": len(mp3_files),
        "loaded": 0,
        "errors": 0,
        "cacheHits": 0,
        "movedFiles": 0,
        "tagTitle": 0,
        "filenameTitle": 0,
        "artworkFound": 0,
        "embeddedArtwork": 0,
        "externalArtwork": 0,
        "legacyInherited": 0,
        "legacyMetadataRepairs": 0,
        "mojibakeRepaired": 0,
        "missingTitleTag": 0,
        "missingArtistTag": 0,
        "missingAlbumTag": 0,
    }

    timestamp = utc_now()
    referenced_embedded_artwork: set[str] = set()
    connection = connect_database()
    scan_run_id = 0
    try:
        initialize_database(connection)
        catalog_backfill_row = connection.execute(
            "SELECT value FROM schema_info WHERE key = 'catalog_sort_tags_backfilled'"
        ).fetchone()
        track_backfill_row = connection.execute(
            "SELECT value FROM schema_info WHERE key = 'track_sort_tags_backfilled'"
        ).fetchone()
        needs_catalog_sort_backfill = (
            not catalog_backfill_row
            or str(catalog_backfill_row["value"]) != "1"
            or not track_backfill_row
            or str(track_backfill_row["value"]) != "1"
        )
        if needs_catalog_sort_backfill:
            print("Catalog sort metadata : one-time ID3 sort-tag refresh")
        scan_run_id = create_scan_run(connection, timestamp)
        connection.commit()

        existing_rows = load_track_rows(connection)
        existing_by_path = {str(row["relative_path"]): row for row in existing_rows}
        missing_signature_rows: dict[str, list[sqlite3.Row]] = {}
        for row in existing_rows:
            old_path = str(row["relative_path"])
            signature = str(row["content_signature"] or "")
            if signature and old_path not in current_paths:
                missing_signature_rows.setdefault(signature, []).append(row)

        connection.execute("UPDATE tracks SET is_available = 0")
        connection.commit()

        for index, path in enumerate(mp3_files, 1):
            relative_path = safe_rel(path)
            try:
                stat = path.stat()
                existing_row = existing_by_path.get(relative_path)

                # SQLite itself is the metadata cache. Unchanged files do not
                # require tag parsing, JSON cache loading, or artwork extraction.
                metadata_unchanged = (
                    existing_row is not None
                    and int(existing_row["file_size"]) == stat.st_size
                    and int(existing_row["modified_time_ns"]) == stat.st_mtime_ns
                )
                artwork_unchanged = True
                if metadata_unchanged and existing_row is not None:
                    cached_artwork = str(existing_row["artwork_relative_path"] or "")
                    cached_source = str(existing_row["artwork_source_type"] or "")
                    if cached_source == "embedded":
                        artwork_unchanged = bool(cached_artwork) and (resolve_virtual_path(cached_artwork) or Path()).is_file()
                    elif cached_source == "external":
                        current_external = find_external_artwork(path, images_by_dir)
                        current_artwork = safe_rel(current_external) if current_external else ""
                        artwork_unchanged = current_artwork == cached_artwork
                    elif not cached_artwork:
                        # A newly added folder image should be picked up even when
                        # the MP3 itself has not changed.
                        artwork_unchanged = find_external_artwork(path, images_by_dir) is None

                if metadata_unchanged and artwork_unchanged and not needs_catalog_sort_backfill:
                    mark_track_seen_without_reparse(
                        connection,
                        track_id=str(existing_row["id"]),
                        timestamp=timestamp,
                    )
                    cached_track = row_to_track(existing_row)
                    if cached_track.get("artworkFile"):
                        stats["artworkFound"] += 1
                        if cached_track.get("artworkSource") == "embedded":
                            stats["embeddedArtwork"] += 1
                            referenced_embedded_artwork.add(str(cached_track["artworkFile"]))
                        else:
                            stats["externalArtwork"] += 1
                    update_stats_from_track(stats, cached_track)
                    stats["cacheHits"] += 1
                    stats["loaded"] += 1
                    if index % 500 == 0:
                        connection.commit()
                        print(f"  {index:,} / {len(mp3_files):,}")
                    continue

                signature = content_signature(path, stat.st_size)
                if existing_row is None:
                    move_candidates = missing_signature_rows.get(signature, [])
                    if len(move_candidates) == 1:
                        existing_row = move_candidates[0]
                        old_path = str(existing_row["relative_path"])
                        connection.execute(
                            "UPDATE tracks SET relative_path = ? WHERE id = ?",
                            (relative_path, str(existing_row["id"])),
                        )
                        existing_by_path.pop(old_path, None)
                        existing_by_path[relative_path] = existing_row
                        missing_signature_rows.pop(signature, None)
                        stats["movedFiles"] += 1
                        diagnostics.append(
                            DiagnosticRow(
                                "info",
                                "mp3_move_detected",
                                relative_path,
                                f"同一MP3を移動として認識しました: {old_path}",
                            )
                        )

                id3, embedded, duration, parser_notes = parse_with_mutagen(path)
                if not id3:
                    fallback_id3, fallback_artwork = parse_id3v2_fallback(path)
                    id3.update(fallback_id3)
                    embedded = embedded or fallback_artwork
                id3v1 = parse_id3v1(path)

                raw_tag_title = id3.get("TIT2", "") or id3v1.get("title", "")
                raw_tag_artist = id3.get("TPE1", "") or id3v1.get("artist", "")
                raw_tag_album_artist = id3.get("TPE2", "")
                raw_tag_album = id3.get("TALB", "") or id3v1.get("album", "")
                raw_tag_title_sort = id3.get("TSOT", "")
                raw_tag_artist_sort = id3.get("TSOP", "")
                raw_tag_album_sort = id3.get("TSOA", "")

                tag_artist, artist_repair_method = repair_mojibake(raw_tag_artist)
                inferred_title, inferred_artist, inferred_track = infer_from_filename(path, tag_artist)
                title, title_source = metadata_value(
                    raw_tag_title, inferred_title.strip() or path.stem, "filename"
                )
                artist, artist_source = metadata_value(
                    raw_tag_artist,
                    inferred_artist.strip(),
                    "filename" if inferred_artist.strip() else "unknown",
                )
                album, album_source = metadata_value(raw_tag_album, path.parent.name, "folder")
                album_artist, album_artist_repair = repair_mojibake(raw_tag_album_artist)
                title_sort, title_sort_repair = repair_mojibake(raw_tag_title_sort)
                artist_sort, artist_sort_repair = repair_mojibake(raw_tag_artist_sort)
                album_sort, album_sort_repair = repair_mojibake(raw_tag_album_sort)
                genre, genre_repair = repair_mojibake(id3.get("TCON", ""))
                composer, composer_repair = repair_mojibake(id3.get("TCOM", ""))

                track_number = parse_number(id3.get("TRCK", "")) or inferred_track
                disc_number = parse_number(id3.get("TPOS", "")) or infer_disc_from_path(path)
                year = parse_number(
                    id3.get("TDRC", "") or id3.get("TYER", "") or id3v1.get("year", "")
                )
                if not duration:
                    duration = detect_audio_duration_ms_fallback(path)

                track_id = str(existing_row["id"]) if existing_row is not None else stable_id(relative_path)
                artwork_relative_path = ""
                artwork_source = ""
                artwork_mime = ""
                artwork_hash = ""
                if embedded:
                    image_data, mime = embedded
                    extension = artwork_extension(mime, image_data)
                    artwork_path = ARTWORK_CACHE / f"{track_id}{extension}"
                    if not artwork_path.exists() or artwork_path.read_bytes() != image_data:
                        artwork_path.write_bytes(image_data)
                    artwork_relative_path = safe_rel(artwork_path)
                    artwork_source = "embedded"
                    artwork_mime = mime
                    artwork_hash = hashlib.sha256(image_data).hexdigest()
                    referenced_embedded_artwork.add(artwork_relative_path)
                else:
                    external = find_external_artwork(path, images_by_dir)
                    if external:
                        artwork_relative_path = safe_rel(external)
                        artwork_source = "external"
                        artwork_hash = artwork_file_hash(external)

                metadata_source = {
                    "title": title_source,
                    "artist": artist_source,
                    "album": album_source,
                }

                track = {
                    "id": track_id,
                    "name": title,
                    "sortTitle": title_sort,
                    "artist": artist,
                    "albumArtist": album_artist,
                    "album": album,
                    "genre": genre,
                    "composer": composer,
                    "year": year,
                    "time": duration,
                    "trackNumber": track_number,
                    "discNumber": disc_number,
                    "playCount": 0,
                    "dateAdded": "",
                    "kind": "MP3オーディオファイル",
                    "size": stat.st_size,
                    "relativePath": relative_path,
                    "audioFile": relative_path,
                    "artworkFile": artwork_relative_path,
                    "artworkSource": artwork_source,
                    "metadataSource": metadata_source,
                }

                # Existing SQLite user data always wins. Legacy JSON is used
                # only for a genuinely new database record.
                if existing_row is None:
                    legacy, match_method = choose_legacy(
                        track, exact_index, album_track_index, size_index
                    )
                    if legacy:
                        for field in ("playCount", "dateAdded"):
                            if legacy.get(field) not in (None, ""):
                                track[field] = legacy[field]
                        track["legacyId"] = legacy.get("id", "")
                        track["legacyMatchMethod"] = match_method
                        stats["legacyInherited"] += 1

                        repaired_fields: list[str] = []
                        for field, legacy_field, source_field in (
                            ("name", "name", "title"),
                            ("artist", "artist", "artist"),
                            ("album", "album", "album"),
                        ):
                            current_value = str(track.get(field) or "")
                            legacy_value = str(legacy.get(legacy_field) or "").strip()
                            if (
                                legacy_value
                                and text_quality(current_value) < 0
                                and text_quality(legacy_value) > text_quality(current_value)
                            ):
                                track[field] = legacy_value
                                metadata_source[source_field] = "legacy_repair"
                                repaired_fields.append(field)
                        if repaired_fields:
                            stats["legacyMetadataRepairs"] += 1
                            diagnostics.append(
                                DiagnosticRow(
                                    "info",
                                    "legacy_metadata_repair",
                                    relative_path,
                                    "文字化けが残ったため旧JSONから補正: " + ", ".join(repaired_fields),
                                )
                            )

                repair_methods = [
                    title_source == "tag_repaired",
                    artist_source == "tag_repaired",
                    album_source == "tag_repaired",
                    bool(album_artist_repair),
                    bool(title_sort_repair),
                    bool(artist_sort_repair),
                    bool(album_sort_repair),
                    bool(genre_repair),
                    bool(composer_repair),
                    bool(artist_repair_method),
                ]
                if any(repair_methods):
                    diagnostics.append(
                        DiagnosticRow(
                            "info",
                            "text_encoding_repaired",
                            relative_path,
                            "MP3タグの文字コードを自動補正しました。",
                        )
                    )

                for note in parser_notes:
                    diagnostics.append(
                        DiagnosticRow("warning", "metadata_parser_note", relative_path, note)
                    )

                artwork_id = upsert_artwork(
                    connection,
                    relative_path=artwork_relative_path,
                    source_type=artwork_source,
                    source_mp3_path=relative_path if artwork_source == "embedded" else "",
                    mime_type=artwork_mime,
                    file_hash=artwork_hash,
                    timestamp=timestamp,
                )
                artist_id = upsert_artist(
                    connection, artist, timestamp, sort_name=artist_sort
                )
                album_id = upsert_album(
                    connection,
                    title=album,
                    album_artist=album_artist,
                    fallback_artist=artist,
                    sort_title=album_sort,
                    year=int(year) if str(year).isdigit() else None,
                    artwork_id=artwork_id,
                    timestamp=timestamp,
                )
                upsert_track(
                    connection,
                    track=track,
                    artist_id=artist_id,
                    album_id=album_id,
                    artwork_id=artwork_id,
                    file_size=stat.st_size,
                    modified_time_ns=stat.st_mtime_ns,
                    content_signature=signature,
                    timestamp=timestamp,
                    existing_row=existing_row,
                )

                if artwork_relative_path:
                    stats["artworkFound"] += 1
                    if artwork_source == "embedded":
                        stats["embeddedArtwork"] += 1
                    else:
                        stats["externalArtwork"] += 1
                update_stats_from_track(stats, track)
                stats["loaded"] += 1

                if index % 250 == 0:
                    connection.commit()
                if index % 500 == 0:
                    print(f"  {index:,} / {len(mp3_files):,}")
            except Exception as exc:
                stats["errors"] += 1
                diagnostic = DiagnosticRow(
                    "error", "mp3_read_error", relative_path, f"{type(exc).__name__}: {exc}"
                )
                diagnostics.append(diagnostic)

                # A temporary tag-reading failure must not make an existing,
                # physically present MP3 disappear from the library. Keep the
                # last successfully stored metadata available and report the
                # error for later inspection.
                fallback_row = existing_by_path.get(relative_path)
                if fallback_row is not None:
                    mark_track_seen_without_reparse(
                        connection,
                        track_id=str(fallback_row["id"]),
                        timestamp=timestamp,
                    )
                    cached_track = row_to_track(fallback_row)
                    if cached_track.get("artworkFile"):
                        stats["artworkFound"] += 1
                        if cached_track.get("artworkSource") == "embedded":
                            stats["embeddedArtwork"] += 1
                            referenced_embedded_artwork.add(str(cached_track["artworkFile"]))
                        else:
                            stats["externalArtwork"] += 1
                    update_stats_from_track(stats, cached_track)
                    stats["loaded"] += 1

        connection.execute(
            "INSERT INTO schema_info(key, value) VALUES('catalog_sort_tags_backfilled', '1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )
        connection.execute(
            "INSERT INTO schema_info(key, value) VALUES('track_sort_tags_backfilled', '1') "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
        )

        # Persist diagnostics and scan summary in the same database.
        for diagnostic in diagnostics:
            add_scan_error(
                connection,
                scan_run_id,
                severity=diagnostic.severity,
                category=diagnostic.category,
                relative_path=diagnostic.path,
                message=diagnostic.message,
            )

        complete_scan_run(
            connection,
            scan_run_id,
            status="completed_with_errors" if stats["errors"] else "completed",
            completed_at=utc_now(),
            stats=stats,
        )
        connection.commit()

        # SQLite API v2.4 reads only the requested page. The browser no longer needs
        # a full JSON export or recursive path indexes at every startup. Remove old
        # generated files left by v1 so they cannot be mistaken for the source.
        for obsolete_path in (OUTPUT_JSON, MP3_INDEX_JSON, ARTWORK_INDEX_JSON):
            try:
                obsolete_path.unlink()
            except FileNotFoundError:
                pass
            except OSError:
                pass

        diagnostic_payload = {
            "database": DATABASE_PATH.name,
            "scanRunId": scan_run_id,
            "scanSummary": stats,
            "diagnostics": [asdict(row) for row in diagnostics],
        }
        write_json(DIAG_JSON, diagnostic_payload)
        with DIAG_CSV.open("w", encoding="utf-8-sig", newline="") as file:
            writer = csv.DictWriter(
                file, fieldnames=["severity", "category", "path", "message"]
            )
            writer.writeheader()
            for row in diagnostics:
                writer.writerow(asdict(row))

        # Remove embedded artwork that is no longer referenced by an available MP3.
        for artwork_path in ARTWORK_CACHE.iterdir():
            if artwork_path.is_file() and safe_rel(artwork_path) not in referenced_embedded_artwork:
                try:
                    artwork_path.unlink()
                except OSError:
                    pass

    except Exception:
        if scan_run_id:
            try:
                complete_scan_run(
                    connection,
                    scan_run_id,
                    status="failed",
                    completed_at=utc_now(),
                    stats=stats,
                )
                connection.commit()
            except Exception:
                connection.rollback()
        raise
    finally:
        connection.close()

    print()
    print(f"SQLite database        : {DATABASE_PATH.name}")
    print(f"MP3 files              : {stats['mp3Files']:,}")
    print(f"Library records        : {stats['loaded']:,}")
    print(f"Errors                 : {stats['errors']:,}")
    print(f"Artwork                : {stats['artworkFound']:,}")
    print(f"Encoding repairs       : {stats['mojibakeRepaired']:,}")
    print(f"Legacy inherited       : {stats['legacyInherited']:,}")
    print(f"Legacy metadata repair : {stats['legacyMetadataRepairs']:,}")
    print(f"SQLite cache hits      : {stats['cacheHits']:,}")
    print(f"Moves detected         : {stats['movedFiles']:,}")
    print("Library generation completed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Cancelled.")
        raise SystemExit(130)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)
