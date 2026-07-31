# GitHub公開ガイド

## 1. 公開対象

- ソースコード
- HTML／CSS／JavaScript
- 空のサンプル音楽フォルダ
- ビルド定義
- インストーラー定義
- テスト
- READMEと設計文書
- 第三者ライセンス通知
- Release Notes
- 完成したインストーラーと検証用ハッシュ

## 2. 公開禁止

- MP3、FLAC、AAC等の音源
- 実運用`library.db`、WAL、SHM
- `.artwork-cache`
- `Backups`、`Exports`、`Logs`
- `config.json`、`remote-url.txt`
- 診断JSON／CSV
- 実際の利用者名、メール、Tailscaleログイン、プロフィールURL
- IP、端末名、tailnet名が分かる画像
- 関連付けコード、Cookie、制御秘密
- 個人用ビルドパスを含むログ

## 3. v2.7.0 Release Assets

推奨:

- `MusicLibrary-Setup-2.7.0-x64.exe`
- SHA-256ファイル
- Release Notes
- ソースZIP（GitHub自動生成を利用可能）
- 必要に応じてビルドレポート

公開済みタグの内容を後から書き換えません。文書修正だけの場合は`main`へ追加コミットし、次の製品リリースへ取り込みます。重大な配布物修正が必要なら新バージョンを発行します。

## 4. 公開前チェック

```text
[ ] git statusに意図しないファイルがない
[ ] git diff --checkが成功
[ ] READMEの製品バージョンが2.7.0
[ ] DBスキーマが5
[ ] 「利用者別状態は未実装」等の旧記述がない
[ ] 音源・DB・診断・個人情報がない
[ ] 第三者ライセンス通知がある
[ ] 全回帰テストPASS
[ ] バンドル済みEXEスモークPASS
[ ] Inno SetupコンパイルPASS
[ ] SHA-256を記録
[ ] 実機の上書き・移行・Tailscale・関連付けPASS
```

## 5. スクリーンショット

- ダミー曲名・ダミーアートワークを使用
- 利用者名は「オーナー」「家族A」等へ置換
- 関連付けコードを写さない
- メール、Tailscaleログイン名、プロフィール画像を写さない
- 外部URLのホスト名を隠す

## 6. 文書更新

READMEだけでなく、API、DB、利用マニュアル、セキュリティ、テスト、変更履歴を同時に更新します。旧仕様を歴史として残す場合はバージョン見出しの下へ記載します。

## 7. コミット例

```text
docs: update documentation for v2.7.0
```

文書だけの更新では既存の`v2.7.0`タグを移動しません。
