from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "src" / "music-library-search.html"


def main() -> None:
    html = HTML.read_text(encoding="utf-8")
    required = [
        '<html lang="ja" data-skin="library">',
        'id="skinSection"',
        'id="skinGrid"',
        'id="skinApplyButton"',
        'id="skinCancelButton"',
        'id="skinPreviewRibbon"',
        'data-skin-option="library"',
        'data-skin-option="midnight"',
        'data-skin-option="neon"',
        'data-skin-option="cyberpunk"',
        'data-skin-option="candy"',
        'data-skin-option="monochrome"',
        "const CURRENT_USER_SKIN_API_URL = './api/me/skin';",
        'const SKIN_OPTIONS = Object.freeze',
        'function normalizeSkinId(value)',
        'function applySkinPreview(skinId',
        'async function commitSkinPreview()',
        "method:'PUT'",
        'body:JSON.stringify({skinId:requestedSkinId})',
        'currentUser.skinId = committedSkinId;',
        "committedSkinId = authenticated",
        'normalizeSkinId(currentUser.skinId)',
        'document.documentElement.dataset.skin = previewSkinId;',
        'els.skinSection.hidden = !authenticated;',
        'まだ保存されていません。',
        'スキンを保存できませんでした。変更前の表示に戻しました。',
        '@media (max-width:600px)',
        '@media (prefers-reduced-motion:reduce)',
        'filter:grayscale(1) saturate(0) contrast(1.08);',
        'html[data-skin="monochrome"] .player-modal-artwork',
    ]
    for token in required:
        assert token in html, token

    forbidden = [
        'const SKIN_PREVIEW_OPTIONS',
        "new URLSearchParams(window.location.search).get('skinPreview')",
        '工程1ではデザイン確認のみのため、DBには保存しません。',
        '適用する（プレビュー）',
        'data-skin-option="record"',
        'html[data-skin="record"]',
        'music-library-skin',
    ]
    for token in forbidden:
        assert token not in html, token

    print("Skin persistence UI contract tests passed.")


if __name__ == "__main__":
    main()
