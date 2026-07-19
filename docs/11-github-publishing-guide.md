# GitHub公開ガイド

## 1. 公開目的

GitHubには次を公開します。

- ソースコード
- 起動BAT
- README
- 設計書
- テンプレート
- Mutagenライセンス
- 空の`Music/.gitkeep`

個人の音楽ライブラリは公開しません。

## 2. 推奨リポジトリ構成

```text
mp3-source-music-library/
├─ README.md
├─ LICENSE
├─ .gitignore
├─ Music/
│  └─ .gitkeep
├─ docs/
├─ screenshots/
├─ vendor/
│  └─ mutagen/
├─ database.py
├─ generate-library.py
├─ serve-library.py
├─ music-library-search.html
├─ library-maintenance.py
├─ start-music-library.bat
├─ backup-library.bat
├─ export-library-json.bat
└─ vendor/MUTAGEN_LICENSE.txt
```

## 3. 絶対に公開しないもの

- MP3・その他音源
- `library.db*`
- `.artwork-cache`
- `Backups`
- `Exports`
- `legacy-library-data.json`
- 診断CSV／JSON
- 実際のアートワーク
- Tailscale IP、tailnet名
- 家族のメールアドレス
- Windowsユーザー名を含むフルパス

## 4. 公開前クリーンコピー

実利用フォルダをそのままGit管理しないことを推奨します。

1. 新しい公開用フォルダを作る
2. ソースと文書だけコピー
3. `Music`を空にする
4. private dataがないことを検索
5. Git初期化

PowerShell例:

```powershell
Get-ChildItem -Recurse -Force |
  Where-Object {
    $_.Name -match 'library\.db|\.mp3$|legacy-library-data|diagnostics'
  }
```

## 5. Git初期化

```powershell
git init
git add .
git status
```

`git status`でMP3、DB、Backupsが表示されないことを確認してから:

```powershell
git commit -m "Initial public release of MP3 Source Music Library v2.4"
git branch -M main
git remote add origin <GitHub repository URL>
git push -u origin main
```

## 6. ライセンス

プロジェクト本体のライセンスは公開者が決めます。

一般例:

- MIT: 再利用しやすい
- Apache-2.0: 特許条項を含む
- GPL-3.0: 派生物にも同じ自由を要求
- ライセンスなし: 権利は留保され、他者は原則再利用できない

選択するまでは、READMEに「Project license not yet selected」と明記します。

Mutagenのライセンスは別であり、`vendor/MUTAGEN_LICENSE.txt`を削除しません。

## 7. Release ZIP

Releaseへ含める前にクリーンなZIPを作成します。

含める:

- プログラム
- 空のMusic
- README
- ライセンス

除外:

- DB
- MP3
- キャッシュ
- 診断
- バックアップ
- 個人設定

ZIPを別フォルダへ展開し、MP3を数曲だけ自分で追加して起動試験します。

## 8. スクリーンショット

推奨画像:

1. 曲一覧
2. アーティスト索引
3. アルバム一覧
4. 最大化プレーヤー
5. スマホ表示
6. システム構成図

注意:

- 市販アートワークは権利物
- 自作ダミー画像を推奨
- 実曲名を隠すか、権利上問題のない音源を使用
- IP・メール・フルパスを消す

`screenshots/README.md`の撮影チェックを使います。

## 9. READMEで明示すること

- 個人利用向け
- MP3は同梱しない
- Python 3が必要
- Windows中心
- アプリ内認証なし
- 外部利用はTailscale推奨
- ポート開放禁止
- 音源の権利は利用者が管理
- v2.4時点の制限

## 10. Issueテンプレートに求める情報

不具合報告:

- OS
- Pythonバージョン
- ブラウザ
- アプリ版
- 曲数
- 再現手順
- `/api/health`
- Consoleエラー
- 診断カテゴリ
- 個人情報を消したログ

MP3本体やDBを公開Issueへ添付しないよう明記します。

## 11. セキュリティ報告

`SECURITY.md`を用意し、次を明記すると安全です。

- 公開IssueへDB・音源を添付しない
- 認証がないことは仕様
- 公開インターネット運用は非対応
- 脆弱性報告用の非公開連絡方法

## 12. noteとの連携

note記事からGitHubへ誘導する場合:

- GitHub README: 技術・導入の正本
- note: 開発経緯・考え方・スクリーンショット
- 詳細なネットワーク・ACLはGitHub文書へリンク
- Release ZIPの直リンクよりReleaseページを案内
- 「MP3は含まれない」と本文に明記

## 13. 公開前最終チェック

- [ ] `git status`にMP3なし
- [ ] DBなし
- [ ] legacy JSONなし
- [ ] 診断なし
- [ ] Backupsなし
- [ ] 実アートワークなし
- [ ] メール・IPなし
- [ ] Mutagenライセンスあり
- [ ] 本体ライセンス方針あり
- [ ] クリーン環境で起動
- [ ] READMEの版がv2.4
- [ ] schema versionが4
- [ ] Release ZIPを再展開して確認
