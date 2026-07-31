# APIリファレンス

ベースURL例:

```text
http://127.0.0.1:8765
```

レスポンスはUTF-8 JSONです。APIとHTMLは`Cache-Control: no-store`です。

## 認証表記

- **公開**: 匿名でも使用可能
- **利用者**: ローカルオーナーCookieまたはTailscale利用者が必要
- **オーナー**: ローカル／Tailscaleのオーナー
- **ローカルオーナー**: 管理画面から開いた自宅PCだけ
- **Tailscale利用者**: Tailscale Serveの利用者ヘッダー必須

## GET API

### `GET /api/health`

権限: 公開

```json
{"ok":true,"database":"library.db"}
```

### `GET /api/current-user`

権限: 公開

```json
{
  "authenticated": true,
  "id": "usr_...",
  "displayName": "オーナー",
  "isOwner": true,
  "provider": "local_owner"
}
```

匿名では`authenticated=false`、`id=null`です。

### `GET /api/browse`

権限: 公開。利用者が識別されていれば個人状態を付加。

主なクエリ:

| 名前 | 内容 |
|---|---|
| `view` | `songs`、`artists`、`artist_albums`、`albums`、`artist_tracks`、`album_tracks` |
| `q` | 検索文字列 |
| `limit` | 1～200、既定80 |
| `offset` | 0以上 |
| `sort` | 表示順 |
| `latinOnly` | 英数字タイトルのみ |
| `correctedOnly` | 補正済みのみ |
| `favoriteOnly` | 現在の利用者のお気に入りのみ |
| `artistKey` | アーティスト文脈 |
| `albumKey` | アーティスト内アルバム文脈 |
| `albumTitle` | 全体アルバム文脈 |
| `indexKey` | 索引キー |

### `GET /api/tracks`

権限: 公開。利用者が識別されていれば個人状態を付加。

利用可能な全曲を返す互換APIです。通常UIは`/api/browse`を使用します。

### `GET /api/stats`

権限: 公開

主な項目:

```json
{
  "database":"library.db",
  "schemaVersion":5,
  "totalRows":8280,
  "availableTracks":8279,
  "unavailableTracks":1,
  "artworkTracks":7507,
  "totalPlays":42,
  "favoriteTracks":3,
  "latestScan":{}
}
```

`totalPlays`と`favoriteTracks`は現在の利用者単位です。匿名では0です。

### `GET /api/users`

権限: オーナー

現在の閲覧者と利用者一覧を返します。

### `GET /api/owner-link/status?code=...`

権限: ローカルオーナー

関連付けチャレンジの状態と候補を返します。

### `GET /api/local-auth/exchange?token=...`

権限: 有効な一時トークン

一時トークンをローカルオーナーCookieへ交換し、`303`でUIへリダイレクトします。通常はランチャーが生成するURLから使用し、手動で呼び出しません。

## POST API

### `POST /api/local-auth/token`

権限: ランチャー制御秘密

ヘッダー:

```text
X-Music-Library-Control-Secret: <launcher-secret>
```

本文:

```json
{"token":"...","expiresInSeconds":60}
```

成功: `201 Created`

### `POST /api/tracks/{trackId}/played`

権限: 公開。匿名では`200 OK`のまま`recorded=false`を返し、個人状態を作成しません。停止中・不正な利用者IDでは`403`です。

成功例:

```json
{"id":"trk_...","playCount":4,"lastPlayedAt":"...","recorded":true}
```

### `POST /api/tracks/{trackId}/favorite`

権限: 利用者

```json
{"favorite":true}
```

サーバー側トグルではなく、希望状態を明示します。

### `POST /api/tracks/{trackId}/title-correction`

権限: 現行実装では公開

```json
{"value":"正式な曲名"}
```

`null`または空文字で解除します。

### `POST /api/artists/{artistId}/correction`

権限: 現行実装では公開

```json
{"value":"正式なアーティスト名"}
```

### `POST /api/users/{userId}/active`

権限: ローカルオーナー

```json
{"active":false}
```

オーナー自身は無効化できません。

### `POST /api/owner-link/start`

権限: ローカルオーナー

```json
{"expiresInSeconds":300}
```

成功例:

```json
{"code":"...","expiresInSeconds":300,"status":"waiting_for_tailscale"}
```

### `POST /api/owner-link/claim`

権限: Tailscale利用者

```json
{"code":"..."}
```

候補の個人状態をプレビューし、ローカル側の承認待ちにします。

### `POST /api/owner-link/confirm`

権限: ローカルオーナー

```json
{
  "code":"...",
  "userId":"usr_...",
  "subject":"tailscale-login"
}
```

候補を再照合し、バックアップ作成、状態統合、識別情報移動を実行します。

### `POST /api/owner-link/cancel`

権限: ローカルオーナー

```json
{"code":"..."}
```

## メディア配信

MP3はRange要求を受け付けます。

```http
Range: bytes=1000000-
```

部分応答:

```http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes ...
```

## 代表的なHTTP状態

| 状態 | 用途 |
|---|---|
| `200` | 成功 |
| `201` | トークン、関連付けコード等の作成 |
| `303` | ローカルオーナーCookie交換後のリダイレクト |
| `400` | JSON、型、クエリ不正 |
| `401` | 利用者識別が必要 |
| `403` | オーナー／ローカルオーナー／Tailscale権限不足 |
| `404` | 曲、利用者、コード、APIなし |
| `409` | オーナー停止、候補競合、評価競合等 |
| `410` | 関連付けコード期限切れ |
| `500` | DB・走査・内部処理エラー |
