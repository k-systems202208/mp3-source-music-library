# 自宅音楽ライブラリ v2.7.5

手元のMP3を音源の正本として、タグ、アートワーク、検索情報、利用者別状態とプレイリストをSQLiteで管理し、Windows PC・スマートフォン・タブレットから検索・再生する個人／家庭向け音楽ライブラリです。

> 製品バージョン: 2.7.5
> DBスキーマ: 7
> 対応OS: Windows 10／11 64bit
> 公開日: 2026-08-03
> 文書監査日: 2026-08-03

## v2.7.5

- 利用者別プレイリスト
- 作成、名称変更、削除
- 曲追加、重複防止、曲順変更、曲除外
- 全曲再生とプレーヤー連携
- DBスキーマ7
- `library-pre-v2.7.5-*.db`の移行前バックアップ
- スキーマ7のバックアップ・復元
- スマートフォン5タブの1行表示
- 本番PWAからプレビュー表示を除去

## v2.7.4までの主な機能

- 8,480曲の実機ライブラリで確認
- Windows長パス201曲、最大364文字、エラー0
- 起動時オーナー認証の安定化
- PWA・ホーム画面追加
- 利用者別スキン
- ライブラリホーム
- バックアップ・復元
- 新版通知
- 利用者別再生履歴・お気に入り
- Tailscale Serve

数値は確認環境の実績であり、固定上限ではありません。

## インストール・更新

初めて設定する場合は、[オーナー導入・家族共有ガイド](../docs/19-owner-setup-guide.md)にダウンロード、インストール、初回設定、Tailscale、家族招待をまとめています。

1. 自宅音楽ライブラリを終了
2. `MusicLibrary-Setup-2.7.5-x64.exe`を実行
3. 旧版をアンインストールせず上書き
4. スタートメニューから起動

データ保存先:

```text
%LOCALAPPDATA%\MusicLibrary
```

schema 6から7への移行前バックアップ:

```text
%LOCALAPPDATA%\MusicLibrary\Backups\library-pre-v2.7.5-*.db
```

## プレイリスト

1. 「プレイリスト」タブで作成
2. 曲カードの「＋」から追加
3. プレイリスト画面で曲順、再生、名称、削除を操作

プレイリストから曲を外したり削除しても、MP3と通常の曲一覧は削除しません。プレイリストは認証済み利用者ごとに分離します。

## スマートフォン

TailscaleのHTTPS URLをSafariまたは対応ブラウザで開き、ホーム画面へ追加します。PWAは画面シェルだけをキャッシュし、MP3、API、DB、バックアップ、アートワーク、認証情報を端末へ保存しません。

## ビルド

短いパスへ配置します。

```text
C:\ML275Build
```

`00_build_installer.bat`を実行します。成功すると`release`へSetup、SHA-256、BUILD LOG、BUILD REPORTを作成します。

## 文書

- [オーナー導入・家族共有ガイド](../docs/19-owner-setup-guide.md)
- `RELEASE_NOTES_v2.7.5.md`
- `docs/DOCUMENT_INDEX_v2.7.5.md`
- `docs/README_USER.txt`
- `docs/README_BUILD.txt`
- `docs/MANUAL_TEST_v2.7.5.txt`
- `docs/DOCUMENTATION_AUDIT_v2.7.5.md`

過去バージョン、RC、Phase文書は履歴資料として保持します。
