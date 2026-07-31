# 自宅音楽ライブラリ v2.7.0 インストーラービルド一式

Windows 10／11 64bit向け`MusicLibrary-Setup-2.7.0-x64.exe`を作成するための一式です。

## v2.7.0

- DBスキーマ5
- ローカルオーナー認証
- Tailscale利用者識別
- 利用者別再生回数・最終再生日時・お気に入り
- お気に入りのみフィルター
- 利用者管理
- ローカルオーナーと本人Tailscaleプロフィールの関連付け
- 既存個人状態の安全な統合
- 移行・関連付け前バックアップ

## ビルド

短いパスへ展開して、次を実行します。

```text
00_build_installer.bat
```

完成物:

```text
release\MusicLibrary-Setup-2.7.0-x64.exe
release\BUILD_REPORT_v2.7.0_RC2.txt
```

正式リリースで使用したRC2は製品バージョン2.7.0です。RC2という名称はビルド候補の区別で、インストール後の製品表示は2.7.0です。

## 更新

旧版をアンインストールせず上書きします。利用者データは`%LOCALAPPDATA%\MusicLibrary`にあり、インストール先とは別です。

## 公開前

- 全回帰テスト
- バンドル済みEXEスモーク
- Inno Setupコンパイル
- SHA-256
- 実運用DB移行
- ローカルオーナー
- Tailscale利用者
- オーナー関連付け・状態統合

詳細は`RELEASE_NOTES_v2.7.0.md`と`docs`を参照してください。
