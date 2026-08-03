# 利用者別プレイリスト v2.7.5

## 目的

認証済み利用者が、自分だけの曲リストを任意の順序で保存し、続けて再生できるようにします。

## DB

### `playlists`

- `id`
- `user_id`
- `name`
- `normalized_name`
- `created_at`
- `updated_at`
- `UNIQUE(user_id, normalized_name)`

### `playlist_tracks`

- `playlist_id`
- `track_id`
- `position`
- `added_at`
- 主キー`(playlist_id, track_id)`
- `UNIQUE(playlist_id, position)`

## 所有権

すべての取得・変更・削除で、現在利用者の`id`と`playlists.user_id`を照合します。他利用者のIDを指定しても詳細を返しません。

匿名接続ではプレイリストAPIを使用できません。

## 操作

- 一覧
- 詳細
- 作成
- 名称変更
- 削除
- 曲追加
- 曲除外
- 曲順更新
- 全曲再生

## 不変条件

- 利用者内で同名を防止
- 同じ曲の二重追加を防止
- 曲順は0以上で一意
- 並び替えでは対象曲集合を維持
- 削除後は順序を詰める
- 利用不能曲は表示・再生時に安全に扱う
- プレイリスト削除でMP3やtrackを削除しない

## API

- `GET /api/playlists`
- `POST /api/playlists`
- `GET /api/playlists/{id}`
- `PATCH /api/playlists/{id}`
- `DELETE /api/playlists/{id}`
- `POST /api/playlists/{id}/tracks`
- `DELETE /api/playlists/{id}/tracks/{trackId}`
- `POST /api/playlists/{id}/tracks/order`

## UI

- 上部プレイリストタブ
- 新規作成
- 自分のプレイリスト一覧
- 詳細と曲数・合計時間
- 曲カードの「＋」
- 個別再生
- 曲順上下
- 曲除外
- 全曲再生
- 名称変更・削除

## 移行

schema 6から7への移行前に`library-pre-v2.7.5-*.db`を作成します。新規テーブルは既存利用者・曲IDへ外部キーで接続し、既存状態を変更しません。

## バックアップ

schema 7のDBバックアップにはプレイリストと曲順が含まれます。復元時も所有者IDと曲IDを含めて戻します。

## 実機

iPhoneで「RC1確認」1件・3曲を作成し、RC2上書き後も名前、曲、曲順が維持されました。
