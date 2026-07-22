# 自宅音楽ライブラリ v2.6.2

公開済みのv2.6.1を変更せず、配布ドキュメントとRelease構成の不統一を修正したメンテナンスリリースです。

## v2.6.2の変更内容

- アプリ、インストーラー、Windowsファイル情報を`2.6.2`へ更新
- 利用者向け・ビルド向け・外部接続向け・GitHub Release向け文書をv2.6.2基準へ統一
- Release Assetsへ次の説明書を必ず含めるよう修正
  - `REMOTE_ACCESS_USER.txt`
  - `REMOTE_ACCESS_FAMILY.txt`
- 配布元パッケージから`__pycache__`と`.pyc`を除外
- GitHub Release作成手順と確認資料をv2.6.2へ更新

## 引き続き含まれる外部接続修正

- 外部URL末尾へ`/music-library-search.html`を自動追加
- 旧形式のルートURLを完全なアプリURLへ補正
- Tailscale ServeのルートURLからアプリ画面へ自動転送
- `remote-url.txt`へ完全なアプリURLを保存

## 正しい外部URL

```text
https://PC名.tailnet名.ts.net/music-library-search.html
```

## 更新方法

v2.6.1以前をアンインストールせず、v2.6.2のインストーラーをそのまま実行して上書き更新できます。

次の利用者データは保持されます。

```text
音楽フォルダ設定
library.db
再生回数
表記補正
アートワークキャッシュ
バックアップ
ログ
Tailscale Serve設定
外部接続URL
```

## 外部接続

Tailscale Serveを使用します。次は使用しません。

```text
ルーターのポート開放
Tailscale Funnel
インターネットへの直接公開
```

## 対応環境

- Windows 10 64bit
- Windows 11 64bit
