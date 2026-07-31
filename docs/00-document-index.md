# 文書一覧

対象バージョンは自宅音楽ライブラリv2.7.0、DBスキーマ5です。

## 最初に読む文書

| 対象 | 推奨文書 |
|---|---|
| 初めて利用する人 | `README.md` → `06-user-manual.md` |
| 外出先から利用する人 | `06-user-manual.md` → `07-operations-security.md` |
| 障害を切り分ける人 | `08-troubleshooting.md` |
| 実装を確認する人 | `01-architecture.md` → `03-detailed-design.md` → `04-api-reference.md` → `05-database-design.md` |
| リリースを行う人 | `09-test-plan.md` → `11-github-publishing-guide.md` |
| 開発経緯を把握する人 | `00-project-origin-and-requirements.md` → `10-changelog.md` → `17-ui-ux-design-history.md` |

## 文書構成

| ファイル | 主な内容 | v2.7.0での更新 |
|---|---|---|
| `00-project-origin-and-requirements.md` | 初期要件と設計方針 | 利用者別状態までの発展を追加 |
| `01-architecture.md` | 全体構成、境界、処理シーケンス | ローカルオーナー、Tailscale、schema 5 |
| `02-application-specification.md` | 機能・非機能・制約 | 利用者識別、管理、お気に入り |
| `03-detailed-design.md` | モジュール別詳細 | `local_auth.py`、`owner_link.py`等 |
| `04-api-reference.md` | APIと権限 | 利用者・関連付け・お気に入りAPI |
| `05-database-design.md` | SQLiteスキーマ | `users`、`user_identities`、`user_track_state` |
| `06-user-manual.md` | 利用手順 | インストーラー版、現在の利用者、関連付け |
| `07-operations-security.md` | 運用・安全境界 | Cookie、Tailscaleヘッダー、管理権限 |
| `08-troubleshooting.md` | 障害切り分け | schema移行、関連付け、長いパス |
| `09-test-plan.md` | 試験計画 | v2.7.0回帰試験と実機確認 |
| `10-changelog.md` | 変更履歴 | v2.5～v2.7.0を追加 |
| `11-github-publishing-guide.md` | GitHub公開 | インストーラー・文書・個人情報除外 |
| `12-note-article.md` | 投稿原稿 | v2.7.0追補記事 |
| `13-roadmap.md` | 今後の候補 | 完了項目を整理 |
| `14-glossary.md` | 用語 | 利用者識別・オーナー統合を追加 |
| `15-source-verification.md` | 根拠対応 | v2.7.0ソース・テスト対応 |
| `16-requirements-traceability.md` | 要件追跡 | 利用者別状態の要件を追加 |
| `17-ui-ux-design-history.md` | UI変遷 | 利用者チップ・管理モーダルを追加 |
| `THIRD_PARTY_NOTICES.md` | 第三者通知 | 同梱ライセンスの参照先を明記 |

## 文書上の表現

v2.7.0は一般的なパスワードログインを実装していませんが、「利用者識別がない」わけではありません。文書では次のように区別します。

- ローカルPC: 管理画面が発行する一時トークンとセッションCookie
- Tailscale: Tailscale Serveが付与する利用者ヘッダー
- 匿名: 検索・再生のみ。個人状態は保存しない

## 履歴文書の扱い

`10-changelog.md`や`17-ui-ux-design-history.md`では旧バージョンの仕様を歴史として記載します。旧仕様の説明と現行仕様を混同しないよう、各節へバージョンを明記します。
