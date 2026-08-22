# v2.7.7 開発基準点

対象: 自宅音楽ライブラリ v2.7.7

## 1. 基準点

次の機能追加へ入る前の正常な v2.7.7 開発基準点を、以下の `main` commit とする。

```text
f5108d19f3a2369aa13ceb80d844ef3e866cfd35
```

このcommitは、v2.7.7の現行製品ソースに加え、再生回数仕様の明文化、旧ソース誤編集防止、日次回帰テスト強化、ワンバッチ開発運用の文書化まで反映した状態である。

この基準点以後に文書や開発運用だけを変更して `main` が進んでも、製品挙動の比較基準としてはこのcommitを参照できる。

## 2. 固定する製品条件

v2.7.7基準点では、少なくとも次を固定条件として扱う。

- 製品バージョン: `2.7.7`
- DB schema: `7`
- 現行製品ソース正本: `windows-installer/src/`
- Windows対象: Windows 10/11 x64
- PWA構成: `manifest.webmanifest`、`service-worker.js`、`offline.html`、PWAアイコンを配布物へ含める
- Windowsインストーラー: `MusicLibrary-Setup-2.7.7-x64.exe`

`tests/test_release_candidate.py` は、バージョン、schema、PWA、インストーラー定義、配布構成、必須回帰テストを整合性確認する。

## 3. 今後のブランチ運用

今後の機能追加・不具合修正・保守変更は、最新の正常な `main` から専用ブランチを作成する。

例:

```text
feature/<topic>
fix/<topic>
maintenance/<topic>
docs/<topic>
```

`main` へ直接Commitしない。

標準フローは次のとおり。

```text
最新main
  ↓
専用ブランチ
  ↓
変更
  ↓
変更内容に対応する必須テスト
  ↓
共通回帰
  ↓
Commit / Push
  ↓
Pull Request
  ↓
Merge
  ↓
main最新化 / 作業ブランチ削除
```

通常は `docs/25-one-batch-workflow.md` のワンバッチ方式でこの一連の処理を行う。

## 4. 変更前後の比較

不具合調査や大きな機能追加で「変更前は正常だったか」を確認する必要がある場合は、この基準点commitを比較対象として使用する。

例:

```text
git diff f5108d19f3a2369aa13ceb80d844ef3e866cfd35..HEAD
```

ただし、通常の開発開始地点は常に最新の `main` とし、基準点commitから直接新しいfeature branchを作成しない。

基準点は「比較のための正常状態」であり、「今後の分岐元を固定するための古いmain」ではない。

## 5. 次バージョンへの更新

v2.7.8以降を正式な新しい正常基準点とする時点で、この文書を新バージョン用に更新または後継文書を追加する。

新しい基準点を決める条件は次のとおり。

- 対象バージョンの回帰試験がすべて成功している。
- `00_build_installer.bat` が正常終了している。
- 実EXEスモーク試験が成功している。
- Inno Setupによる正式インストーラー作成が成功している。
- リリース候補整合性テストが成功している。
