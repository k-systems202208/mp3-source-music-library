# 文書一覧

対象は自宅音楽ライブラリv2.7.5、DBスキーマ7です。

## 最初に読む文書

| 目的 | 文書 |
|---|---|
| 概要を知る | [README](../README.md) |
| 初めて導入・家族共有する | [オーナー導入・家族共有ガイド](19-owner-setup-guide.md) |
| 利用する | [利用マニュアル](06-user-manual.md) |
| 外部接続・安全性 | [運用・セキュリティ](07-operations-security.md) |
| 障害を切り分ける | [トラブルシューティング](08-troubleshooting.md) |
| 実装を確認する | [アーキテクチャ](01-architecture.md) → [詳細設計](03-detailed-design.md) → [API](04-api-reference.md) → [DB](05-database-design.md) |
| ビルド・公開する | [試験計画](09-test-plan.md) → [GitHub公開ガイド](11-github-publishing-guide.md) |
| 経緯を追う | [起点と要件](00-project-origin-and-requirements.md) → [変更履歴](10-changelog.md) → [UI/UX履歴](17-ui-ux-design-history.md) |

## 現行文書

| ファイル | 内容 |
|---|---|
| `00-project-origin-and-requirements.md` | プロジェクトの起点、要件、発展 |
| `01-architecture.md` | 構成、信頼境界、データフロー |
| `02-application-specification.md` | 現行機能・非機能仕様 |
| `03-detailed-design.md` | モジュール・処理詳細 |
| `04-api-reference.md` | HTTP API、権限、代表入出力 |
| `05-database-design.md` | SQLiteスキーマ7、移行、バックアップ |
| `06-user-manual.md` | インストール、検索、再生、プレイリスト |
| `07-operations-security.md` | 運用、安全境界、Tailscale |
| `08-troubleshooting.md` | 起動、認証、PWA、長パス、DB |
| `09-test-plan.md` | 自動試験・実機受入項目 |
| `10-changelog.md` | バージョン別変更履歴 |
| `11-github-publishing-guide.md` | ビルド、タグ、Release、文書更新 |
| `12-note-article.md` | 紹介記事の草稿 |
| `13-roadmap.md` | 完了事項と今後の候補 |
| `14-glossary.md` | 用語集 |
| `15-source-verification.md` | 仕様とソース・試験の対応 |
| `16-requirements-traceability.md` | 要件追跡表 |
| `17-ui-ux-design-history.md` | UI/UXの変遷 |
| `18-documentation-audit-v2.7.5.md` | 今回の全文書監査 |
| `19-owner-setup-guide.md` | PC初心者向けの導入、Tailscale、家族招待、運用手順 |
| `THIRD_PARTY_NOTICES.md` | 第三者ライブラリ通知 |

Windowsインストーラーと配布物の文書は[DOCUMENT_INDEX_v2.7.5](../windows-installer/docs/DOCUMENT_INDEX_v2.7.5.md)を参照してください。

## 履歴文書の扱い

`windows-installer/docs`にある過去バージョン、`RC*`、`PHASE*`の文書は、開発判断と試験履歴を残す資料です。現行仕様の根拠として参照する場合は、README、正式版のRelease Notes、現行設計文書と照合してください。履歴文書の本文は後から現行仕様へ書き換えません。
