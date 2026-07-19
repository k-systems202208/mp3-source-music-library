# 運用・セキュリティ設計

## 1. 基本方針

アプリに独自ログインはありません。次の層で保護します。

```text
アプリの静的公開制限
＋ Windowsファイアウォール
＋ Tailscale参加者管理
＋ Tailscaleアクセス制御
＋ 運用ルール
```

## 2. 公開方式

| 方式 | 公開範囲 | 推奨 |
|---|---|---|
| 127.0.0.1 | PC自身 | 通常 |
| 0.0.0.0 + Firewall | 同一LAN | 家庭内 |
| Tailscale Serve | tailnet | 外出先 |
| ルーターポート開放 | Internet | 禁止 |
| Tailscale Funnel | Internet | 禁止 |

## 3. 守る対象

- MP3
- ライブラリ構成
- 再生履歴・補正
- ファイルパス
- Tailscale参加情報
- メール・端末名

## 4. LAN

- 自宅Wi-Fiのみ
- TCP 8765のみ
- `LocalSubnet4`
- Private優先
- Publicルールは必要時のみ
- 公共・ゲストWi-Fiで起動しない

Group PolicyでPrivateへ変更できない場合、Publicルールが他のPublicネットワークでも適用され得ます。使用後はDisableしてください。

## 5. Tailscale

### Serve

```powershell
tailscale serve --bg 8765
tailscale serve status
tailscale serve reset
```

### Funnel禁止

Funnelは公開インターネットから接続可能にします。本アプリは認証がないため使用しません。

### 外部招待

`Invite external users`で参加したMemberはアクセス制御に従います。allow-allが残る場合、音楽PC以外へ接続できる可能性があります。

## 6. Tailscale Grants最小権限例

> メールとIPを置換し、Preview changesと接続試験を行ってください。  
> 既存のallow-all grantが残っていると、下の制限を追加しても広い許可が有効です。

```hujson
{
  "groups": {
    "group:music-users": [
      "family1@example.com",
      "family2@example.com",
    ],
  },

  "hosts": {
    "music-server": "100.100.100.100",
  },

  "grants": [
    {
      "src": ["group:music-users"],
      "dst": ["music-server"],
      "ip": ["tcp:443"],
    },
  ],
}
```

Tailscale Serveの利用者側はHTTPS 443です。ローカル8765はPC内の転送先です。

管理者例:

```hujson
{
  "grants": [
    {
      "src": ["owner@example.com"],
      "dst": ["*"],
      "ip": ["*"],
    },
    {
      "src": ["group:music-users"],
      "dst": ["music-server"],
      "ip": ["tcp:443"],
    },
  ],
}
```

### 適用

1. Access controlsを開く
2. 現ポリシーをバックアップ
3. 正式ログイン名を確認
4. 音楽PCのTailscale IPv4を確認
5. Grants編集
6. Preview
7. 保存
8. 音楽URLへ接続
9. 他PCへの接続が拒否されることを確認

## 7. アプリ内防御

実装済み:

- DB、Python、BAT取得拒否
- Backups、Exports取得拒否
- no-store
- nosniff
- same-origin referrer
- POSTサイズ制限
- SQLバインド

未実装:

- 認証
- CSRF
- 更新者記録
- 権限分離
- 補正監査ログ
- レート制限

接続できる利用者は検索・再生・補正ができます。

## 8. バックアップ

最低限:

- `Music`: 別媒体
- `library.db`: 日次＋手動
- ソース: GitHubまたはZIP
- `.artwork-cache`: 再生成可能

重要音源は3-2-1を検討してください。

## 9. 復旧

1. サーバー停止
2. 障害DB、WAL、SHMを退避
3. バックアップをlibrary.dbへ
4. `check`
5. 起動
6. 曲数・再生回数・補正確認
7. MP3と再同期

## 10. 更新

1. サーバー停止
2. 手動バックアップ
3. 旧フォルダ退避
4. プログラムだけ上書き
5. Music、DB、cache、Backups維持
6. 起動
7. 回帰試験

## 11. 診断の機密性

診断にはファイル名・フォルダ構成が含まれます。公開Issueへ添付する場合は匿名化します。

スクリーンショットで隠すもの:

- Windowsユーザー名
- フルパス
- IP
- tailnet名
- メール
- 端末名

## 12. 著作権

- MP3をGitHubへ含めない
- 実アートワークを含めない
- 誰でも接続できる形で公開しない
- 適法に保有する音源を対象にする

## 13. 日常チェック

- 不要なLAN公開がない
- Serveがtailnet内だけ
- Funnel無効
- 不要ユーザー削除
- バックアップあり
- 診断エラー増加なし
- GitHubにprivate dataなし
