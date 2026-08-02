from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "src" / "music-library-search.html").read_text(encoding="utf-8")

for required in (
    "env(safe-area-inset-top)",
    "env(safe-area-inset-bottom)",
    "min-height:44px",
    "touch-action:manipulation",
    "position:sticky",
    "top:env(safe-area-inset-top)",
    "font-size:16px",
    ".pwa-status-grid{grid-template-columns:1fr;}",
    ".pwa-url-box{grid-template-columns:1fr;}",
    "html.pwa-standalone .player-bar",
    "html.pwa-standalone .user-panel",
):
    assert required in html, required

# Page-wide horizontal overflow must not be introduced by fixed pixel widths.
pwa_css_match = re.search(
    r"/\* ---- v2\.7\.3 Phase 1: smartphone home-screen / PWA preview ---- \*/(.*?)::selection",
    html,
    re.S,
)
assert pwa_css_match, "PWA CSS block was not found"
pwa_css = pwa_css_match.group(1)
assert "width:100vw" not in pwa_css
assert "min-width:600px" not in pwa_css

print("PWA smartphone responsive-layout contract tests passed.")
