# 自宅音楽ライブラリ v2.6.1

外部接続URLの入口パスを修正したメンテナンスリリースです。

## 修正内容

- 「外部URLを開く」がTailscale ServeのルートURLだけを開き、404になる問題を修正
- 外部URLへ `/music-library-search.html` を自動追加
- 保存済みのv2.6.0形式URLも、開く際に自動補正
- `https://PC名.tailnet名.ts.net/` を開いた場合も、アプリ画面へ自動転送
- 外部URLファイルへ完全なアプリURLを保存
- URL正規化とルート転送のビルドテストを追加

## 正しい外部URL

```text
https://PC名.tailnet名.ts.net/music-library-search.html
```

## 更新方法

旧版をアンインストールせず、v2.6.1のインストーラーをそのまま実行して上書き更新できます。
音楽フォルダ、SQLite、再生回数、表記補正、Tailscale Serve設定は保持されます。
