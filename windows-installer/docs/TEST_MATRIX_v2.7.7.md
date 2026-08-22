# v2.7.7 変更内容別 必須テストマトリクス

対象: 自宅音楽ライブラリ v2.7.7 / DB schema 7

目的: 変更内容ごとに最低限実行すべきテストを固定し、変更時の試験漏れと不要な全試験実行を減らす。

## 1. 基本ルール

- 変更した機能に対応する「個別必須テスト」を最初に実行する。
- 実行コードを変更した場合、Pull RequestをMergeする前に原則 `06_verify_next_improvements.bat` も実行する。
- 文書のみの変更では `git diff --check` を必須とし、実行コードへ影響しない場合は回帰試験を省略できる。
- リリース候補または正式リリース前は、個別試験の結果にかかわらず `00_build_installer.bat` を実行する。
- テストが1件でも失敗した場合、Commit後であってもMergeへ進まない。原因を修正して再試験する。
- 複数領域を変更した場合は、該当する行の必須テストを合算する。

## 2. 変更内容別マトリクス

| 変更領域 | 個別必須テスト | Merge前の共通確認 |
|---|---|---|
| プレイリスト DB/API | `tests/test_playlists.py` | `06_verify_next_improvements.bat` |
| プレイリスト UI/並び替え/複製 | `tests/test_playlists.py`、`tests/test_playlist_production_ui.py` | `06_verify_next_improvements.bat` |
| ローカルオーナー認証 | `tests/test_local_owner_auth.py`、`tests/test_startup_auth_handoff.py`、`tests/test_tailscale_identity.py` | `06_verify_next_improvements.bat` |
| Tailscale識別 | `tests/test_tailscale_identity.py`、`tests/test_owner_tailscale_link.py`、`tests/test_startup_auth_handoff.py` | `06_verify_next_improvements.bat` |
| 利用者プロフィール/アルバム補正/診断権限 | `tests/test_user_management_ui.py` | `06_verify_next_improvements.bat` |
| 再生状態 | `tests/test_user_playback_state.py`、`tests/test_playback_count_policy.py` | `06_verify_next_improvements.bat` |
| お気に入り | `tests/test_user_favorites.py`、`tests/test_favorite_filter.py` | `06_verify_next_improvements.bat` |
| ライブラリホーム | `tests/test_library_home.py`、`tests/test_library_home_layout.py` | `06_verify_next_improvements.bat` |
| スキン/表示テーマ | `tests/test_skin_persistence.py`、`tests/test_skin_preview.py`、`tests/test_skin_preview_layout.py`、`tests/test_skin_stat_cards.py`、`tests/test_skin_user_chip.py` | `06_verify_next_improvements.bat` |
| PWA | `tests/test_pwa_assets.py`、`tests/test_pwa_ui_contract.py`、`tests/test_pwa_mobile_layout.py`、`tests/test_pwa_server.py` | `06_verify_next_improvements.bat` |
| リモートアクセス/接続処理 | `tests/test_client_disconnects.py`、`tests/test_remote_access.py`、`tests/test_remote_entry_path.py` | `06_verify_next_improvements.bat` |
| DB schema/移行 | `tests/test_schema_v5_migration.py`、`tests/test_backup_restore.py`、`tests/test_release_candidate.py` | `06_verify_next_improvements.bat` |
| バックアップ/復元 | `tests/test_backup_restore.py` | `06_verify_next_improvements.bat` |
| Launcher/起動安定性 | `tests/test_windows_batch_launchers.py`、`tests/test_launcher_stability.py`、`tests/build_sanity.py` | `06_verify_next_improvements.bat` |
| 長パス/フルスキャン | `tests/test_long_path_support.py`、`tests/test_live_long_path_probe.py`、`tests/test_phase2_copied_full_scan_workflow.py` | `06_verify_next_improvements.bat` |
| 更新通知/GitHub Release確認 | `tests/test_update_notification.py`、`tests/test_release_candidate.py` | `06_verify_next_improvements.bat` |
| バージョン/PWAキャッシュ/インストーラー定義 | `tests/test_release_candidate.py` | `06_verify_next_improvements.bat` |
| ビルド構成/同梱ファイル | `tests/verify_package_manifest.py`、`tests/test_windows_batch_launchers.py`、`tests/build_sanity.py`、`tests/test_release_candidate.py` | `06_verify_next_improvements.bat` |
| 文書のみ | `git diff --check` | 実行コードへ影響しなければ回帰試験省略可 |
| 正式リリース候補 | `00_build_installer.bat` | これを最終ゲートとする |

## 3. 日常回帰バッチの役割

`06_verify_next_improvements.bat` は通常開発の共通回帰確認として使用する。

現時点では次をまとめて確認する。

- Python構文
- JavaScript構文
- プレイリスト
- 利用者管理UI
- 利用者別再生状態
- 利用者別お気に入り
- 再生回数仕様
- ライブラリホーム
- リリース候補整合性

個別必須テストに `06_verify_next_improvements.bat` に含まれていない試験がある場合は、個別試験を先に実行したうえで共通回帰を実行する。

## 4. 正式ビルドの役割

正式リリース前は `00_build_installer.bat` を最終ゲートとする。

このバッチは次を連続して実行する。

1. 配布パッケージ構成確認
2. Pythonソース構文確認
3. 全回帰テスト
4. PyInstallerによる `MusicLibrary.exe` 作成
5. バンドル済みEXEのバージョン確認
6. 空ライブラリを使った実EXEスモーク試験
7. Inno SetupによるWindowsインストーラー作成
8. SHA-256計算
9. ビルドログ/ビルドレポート作成

したがって、正式リリース時に個別テストだけで `00_build_installer.bat` を代替してはならない。

## 5. テスト追加時の更新ルール

新機能または不具合修正で新しい回帰テストを追加した場合は、同じPull Request内で次を検討する。

- このマトリクスの対象行へ追加する。
- 日常的に必要なら `06_verify_next_improvements.bat` へ追加する。
- 正式リリースで必須なら `00_build_installer.bat` へ追加する。
- リリースビルドに含まれること自体を固定すべき場合は `tests/test_release_candidate.py` の必須テスト一覧へ追加する。
