# 実装確認メモ

この文書はv2.7.0の説明と実装の対応を示します。

## バージョン

| 説明 | 根拠 |
|---|---|
| アプリ2.7.0 | `windows-installer/src/launcher.py`、`paths.py` |
| サーバー2.7.0 | `server.py`の`server_version` |
| schema 5 | `database.py`の`SCHEMA_VERSION` |

## 利用者識別

| 説明 | ソース | テスト |
|---|---|---|
| ローカル一時トークン | `local_auth.py`、`launcher.py`、`server.py` | `test_local_owner_auth.py` |
| Cookie12時間 | `local_auth.py`、`server.py` | `test_local_owner_auth.py` |
| Tailscaleヘッダー | `tailscale_identity.py`、`server.py` | `test_tailscale_identity.py` |
| Tailscale優先解決 | `server.py::_resolve_current_user` | Tailscale／local authテスト |
| 匿名時に個人状態を保存しない | `database.py`、`server.py` | `test_user_playback_state.py`、`test_user_favorites.py` |

## DBと移行

| 説明 | ソース | テスト |
|---|---|---|
| `users`等の作成 | `database.py::SCHEMA_SQL` | `test_schema_v5_migration.py` |
| オーナー1人 | 部分ユニーク索引＋検証 | `test_schema_v5_migration.py` |
| 旧状態をオーナーへ移行 | `_migrate_legacy_user_state` | `test_schema_v5_migration.py` |
| 移行前バックアップ | `create_pre_v27_migration_backup` | `test_schema_v5_migration.py` |
| foreign key検査 | `_verify_schema_v5` | `test_schema_v5_migration.py` |

## 個人状態

| 説明 | ソース | テスト |
|---|---|---|
| 再生回数 | `record_user_playback` | `test_user_playback_state.py` |
| お気に入り | `set_user_favorite` | `test_user_favorites.py` |
| お気に入りのみ | `browse_library`／UI | `test_favorite_filter.py` |
| 状態の疎化 | `set_user_favorite`の空行削除 | `test_user_favorites.py` |

## オーナー統合

| 説明 | ソース | テスト |
|---|---|---|
| コード状態機械 | `owner_link.py` | `test_owner_tailscale_link.py` |
| 統合プレビュー | `get_owner_link_merge_preview` | 同上 |
| 再生合算・お気に入りOR | `_merge_user_track_state_into_owner` | 同上 |
| 評価競合停止 | 同上 | 同上 |
| 関連付け前バックアップ | `create_pre_owner_link_backup` | 同上 |
| 識別情報移動 | `link_tailscale_identity_to_owner` | 同上 |

## 利用者管理

| 説明 | ソース | テスト |
|---|---|---|
| 一覧 | `list_users_for_management`、`/api/users` | `test_user_management_ui.py` |
| 停止・再開 | `set_user_active`、`/active` | `test_user_management_ui.py` |
| ローカル限定 | `_require_local_owner` | 同上 |
| オーナー停止不可 | `handle_user_active` | 同上 |

## 既存機能

| 説明 | ソース／テスト |
|---|---|
| 検索・ページング | `database.py::browse_*`、`server.py` |
| MP3走査・タグ | `generator.py` |
| Range配信 | `server.py::send_head` |
| ランチャー安定性 | `test_launcher_stability.py` |
| Tailscale URL | `remote_access.py`、`test_remote_access.py`、`test_remote_entry_path.py` |
| ブラウザ切断 | `test_client_disconnects.py` |

## 文書化上の注意

- `tracks`の旧共通状態列は残っていますが、v2.7.0の利用者状態の正本は`user_track_state`です。
- 一般的なパスワードログインはありませんが、ローカル一時トークンとTailscaleによる利用者識別は実装済みです。
- ratingはDB・移行・統合に存在しますが、v2.7.0の操作UIはありません。
- 曲名・アーティスト補正APIは現行実装でオーナー限定ではありません。
