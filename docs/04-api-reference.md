# APIリファレンス

ベースURL例:

```text
http://127.0.0.1:8765
```

レスポンスはUTF-8 JSONです。API、HTML、JSONは原則`Cache-Control: no-store`です。

## 権限表記

| 表記 | 意味 |
|---|---|
| 公開 | 匿名でも利用可能 |
| 利用者 | ローカルオーナーまたは有効なTailscale利用者 |
| オーナー | `isOwner=true`の利用者 |
| ローカルオーナー | 管理画面から認証した自宅PCだけ |
| ランチャー | control secretを持つローカルプロセス |

## GET

| パス | 権限 | 内容 |
|---|---|---|
| `/api/health` | 公開 | サーバーとDB名 |
| `/api/current-user` | 公開 | 現在の利用者、匿名状態、スキン |
| `/api/home` | 公開 | ホーム統計と利用者別セクション |
| `/api/browse` | 公開 | 曲・アーティスト・アルバム検索 |
| `/api/tracks` | 公開 | 利用可能曲の互換一覧 |
| `/api/stats` | 公開 | DB、schema、曲数、利用者別統計 |
| `/api/users` | オーナー | 利用者管理一覧 |
| `/api/backups` | ローカルオーナー | バックアップと復元状態 |
| `/api/update-status` | オーナー | 現在版・最新版・確認状態 |
| `/api/playlists` | 利用者 | 自分のプレイリスト一覧 |
| `/api/playlists/{id}` | 利用者 | 自分のプレイリスト詳細と曲 |
| `/api/owner-link/status?code=...` | ローカルオーナー | 関連付け状態 |
| `/api/local-auth/exchange?token=...` | 一時トークン | Cookie発行とUI遷移 |

### `/api/browse`の主なクエリ

| 名前 | 内容 |
|---|---|
| `view` | `songs`、`artists`、`artist_albums`、`albums`、`artist_tracks`、`album_tracks` |
| `q` | 検索文字列 |
| `limit` | 1～200、既定80 |
| `offset` | 0以上 |
| `sort` | 表示順 |
| `latinOnly` | 英数字タイトルのみ |
| `correctedOnly` | 補正済みのみ |
| `favoriteOnly` | 現在利用者のお気に入りのみ |
| `artistKey` | アーティスト文脈 |
| `albumKey` | アーティスト内アルバム文脈 |
| `albumTitle` | 全体アルバム文脈 |
| `indexKey` | 索引キー |

### `/api/home`

現在利用者に応じて、最近再生、お気に入り、よく聴く曲、最近追加した曲と統計を返します。匿名では個人セクションを空または0として返します。

### `/api/stats`の代表例

```json
{
  "database": "library.db",
  "schemaVersion": 7,
  "availableTracks": 8480,
  "artworkTracks": 7708,
  "totalPlays": 270,
  "favoriteTracks": 4,
  "latestScan": {}
}
```

数値は利用環境で変わります。`totalPlays`と`favoriteTracks`は現在利用者単位です。

## POST

| パス | 権限 | 内容 |
|---|---|---|
| `/api/local-auth/token` | ランチャー | ワンタイムトークン登録 |
| `/api/tracks/{id}/played` | 利用者 | 再生回数・最終再生更新 |
| `/api/tracks/{id}/favorite` | 利用者 | お気に入り更新 |
| `/api/tracks/{id}/title-correction` | オーナー | 曲名表示補正 |
| `/api/artists/{id}/correction` | オーナー | アーティスト表示補正 |
| `/api/users/{id}/active` | ローカルオーナー | 利用者停止・再開 |
| `/api/me/skin` | 利用者 | スキン保存 |
| `/api/backups/create` | ローカルオーナー | DBバックアップ作成 |
| `/api/backups/restore` | ローカルオーナー | 次回起動時の復元予約 |
| `/api/backups/restore/cancel` | ローカルオーナー | 復元予約取消 |
| `/api/playlists` | 利用者 | プレイリスト作成 |
| `/api/playlists/{id}/tracks` | 利用者 | 曲追加 |
| `/api/playlists/{id}/tracks/order` | 利用者 | 曲順更新 |
| `/api/owner-link/start` | ローカルオーナー | 関連付け開始 |
| `/api/owner-link/claim` | Tailscale利用者 | コード申請 |
| `/api/owner-link/confirm` | ローカルオーナー | 統合確認 |
| `/api/owner-link/cancel` | ローカルオーナー | 取消 |

## PATCH／DELETE

| メソッド・パス | 権限 | 内容 |
|---|---|---|
| `PATCH /api/playlists/{id}` | 利用者 | 自分のプレイリスト名変更 |
| `DELETE /api/playlists/{id}` | 利用者 | 自分のプレイリスト削除 |
| `DELETE /api/playlists/{id}/tracks/{trackId}` | 利用者 | 曲を外す |

## プレイリストのエラー

- 未認証: `401`
- 他利用者のIDまたは存在しないID: 情報漏えいを避けて`404`
- 同名または同一曲の重複: `409`
- 不正な名前、空配列、重複した曲順: `400`

## 音楽・アートワーク配信

UIが返すURLからMP3と画像を取得します。MP3は`Range`を受け付け、`206 Partial Content`、`Content-Range`、`Accept-Ranges: bytes`を返します。DBや任意のローカルパスは配信しません。

## キャッシュとセキュリティ

- API: `no-store`
- 認証Cookie: `HttpOnly; SameSite=Strict`
- 認証交換: CSP、`X-Frame-Options: DENY`、明示的接続終了
- 静的ファイル: 許可リストとルート配下検証
- PWA: API、音楽、DB、バックアップ、アートワークをキャッシュしない
