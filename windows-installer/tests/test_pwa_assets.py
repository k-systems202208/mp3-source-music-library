from __future__ import annotations

import json
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def png_dimensions(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise AssertionError(f"Not a PNG file: {path}")
    if data[12:16] != b"IHDR":
        raise AssertionError(f"PNG IHDR was not found: {path}")
    return struct.unpack(">II", data[16:24])


manifest_path = SRC / "manifest.webmanifest"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
assert manifest["name"] == "自宅音楽ライブラリ"
assert manifest["short_name"] == "音楽ライブラリ"
assert manifest["display"] == "standalone"
assert manifest["start_url"].startswith("./music-library-search.html")
assert manifest["scope"] == "./"
assert manifest["background_color"] == "#efe8d8"
assert manifest["theme_color"] == "#24392b"

expected_icons = {
    "./pwa-icons/icon-192.png": (192, 192, "any"),
    "./pwa-icons/icon-512.png": (512, 512, "any"),
    "./pwa-icons/icon-maskable-512.png": (512, 512, "maskable"),
}
actual_icons = {item["src"]: item for item in manifest["icons"]}
assert set(actual_icons) == set(expected_icons)
for relative, (width, height, purpose) in expected_icons.items():
    item = actual_icons[relative]
    assert item["type"] == "image/png"
    assert item["purpose"] == purpose
    path = SRC / relative.removeprefix("./")
    assert path.is_file(), relative
    assert png_dimensions(path) == (width, height)

assert png_dimensions(SRC / "pwa-icons/icon-180.png") == (180, 180)
assert png_dimensions(SRC / "pwa-icons/icon-32.png") == (32, 32)
assert (SRC / "favicon.ico").is_file()

worker = (SRC / "service-worker.js").read_text(encoding="utf-8")
for required in (
    "music-library-shell-v2.7.7",
    "self.addEventListener('install'",
    "self.addEventListener('activate'",
    "self.addEventListener('fetch'",
    "request.mode === 'navigate'",
    "./offline.html",
):
    assert required in worker, required
for excluded in ("/api/", "/music/", "/.artwork-cache/", "/backups/", "mp3", "sqlite"):
    assert excluded in worker.lower(), excluded
assert "cache.put(request" in worker
assert "isPrivateOrMediaRequest(url)" in worker

offline = (SRC / "offline.html").read_text(encoding="utf-8")
for required in (
    "自宅音楽ライブラリへ接続できません",
    "Wi-FiまたはTailscale",
    "オフラインでは再生できません",
    "viewport-fit=cover",
    "env(safe-area-inset-bottom)",
):
    assert required in offline, required

print("PWA manifest, icon, service-worker and offline asset tests passed.")
