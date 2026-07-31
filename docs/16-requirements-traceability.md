# 要件トレーサビリティ

## 初期・基盤要件

| ID | 要件 | 実装 | 主な試験 | 状態 |
|---|---|---|---|---|
| R-001 | 大量曲を検索 | SQLite browse API | 回帰・実機検索 | 完了 |
| R-002 | 曲・アーティスト・アルバム | 3ビュー＋ドリルダウン | UI回帰 | 完了 |
| R-003 | MP3を音源正本 | generator／paths | 走査試験 | 完了 |
| R-004 | MP3を変更しない | 読取専用走査・HTTP配信 | 実機確認 | 完了 |
| R-005 | 表記補正 | override列・API | 回帰 | 完了 |
| R-006 | スマホ利用 | LAN／Tailscale | 実機 | 完了 |
| R-007 | 外部へ直接公開しない | localhost＋Serve | remote tests | 完了 |
| R-008 | 更新でデータ維持 | `%LOCALAPPDATA%`分離 | 上書き試験 | 完了 |

## v2.7.0要件

| ID | 要件 | 実装 | 主な試験 | 状態 |
|---|---|---|---|---|
| U-001 | ローカルPCをオーナー識別 | one-time token＋Cookie | local auth | 完了 |
| U-002 | Tailscale利用者を識別 | login header正規化 | identity test | 完了 |
| U-003 | 匿名を誤ユーザーへ保存しない | anonymous current user | playback/favorite | 完了 |
| U-004 | 利用者別再生回数 | `user_track_state.play_count` | user playback | 完了 |
| U-005 | 利用者別最終再生日時 | `last_played_at` | user playback | 完了 |
| U-006 | 利用者別お気に入り | `favorite` | favorites | 完了 |
| U-007 | お気に入り絞り込み | `favoriteOnly` | favorite filter | 完了 |
| U-008 | 現在利用者表示 | user chip/modal | management UI | 完了 |
| U-009 | 利用者一覧 | `/api/users` | management UI | 完了 |
| U-010 | 家族の停止・再開 | `/active` | management UI | 完了 |
| U-011 | オーナー停止防止 | owner guard | management UI | 完了 |
| U-012 | 本人Tailscale関連付け | owner link challenge | owner link | 完了 |
| U-013 | 家族の誤昇格防止 | local explicit confirm | owner link | 完了 |
| U-014 | 既存個人状態を統合 | merge transaction | owner link | 完了 |
| U-015 | 評価競合を推測しない | conflict abort | owner link | 完了 |
| U-016 | 旧共通状態をオーナーへ移行 | schema 5 migration | migration test | 完了 |
| U-017 | 移行前バックアップ | pre-v2.7.0 backup | migration test | 完了 |
| U-018 | 関連付け前バックアップ | pre-owner-link backup | owner link test | 完了 |
| U-019 | 失敗時ロールバック | transactions | migration/link tests | 完了 |

## 非機能要件

| ID | 要件 | 対応 | 状態 |
|---|---|---|---|
| N-001 | APIデータをキャッシュしない | `no-store` | 完了 |
| N-002 | 静的配信からDBを除外 | blocked names／path resolver | 完了 |
| N-003 | ブラウザ切断でサーバー異常にしない | expected disconnect判定 | 完了 |
| N-004 | 1人だけのオーナー | DB索引＋検査 | 完了 |
| N-005 | 個人状態の分離 | 複合主キー | 完了 |
| N-006 | 外部接続HTTPS | Tailscale Serve | 完了 |
| N-007 | 長いパスへの完全対応 | 未完 | 課題 |
| N-008 | コード署名 | 未導入 | 課題 |

## 将来要件

| ID | 要件 | 現状 |
|---|---|---|
| F-001 | プレイリスト | 未実装 |
| F-002 | 評価操作UI | DBのみ |
| F-003 | FLAC／AAC走査 | 未実装 |
| F-004 | PWAオフライン | 未実装 |
| F-005 | Windowsサービス | 未実装 |
