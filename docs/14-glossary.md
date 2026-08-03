# 用語集

| 用語 | 意味 |
|---|---|
| 音楽ルート | MP3を保存している利用者選択フォルダー |
| 正本 | その情報の最終的な基準 |
| `library.db` | 検索情報・利用者状態・プレイリストを保存するSQLite DB |
| schema 7 | v2.7.5のDB構造 |
| ローカルオーナー | Windows管理画面から認証した管理利用者 |
| Tailscale利用者 | Tailscale Serve経由で識別された利用者 |
| 匿名 | 利用者を識別できない接続 |
| owner link | ローカルオーナーと本人Tailscaleプロフィールの関連付け |
| `user_track_state` | 利用者別の再生回数・お気に入り等 |
| `user_preferences` | 利用者別スキン |
| `playlists` | プレイリスト本体 |
| `playlist_tracks` | プレイリストの曲と順序 |
| PWA | ホーム画面追加・standalone表示を行うWebアプリ方式 |
| Service Worker | PWAのシェルキャッシュを制御するブラウザ機能 |
| shell cache | HTML、manifest、アイコン等の画面資産キャッシュ |
| Range配信 | MP3の一部だけを返し、シークを可能にするHTTP配信 |
| 長いパス | Windowsで従来の260文字制限を超える絶対パス |
| `\\?\` | Windows API向けの拡張長パス表現 |
| 内容署名 | 移動・改名検出に使うファイル内容の特徴 |
| 移行前バックアップ | schema更新直前に自動作成するDB複製 |
| RC | Release Candidate。正式公開前の候補版 |
| Phase文書 | 機能の段階検証を記録した履歴文書 |
