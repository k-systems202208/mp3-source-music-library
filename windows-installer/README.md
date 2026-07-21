# 自宅音楽ライブラリ v2.6.1 インストーラービルド一式

## 主な変更

- 管理画面へ「外部接続（Tailscale）」を追加
- Tailscaleの導入状態・ログイン状態・Serve状態を自動確認
- ローカルサーバーの実際のポートをTailscale Serveへ自動設定
- 外部HTTPS URLを自動取得・保存・ブラウザ表示
- 外部接続の停止ボタン
- スタートメニューへ「外部接続を設定」を追加
- インストール時にWindowsログイン時の自動起動を任意選択
- Tailscale本体は同梱せず、常に公式最新版を利用

## ビルド

`00_build_installer.bat`をダブルクリックします。

完成物：

`release\MusicLibrary-Setup-2.6.1-x64.exe`

## 更新

v2.5.1と同じAppIdを使用しているため、通常はアンインストール不要です。
新しいSetup.exeを実行すると上書き更新され、library.dbと設定は維持されます。
