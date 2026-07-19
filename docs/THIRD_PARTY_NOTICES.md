# 第三者ソフトウェア

## Mutagen

本アプリはMP3のID3タグ、再生時間、埋め込みアートワークを解析するため、Mutagenを`vendor/mutagen`へ同梱しています。

公開・再配布時は、アプリに含まれる次のファイルを保持してください。

```text
vendor/MUTAGEN_LICENSE.txt
```

Mutagenの正確なライセンス条件は、同梱ライセンス本文を正本としてください。

## Python標準ライブラリ

主に次を使用します。

- sqlite3
- http.server
- pathlib
- hashlib
- json
- csv
- urllib.parse

Python自体をアプリへ同梱していない場合、利用者がPythonを別途インストールします。

## プロジェクト本体

プロジェクト本体のライセンスは公開者が別途選択してください。第三者ライセンスとプロジェクト本体ライセンスは別です。
