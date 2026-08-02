自宅音楽ライブラリ v2.7.3
配布用インストーラーの作成方法
================================

位置づけ
--------
このソースは、実機確認済みv2.7.3 RC1と同じ機能コードを使用します。
正式Release準備ではREADME・利用ガイド・Release文書を最新化した後、
同じ回帰試験とビルドを再実行します。

完成物
------
release\MusicLibrary-Setup-2.7.3-x64.exe
release\MusicLibrary-Setup-2.7.3-x64_SHA256.txt
release\BUILD_REPORT_v2.7.3_RC1.txt
release\BUILD_LOG_v2.7.3_RC1.txt

必要なもの
----------
・Windows 10または11 64bit
・64bit版Python 3
・Inno Setup 6または7

ビルド
------
短いパス（例 C:\ML273Build）へ配置し、
00_build_installer.batをダブルクリックします。

自動実行する内容:
1. パッケージSHA-256検証
2. Windows BATのBOM・改行・パス検査
3. Pythonソースのコンパイル検査
4. 全機能の回帰試験
5. スキーマv6・スキン保存の検査
6. PWAマニフェスト・アイコン・キャッシュ安全性検査
7. ホーム画面追加案内・接続表示検査
8. スマートフォンのレスポンシブ表示検査
9. PWA静的ファイルのMIMEとキャッシュヘッダー検査
10. v2.7.3のバージョン整合性検査
11. Python不要のMusicLibrary.exe作成
12. 空の音楽フォルダを使った起動試験
13. Inno SetupによるSetup.exe作成
14. Setup.exeのSHA-256とビルド報告作成

成功時:
BUILD COMPLETED
