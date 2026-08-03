自宅音楽ライブラリ v2.7.5
配布用インストーラーの作成方法
================================

位置づけ
--------
このソースは、実機確認済みv2.7.5 RC2と同じ機能コードを使用します。
正式Release準備ではREADME・利用ガイド・Release文書を最新化した後、
同じ回帰試験とビルドを再実行します。

完成物
------
release\MusicLibrary-Setup-2.7.5-x64.exe
release\MusicLibrary-Setup-2.7.5-x64_SHA256.txt
release\BUILD_REPORT_v2.7.5_RC2.txt
release\BUILD_LOG_v2.7.5_RC2.txt

必要なもの
----------
・Windows 10または11 64bit
・64bit版Python 3
・Inno Setup 6または7

ビルド
------
短いパス（例 C:\ML275Build）へ配置し、
00_build_installer.batをダブルクリックします。

自動実行する内容:
1. パッケージSHA-256検証
2. Windows BATのBOM・改行・パス検査
3. Pythonソースのコンパイル検査
4. 全機能の回帰試験
5. DBスキーマ7と移行前バックアップの検査
6. 利用者別プレイリストのDB・API・画面検査
7. 本番画面のプレビュー案内除去とスマートフォンタブ検査
8. バックアップ・復元の検査
9. PWA・スマートフォン表示の検査
10. 長いWindowsパスの走査・タグ・アートワーク・Range再生検査
11. 起動時オーナー認証の連続ハンドオフ検査
12. v2.7.5のバージョン整合性検査
13. Python不要のMusicLibrary.exe作成
14. 空の音楽フォルダを使った起動試験
15. Inno SetupによるSetup.exe作成
16. Setup.exeのSHA-256とビルド報告作成

成功時:
BUILD COMPLETED
