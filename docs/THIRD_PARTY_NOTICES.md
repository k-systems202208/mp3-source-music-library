# Third-Party Notices

自宅音楽ライブラリv2.7.7は、ビルドまたは実行時に第三者ソフトウェアを利用します。ライセンス本文・配布条件は各プロジェクトの正式なライセンスを優先します。

## 主な構成

- Python
- Mutagen
- PyInstaller
- PyInstaller Hooks Contrib
- Inno Setup
- SQLite（Python標準ライブラリ経由）
- Tcl/Tk（Windows管理画面の実行環境）

Windows配布パッケージに含めるMutagenのライセンス参照:

```text
windows-installer/docs/MUTAGEN_LICENSE.txt
```

ビルド時に取得される依存関係は`windows-installer/build/requirements-build.txt`とビルドログで確認してください。

この文書は第三者ライセンスの全文を置き換えるものではありません。再配布時は、実際に同梱されるバイナリとライセンス通知をビルド成果物で確認してください。
