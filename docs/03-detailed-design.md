# 詳細設計

## `paths.py`

アプリ名、バージョン、データ保存先、DB、ログ、バックアップ、静的資産のパスを一元管理します。現行`APP_VERSION`は`2.7.6`です。

## `launcher.py`

- Windows GUIを表示
- 音楽ルートを設定
- generatorとserverを起動
- 空きポートを決定
- ローカルオーナー用ワンタイムトークンを登録
- 認証交換URLをブラウザで開く
- Tailscale導入・Serve設定を案内
- 終了処理とプロセス監視を行う

## `generator.py`

- MP3と外部画像を走査
- ファイル更新情報と内容署名でキャッシュ判定
- MutagenでID3・音声情報・埋め込み画像を取得
- アーティスト、アルバム、曲を正規化
- 移動・改名時に既存曲IDを引き継ぐ
- 取得不能ファイルを`scan_errors`へ記録
- 診断JSON／CSVを生成

## `long_paths.py`

Windowsのローカル絶対パスを`\\?\C:\...`、UNCパスを`\\?\UNC\server\share\...`へ変換します。変換はWindowsのファイルI/O境界だけで使用し、DBの`relative_path`、API、画面には露出しません。

対象:

- ディレクトリー走査
- `stat`、存在確認
- ファイル読み込み・シーク
- Mutagen解析
- アートワーク読み込み
- 内容署名
- MP3 Range配信

## `database.py`

- `SCHEMA_VERSION = 7`
- スキーマ作成と段階移行
- アーティスト、アルバム、曲のupsert
- 利用者・識別・個人状態
- スキン
- プレイリスト・曲順
- ホーム、検索、統計
- 走査履歴・エラー
- 移行前バックアップ検証

### プレイリストの不変条件

- 名前は利用者内で一意
- 同じ曲は同じプレイリストへ1回だけ
- 位置はプレイリスト内で一意
- 所有者以外の取得・変更・削除は不可
- 曲を外すと位置を詰める
- プレイリスト削除は`ON DELETE CASCADE`で中間行だけを削除
- 曲レコードとMP3は保持

## `server.py`

- 静的UI、manifest、Service Worker、offlineページを配信
- JSON APIを提供
- ローカルオーナーCookieとTailscale利用者を解決
- APIごとの権限を検査
- MP3とアートワークを安全なルート配下から配信
- HTTP Rangeを処理
- API・HTMLへ`no-store`を設定
- DB・設定・ソースなど禁止資産を拒否

## 起動時認証引き渡し

`/api/local-auth/exchange`はワンタイムトークンを消費し、セッションCookieを発行します。Windows版Chromeで本文なし303が読み込み中のまま残るケースに対応するため、v2.7.4以降は次を備えた小さなHTMLを返します。

- `location.replace`
- meta refresh
- 手動リンク
- 500ms後の予備遷移
- `Connection: close`
- トークンを本文へ含めない
- CSPと`X-Frame-Options: DENY`

## `identity.py`

Tailscale利用者情報を解析し、制御文字、重複値、不正URL等を拒否します。利用者の安定識別には表示名ではなくprovider内subjectを使用します。

## `local_auth.py`

- ランチャーとサーバー間のcontrol secret
- 短時間・1回限りのトークン
- 12時間のローカルオーナーセッション
- `HttpOnly; SameSite=Strict` Cookie

## `owner_link.py`

ローカルオーナーが開始し、Tailscale本人が要求し、ローカルオーナーが確認するチャレンジ方式です。統合時は再生回数を合算、最終再生日時は新しい方、お気に入りはORとし、矛盾する評価は安全のため中止します。

## `backup_restore.py`

- SQLite quick check
- schema 5、6、7の受入
- ファイル名と保存場所の検証
- バックアップ一覧・作成
- 復元要求の予約と取消
- 次回起動時の安全な置換

## `update_check.py`

`CURRENT_VERSION = 2.7.6`としてGitHub Releases APIを確認します。公開済みReleaseとプレリリースを比較し、現在版より新しい場合だけ通知します。通信失敗はライブラリ機能へ影響させません。

## `music-library-search.html`

単一ページUIとしてホーム、曲名、アーティスト、アルバム、プレイリスト、プレーヤー、利用者管理、スキン、バックアップ、新版通知、PWA案内を提供します。

## `service-worker.js`

画面シェルとアイコンだけをキャッシュします。次を明示的に除外します。

- `/api/`
- MP3・音楽配信
- DB・設定・バックアップ
- アートワーク
- 認証交換
- 個人データ

## エラー処理

- 入力不正: 400
- 未認証: 401
- 権限不足: 403
- 対象なし: 404
- 競合: 409
- 予期しない障害: 500
- ブラウザ切断: 期待される切断として静かに処理
