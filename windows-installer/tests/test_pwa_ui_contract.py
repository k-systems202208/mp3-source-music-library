from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
html = (ROOT / "src" / "music-library-search.html").read_text(encoding="utf-8")

for required in (
    'name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover"',
    'name="theme-color" id="pwaThemeColor"',
    'name="apple-mobile-web-app-capable" content="yes"',
    'name="apple-mobile-web-app-title" content="音楽ライブラリ"',
    'rel="manifest" href="./manifest.webmanifest"',
    'rel="apple-touch-icon" sizes="180x180"',
    'id="appStartup"',
    'id="pwaInstallSection"',
    'id="pwaConnectionStatus"',
    'id="pwaSecureStatus"',
    'id="pwaDisplayStatus"',
    'id="pwaCurrentUrl"',
    'id="pwaCopyUrlButton"',
    'id="pwaInstallButton"',
    'id="pwaWorkerStatus"',
    "beforeinstallprompt",
    "appinstalled",
    "navigator.standalone",
    "(display-mode: standalone)",
    "navigator.serviceWorker.register('./service-worker.js'",
    "window.isSecureContext",
    "接続の種類",
    "通信方式",
    "Tailscale経由",
    "自宅PC内のローカル接続",
    "HTTP（このPC内のみ）",
    "HTTPS",
    "Tailscale接続用URL",
    "Safari下部の共有ボタン",
    "アプリをインストール",
    "PWA_PREVIEW_MODE",
):
    assert required in html, required

# The preview must not install a PWA that points to an ephemeral test port.
assert "if (PWA_PREVIEW_MODE)" in html
assert "プレビュー（未登録）" in html
assert "ホーム画面へは追加しないでください" in html

# Theme color must follow the selected skin.
for skin, color in (
    ("library", "#24392b"),
    ("midnight", "#101c2e"),
    ("neon", "#041219"),
    ("cyberpunk", "#16131d"),
    ("candy", "#ff4f9a"),
    ("monochrome", "#111111"),
):
    assert f"{skin}:'{color}'" in html
assert "updatePwaThemeColor(previewSkinId)" in html

# localhost is a secure browser context for PWA APIs, but it must never be mislabeled as HTTPS.
assert "HTTPS／localhost" not in html
assert "const protocol = location.protocol.toLowerCase();" in html
assert "localOrigin && protocol === 'http:'" in html

print("PWA install guidance and UI contract tests passed.")
