# v2.7.5 利用者別プレイリスト

## 目的

お気に入りとは別に、利用者が任意の名前と曲順を持つ曲リストを作成し、続けて再生できるようにします。

プレイリストは認証利用者ごとに分離し、別利用者からは参照・変更できません。

## 機能

- プレイリストの作成
- 名称変更
- プレイリスト削除
- 曲の追加
- 同じ曲の重複追加防止
- 曲の削除
- 曲順変更
- 全曲再生
- 前へ・次へ・シャッフル・1曲／全曲リピート
- PC・スマートフォン向けレスポンシブ表示

## データベース

DBスキーマを6から7へ更新します。

```text
playlists
  id
  user_id
  name
  normalized_name
  created_at
  updated_at

playlist_tracks
  playlist_id
  track_id
  position
  added_at
```

同じ利用者は同名のプレイリストを重複作成できません。
同じ曲は同じプレイリストへ重複追加できません。
プレイリスト削除は管理情報だけを削除し、MP3や曲レコードを削除しません。

スキーマ6のDBを更新する前に、次を自動作成します。

```text
Backups\library-pre-v2.7.5-*.db
```

## API

```text
GET    /api/playlists
POST   /api/playlists
GET    /api/playlists/{playlistId}
PUT    /api/playlists/{playlistId}
DELETE /api/playlists/{playlistId}
POST   /api/playlists/{playlistId}/tracks
DELETE /api/playlists/{playlistId}/tracks/{trackId}
PUT    /api/playlists/{playlistId}/tracks/order
```

すべて現在の認証利用者を基準に処理します。
他利用者のプレイリストIDを指定しても内容を返しません。

## バックアップ・復元

スキーマ7の`playlists`と`playlist_tracks`は、通常のSQLiteバックアップ・復元に含まれます。

復元先DBが現在のアプリより新しいスキーマの場合は、従来どおり安全のため拒否します。

## 既存機能との関係

- お気に入りとは独立した機能
- プレイリスト再生でも利用者別再生回数・履歴を更新
- 曲カードの通常再生、お気に入り、アートワーク表示を維持
- 長いパスの曲も通常の曲IDを使って登録・再生
- スマートフォンのホーム画面から同じ利用者のプレイリストへアクセス
