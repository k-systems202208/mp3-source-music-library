from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "src" / "music-library-search.html").read_text(encoding="utf-8")
worker = (ROOT / "src" / "service-worker.js").read_text(encoding="utf-8")

# The copied-database Phase 1 notice must never ship in the installed app.
for forbidden in (
    "v2.7.5 機能プレビュー",
    "複製DBでプレイリスト機能を確認しています",
    'id="playlistFeaturePreviewBanner"',
    "PLAYLIST_FEATURE_PREVIEW_MODE",
):
    assert forbidden not in html, forbidden

# A stale saved preview URL is normalized without dropping the PWA source flag.
assert "startupUrl.searchParams.has('playlistPreview')" in html
assert "startupUrl.searchParams.delete('playlistPreview')" in html
assert "history.replaceState" in html

# Five mobile tabs remain on one line instead of splitting Japanese labels.
view_tab_block = html.split(".view-tab{", 1)[1].split("}", 1)[0]
for required in (
    "white-space:nowrap",
    "word-break:keep-all",
    "overflow-wrap:normal",
):
    assert required in view_tab_block, required

# Invalidate the RC1 PWA shell so iPhone/Android receives the corrected HTML.
assert "music-library-shell-v2.7.7" in worker

print("Production playlist banner removal, PWA cache refresh and mobile tab tests passed.")
