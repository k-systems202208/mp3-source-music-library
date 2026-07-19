# アプリ詳細設計書

## 1. モジュール構成

| ファイル | 責務 |
|---|---|
| `start-music-library.bat` | 環境確認、スキャン実行、空きポート取得、ブラウザ起動 |
| `generate-library.py` | MP3・画像走査、タグ解析、補完、移行、DB同期、診断 |
| `database.py` | スキーマ、マイグレーション、CRUD、検索・集計、バックアップ |
| `serve-library.py` | HTTP API、静的配信、Byte Range、公開禁止制御 |
| `music-library-search.html` | UI、ページング、検索状態、プレーヤー、補正 |
| `library-maintenance.py` | stats、check、backup、vacuum、export |
| `legacy-library-data.json` | 初回移行用補助データ |
| `vendor/mutagen` | ID3・MPEG解析 |


## 1.1 前身から引き継いだUI設計

現行の`music-library-search.html`は、iTunes XMLを単一HTMLで検索していた前身のUIを継承しています。

- カード目録モチーフ
- 曲・アーティスト・アルバムの3ビュー
- パンくず
- アルバム・アーティストのクリック遷移
- 英数字タイトルのみ
- 訂正済みのみ
- 曲名・アーティスト補正
- Google検索による確認

前身では検索・補正をJavaScriptとlocalStorageで処理しました。現行では同じ操作概念を維持し、検索はSQLite API、補正はSQLiteへ移しています。

## 2. 起動処理

`start-music-library.bat`は次を行います。

1. 作業ディレクトリをBAT配置先へ変更
2. UTF-8関連環境変数を設定
3. HTML、generator、serverの存在確認
4. `py -3`を優先し、なければ`python`を確認
5. `generate-library.py`を同期実行
6. 失敗時はサーバーを開始しない
7. Loopback上の空きポートをPowerShellで取得
8. ブラウザを遅延起動
9. `serve-library.py --host 127.0.0.1`を実行

## 3. ファイル走査

### 対象

- 音声: `.mp3`
- 画像: `.jpg`、`.jpeg`、`.png`、`.webp`、`.gif`

`os.walk`を使用し、シンボリックリンクは追跡しません。相対パスは`/`区切りに正規化します。走査結果はcasefold順に並べ、処理順を安定させます。

## 4. ID3解析

### Mutagenで読むフレーム

| フレーム | 内容 |
|---|---|
| TIT2 | 曲名 |
| TPE1 | アーティスト |
| TPE2 | アルバムアーティスト |
| TALB | アルバム |
| TCON | ジャンル |
| TCOM | 作曲者 |
| TRCK | トラック番号 |
| TPOS | ディスク番号 |
| TDRC／TYER | 年 |
| TSOT | 曲名の並べ替え・読み |
| TSOP | アーティストの並べ替え・読み |
| TSOA | アルバムの並べ替え・読み |
| APIC | 埋め込み画像 |

APICが複数ある場合、picture type 3（Front cover）を優先します。

### フォールバック順

1. Mutagen
2. 自前の簡易ID3v2フレーム解析
3. ID3v1
4. ファイル名・フォルダ名
5. MPEGフレームから再生時間推定

## 5. 文字コード補正

誤デコードされた文字列について、次の再解釈候補を作ります。

- Latin-1の文字列を元バイトへ戻し、UTF-8として再解釈
- Latin-1 → CP932
- CP1252 → UTF-8
- CP1252 → CP932

候補の品質評価:

- 日本語文字・英数字を加点
- 置換文字、制御文字、典型的な文字化け記号を減点
- 元より一定以上品質が高い候補だけ採用

ID3 encoding byte 0は、UTF-8、CP932、Latin-1を比較します。

## 6. ファイル名・フォルダ補完

### ファイル名先頭番号

```text
01 - Song Title.mp3
Track 01 Song Title.mp3
Disc 2 - 03 - Song Title.mp3
```

### アーティストと曲名

タグにアーティストがない場合、`Artist - Title.mp3`を分割します。

### ディスク番号

親フォルダ名の`Disc 2`、`Disk-2`、`CD03`等から取得します。

## 7. ID設計

### 曲ID

相対パスのSHA-256先頭20桁:

```text
mp3_<20桁hex>
```

移動検出時は旧IDを維持します。

### アーティストID

正規化アーティスト名の安定ハッシュです。

### アルバムID

次の組み合わせをハッシュします。

```text
正規化アルバム名 + 正規化アルバムアーティスト
```

### アートワークID

`source_type + relative_path`から生成します。

## 8. 差分スキャン

### キャッシュヒット条件

- 相対パスが既存
- ファイルサイズ一致
- `modified_time_ns`一致
- 必要なsortタグ一括更新が完了済み

この場合、タグを読まずに`last_scanned_at`と`is_available`を更新します。

### 移動・改名検出

軽量内容署名:

```text
SHA-256(
  ファイルサイズ
  + 先頭64KiB
  + 末尾64KiB
)
```

新パスの署名が、今回消えた旧レコード1件にのみ一致した場合、移動と判定します。

- 曲ID維持
- 再生回数維持
- 補正維持
- パス更新

複数候補の場合は誤結合を避け、新規曲とします。

## 9. 旧JSON移行

SQLiteが正本です。旧JSONはDBにまだ行がない新規登録時だけ参照します。

照合優先順位:

1. アーティスト＋アルバム＋曲名の正規化一致
2. 複数候補なら再生時間差が一意に最小
3. アルバム＋トラック番号＋再生時間差4秒以内
4. ファイルサイズ一意＋再生時間差4秒以内

引き継ぐ項目:

- playCount
- dateAdded
- legacyId
- legacyMatchMethod

現在の表記が明確な文字化けと評価された場合のみ、旧JSON表記を補修へ使用します。

