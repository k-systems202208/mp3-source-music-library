# 利用マニュアル

## 1. 必要なもの

- Windows PC
- Python 3
- ChromeまたはEdge等
- MP3
- スマホ利用時は同一Wi-FiまたはTailscale

## 2. 初回導入

1. ZIPを展開
2. `Music`へMP3をコピー
3. `start-music-library.bat`を実行
4. 初回解析を待つ
5. 自動で開いたブラウザを使用

例:

```text
Music/
├─ Artist A/
│  └─ Album A/
│     ├─ 01 - Song.mp3
│     └─ folder.jpg
└─ Artist B/
   └─ Song.mp3
```

黒い画面はサーバーです。使用中は閉じないでください。

## 3. 通常起動

```text
start-music-library.bat
```

- MP3追加・削除・変更確認
- SQLite更新
- 日次バックアップ
- ブラウザ起動

変更がないMP3は再解析しません。

## 4. MP3の追加・移動・削除

### 追加

`Music`へ追加し、再起動します。

### 移動・改名

`Music`内で変更して再起動します。内容署名が一意一致すればID、再生回数、補正を維持します。

### 削除

画面から消えますが、DBでは`is_available=0`として履歴を残します。

## 5. 検索・表示

曲タブは曲名、アーティスト、アルバム、作曲者を検索します。

表示タブ:

- 曲
- アーティスト
- アルバム

## 6. 索引

```text
0-9 A B C ... Z
あ か さ た な は ま や ら わ 漢字・他
```

該当0件は無効です。TSOT／TSOP／TSOAがあれば読みを使います。

`The Beatles`はB、`A Day in the Life`はDです。

## 7. 絞り込み・表示順

絞り込み:

- 英数字タイトルのみ
- 訂正済のみ

表示順:

- 曲名
- アーティスト
- アルバム
- 再生回数
- 追加日

アルバム内はディスク・トラック番号順です。

## 8. 再生

曲カードの再生ボタンを押します。

プレーヤー:

- 再生・一時停止
- シーク
- 音量
- 前曲・次曲
- シャッフル
- リピート
- 1曲
- 最大化

最大化はアートワーク、曲名部分、最大化ボタンから開きます。×、背景、Escで閉じ、再生は継続します。

## 9. 再生モード

### シャッフル

再生開始時点の検索・索引・アーティスト・アルバム範囲を、重複なしで一巡します。

### リピート

対象範囲末尾から先頭へ戻ります。

### 1曲

同じ曲を繰り返します。

リピートと1曲は排他です。設定はブラウザごとに保存されます。

### 前へ

- 5秒超: 現曲先頭
- 5秒以内: 前曲

## 10. 表記補正

### 曲名

鉛筆ボタンから補正します。SQLiteへ保存し、MP3タグは変更しません。空欄または元値で解除します。

### アーティスト

同じartist_idの全曲へ反映します。

## 11. 再生回数・複数利用者

新しい曲の再生開始で1増えます。一時停止再開では増えません。

複数端末は別曲を独立再生できます。

共有:

- 再生回数
- 曲名補正
- アーティスト補正

端末別:

- 再生中曲
- 再生位置
- 音量
- シャッフル・リピート
- 検索状態

## 12. 音質

MP3をそのまま配信するため、サーバー処理による音質劣化はありません。低速時はバッファリングします。Bluetooth再圧縮は端末側の事情です。

## 13. 同一Wi-Fiへ公開

### 固定ポート

`templates/start-music-library-lan.bat`をアプリへコピーするか、通常BATを次のように変更します。

```bat
set "PORT=8765"
set "URL=http://127.0.0.1:%PORT%/%HTML_FILE%"
...
%PYTHON_CMD% "%~dp0%SERVER%" --host 0.0.0.0 --port %PORT%
```

### IP確認

```powershell
ipconfig
```

例: `192.168.1.25`

### ネットワーク確認

```powershell
Get-NetConnectionProfile
```

自宅Wi-Fiで管理者権限がある場合:

```powershell
Set-NetConnectionProfile -InterfaceIndex <番号> -NetworkCategory Private
```

### Private用ファイアウォール

```powershell
New-NetFirewallRule `
  -DisplayName "Music Library LAN 8765" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8765 `
  -Profile Private `
  -RemoteAddress LocalSubnet4
```

### Privateへ変更できない場合

Group Policy等でPublicのままなら:

```powershell
New-NetFirewallRule `
  -DisplayName "Music Library LAN 8765 Public" `
  -Direction Inbound `
  -Action Allow `
  -Protocol TCP `
  -LocalPort 8765 `
  -Profile Public `
  -RemoteAddress LocalSubnet4
```

使用後:

```powershell
Disable-NetFirewallRule -DisplayName "Music Library LAN 8765 Public"
```

再開:

```powershell
Enable-NetFirewallRule -DisplayName "Music Library LAN 8765 Public"
```

### スマホ

```text
http://192.168.1.25:8765/api/health
http://192.168.1.25:8765/music-library-search.html
```

同じ通常Wi-Fiを使い、ゲストWi-Fiは避けます。

## 14. 外出先から利用

### Tailscale導入

- PCとスマホへTailscale
- 同じtailnetへ参加
- PCは必要に応じてRun Unattended

### 固定ローカルポート

Tailscale専用なら`templates/start-music-library-local-fixed.bat`を推奨します。

```bat
--host 127.0.0.1 --port 8765
```

### Serve

```powershell
tailscale serve --bg 8765
tailscale serve status
```

URL:

```text
https://PC名.tailnet名.ts.net/music-library-search.html
```

### 外部ユーザー招待

```text
Users
→ Invite external users
→ Role: Member
```

承認後、必要ならユーザー・端末をApproveします。

### 招待された側

1. Tailscaleアプリ
2. 招待承認と同じアカウント
3. VPN構成許可
4. 招待先tailnet
5. Connected
6. HTTPS URLを開く

### モバイル回線確認

```text
Wi-Fi: オフ
モバイル通信: オン
Tailscale: Connected
```

### ホーム画面

iOS: Safari → 共有 → ホーム画面に追加  
Android: Chrome → ︙ → ホーム画面に追加

## 15. アクセス制限

外部Memberは既定ポリシー次第で他端末へ接続できます。[運用・セキュリティ設計](07-operations-security.md)のGrants例で音楽PC:443だけへ制限してください。

## 16. バックアップ

自動:

```text
Backups/library-YYYYMMDD.db
```

手動:

```text
backup-library.bat
```

MP3は含まれません。

## 17. 保守

```powershell
py -3 library-maintenance.py stats
py -3 library-maintenance.py check
py -3 library-maintenance.py backup
py -3 library-maintenance.py export
```

サーバー停止後:

```powershell
py -3 library-maintenance.py vacuum
```

## 18. 終了

黒い画面でCtrl+Cまたは閉じます。

Serve設定削除:

```powershell
tailscale serve reset
```

Firewall削除:

```powershell
Remove-NetFirewallRule -DisplayName "Music Library LAN 8765"
```
