# 実装確認メモ

このドキュメントは、次の実装パッケージを展開し、コードを確認して作成しています。

```text
music_library_mp3_source_sqlite_api_v2_4_playback_modes.zip
```

確認した主要ファイル:

- `README.txt`
- `SQLITE-SCHEMA.txt`
- `database.py`
- `generate-library.py`
- `serve-library.py`
- `music-library-search.html`
- `library-maintenance.py`
- `start-music-library.bat`

## 実装コードを正とした事項

- `database.py`の`SCHEMA_VERSION = 4`
- APIサーバー識別子`MusicLibrary/SQLiteAPI2.4`
- ページサイズ80、API上限200
- SQLite WAL、busy timeout 30秒
- Byte Range
- v2.4の再生モード
- TSOT／TSOP／TSOA
- 静的公開禁止対象

## 公開前に確認したい点

アプリ同梱の`SQLITE-SCHEMA.txt`は見出しが`version 3`のままですが、実装コード上のスキーマはversion 4です。GitHubへ公開する際は、同梱文書の見出しをversion 4へ統一することを推奨します。


## 開発前史の確認資料

現行チャット開始以前の作業記録として、利用者提供の`cloudeで実装.txt`を確認しました。

同資料から反映した事項:

- iTunesエクスポートXMLを起点としたこと
- 8,383曲
- 完全静的・単一HTML・サーバー／DBなしの初期構成
- カード目録デザイン
- 曲名・アーティスト・アルバム・作曲者検索
- ジャンル絞り込みと複数並べ替え
- アルバム・アーティストのリンク絞り込み
- フィルターチップ
- ローマ字曲名を自動変換しない判断
- 曲名・アーティストのlocalStorage補正
- Google検索による正式表記確認
- 英数字タイトル・訂正済みフィルター
- 3ビュー、ドリルダウン、パンくず
- JSON外部化要求

これらは現行仕様と混同しないよう、初期要件・開発履歴・要件トレーサビリティとして記載しました。

## 外部仕様の参照先

ネットワーク・Tailscale手順は、2026-07-19時点で次の公式文書を参照してください。

- Tailscale Serve: https://tailscale.com/docs/features/tailscale-serve
- Serve CLI: https://tailscale.com/docs/reference/tailscale-cli/serve
- Invite external users: https://tailscale.com/docs/features/sharing/how-to/invite-any-user
- Inviting vs sharing: https://tailscale.com/docs/reference/inviting-vs-sharing
- Tailnet policy: https://tailscale.com/docs/features/tailnet-policy-file
- Grants syntax: https://tailscale.com/docs/reference/syntax/grants
- Microsoft Set-NetConnectionProfile: https://learn.microsoft.com/powershell/module/netconnection/set-netconnectionprofile
- Microsoft New-NetFirewallRule: https://learn.microsoft.com/powershell/module/netsecurity/new-netfirewallrule

外部サービスの画面・コマンド仕様は変更される可能性があります。公開後も参照日を明記し、定期的に更新してください。
