自宅音楽ライブラリ v2.6.2
配布用インストーラーの作成方法
================================

完成物
------
release\MusicLibrary-Setup-2.6.2-x64.exe

この1ファイルを利用者へ配布します。
利用者側にPythonやInno Setupは不要です。

初回だけ必要なもの
------------------
1. 64bit版Python 3
2. Inno Setup 6または7

Pythonがない場合:
02_install_python.bat

Inno Setupがない場合:
01_install_inno_setup.bat

ビルド
------
00_build_installer.batをダブルクリックします。

自動実行される処理:
1. ビルド専用Python環境を作成
2. PyInstallerを導入
3. Pythonソースを検査
4. v2.6.2の構成とバージョンを検査
5. 通信切断処理を検査
6. Tailscale外部接続処理を検査
7. 外部URL入口パスを検査
8. Python不要のMusicLibrary.exeを作成
9. 空の音楽フォルダで起動検査
10. Inno SetupでSetup.exeを作成
11. releaseフォルダを開く

成功時の主な表示
----------------
Build sanity check passed.
Client disconnect tests passed.
Remote access parsing tests passed.
Remote entry-path tests passed.
BUILD COMPLETED

配布前の基本確認
----------------
・インストールできる
・管理画面にv2.6.2と表示される
・初回に音楽フォルダを選べる
・曲を検索・再生・シークできる
・シャッフルとリピートが動作する
・上書き更新でlibrary.dbが残る
・アンインストール後も利用者データが残る
・WinError 10054のTracebackが表示されない

v2.6.2 外部接続確認
-------------------
・管理画面に外部接続欄が表示される
・Tailscale未導入時に公式ページを開ける
・ログイン済み環境でServe URLを取得できる
・外部URLが次の形式で表示される

https://PC名.tailnet名.ts.net/music-library-search.html

・外部URLを開くボタンで404にならない
・ルートURLからアプリ画面へ転送される
・外部接続を停止できる
・スタートメニューの「外部接続を設定」が動く
・自動起動オプションを選択できる

Windows SmartScreen
-------------------
コード署名していないSetup.exeは
「不明な発行元」と表示される可能性があります。

インストーラー形式にしただけでは解消できません。
広く一般公開する場合はコードサイニング証明書を検討してください。
