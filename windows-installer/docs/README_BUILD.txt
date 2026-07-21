配布用インストーラーの作成方法
================================

完成物
------
release\MusicLibrary-Setup-2.6.1-x64.exe

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
4. Python不要のMusicLibrary.exeを作成
5. 空の音楽フォルダで起動検査
6. Inno SetupでSetup.exeを作成
7. releaseフォルダを開く

配布前の確認
------------
別のWindowsユーザーまたは仮想PCで、次を確認してください。

・インストールできる
・初回に音楽フォルダを選べる
・曲を検索・再生できる
・終了後に再起動できる
・上書き更新でlibrary.dbが残る
・アンインストール後も利用者データが残る

Windows SmartScreen
-------------------
コード署名をしていないSetup.exeは「不明な発行元」と表示される可能性があります。
これはインストーラー形式だけでは解消できません。
広く一般公開する段階ではコードサイニング証明書を検討してください。


v2.6.1の追加確認
----------------
・外部接続ボタンが表示される
・Tailscale未導入時に公式ページを開ける
・ログイン済み環境でServe URLを取得できる
・外部接続を停止できる
・スタートメニューの「外部接続を設定」が動く
・自動起動タスクを選択できる

追加テスト成功表示:
Remote entry-path tests passed.
