# v2.7.0 DBスキーマ5移行仕様

## 目的

v2.6.3以前の共通再生状態を失わず、利用者別状態へ移行します。

## 追加テーブル

- `users`
- `user_identities`
- `user_track_state`

## 事前バックアップ

```text
Backups/library-pre-v2.7.0-YYYYMMDD-HHMMSS.db
```

バックアップをSQLiteとして開けること、integrity check、曲件数一致を確認します。失敗時は移行しません。

## 移行

1. schema 5テーブル・索引を作成
2. オーナーが存在しなければ作成
3. `local_owner/local-owner`識別情報を作成
4. `tracks`の再生回数・最終再生日時・お気に入り・評価をオーナーの`user_track_state`へコピー
5. 件数・値一致を検査
6. オーナーが1人であることを検査
7. `PRAGMA foreign_key_check`
8. schema versionを5へ更新

処理は一つのトランザクションで行い、失敗時はロールバックします。

## 互換列

`tracks.play_count`、`last_played_at`、`favorite`、`rating`は旧版移行互換のため残します。v2.7.0の利用者状態の正本は`user_track_state`です。
