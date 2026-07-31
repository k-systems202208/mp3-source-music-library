自宅音楽ライブラリ v2.7.0 RC2
配布用インストーラーの作成方法
================================

完成物
------
release\MusicLibrary-Setup-2.7.0-x64.exe
release\MusicLibrary-Setup-2.7.0-x64_SHA256.txt
release\BUILD_REPORT_v2.7.0_RC2.txt

初回だけ必要なもの
------------------
・64bit版Python 3
・Inno Setup 6または7

Pythonがない場合:
02_install_python.bat

Inno Setupがない場合:
01_install_inno_setup.bat

ビルド
------
00_build_installer.batをダブルクリックします。

自動実行する内容:
1. ビルド用仮想環境を作成
2. PyInstallerを導入
3. Pythonソースをコンパイル検査
4. v2.7.0 RC構成検査
5. 全機能の回帰テスト
6. Python不要のMusicLibrary.exeを作成
7. EXEのバージョン表示を確認
8. 空の音楽フォルダで新規DB起動検査
9. Inno SetupでSetup.exeを作成
10. Setup.exeのSHA-256とビルド報告を作成

成功時:
BUILD COMPLETED

このRC2では、ビルド成功後もまだSetup.exeをインストールしません。
次工程で上書き更新手順を確認します。
