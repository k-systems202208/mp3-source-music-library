# 自宅音楽ライブラリ v2.6.3 インストーラービルド一式

このパッケージは、Windows 10・11（64bit）向けの
「自宅音楽ライブラリ v2.6.3」インストーラーを作成するための一式です。

## v2.6.3の内容

新機能は追加せず、v2.6.2で確認された次の不具合を修正しています。

- 管理画面の起動状態確認URL
- 停止・終了時の未定義変数エラー
- ブラウザ上の旧バッチ版向け復旧案内
- Windowsの発行元表記を`k-systems202208`へ統一
- 上記不具合の再発防止テスト

従来の検索・再生・表記訂正・Tailscale外部接続機能はそのまま維持します。

## ビルド方法

```text
00_build_installer.bat
```

をダブルクリックします。

完成物：

```text
release\MusicLibrary-Setup-2.6.3-x64.exe
```

## v2.6.3への更新

v2.6.3は従来版と同じAppIdを使用しています。

通常は旧版をアンインストールせず、
`MusicLibrary-Setup-2.6.3-x64.exe`をそのまま実行して
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
docs\GITHUB_RELEASE_2.6.3.txt
```

を確認してください。
