# アーキテクチャ

## 構成要素

| 要素 | 役割 |
|---|---|
| `launcher.py` | Windows管理画面、サーバー起動、ブラウザ起動、Tailscale案内 |
| `generator.py` | MP3走査、タグ解析、アートワーク、差分更新 |
| `long_paths.py` | Windows長パスの内部表現変換 |
| `database.py` | スキーマ作成・移行、検索、利用者状態、プレイリスト |
| `server.py` | HTTP配信、API、認証、Range配信 |
| `local_auth.py` | ローカルオーナー一時トークンとCookie |
| `identity.py` | Tailscale利用者の解析 |
| `owner_link.py` | ローカルオーナーと本人Tailscaleプロフィールの関連付け |
| `backup_restore.py` | DB検証、バックアップ、次回起動時復元 |
| `update_check.py` | GitHub Release確認 |
| `music-library-search.html` | ブラウザUI |
| `service-worker.js` | PWAシェルキャッシュ |
| `library.db` | SQLite schema 7 |
| `.artwork-cache` | 埋め込み画像の展開キャッシュ |

## データ境界

- MP3と外部画像は利用者が選択した音楽フォルダーに残る
- DB、設定、ログ、バックアップ、展開画像は`%LOCALAPPDATA%\MusicLibrary`に置く
- インストール先には実行ファイルと静的資産を置く
- PWAは画面シェルだけをキャッシュし、個人データを保持しない

## 接続経路

### ローカル

管理画面が短時間の一時トークンを発行し、ブラウザが`/api/local-auth/exchange`でCookieへ交換します。交換後は安全なHTML引き渡しでライブラリ画面へ遷移します。

### Tailscale

サーバーはlocalhostへバインドし、Tailscale ServeがHTTPSを終端して利用者情報を付与します。信頼条件を満たす場合だけ利用者ヘッダーを採用します。

### 匿名

識別情報がない接続は検索・再生に限定します。再生回数、お気に入り、スキン、プレイリストは保存しません。

## スキャン処理

1. 音楽ルートを再帰走査
2. Windows長パスをファイルI/O用に変換
3. ファイルサイズ、更新時刻、内容署名を確認
4. ID3、音声情報、アートワークを解析
5. 既存キャッシュまたは移動検出を利用
6. トランザクションでDBを更新
7. `scan_runs`と`scan_errors`へ結果を記録
8. 診断JSON／CSVを生成

DBには通常形式の相対パスを保存し、`\\?\`形式は保存しません。

## 再生処理

ブラウザは曲IDでサーバーへ要求します。サーバーはDBから相対パスを取得し、音楽ルート配下であることを確認してからファイルを開き、`Range`に応じて`206 Partial Content`を返します。再エンコードは行いません。

## スキーマ移行

スキーマ6から7では、移行前バックアップを作成・検証後、`playlists`と`playlist_tracks`を追加します。失敗時はロールバックし、スキーマ番号を更新しません。

## 信頼境界

- ブラウザ入力はすべて未信頼
- プレイリストID・曲IDだけで所有権を信頼しない
- Tailscaleヘッダーは接続条件を満たす場合だけ信頼
- ローカルオーナー用秘密はブラウザへ恒久保存しない
- 静的配信は許可リスト方式
