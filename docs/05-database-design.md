# データベース設計書

## 1. 基本情報

| 項目 | 内容 |
|---|---|
| ファイル | `%LOCALAPPDATA%\MusicLibrary\library.db` |
| エンジン | SQLite |
| 現行スキーマ | 5 |
| 外部キー | 有効 |
| 更新方式 | トランザクション |

## 2. テーブル一覧

| テーブル | 用途 |
|---|---|
| `schema_info` | schemaバージョン、オーナーID、移行完了フラグ |
| `artists` | アーティスト正規化・表示補正 |
| `albums` | アルバム正規化・年・アートワーク |
| `artworks` | 埋め込み／外部画像の索引 |
| `tracks` | MP3メタデータ、存在、旧共通状態、補正 |
| `users` | 利用者プロフィール、オーナー、有効状態 |
| `user_identities` | ローカル／Tailscale識別情報 |
| `user_track_state` | 利用者別状態 |
| `scan_runs` | 走査単位の集計 |
| `scan_errors` | 走査エラー |

## 3. `users`

| 列 | 内容 |
|---|---|
| `id` | `usr_...`形式の内部ID |
| `display_name` | UI表示名 |
| `is_owner` | 0／1。部分ユニーク索引で1人だけ |
| `is_active` | 停止・再開 |
| `created_at`／`updated_at` | UTC ISO日時 |
| `last_seen_at` | 最終識別日時 |

`idx_users_single_owner`により`is_owner=1`は最大1行です。

## 4. `user_identities`

| 列 | 内容 |
|---|---|
| `id` | 安定キー |
| `user_id` | `users.id` |
| `provider` | `local_owner`または`tailscale` |
| `subject` | provider内の安定識別子 |
| `provider_display_name` | providerから得た表示用情報 |
| `profile_picture_url` | 検証済みURL |
| `created_at`／`last_seen_at` | 監査用日時 |

`UNIQUE(provider, subject)`により同じTailscaleログインを複数利用者へ割り当てません。

ローカルオーナー識別:

```text
provider = local_owner
subject  = local-owner
```

## 5. `user_track_state`

複合主キーは`(user_id, track_id)`です。

| 列 | 内容 |
|---|---|
| `favorite` | 0／1 |
| `rating` | NULLまたは0～5 |
| `play_count` | 0以上 |
| `last_played_at` | UTC ISO日時または空 |
| `created_at`／`updated_at` | 状態作成・更新日時 |

索引:

- `(user_id, play_count DESC)`
- `(user_id, last_played_at DESC)`
- `(user_id, favorite)`

状態がすべて空の場合は行を削除し、疎なテーブルとして維持します。

## 6. `tracks`の旧共通状態

`tracks`には互換性とschema 5移行のため、`play_count`、`last_played_at`、`favorite`、`rating`が残っています。v2.7.0の利用者別表示・更新の正本は`user_track_state`です。

これら旧列を安易に削除すると旧版DBの移行や互換処理へ影響するため、将来のschema変更で明示的に扱います。

## 7. schema 5移行

### 事前条件

- DBがアプリより新しいschemaでない
- 未処理トランザクションがない
- 移行前バックアップを作成・検証できる

### 処理

1. 新規テーブル・索引を作成
2. 既存開発版向けの加算的列移行
3. オーナーが0人なら作成、2人以上なら中止
4. ローカルオーナー識別情報を作成・照合
5. `tracks`の旧共通状態をオーナーの`user_track_state`へコピー
6. 件数と全項目の一致を検査
7. `PRAGMA foreign_key_check`
8. `schema_version=5`を保存
9. コミット

失敗時はロールバックします。

### バックアップ名

```text
Backups\library-pre-v2.7.0-YYYYMMDD-HHMMSS.db
```

## 8. オーナー関連付け時の統合

### 事前検査

- 候補利用者が存在・有効
- 対象Tailscale識別情報が候補に属する
- 候補の識別情報が想定件数
- 日時を解釈可能
- 評価競合がない

### 統合

| 状態 | 結果 |
|---|---|
| オーナー側だけ | 維持 |
| 候補側だけ | オーナーへ移動 |
| 両側の再生回数 | 合算 |
| 両側の最終再生日時 | 新しい方 |
| 両側のお気に入り | OR |
| 評価片側のみ | 設定済み側 |
| 評価同値 | 維持 |
| 評価異値 | 全処理中止 |

識別情報移動、候補プロフィール削除、外部キー検査まで同じトランザクションで行います。

バックアップ名:

```text
Backups\library-pre-owner-link-YYYYMMDD-HHMMSS.db
```

## 9. 通常バックアップ

起動時に同日のバックアップがなければ作成します。

```text
Backups\library-YYYYMMDD.db
```

バックアップはSQLiteとして開けること、整合性検査が通ること、元DBと曲件数が一致することを確認します。

## 10. 削除方針

- MP3削除・不在: `tracks.is_available=0`
- 利用者停止: `users.is_active=0`
- 利用者完全削除: UIでは提供しない
- オーナー: 削除・停止不可
- オーナー統合後の空候補プロフィール: 関連付けトランザクション内で削除
