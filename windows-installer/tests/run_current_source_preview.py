from __future__ import annotations

import argparse
import json
import os
import secrets
import shutil
import sqlite3
import sys
import tempfile
import threading
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"


def default_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        return Path(local_app_data) / "MusicLibrary"
    return Path.home() / ".musiclibrary"


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (FileNotFoundError, UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def copy_database(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_connection = sqlite3.connect(
        f"{source.resolve().as_uri()}?mode=ro",
        timeout=30.0,
        uri=True,
    )
    target_connection = sqlite3.connect(destination, timeout=30.0)
    try:
        source_connection.backup(target_connection)
        target_connection.commit()
    finally:
        target_connection.close()
        source_connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview the current source with a copied MusicLibrary database."
    )
    parser.add_argument(
        "--data-root",
        default=str(default_data_root()),
        help="Installed MusicLibrary data directory",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify preview startup without opening a browser",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    live_data_root = Path(args.data_root).expanduser().resolve()
    live_database = live_data_root / "library.db"
    config = load_json(live_data_root / "config.json")
    music_value = str(config.get("musicRoot") or "").strip()

    if not live_database.is_file():
        print(f"ERROR: ライブラリDBが見つかりません: {live_database}")
        print("先にインストール済みアプリでライブラリを開始してください。")
        return 2
    if not music_value:
        print(f"ERROR: 音楽フォルダー設定が見つかりません: {live_data_root / 'config.json'}")
        return 2

    music_root = Path(music_value).expanduser().resolve()
    if not music_root.is_dir():
        print(f"ERROR: 音楽フォルダーが見つかりません: {music_root}")
        return 2

    preview_root = Path(tempfile.mkdtemp(prefix="music-library-current-source-preview-"))
    preview_database = preview_root / "library.db"
    httpd = None
    try:
        print("確認用DBを作成しています…")
        copy_database(live_database, preview_database)

        os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(preview_root)
        os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)
        os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
        sys.path.insert(0, str(SRC))

        import server  # noqa: E402

        httpd = server.create_server(
            "127.0.0.1",
            0,
            owner_control_secret=secrets.token_urlsafe(48),
        )
        port = int(httpd.server_address[1])
        one_time_token = secrets.token_urlsafe(32)
        httpd.local_owner_auth.register_one_time_token(
            one_time_token,
            ttl_seconds=120,
        )

        preview_path = "/music-library-search.html?pwaPreview=1"
        query = urllib.parse.urlencode(
            {"token": one_time_token, "next": preview_path}
        )
        owner_url = f"http://127.0.0.1:{port}/api/local-auth/exchange?{query}"
        non_owner_url = f"http://localhost:{port}{preview_path}"

        if args.check_only:
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/api/health",
                    timeout=10,
                ) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    if response.status != 200 or payload.get("ok") is not True:
                        raise RuntimeError(f"preview health check failed: {payload}")
            finally:
                httpd.shutdown()
                thread.join(timeout=10)
            print("確認用バッチの起動チェックに合格しました。")
            return 0

        print()
        print("修正版の確認画面を2つ開きます。")
        print("  1. オーナー画面: 曲名・アーティスト名の編集ボタンあり")
        print("  2. 非オーナー画面: 編集ボタンなし")
        print()
        print("確認項目:")
        print("  - 『訂正済のみ』ボタンと『訂正済』表示がない")
        print("  - オーナー画面だけ編集ボタンが表示される")
        print("  - プレイヤーのアーティスト名・アルバム名から一覧へ移動できる")
        print()
        print(f"確認用DB: {preview_database}")
        print("変更は確認用DBだけへ保存され、終了時に削除されます。")
        print("埋め込みアートワークは確認用画面では表示されない場合があります。")
        print("終了するには、この画面で Ctrl+C を押してください。")

        webbrowser.open(owner_url, new=2)
        time.sleep(1.0)
        webbrowser.open(non_owner_url, new=2)

        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n確認用サーバーを終了します。")
        return 0
    finally:
        if httpd is not None:
            httpd.server_close()
        shutil.rmtree(preview_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
