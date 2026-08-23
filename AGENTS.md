# リポジトリ編集ルール

## 現行製品ソースの正本

現行Windows製品のソース正本は `windows-installer/src/` です。

現行製品を変更する場合は、`windows-installer/` 配下の実装と `docs/` 配下の現行ドキュメントを編集します。リポジトリ直下にある同名のPython、HTML、バッチ、template、vendor等は、明示的に旧版・履歴を対象とする作業を除き、現行実装として編集しません。

特に、次のリポジトリ直下ファイル・フォルダーを現行製品の実装元として使用しません。

- `database.py`
- `generate-library.py`
- `serve-library.py`
- `music-library-search.html`
- `templates/`
- `vendor/`

現行製品では次を使用します。

- DB、検索、利用者、プレイリスト: `windows-installer/src/database.py`
- 走査・生成: `windows-installer/src/generator.py`
- HTTP/API: `windows-installer/src/server.py`
- ブラウザUI: `windows-installer/src/music-library-search.html`
- 同梱依存・静的資産: `windows-installer/src/vendor/` および `windows-installer/src/`
- ランチャー、ビルド、リリース: `windows-installer/`

リポジトリ直下の履歴ファイルと現行実装が食い違う場合は、`windows-installer/` 配下の現行実装を優先します。

## ドキュメントの言語

このリポジトリで新規作成・更新するプロジェクト独自ドキュメントは、原則として日本語で記述します。

コード上の識別子、API名、製品名、コマンド、ファイル名など、原文の維持が必要なものは英語のままで構いません。また、MIT License等の第三者ライセンス原文は翻訳に置き換えず、そのまま保持します。

## ワンバッチ開発運用

通常のユーザー操作を伴うリポジトリ変更では、`docs/25-one-batch-workflow.md` のワンバッチ方式を優先します。

安全に1本の `.bat` へまとめられる作業について、ユーザーへ多数のGitコマンドを順番に実行させる方式は避けます。Merge、ブランチ削除等の取り消しにくい操作は、バッチ内で明示確認を取ります。

## v2.7.7開発基準点と必須テスト

v2.7.7の正常な比較基準点は `windows-installer/docs/DEVELOPMENT_BASELINE_v2.7.7.md` に記録しています。

新しい作業は最新のcleanな `main` から開始し、`feature/`、`fix/`、`maintenance/`、`docs/` 等の専用ブランチを作成します。現行開発内容を `main` へ直接Commitしません。

変更内容ごとの必須テストは `windows-installer/docs/TEST_MATRIX_v2.7.7.md` に従います。通常のコード変更では、対象領域の個別テストに加えて日常回帰確認をMerge前に実行します。正式リリース前は `windows-installer/00_build_installer.bat` を実行します。

## 現行動作を変更する前の確認

1. `docs/23-reimplementation-detailed-design.md` を読む。
2. `windows-installer/src/` 配下の対象となる現行ソースを確認する。
3. 変更対象サブシステムに対応するテストを実行する。
4. 通常の回帰確認として `windows-installer/06_verify_next_improvements.bat` を実行する。
5. 正式リリース前は `windows-installer/00_build_installer.bat` を実行する。

現行ソースに似せる目的だけで、リポジトリ直下の旧ファイルを削除・近代化しません。これらは履歴資産として保持します。
