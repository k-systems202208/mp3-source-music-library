# 自宅音楽ライブラリ v2.6.2 インストーラービルド一式

このパッケージは、Windows 10・11（64bit）向けの
「自宅音楽ライブラリ v2.6.2」インストーラーを作成するための一式です。

## v2.6.2の内容

- MP3を正本とする音楽ライブラリ
- SQLiteによる再生回数・表記補正・履歴管理
- ブラウザでの検索・再生・シーク
- シャッフル、全体リピート、1曲リピート
- WinError 10054など、ブラウザによる正常な通信切断の抑止
- 管理画面からのTailscale Serve設定
- 外部HTTPS URLの自動取得・保存
- 外部URL末尾の`/music-library-search.html`自動補正
- ルートURLからアプリ画面への自動転送
- Windowsログイン時の自動起動オプション

## ビルド方法

```text
00_build_installer.bat
```

をダブルクリックします。

完成物：

```text
release\MusicLibrary-Setup-2.6.2-x64.exe
```

## v2.6.2への更新

v2.6.2は従来版と同じAppIdを使用しています。

通常は旧版をアンインストールせず、
`MusicLibrary-Setup-2.6.2-x64.exe`をそのまま実行して
上書き更新できます。

次の利用者データは維持されます。

```text
音楽フォルダ設定
library.db
再生回数
表記補正
アートワークキャッシュ
バックアップ
ログ
外部接続URL
```

## 外部接続

正しい外部URL形式：

```text
https://PC名.tailnet名.ts.net/music-library-search.html
```

Tailscale Funnelやルーターのポート開放は使用しません。

## 配布前の確認

```text
docs\README_BUILD.txt
docs\GITHUB_RELEASE_2.6.2.txt
```

を確認してください。
