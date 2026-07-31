# 運用・セキュリティ設計

## 1. 保護対象

- MP3音源
- `library.db`
- 利用者別再生状態
- 曲名・アーティスト名補正
- Tailscaleログイン名・表示名・プロフィールURL
- 外部接続URL
- バックアップ・診断・ログ

## 2. 信頼境界

### ローカル管理画面

ランチャーはサーバーと制御秘密を共有し、一時トークンを登録します。ブラウザは短時間だけ有効な一時トークンをCookieへ交換します。単にlocalhost URLを知っているだけではローカルオーナーになりません。

### Tailscale Serve

サーバーはlocalhostへバインドし、Tailscale Serveから渡された利用者ヘッダーを使用します。利用者がブラウザから直接送った同名ヘッダーを一般公開サーバーで信頼する設計ではありません。

### 匿名

識別不能な接続は閲覧・再生に限定し、個人状態を保存しません。

## 3. Cookie

```text
music_library_owner_session
Path=/
HttpOnly
SameSite=Strict
Max-Age=43200
```

HTTPS属性はlocalhostのHTTP運用との互換上付与していません。外部接続はTailscale ServeのHTTPSを使用しますが、Tailscale利用者はヘッダーで識別します。

## 4. オーナー関連付け

- コードは十分な乱数長を持つ
- DBへ平文保存しないサーバーメモリ上の一時状態
- 既定5分で期限切れ
- Tailscale利用者本人だけclaim可能
- ローカルオーナーだけ承認可能
- 候補のIDとsubjectを承認時に再照合
- 評価競合時は自動判断しない
- 処理前バックアップ
- 統合・識別移動・候補削除を1トランザクション

## 5. 利用者管理

- オーナーは1人
- オーナーは停止不可
- 状態変更はローカルオーナー限定
- Tailscale経由オーナーは一覧閲覧だけ
- 完全削除ではなく停止を基本とする

停止された利用者の既存状態は保持し、再開時に再利用できます。

## 6. ネットワーク

推奨:

```text
ブラウザ → Tailscale → Tailscale Serve → 127.0.0.1:8765
```

禁止／非推奨:

- ルーターのポート開放
- DMZ
- Tailscale Funnel
- 接続URLの一般公開
- Tailscaleアカウントのパスワード共有

家族は個別のTailscaleアカウントを使用します。

## 7. HTTP防御

- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: same-origin`
- API／HTML／JSONは`no-store`
- DB・WAL・SHM・旧JSON・ソース名を静的配信から遮断
- メディアパスを許可ルート内へ限定
- POST本文を完全に読み取ってから権限判定し、Windowsの接続リセットを抑制

## 8. バックアップ

| 種別 | タイミング | 例 |
|---|---|---|
| 日次 | 起動時、当日未作成 | `library-20260801.db` |
| schema 5移行前 | v2.7.0初回初期化 | `library-pre-v2.7.0-...db` |
| オーナー関連付け前 | 承認直前 | `library-pre-owner-link-...db` |
| 手動 | 利用者操作／保守 | 任意 |

バックアップは別媒体へ定期コピーすることを推奨します。

## 9. GitHub公開

公開しない:

- 音源
- 実DBとWAL／SHM
- 利用者データディレクトリ
- 診断、ログ、バックアップ、設定、外部URL
- 実利用者名・メール・プロフィールURL
- 関連付けコード、Cookie、制御秘密

スクリーンショットはダミー利用者・ダミー曲で撮影します。

## 10. インシデント対応

### 関連付け先を誤った疑い

1. ライブラリを停止
2. `library-pre-owner-link-*.db`を保全
3. 現在の`library.db`も別名コピー
4. 操作を続けず差分確認

### DB移行失敗

1. 起動を繰り返さない
2. `library-pre-v2.7.0-*.db`を保全
3. エラー画面、Logs、診断を保存
4. バックアップ復元は確認後に行う

### Tailscale URL漏えい

URLだけではTailscale認証を通過できませんが、公開情報から削除し、tailnet共有・Grants・端末一覧を確認します。
