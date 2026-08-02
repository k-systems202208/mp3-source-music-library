from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "music-library-search.html"


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    required = [
        "background:var(--home-stat-bg,rgba(250,246,236,.72));",
        "border:1px solid var(--home-stat-border,var(--line));",
        "color:var(--home-stat-value,var(--ink));",
        "color:var(--home-stat-label,var(--ink-faint));",
        "--home-stat-shadow:",
        'html[data-skin="candy"] .home-stat:nth-child(1)',
        'html[data-skin="candy"] .home-stat:nth-child(2)',
        'html[data-skin="candy"] .home-stat:nth-child(3)',
        'html[data-skin="candy"] .home-stat:nth-child(4)',
        'html[data-skin="monochrome"] .home-stat:nth-child(even)',
        'html[data-skin="monochrome"] .home-stat:nth-child(odd)',
    ]
    for token in required:
        assert token in html, token
    base_stat = html.split(".home-stat{", 1)[1].split("}", 1)[0]
    assert "background:rgba(250,246,236,.72);" not in base_stat
    for skin in ("midnight", "neon", "cyberpunk", "candy", "monochrome"):
        blocks = re.findall(rf'html\[data-skin="{skin}"\]\{{(.*?)\n  \}}', html, flags=re.S)
        block = next((item for item in blocks if "--home-stat-bg:" in item), "")
        assert "--home-stat-bg:" in block, skin
        assert "--home-stat-border:" in block, skin
        assert "--home-stat-value:" in block, skin
        assert "--home-stat-label:" in block, skin
    print("Skin home-stat styling tests passed.")


if __name__ == "__main__":
    main()
