# 自宅音楽ライブラリ v2.7.1 RC2 ビルドパッケージ

このパッケージは、公開済みv2.7.0を土台に、次の機能を統合したv2.7.1 RC2インストーラーを作成します。

- ライブラリホーム
- ローカルオーナー向けバックアップ・復元画面
- GitHub公開済みRelease（プレリリース設定を含む）の新版通知

## 実行場所

Windowsの短いパスへ展開してください。

```text
C:\ML271RC2
```

長いパスやクラウド同期フォルダーは、PyInstallerの処理で失敗する原因になるため避けてください。

## ビルド

`00_build_installer.bat`を実行します。

正常終了時は`release`フォルダーに次が作成されます。

- `MusicLibrary-Setup-2.7.1-x64.exe`
- `MusicLibrary-Setup-2.7.1-x64_SHA256.txt`
- `BUILD_REPORT_v2.7.1_RC2.txt`
- `BUILD_LOG_v2.7.1_RC2.txt`

ビルド直後はインストールせず、完了画面または`BUILD_REPORT_v2.7.1_RC2.txt`を確認します。

## 補助ファイル

- Pythonがない場合：`02_install_python.bat`
- Inno Setupがない場合：`01_install_inno_setup.bat`
- 正式リリース用ファイルの準備：`03_prepare_release_assets.bat`（RC確認後に使用）

## 重要事項

- 公開済みのv2.7.0タグとGitHub Releaseは変更しません。
- `library.db`、MP3、実運用設定はこのビルドパッケージに含まれません。
- v2.7.0からv2.7.1への更新では、既存の利用者別再生回数・お気に入り・設定を引き継ぎます。
- スキーマ5への旧版移行用バックアップ名`library-pre-v2.7.0-*`は、履歴上の仕様として変更していません。

## RC2での修正

RC1実機確認で、公開済みReleaseがすべてGitHub上のプレリリース設定だったため、`/releases/latest`がHTTP 404を返すことを確認しました。RC2では公開済みRelease一覧を取得し、下書きを除外したうえで最も新しいセマンティックバージョンを選択します。
