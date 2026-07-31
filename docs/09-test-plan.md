# テスト計画書

## 1. 方針

v2.7.0はDB移行、利用者識別、個人状態、オーナー統合を含むため、ソース回帰試験、バンドル済みEXEのスモーク試験、実運用DBによる受入試験を分けます。

## 2. 自動回帰試験

| テスト | 主な確認 |
|---|---|
| `build_sanity.py` | 必須ファイル、構文、ビルド前提 |
| `test_client_disconnects.py` | ブラウザ切断を正常に扱う |
| `test_remote_access.py` | Tailscale状態・URL解析 |
| `test_remote_entry_path.py` | 外部URLの正しいアプリパス |
| `test_launcher_stability.py` | ヘルスURL、停止状態、管理画面安定性 |
| `test_schema_v5_migration.py` | バックアップ、旧状態移行、ロールバック、整合性 |
| `test_local_owner_auth.py` | 制御秘密、一時トークン、Cookie、期限 |
| `test_tailscale_identity.py` | ヘッダー検証、正規化、重複拒否 |
| `test_owner_tailscale_link.py` | コード、候補、承認、統合、競合、ロールバック |
| `test_user_management_ui.py` | 利用者表示・管理UI |
| `test_user_playback_state.py` | 利用者別再生状態 |
| `test_user_favorites.py` | お気に入り保存・解除・分離 |
| `test_favorite_filter.py` | お気に入りのみの検索 |
| `test_release_candidate.py` | バージョン、文書、ビルド候補の一貫性 |

## 3. ビルド試験

- PyInstaller 6.21.0でEXE生成
- バンドル済みEXEを空ライブラリで起動
- Inno Setupでx64インストーラー生成
- バージョン情報と発行元表記
- SHA-256生成
- `git diff --check`
- 公開禁止ファイル検査

## 4. schema移行試験

### 複製DB

実運用DBを直接編集せず、ファイルとして複製して次を確認します。

- schema 4→5
- オーナー1人
- ローカルオーナー識別
- 旧再生回数・最終再生日時・お気に入り・評価の件数一致
- 外部キー整合性
- 元DBが変更されていない

### 実運用更新

- 更新前に手動バックアップ
- 旧版をアンインストールせず上書き
- `library-pre-v2.7.0-*`生成
- 曲数、設定、補正の維持

## 5. ローカルオーナー受入試験

1. 管理画面からブラウザを開く
2. 右上が「オーナー（オーナー）」
3. ★登録・解除
4. お気に入りのみ
5. 再生回数増加
6. アプリ再起動
7. 状態が保持される

## 6. Tailscale受入試験

1. スマートフォンをWi-Fi OFF、モバイル通信、Tailscale ON
2. Serve URLを開く
3. 右上にTailscale利用者
4. PCと別プロフィールとして状態保存
5. 利用停止時は匿名相当

## 7. オーナー関連付け受入試験

1. ローカルでコード発行
2. 本人Tailscale側からclaim
3. ローカルへ表示名・ログイン名・件数表示
4. 承認
5. `library-pre-owner-link-*`生成
6. 再生回数が合算
7. お気に入りがOR
8. Tailscale側もオーナー表示
9. PC・スマートフォンで状態共有
10. 再起動後も維持

## 8. 利用者管理受入試験

- 家族利用者の一覧表示
- ローカルオーナーから停止・再開
- Tailscaleオーナーから変更不可
- オーナー停止不可
- 停止後も既存状態は保持

## 9. 検索・再生回帰

- 曲／アーティスト／アルバム
- 検索、索引、ページング
- ドリルダウン
- 補正
- アートワーク
- Range再生・シーク
- シャッフル・リピート
- 複数端末

## 10. 合格基準

- 全自動テストPASS
- EXEスモークPASS
- インストーラー生成PASS
- DB移行・バックアップ・整合性PASS
- ローカル／Tailscale／関連付けの実機試験PASS
- 重大なデータ消失・誤ユーザー紐付けなし

MP3の長いパスによる既知の読み取りエラーは、該当ファイルと原因を診断で特定し、v2.7.0利用者機能の合否とは分離して管理します。
