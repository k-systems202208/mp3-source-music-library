from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "music-library-search.html"


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    required = [
        ".home-panel{\n    width:100%;\n    min-width:0;\n    max-width:100%;",
        "grid-template-columns:minmax(0,1fr);",
        "#homeSections{\n    width:100%;\n    min-width:0;\n    max-width:100%;\n    overflow:hidden;",
        ".home-section{\n    width:100%;\n    min-width:0;\n    max-width:100%;\n    overflow:hidden;",
        ".home-track-row{\n    display:flex;",
        "overflow-x:auto;",
        "flex:0 0 clamp(178px,23%,218px);",
        ".home-track-card{flex-basis:min(72vw,218px);}",
    ]
    for token in required:
        assert token in html, token
    assert "grid-auto-flow:column;" not in html
    assert "grid-auto-columns:minmax(178px,218px);" not in html
    print("Library home layout contract tests passed.")


if __name__ == "__main__":
    main()
