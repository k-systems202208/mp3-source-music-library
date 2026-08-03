# GitHub公開ガイド

## 前提

- ブランチは`main`
- 作業ツリーがclean
- `origin/main`と同期
- ソース、インストーラー、文書の版が一致
- 全試験合格
- 実機受入完了
- 秘密情報・個人パスを除外

## 文書更新

正式公開前に少なくとも次を確認します。

- ルート`README.md`
- `UPDATE_SUMMARY.md`
- `docs/00-document-index.md`
- 仕様、API、DB、利用、運用、試験、変更履歴
- `windows-installer/README.md`
- `RELEASE_NOTES_vX.Y.Z.md`
- Windows配布文書
- 文書内ローカルリンク
- 末尾空白とEOF
- `git diff --check`

RC／Phase文書は履歴として保持し、正式仕様へ後書きで改変しません。

## ビルド

短いパスへ`windows-installer`を置きます。

```text
C:\ML275Build
```

`00_build_installer.bat`を実行し、次を確認します。

- 全ソース回帰試験
- PyInstaller
- EXEスモーク試験
- Inno Setup
- バージョン整合性
- SHA-256
- BUILD LOG／REPORT

## タグ・Release

v2.7.5の例:

```text
tag: v2.7.5
title: 自宅音楽ライブラリ v2.7.5
```

Release本文は正式なRelease Notesを使用します。Draft／pre-releaseで作成し、人が内容・添付を確認してから公開する運用を採用できます。

## 代表的なRelease Assets

- `MusicLibrary-Setup-2.7.5-x64.exe`
- `SHA256SUMS.txt`
- `README_USER.txt`
- `REMOTE_ACCESS_USER.txt`
- `REMOTE_ACCESS_FAMILY.txt`
- `RELEASE_NOTES_v2.7.5.md`

## 公開後確認

- Release URLが`/releases/tag/v2.7.5`
- タグとReleaseが一致
- Assetsをダウンロード可能
- Setup.exeのSHA-256一致
- READMEの最新版リンク・版表記
- アプリの新版通知

v2.7.5は2026-08-03に公開完了したことをユーザーが確認しています。本監査ではRelease画面や新版通知の追加取得は行っていません。

## 既公開タグの扱い

文書だけを後から修正する場合:

- `main`へ文書コミットを追加
- 公開済みタグを移動しない
- Release Assetsを暗黙に差し替えない
- Release本文の訂正が必要なら変更理由を残す
- ソース版と配布版の歴史を保持する
