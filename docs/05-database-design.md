# データベース設計書

## 基本情報

| 項目 | 内容 |
|---|---|
| ファイル | `%LOCALAPPDATA%\MusicLibrary\library.db` |
| エンジン | SQLite |
| 現行スキーマ | 7 |
| 外部キー | 有効 |
| 更新方式 | トランザクション |
| バックアップ | `%LOCALAPPDATA%\MusicLibrary\Backups` |

## テーブル一覧

| テーブル | 用途 |
|---|---|
| `schema_info` | schema番号、移行情報 |
| `artists` | アーティストと表示補正 |
| `albums` | アルバム、年、アートワーク |
| `artworks` | 埋め込み／外部画像の索引 |
| `tracks` | MP3メタデータ、相対パス、存在状態、補正 |
| `users` | 利用者、オーナー、有効状態 |
| `user_identities` | ローカル／Tailscale識別 |
| `user_track_state` | 利用者別再生状態 |
| `user_preferences` | 利用者別スキン |
| `playlists` | 利用者別プレイリスト |
| `playlist_tracks` | プレイリストの曲と順序 |
| `scan_runs` | 走査集計 |
| `scan_errors` | 走査エラー |

## 主要テーブル

### `tracks`

`relative_path`は音楽ルートからの通常形式の相対パスです。Windows長パス用`\\?\`表現は保存しません。

主な列:

- `title`、`artist_id`、`album_id`、`composer`、`genre`
- `duration_ms`、`track_number`、`disc_number`
- `file_size`、`modified_time_ns`、`content_signature`
- `audio_file`、`artwork_id`
- `title_override`、`artist_override`、`album_override`
- `is_available`、`last_scanned_at`
- 旧共通状態列（互換・移行用）

### `users`

- `id`
- `display_name`
- `is_owner`
- `is_active`
- 作成・更新・最終確認日時

部分ユニーク索引でオーナーは最大1人です。

### `user_identities`

`UNIQUE(provider, subject)`で同じ外部識別を複数利用者へ割り当てません。

代表provider:

- `local_owner`
- `tailscale`

### `user_track_state`

複合主キーは`(user_id, track_id)`です。

- `favorite`
- `rating`
- `play_count`
- `last_played_at`
- 作成・更新日時

表示・更新の正本はこのテーブルです。`tracks`の共通状態列は互換目的で残します。

### `user_preferences`

利用者1人につき1行です。`skin_id`は次のいずれかです。

```text
library, midnight, neon, cyberpunk, candy, monochrome
```

### `playlists`

| 列 | 内容 |
|---|---|
| `id` | プレイリスト内部ID |
| `user_id` | 所有者 |
| `name` | 表示名 |
| `normalized_name` | 利用者内重複判定 |
| `created_at`／`updated_at` | 日時 |

`UNIQUE(user_id, normalized_name)`により利用者内の同名を防止します。

### `playlist_tracks`

| 列 | 内容 |
|---|---|
| `playlist_id` | プレイリスト |
| `track_id` | 曲 |
| `position` | 0以上の順序 |
| `added_at` | 追加日時 |

制約:

- 主キー`(playlist_id, track_id)`で同じ曲の重複を防止
- `UNIQUE(playlist_id, position)`で順序を一意化
- プレイリスト削除時は中間行をcascade削除
- 曲削除はrestrictし、プレイリストからMP3を消さない

## スキーマ移行

### v2.7.0／schema 5

利用者、識別、利用者別状態を追加し、旧共通状態をオーナーへ移行しました。

### v2.7.2／schema 6

`user_preferences`を追加しました。

### v2.7.5／schema 7

`playlists`と`playlist_tracks`を追加しました。スキーマ6からの移行前に次を自動作成します。

```text
Backups\library-pre-v2.7.5-YYYYMMDD-HHMMSS.db
```

処理:

1. 現行DBのschemaと整合性を確認
2. SQLiteバックアップAPIで移行前バックアップ作成
3. バックアップのschema・件数・quick checkを確認
4. 新規テーブル・索引をトランザクション内で作成
5. `schema_version=7`を保存
6. 外部キーを確認してコミット
7. 失敗時はロールバック

## バックアップ・復元

バックアップとして受け入れるschemaは5、6、7です。復元前にSQLite整合性、schema、ファイル名、保存先を確認します。復元は起動中の接続へ直接上書きせず、次回起動時に適用します。

## 削除方針

- プレイリスト削除: プレイリストと中間行だけ
- プレイリストから曲を外す: 中間行だけ
- 利用者削除: 現行UIでは完全削除せず停止・再開
- MP3消失: 曲を`is_available=0`として履歴を保持
- MP3の再出現・移動: 署名等で既存ID維持を試行