## 10. アートワーク設計

### 優先順位

1. MP3埋め込みAPIC
2. 同一フォルダの外部画像
3. 親フォルダの外部画像
4. `Music`直下まで探索

### 外部画像の優先名

1. folder
2. cover
3. front
4. albumart
5. small
6. その他をファイル名順

### 埋め込み画像

- 曲IDをファイル名に使用
- MIMEまたはマジックナンバーから拡張子決定
- 同じ内容なら再書込しない
- 利用可能曲から参照されない画像を削除

## 11. SQLite接続

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 30000;
```

独自SQLite関数:

| 関数 | 用途 |
|---|---|
| `is_latin_only(text)` | 英数字タイトルフィルター |
| `catalog_bucket(text)` | A-Z／五十音／他の分類 |
| `catalog_sort_key(text)` | NFKC、冠詞除外、カタカナ→ひらがなで並べ替え |

## 12. 表示名の優先式

```text
曲名:
  title_override → title

曲名索引用:
  title_override → sort_title(TSOT) → title

アーティスト:
  track.artist_override
  → artists.display_name_override
  → artists.name

アーティスト索引用:
  artists.sort_name(TSOP) → 表示アーティスト

アルバム:
  album_override → albums.title

アルバム索引用:
  albums.sort_title(TSOA) → 表示アルバム
```

## 13. 検索・索引

### 正規化検索

表示文字列の`LIKE`に加え、空白・句読点・区切りを除いた正規化列を検索します。

### 頭文字分類

- 数字: `0-9`
- ASCII英字: `A`～`Z`
- ひらがな・カタカナ: 五十音の行
- 濁音・半濁音: 清音と同じ行
- その他: `他`

`The`、`A`、`An`は次が英数字の場合に除外します。

### ページング

- 既定80件
- API上限200件
- offset方式
- 応答に`hasMore`
- 索引件数はindexKey適用前の現在条件で集計
- 総曲数・合計時間はindexKey適用後

## 14. UI状態

主要状態:

```text
currentView
query
sort
latinOnly
correctedOnly
artistKey
albumKey
albumTitle
indexKey
offset
items
hasMore
```

検索・タブ・索引・絞り込み変更時はoffsetを0へ戻します。

## 15. 再生キュー

### 対象範囲

曲を再生した時点の検索条件を再生コンテキストとして使います。

- 検索語
- 英数字／訂正済フィルター
- アーティスト
- アルバム
- 頭文字索引
- 表示順

### シャッフル

- 現在曲を起点に履歴を管理
- 未再生候補からランダム選択
- 同一巡回内で重複なし
- 一巡後、全体リピートなしなら停止
- 全体リピート時は新しい巡回

### リピート

```text
repeatMode = off | all | one
```

`all`と`one`は排他です。

### 前曲

- `currentTime > 5秒`: 現曲先頭
- それ以外: 前曲または履歴へ

### 設定保存

localStorage:

```json
{
  "shuffleEnabled": true,
  "repeatMode": "all"
}
```

端末・ブラウザごとに独立します。

## 16. Media Session

対応ブラウザへ次を登録します。

- metadata
- play
- pause
- previoustrack
- nexttrack

ロック画面やBluetooth機器からの操作可否はOS・ブラウザ依存です。

## 17. 再生回数

新しい曲の再生開始時:

```text
POST /api/tracks/{id}/played
```

```sql
UPDATE tracks
SET play_count = play_count + 1,
    last_played_at = ?,
    updated_at = ?
WHERE id = ? AND is_available = 1;
```

一時停止からの再開では加算しません。

## 18. 表記補正

### 曲名

- 元title保持
- title_overrideへ保存
- 空または元値と同じならNULL

### アーティスト

- artists.display_name_overrideへ保存
- 同じartist_idの全曲へ反映
- 開発途中のtrack.artist_overrideはクリア

### 競合

楽観ロックや更新者管理はありません。最後のコミットが有効です。

## 19. HTTPサーバー

- `ThreadingHTTPServer`
- `SimpleHTTPRequestHandler`拡張
- HTML／JSON／JS／CSS／TXTはUTF-8
- MP3は`audio/mpeg`
- 単一Byte Range
- 正常Rangeは206
- 不正Rangeは416
- 64KiBずつコピー

## 20. 静的公開禁止

404として扱う対象:

- library.db、WAL、SHM
- legacy-library-data.json
- Pythonソース
- BAT
- `.db`、`.sqlite`
- Backups
- Exports

アプリは認証を持たないため、MP3・画像・検索APIは接続可能な利用者へ公開されます。

## 21. エラー処理

### スキャン

- 1曲の失敗で全体停止しない
- 既存レコードがあれば前回メタデータ再利用
- severity、category、path、messageを記録
- 致命的例外時はscan_runをfailed

### API

- 不正パラメーター: 400
- 対象なし: 404
- 内部エラー: 500

### UI

- fetch失敗を画面表示
- 補正保存失敗をalert
- 一時障害はサーバー再起動で復旧する場合あり

## 22. バックアップ

自動:

```text
Backups/library-YYYYMMDD.db
```

手動:

```text
Backups/library-manual-YYYYMMDD-HHMMSS.db
```

SQLite Online Backup APIを使用します。

## 23. マイグレーション

`initialize_database`が列の存在を確認し、加算的に更新します。

スキーマversion 4の主な追加列:

- artists.sort_name
- artists.display_name_override
- tracks.sort_title
- albums.sort_title

## 24. 未使用・予約項目

| 項目 | 状態 |
|---|---|
| favorite | DB列のみ |
| rating | DB列のみ |
| album_override | DB列のみ |
| track.artist_override | 将来の曲単位補正用 |
| GET /api/tracks | 旧互換・全件取得 |
