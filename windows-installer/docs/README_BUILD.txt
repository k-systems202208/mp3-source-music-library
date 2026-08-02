自宅音楽ライブラリ v2.7.2
配布用インストーラーの作成方法
================================

位置づけ
--------
このソースは、実機確認済みv2.7.2 RC1と同じ機能コードを使用します。
正式Release準備では、README・利用ガイド・Release文書を最新化した後、
同じ回帰試験とビルドを再実行します。

完成物
------
release\MusicLibrary-Setup-2.7.2-x64.exe
release\MusicLibrary-Setup-2.7.2-x64_SHA256.txt
release\BUILD_REPORT_v2.7.2_RC1.txt
release\BUILD_LOG_v2.7.2_RC1.txt

ビルド報告のRC1表記は、正式リリースの基準になった候補番号を示します。
アプリ本体とインストーラーの製品バージョンは2.7.2です。

必要なもの
----------
・Windows 10または11 64bit
・64bit版Python 3
・Inno Setup 6または7

Pythonがない場合:
02_install_python.bat

Inno Setupがない場合:
01_install_inno_setup.bat

ビルド
------
短いパス（例 C:\ML272Build）へ配置し、
00_build_installer.batをダブルクリックします。

自動実行する内容:
1. パッケージSHA-256検証
2. Windows BATのBOM・改行・パス検査
3. ビルド用仮想環境の作成
4. PyInstallerの導入
5. Pythonソースのコンパイル検査
6. 全機能の回帰試験
7. スキーマv6・利用者別スキン保存の検査
8. 6スキンのUI・レスポンシブ・視認性検査
9. v2.7.2のバージョン整合性検査
10. Python不要のMusicLibrary.exe作成
11. EXEのバージョン情報確認
12. 空の音楽フォルダを使った起動試験
13. Inno SetupによるSetup.exe作成
14. Setup.exeのSHA-256とビルド報告作成

成功時:
BUILD COMPLETED

公開前には、作成したSetup.exeをv2.7.1へ上書きインストールし、
MANUAL_TEST_v2.7.2.txtの実機項目を確認します。
