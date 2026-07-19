# APIリファレンス

## 1. 共通

ローカル例:

```text
http://127.0.0.1:54321
```

LAN例:

```text
http://192.168.1.25:8765
```

Tailscale Serve例:

```text
https://music-server.example.ts.net
```

JSONはUTF-8、APIは`Cache-Control: no-store`です。

## 2. `GET /api/health`

```json
{
  "ok": true,
  "database": "library.db"
}
```

## 3. `GET /api/stats`

```json
{
  "database": "library.db",
  "schemaVersion": 4,
  "totalRows": 8383,
  "availableTracks": 8265,
  "unavailableTracks": 118,
  "artworkTracks": 6120,
  "totalPlays": 12345,
  "latestScan": {
    "id": 42,
    "started_at": "2026-07-19T09:00:00+09:00",
    "completed_at": "2026-07-19T09:01:20+09:00",
    "status": "completed",
    "mp3_files": 8265,
    "loaded": 8265,
    "errors": 0,
    "cache_hits": 8250
  }
}
```

## 4. `GET /api/browse`

### 共通クエリ

| パラメーター | 型 | 既定 | 内容 |
|---|---:|---:|---|
| view | string | songs | 表示種別 |
| q | string | 空 | 検索文字 |
| limit | integer | 80 | 1～200 |
| offset | integer | 0 | 0以上 |
| sort | string | title | 表示順 |
| latinOnly | boolean | false | 英数字曲名のみ |
| correctedOnly | boolean | false | 補正済みのみ |
| artistKey | string | 空 | アーティストID |
| albumKey | string | 空 | アルバムID |
| albumTitle | string | 空 | 全体アルバム表示名 |
| indexKey | string | 空 | 頭文字 |

booleanは`1`、`true`、`yes`、`on`をtrueとして扱います。

### view

| view | 必須条件 | 応答kind |
|---|---|---|
| songs | なし | tracks |
| artists | なし | artists |
| artist_albums | artistKey | artist_albums |
| artist_tracks | artistKey、albumKey | tracks |
| albums | なし | albums |
| album_tracks | albumTitle | tracks |

### sort

| 値 | 内容 |
|---|---|
| title | 曲名順 |
| artist | アーティスト順 |
| album | アルバム順 |
| plays | 再生回数降順 |
| added | 追加日降順 |
| album_order | ディスク・トラック番号順 |

### indexKey

```text
0-9
A ～ Z
あ か さ た な は ま や ら わ
他
```

### 要求例

```text
GET /api/browse?view=songs&q=night&limit=80&offset=0&sort=title&indexKey=N
```

### 曲一覧応答例

```json
{
  "kind": "tracks",
  "items": [
    {
      "id": "mp3_0123456789abcdef0123",
      "name": "Night Song",
      "originalName": "Night Song",
      "isCorrected": false,
      "artist": "Example Artist",
      "originalArtist": "Example Artist",
      "artistDbId": "artist_...",
      "isArtistCorrected": false,
      "albumArtist": "",
      "album": "Example Album",
      "originalAlbum": "Example Album",
      "genre": "Rock",
      "composer": "",
      "year": 2020,
      "time": 240000,
      "trackNumber": 1,
      "discNumber": 1,
      "playCount": 10,
      "dateAdded": "2026-07-18T12:00:00+09:00",
      "lastPlayedAt": "",
      "favorite": false,
      "rating": "",
      "kind": "MP3オーディオファイル",
      "size": 9600000,
      "relativePath": "Music/Artist/Album/01 - Night Song.mp3",
      "audioFile": "Music/Artist/Album/01 - Night Song.mp3",
      "artworkFile": ".artwork-cache/mp3_....jpg",
      "artworkSource": "embedded",
      "metadataSource": {
        "title": "tag",
        "artist": "tag",
        "album": "tag"
      }
    }
  ],
  "total": 123,
  "trackTotal": 123,
  "totalDurationMs": 29520000,
  "offset": 0,
  "limit": 80,
  "hasMore": true,
  "indexKey": "N",
  "indexCounts": {
    "0-9": 1,
    "A": 2,
    "N": 123,
    "他": 4
  }
}
```

### アーティスト項目

```json
{
  "key": "artist_...",
  "display": "The Example",
  "originalArtist": "The Example",
  "indexKey": "E",
  "count": 25,
  "albumCount": 3,
  "isCorrected": false
}
```

### 全体アルバム項目

```json
{
  "key": "Album Title",
  "display": "Album Title",
  "indexKey": "A",
  "count": 12,
  "artists": ["Artist A", "Artist B"],
  "artworkFile": "Music/Artist/Album/folder.jpg"
}
```

## 5. `GET /api/tracks`

利用可能な全曲を返す互換用APIです。v2.4通常画面では使用しません。外部実装は`/api/browse`を使ってください。

## 6. `POST /api/tracks/{trackId}/played`

本文不要。

```json
{
  "id": "mp3_...",
  "playCount": 11
}
```

対象なしはHTTP 404です。

## 7. `POST /api/tracks/{trackId}/title-correction`

本文:

```json
{
  "value": "補正後の曲名"
}
```

`null`、空文字、元と同じ値で解除します。

応答:

```json
{
  "id": "mp3_...",
  "name": "補正後の曲名",
  "originalName": "元のタグ曲名",
  "isCorrected": true
}
```

## 8. `POST /api/artists/{artistId}/correction`

本文:

```json
{
  "value": "補正後のアーティスト名"
}
```

応答:

```json
{
  "artistId": "artist_...",
  "artist": "補正後のアーティスト名",
  "originalArtist": "元のタグ名",
  "isCorrected": true,
  "updatedTracks": 42
}
```

## 9. POST制限

- JSONオブジェクト
- UTF-8
- Content-Length最大64KiB
- `value`はstringまたはnull

## 10. エラー

```json
{
  "error": "エラー内容"
}
```

| HTTP | 意味 |
|---:|---|
| 400 | パラメーター・JSON不正 |
| 404 | API・曲・アーティストなし |
| 500 | SQLite・内部処理エラー |

## 11. MP3・画像配信

```text
/Music/Artist/Album/Song.mp3
/.artwork-cache/mp3_xxx.jpg
```

MP3は単一Rangeに対応します。

```http
Range: bytes=1000000-
```

```http
HTTP/1.1 206 Partial Content
Accept-Ranges: bytes
Content-Range: bytes 1000000-9999999/10000000
```

## 12. 非公開静的パス

404対象:

- DB
- Python
- BAT
- Backups
- Exports
- legacy-library-data.json
