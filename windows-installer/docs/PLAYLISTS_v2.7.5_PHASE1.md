# v2.7.5 工程1：利用者別プレイリスト

## 目的

お気に入りとは別に、利用者が任意の名前と曲順を持つ曲リストを作れるようにする。
プレイリストは利用者ごとに分離し、別利用者からは参照・変更できない。

## 工程1の実装範囲

- プレイリストの作成、名称変更、削除
- 曲の追加、削除、並べ替え
- プレイリスト内の全曲連続再生
- 前へ、次へ、シャッフル、1曲／全曲リピートとの連携
- 曲カードからプレイリストを選んで追加
- プレイリスト画面とホーム画面導線
- PC・スマートフォン向けレスポンシブ表示
- 利用者別のアクセス制御

## データベース

DBスキーマを6から7へ更新する。

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

同じ利用者は同名のプレイリストを重複作成できない。
同じ曲は同じプレイリストへ重複追加できない。
プレイリスト削除は管理情報だけを削除し、MP3や曲レコードを削除しない。

スキーマ6の実運用DBを更新する前には、
`library-pre-v2.7.5-*.db`を自動作成する。

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

すべて現在の認証利用者を基準に処理する。
他利用者のプレイリストIDを指定しても内容を返さない。

## 工程1プレビューの安全性

- インストール済みサーバーが動作中の場合は安全のため開始しない
- 実運用DBをSQLiteバックアップAPIで複製
- 複製DBだけをスキーマ7へ更新
- サーバーは127.0.0.1の一時ポートで起動
- MP3は読み取り・再生だけ
- Service Workerとホーム画面追加はプレビューモードで無効
- 終了後に実運用DBのSHA-256が変わっていないことを確認

## 工程1では行わないこと

- 実運用DBへのプレイリスト保存
- v2.7.5インストーラー作成
- mainへの統合
- GitHub Release作成
- プレイリストの共有・共同編集
- M3Uなど外部形式の入出力
