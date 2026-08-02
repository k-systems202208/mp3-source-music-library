# 自宅音楽ライブラリ v2.7.3

手元のMP3を音源の正本として、タグ、アートワーク、検索情報、利用者別の再生状態をSQLiteで管理し、Windows PC・スマートフォン・タブレットのブラウザから検索・再生する個人／家庭向け音楽ライブラリです。

> 製品バージョン：2.7.3
> DBスキーマ：6
> 対応OS：Windows 10／11 64bit
> 更新日：2026-08-02

## v2.7.3の主な内容

TailscaleのHTTPS接続先をスマートフォンのホーム画面へ追加し、専用アイコンからアプリのように起動できるPWA対応を追加しました。

- iPhone・iPad・Android向けアプリアイコン
- アプリ名「自宅音楽ライブラリ」、短縮名「音楽ライブラリ」
- ホーム画面からのstandalone起動
- 起動中画面と通信不能時の案内
- 利用者メニューのホーム画面追加手順
- 接続先URLの表示・コピー
- ローカル接続とTailscale HTTPSの表示区別
- safe-area、タップ領域、縦横表示の調整
- 6種類のスキンに応じたテーマ色

Service Workerが保存するのは画面表示に必要な静的資産だけです。MP3、API応答、DB、バックアップ、アートワーク、認証情報はキャッシュしません。

## インストールまたは更新

1. 自宅音楽ライブラリを終了します。
2. `MusicLibrary-Setup-2.7.3-x64.exe`を実行します。
3. v2.7.2以前が入っていても、アンインストールせず上書きします。
4. スタートメニューから「自宅音楽ライブラリ」を起動します。

利用者データとMP3はインストール先とは別に保持されます。

```text
%LOCALAPPDATA%\MusicLibrary
```

## スマートフォンのホーム画面へ追加

外出先でも利用する場合は、普段使うTailscale HTTPS URLをスマートフォンで開いてから追加します。

```text
https://PC名.tailnet名.ts.net/music-library-search.html
```

- iPhone・iPad：Safariの共有ボタン → ホーム画面に追加
- Android：ブラウザメニュー → アプリをインストール、またはホーム画面に追加

追加後は「音楽ライブラリ」の専用アイコンから起動し、ブラウザのアドレスバーを表示しないstandalone画面で利用できます。

## 主な機能

- MP3・ID3タグ・アートワークの読込み
- ライブラリホーム
- 曲名・アーティスト・アルバム検索
- ブラウザ再生、シーク、シャッフル、リピート
- 利用者別の再生回数・最終再生日時・お気に入り
- 6種類の利用者別スキン
- バックアップ・復元
- GitHub Releaseを利用した新版通知
- Tailscale Serve経由の外部利用
- ローカルオーナーと本人Tailscaleプロフィールの関連付け
- スマートフォンのホーム画面追加とPWA起動

## PWAの安全設計

キャッシュ対象：

- メインHTML
- Web App Manifest
- アプリアイコン
- 通信不能時の案内画面

キャッシュ対象外：

- API応答
- MP3などの音楽ファイル
- SQLite DBとバックアップ
- アートワーク
- Tailscale・利用者の認証情報

オフライン再生には対応していません。自宅PCとTailscaleまたはWi-Fiへ接続できる状態が必要です。

## ビルド

短いパスへソースを配置し、`00_build_installer.bat`を実行します。

```text
C:\ML273Build
```

成功すると`release`フォルダーに次を作成します。

- `MusicLibrary-Setup-2.7.3-x64.exe`
- `MusicLibrary-Setup-2.7.3-x64_SHA256.txt`
- ビルドログ
- ビルド報告

## ドキュメント

| 文書 | 内容 |
|---|---|
| `RELEASE_NOTES_v2.7.3.md` | v2.7.3の変更内容 |
| `docs/DOCUMENT_INDEX_v2.7.3.md` | v2.7.3関連文書の一覧 |
| `docs/README_USER.txt` | 利用者向けガイド |
| `docs/INSTALL_INFO.txt` | インストール前の確認事項 |
| `docs/README_BUILD.txt` | インストーラー作成手順 |
| `docs/MOBILE_HOME_v2.7.3.md` | PWA・ホーム画面追加の正式仕様 |
| `docs/RELEASE_SCOPE_v2.7.3.md` | 正式リリース対象範囲 |
| `docs/MANUAL_TEST_v2.7.3.txt` | 実機確認項目と結果 |
| `docs/REMOTE_ACCESS_USER.txt` | Tailscale外部接続ガイド |
| `docs/REMOTE_ACCESS_FAMILY.txt` | 家族向け接続案内 |

工程別・RC別の既存文書は、実装履歴として残しています。

## GitHubへ公開しないもの

- MP3・音源ファイル
- `library.db`、WAL、SHM
- `.artwork-cache`
- `Backups`、`Exports`、`Logs`
- `config.json`、`remote-url.txt`
- 実際のTailscale利用者情報
- トークン、秘密鍵、Cookie、関連付けコード

## 制限

- 対象音源はMP3です
- スマートフォンへの音楽オフライン保存は行いません
- App Store・Google Playでは配布しません
- 公開インターネットへ直接ポートを開ける運用は対象外です
- 自宅PCが停止またはスリープ中は外部接続できません
- Windowsサービスとしての常駐には対応していません
