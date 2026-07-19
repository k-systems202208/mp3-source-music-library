# 用語集

| 用語 | 意味 |
|---|---|
| 正本 | 存在や値を最終的に正しいと判断するデータ |
| MP3正本 | 物理MP3の有無を曲の有無とする設計 |
| SQLite正本 | 履歴・補正・管理情報をlibrary.dbへ集約する設計 |
| ID3 | MP3へ曲名等を保存するタグ規格 |
| TIT2 | 曲名 |
| TPE1 | アーティスト |
| TPE2 | アルバムアーティスト |
| TALB | アルバム |
| APIC | 埋め込み画像 |
| TSOT | 曲名の並べ替え・読み |
| TSOP | アーティストの並べ替え・読み |
| TSOA | アルバムの並べ替え・読み |
| Mutagen | Pythonの音声メタデータ解析ライブラリ |
| Byte Range | 音声の必要部分だけHTTP取得する仕組み |
| WAL | SQLiteで読み取りと書き込みの競合を減らすJournal方式 |
| busy timeout | SQLiteロック解除を待つ時間 |
| UPSERT | 既存なら更新、なければ追加 |
| 論理削除 | DB行を消さず利用不可フラグを立てる |
| 内容署名 | MP3の移動判定に使う軽量ハッシュ |
| localStorage | ブラウザ内へ端末別設定を保存する領域 |
| Media Session | OSの再生UIとWebプレーヤーを連携するAPI |
| tailnet | Tailscaleで構成するプライベートネットワーク |
| Tailscale Serve | tailnet内へローカルWebサービスを公開する機能 |
| Tailscale Funnel | 公開インターネットへサービスを出す機能。本アプリでは非推奨 |
| Grants | Tailscaleのアクセス制御ルール |
| LocalSubnet4 | Windows Firewallで同一IPv4サブネットを表す指定 |

| iTunes XML | iTunes／Musicライブラリからエクスポートした初期入力データ |
| 埋め込みJSON | JSONをHTMLソース内へ直接格納する初期方式 |
| フィルターチップ | 選択中のアーティスト・アルバム条件を示す解除可能なUI |
| ドリルダウン | 一覧から関連する下位一覧へ段階的に移動する操作 |
| パンくず | 現在位置と上位階層を示すナビゲーション |
| 表記補正 | 元タグを残したまま表示名だけを修正する機能 |
