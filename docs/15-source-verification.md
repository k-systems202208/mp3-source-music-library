# ソース確認対応表

本書はv2.7.7の仕様記述を、主要ソースと試験へ対応付けます。

| 仕様 | 主なソース | 主な試験 |
|---|---|---|
| 製品版2.7.7 | `src/launcher.py`、`src/paths.py`、`src/update_check.py`、`build/version_info.txt` | RC consistency |
| DB schema 7 | `src/database.py` | schema migration through v7 |
| ローカル認証 | `src/local_auth.py`、`src/server.py` | local owner auth、startup handoff |
| Tailscale識別 | `src/tailscale_identity.py`、`src/server.py` | tailscale identity |
| オーナー関連付け | `src/owner_link.py` | owner and Tailscale linking |
| 利用者別状態 | `src/database.py`、`src/server.py` | playback state、favorites |
| 再生回数記録規約 | `src/database.py`、`src/music-library-search.html`、`docs/24-playback-count-policy.md` | playback count policy、playback state |
| ライブラリホーム | `src/database.py`、`src/server.py`、HTML | library home |
| バックアップ・復元 | `src/backup_restore.py`、`src/database.py` | backup and restore |
| 新版通知 | `src/update_check.py`、`src/server.py` | update notification |
| スキン | `user_preferences`、HTML、`/api/me/skin` | skin persistence、UI |
| PWA | manifest、Service Worker、offline、HTML | PWA assets、mobile、static serving |
| 長いパス | `src/long_paths.py`、generator、server | long path support、probe、copied scan |
| プレイリスト | `playlists`、`playlist_tracks`、server、HTML | per-user playlists |
| 本番モバイル表示 | HTML、Service Worker | production playlist UI |

## 開発時の確認ルール

- 変更内容ごとの個別必須試験は`windows-installer/docs/TEST_MATRIX_v2.7.7.md`に従う
- 通常コード変更では個別試験に加えて`windows-installer/06_verify_next_improvements.bat`をMerge前に実行する
- 正式リリース前は`windows-installer/00_build_installer.bat`を最終ゲートとする
- v2.7.7の正常比較基準点は`windows-installer/docs/DEVELOPMENT_BASELINE_v2.7.7.md`を参照する

## 現行値

- `APP_VERSION = 2.7.7`
- `CURRENT_VERSION = 2.7.7`
- server version `MusicLibrary/SQLiteAPI2.7.7`
- `SCHEMA_VERSION = 7`
- 対応復元schema: 5、6、7

## 確認上の注意

- 実機値8,480曲、7,708アートワークはソース定数ではない
- GitHub Release公開完了はユーザー報告に基づく
- 公開後の新版通知画面は今回の資料に含まれていない
- RC／Phase文書は当時の判断を示し、現行ソースと異なる場合がある
