from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "music-library-search.html"


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    checks = [
        ".skin-grid{\n    display:grid;\n    grid-template-columns:repeat(2,minmax(0,1fr));",
        ".skin-card{\n    min-width:0;",
        ".skin-card-scene{\n    height:86px;",
        ".skin-grid{grid-template-columns:1fr;}",
        "html[data-skin=\"midnight\"]",
        "html[data-skin=\"neon\"]",
        "html[data-skin=\"cyberpunk\"]",
        "html[data-skin=\"candy\"]",
        "html[data-skin=\"monochrome\"]",
        ".home-track-artwork img{\n    filter:grayscale(1) saturate(0) contrast(1.08);",
    ]
    for token in checks:
        assert token in html, token
    assert 'html[data-skin="record"]' not in html
    print("Skin preview layout contract tests passed.")


if __name__ == "__main__":
    main()
