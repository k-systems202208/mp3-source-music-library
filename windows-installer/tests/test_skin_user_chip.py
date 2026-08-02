from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "music-library-search.html"


def rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) == 3:
        value = "".join(ch * 2 for ch in value)
    assert len(value) == 6, value
    return tuple(int(value[index:index + 2], 16) for index in (0, 2, 4))


def luminance(value: str) -> float:
    channels = []
    for channel in rgb(value):
        component = channel / 255
        channels.append(component / 12.92 if component <= 0.04045 else ((component + 0.055) / 1.055) ** 2.4)
    return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]


def contrast(foreground: str, background: str) -> float:
    a, b = luminance(foreground), luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)


def theme_block(html: str, skin: str) -> str:
    matches = re.findall(rf'html\[data-skin="{re.escape(skin)}"\]\{{(.*?)\n  \}}', html, flags=re.S)
    block = next((item for item in matches if "--user-chip-bg" in item), "")
    assert block, skin
    return block


def variable(block: str, name: str) -> str:
    match = re.search(rf'{re.escape(name)}\s*:\s*(#[0-9a-fA-F]{{3,6}})', block)
    assert match, name
    return match.group(1)


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    required = [
        "background:var(--user-chip-bg,rgba(239,232,216,.08));",
        "border:1px solid var(--user-chip-border,rgba(239,232,216,.34));",
        "color:var(--user-chip-text,var(--paper));",
        "box-shadow:var(--user-chip-shadow,none);",
        "background:var(--user-chip-hover-bg,rgba(239,232,216,.14));",
        "color:var(--user-chip-hover-text,var(--user-chip-text,var(--paper)));",
        "var(--user-chip-dot-ring,rgba(239,232,216,.12))",
    ]
    for token in required:
        assert token in html, token

    chip_block = html.split(".user-chip{", 1)[1].split("}", 1)[0]
    assert "color:var(--paper);" not in chip_block

    for skin in ("midnight", "neon", "cyberpunk", "candy", "monochrome"):
        block = theme_block(html, skin)
        background = variable(block, "--user-chip-bg")
        text = variable(block, "--user-chip-text")
        hover_background = variable(block, "--user-chip-hover-bg")
        hover_text = variable(block, "--user-chip-hover-text")
        assert contrast(text, background) >= 4.5, (skin, text, background, contrast(text, background))
        assert contrast(hover_text, hover_background) >= 4.5, (skin, hover_text, hover_background, contrast(hover_text, hover_background))

    print("Skin current-user chip contrast tests passed.")


if __name__ == "__main__":
    main()
