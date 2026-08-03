自宅音楽ライブラリ v2.7.6
ビルド手順
================================

前提
----
・Windows 10／11 64bit
・Python 3.13系
・Inno Setup 6
・Git
・短い作業パス
・インターネット接続（依存取得時）

推奨配置
--------
C:\ML276Build

実行
----
00_build_installer.bat

処理
----
1. パッケージマニフェスト確認
2. Python仮想環境作成
3. PyInstaller依存導入
4. 全ソース回帰試験
5. PyInstallerで実行ファイル作成
6. 組み込みEXEスモーク試験
7. Inno Setupでインストーラー作成
8. SHA-256、BUILD LOG、BUILD REPORT作成

成果物
------
release\MusicLibrary-Setup-2.7.6-x64.exe
release\MusicLibrary-Setup-2.7.6-x64_SHA256.txt
release\BUILD_LOG_v2.7.6.txt
release\BUILD_REPORT_v2.7.6.txt

整合性
------
・launcher、paths、update checker、server、EXE metadata、installerが2.7.6
・database SCHEMA_VERSIONが7
・Service Workerが本番プレイリストUIの更新を反映
・Release Notesと利用者文書が2.7.6

注意
----
・長い作業パスはPyInstaller等の障害要因になるため避ける
・ビルド中に実運用DBやMP3を参照・変更しない
・テスト失敗時はインストーラーを公開しない
・RC文書は履歴であり、正式版の現行文書を優先
・公開済みの過去タグを移動せず、Release Assetsを暗黙差替えしない
