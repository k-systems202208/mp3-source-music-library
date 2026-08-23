# 旧ソースに関する注意

このリポジトリには、現行のWindows製品ソースと、開発途中の履歴として残している旧ソースの両方が含まれています。

## 現行製品ソースの正本

現行製品では、次のディレクトリをソースの正本として使用します。

```text
windows-installer/src/
```

リリースビルド、Windowsランチャー、サーバー、データベース実装、ブラウザUI、テスト、PyInstaller構成、インストーラーは、すべて `windows-installer/` 配下で保守します。

統合された実装仕様の正本は次です。

```text
docs/23-reimplementation-detailed-design.md
```

## リポジトリ直下の履歴ソース

リポジトリ直下には、プロジェクトの以前の段階を記録するため、現行ソースと似た名前のファイルが残っています。これらは現行製品を変更する際のソース正本ではありません。

| リポジトリ直下の履歴資産 | 現行製品ソース |
|---|---|
| `database.py` | `windows-installer/src/database.py` |
| `generate-library.py` | `windows-installer/src/generator.py` |
| `serve-library.py` | `windows-installer/src/server.py` |
| `music-library-search.html` | `windows-installer/src/music-library-search.html` |
| `templates/` | 現行UIは `windows-installer/src/` から同梱 |
| `vendor/` | `windows-installer/src/vendor/` |

旧版だからという理由だけで、これらの履歴ファイルを削除しません。また、旧版履歴や互換性を明示的に対象とする作業でない限り、現行製品の修正をこれらへ適用しません。

ドキュメントまたはリポジトリ直下の履歴ファイルと現行実装が食い違う場合は、`windows-installer/src/` 配下の実装と現行テストを確認してください。
