#!/usr/bin/env python3
from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import webbrowser

import remote_access
from datetime import datetime
from pathlib import Path
from typing import Any

APP_NAME = "自宅音楽ライブラリ"
APP_VERSION = "2.6.2"
APP_ID = "MusicLibrary"
DEFAULT_PORT = 8765


def default_data_root() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data).expanduser().resolve() / APP_ID
    return Path.home().resolve() / f".{APP_ID.casefold()}"


def atomic_write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def free_port(preferred: int = DEFAULT_PORT) -> int:
    for port in (preferred, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                continue
            return int(sock.getsockname()[1])
    raise RuntimeError("利用できるローカルポートが見つかりませんでした。")


def health_ok(url: str) -> bool:
    if not url:
        return False
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/health", timeout=1.0) as response:
            return response.status == 200
    except Exception:
        return False


def worker_main(args: argparse.Namespace) -> int:
    music_root = Path(args.music_root).expanduser().resolve()
    data_root = Path(args.data_root).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    log_dir = data_root / "Logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "launcher.log"
    runtime_path = data_root / "runtime.json"

    os.environ["MUSIC_LIBRARY_MUSIC_DIR"] = str(music_root)
    os.environ["MUSIC_LIBRARY_DATA_DIR"] = str(data_root)
    os.environ["PYTHONUTF8"] = "1"
    os.environ["PYTHONIOENCODING"] = "utf-8"
    os.environ["PYTHONDONTWRITEBYTECODE"] = "1"

    with log_path.open("a", encoding="utf-8", buffering=1) as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
        print()
        print("=" * 72)
        print(f"{APP_NAME} {APP_VERSION}")
        print(f"開始時刻: {datetime.now().isoformat(timespec='seconds')}")
        print(f"音楽フォルダ: {music_root}")
        print(f"データ保存先: {data_root}")
        print("=" * 72)

        if not music_root.is_dir():
            message = f"音楽フォルダが見つかりません: {music_root}"
            print(f"ERROR: {message}")
            atomic_write_json(runtime_path, {"state": "error", "message": message, "pid": os.getpid()})
            return 2

        try:
            atomic_write_json(runtime_path, {
                "state": "scanning",
                "pid": os.getpid(),
                "musicRoot": str(music_root),
                "startedAt": datetime.now().isoformat(timespec="seconds"),
            })

            import generator

            result = int(generator.main() or 0)
            if result != 0:
                message = f"ライブラリ更新が終了コード {result} で停止しました。"
                atomic_write_json(runtime_path, {"state": "error", "message": message, "pid": os.getpid()})
                return result

            if args.scan_only:
                atomic_write_json(runtime_path, {"state": "scan_completed", "pid": os.getpid()})
                print("スキャンのみを完了しました。")
                return 0

            import server as music_server

            port = free_port(args.port)
            httpd = music_server.create_server("127.0.0.1", port)
            url = f"http://127.0.0.1:{port}/music-library-search.html"
            atomic_write_json(runtime_path, {
                "state": "running",
                "pid": os.getpid(),
                "port": port,
                "url": url,
                "musicRoot": str(music_root),
                "startedAt": datetime.now().isoformat(timespec="seconds"),
            })
            print(f"ブラウザURL: {url}")
            print("このアプリを終了するまで音楽ライブラリを利用できます。")

            if not args.no_browser:
                threading.Timer(0.6, lambda: webbrowser.open(url)).start()

            try:
                httpd.serve_forever(poll_interval=0.5)
            finally:
                httpd.server_close()
            return 0
        except Exception as exc:
            message = f"{type(exc).__name__}: {exc}"
            print(f"ERROR: {message}")
            atomic_write_json(runtime_path, {"state": "error", "message": message, "pid": os.getpid()})
            return 1
        finally:
            current = read_json(runtime_path)
            if int(current.get("pid") or 0) == os.getpid() and current.get("state") == "running":
                try:
                    runtime_path.unlink()
                except OSError:
                    pass


class LauncherWindow:
    def __init__(self, auto_remote_setup: bool = False) -> None:
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.tk = tk
        self.ttk = ttk
        self.filedialog = filedialog
        self.messagebox = messagebox

        self.data_root = default_data_root()
        self.data_root.mkdir(parents=True, exist_ok=True)
        self.config_path = self.data_root / "config.json"
        self.runtime_path = self.data_root / "runtime.json"
        self.log_path = self.data_root / "Logs" / "launcher.log"
        self.config = read_json(self.config_path)
        self.process: subprocess.Popen[Any] | None = None
        self.last_log_size = 0
        self.current_url = ""
        self.remote_url = str(self.config.get("remoteUrl") or "")
        self.remote_busy = False
        self.auto_remote_setup = auto_remote_setup
        self.auto_remote_setup_started = False

        self.root = tk.Tk()
        self.root.title(f"{APP_NAME} {APP_VERSION}")
        self.root.geometry("780x690")
        self.root.minsize(700, 590)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        main = ttk.Frame(self.root, padding=18)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text=APP_NAME, font=("Yu Gothic UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            main,
            text="MP3フォルダを選ぶだけで、ブラウザから検索・再生できます。",
            font=("Yu Gothic UI", 10),
        ).pack(anchor="w", pady=(2, 14))

        folder_frame = ttk.LabelFrame(main, text="音楽フォルダ", padding=10)
        folder_frame.pack(fill="x")
        self.folder_var = tk.StringVar(value=str(self.config.get("musicRoot") or "未設定"))
        ttk.Label(folder_frame, textvariable=self.folder_var, wraplength=610).pack(side="left", fill="x", expand=True)
        ttk.Button(folder_frame, text="変更", command=self.choose_music_folder).pack(side="right", padx=(10, 0))

        button_frame = ttk.Frame(main)
        button_frame.pack(fill="x", pady=14)
        self.start_button = ttk.Button(button_frame, text="ライブラリを開始", command=self.start_library)
        self.start_button.pack(side="left")
        self.open_button = ttk.Button(button_frame, text="ブラウザで開く", command=self.open_browser, state="disabled")
        self.open_button.pack(side="left", padx=8)
        self.stop_button = ttk.Button(button_frame, text="停止", command=self.stop_library, state="disabled")
        self.stop_button.pack(side="left")
        ttk.Button(button_frame, text="データ保存先を開く", command=self.open_data_folder).pack(side="right")

        remote_frame = ttk.LabelFrame(main, text="外部接続（Tailscale）", padding=10)
        remote_frame.pack(fill="x", pady=(0, 12))
        self.remote_status_var = tk.StringVar(value="状態を確認しています…")
        ttk.Label(
            remote_frame,
            textvariable=self.remote_status_var,
            wraplength=710,
            font=("Yu Gothic UI", 9),
        ).pack(anchor="w", fill="x")

        remote_buttons = ttk.Frame(remote_frame)
        remote_buttons.pack(fill="x", pady=(8, 0))
        self.remote_setup_button = ttk.Button(
            remote_buttons,
            text="外部接続をかんたん設定",
            command=self.setup_remote_access,
        )
        self.remote_setup_button.pack(side="left")
        self.remote_open_button = ttk.Button(
            remote_buttons,
            text="外部URLを開く",
            command=self.open_remote_access,
            state="disabled",
        )
        self.remote_open_button.pack(side="left", padx=8)
        self.remote_stop_button = ttk.Button(
            remote_buttons,
            text="外部接続を停止",
            command=self.stop_remote_access,
            state="disabled",
        )
        self.remote_stop_button.pack(side="left")
        ttk.Button(
            remote_buttons,
            text="Tailscale／ヘルプ",
            command=self.open_remote_help,
        ).pack(side="right")

        self.status_var = tk.StringVar(value="準備完了")
        ttk.Label(main, textvariable=self.status_var, font=("Yu Gothic UI", 10, "bold")).pack(anchor="w", pady=(0, 6))

        self.log_text = tk.Text(main, height=12, wrap="word", state="disabled", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)

        ttk.Label(
            main,
            text="この画面を閉じるとローカルサーバーも停止します。MP3ファイル自体は変更しません。",
            font=("Yu Gothic UI", 9),
        ).pack(anchor="w", pady=(8, 0))

        self.root.after(300, self.initial_action)
        self.root.after(500, self.poll_status)
        self.root.after(700, self.poll_log)
        self.root.after(1200, self.refresh_remote_status)

    def save_config(self) -> None:
        atomic_write_json(self.config_path, self.config)

    def initial_action(self) -> None:
        music_root = str(self.config.get("musicRoot") or "")
        if music_root and Path(music_root).is_dir():
            self.start_library()
            return
        self.messagebox.showinfo(
            APP_NAME,
            "最初に、MP3ファイルが入っているフォルダを選択します。\n\n"
            "音楽ファイルはコピーも変更もされません。",
        )
        self.choose_music_folder(auto_start=True)

    def choose_music_folder(self, auto_start: bool = False) -> None:
        current = str(self.config.get("musicRoot") or Path.home())
        selected = self.filedialog.askdirectory(
            title="MP3ファイルが入っている音楽フォルダを選択",
            initialdir=current if Path(current).is_dir() else str(Path.home()),
            mustexist=True,
        )
        if not selected:
            return
        path = str(Path(selected).resolve())
        self.config["musicRoot"] = path
        self.config.setdefault("port", DEFAULT_PORT)
        self.save_config()
        self.folder_var.set(path)
        self.append_log(f"音楽フォルダを設定しました: {path}\n")
        if auto_start:
            self.start_library()

    def worker_command(self, music_root: str) -> list[str]:
        args = [
            "--worker",
            "--music-root", music_root,
            "--data-root", str(self.data_root),
            "--port", str(int(self.config.get("port") or DEFAULT_PORT)),
        ]
        if getattr(sys, "frozen", False):
            return [sys.executable, *args]
        return [sys.executable, str(Path(__file__).resolve()), *args]

    def start_library(self) -> None:
        music_root = str(self.config.get("musicRoot") or "")
        if not music_root or not Path(music_root).is_dir():
            self.choose_music_folder(auto_start=True)
            return

        runtime = read_json(self.runtime_path)
        existing_url = str(runtime.get("url") or "")
        if health_ok(existing_url):
            self.current_url = existing_url
            self.status_var.set("実行中")
            self.set_running_controls(True)
            webbrowser.open(existing_url)
            return

        try:
            self.runtime_path.unlink()
        except OSError:
            pass

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.log_path.write_text("", encoding="utf-8")
        self.last_log_size = 0
        self.status_var.set("MP3を確認しています…")
        self.set_running_controls(True, starting=True)

        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.process = subprocess.Popen(
            self.worker_command(music_root),
            cwd=str(Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).parent),
            creationflags=flags,
        )

    def set_running_controls(self, running: bool, starting: bool = False) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")
        self.open_button.configure(state="normal" if running and not starting else "disabled")

    def poll_status(self) -> None:
        runtime = read_json(self.runtime_path)
        state = str(runtime.get("state") or "")
        if state == "running":
            url = str(runtime.get("url") or "")
            if health_ok(url):
                self.current_url = url
                self.status_var.set("実行中 — ブラウザで利用できます")
                self.set_running_controls(True)
                if self.auto_remote_setup and not self.auto_remote_setup_started:
                    self.auto_remote_setup_started = True
                    self.root.after(500, self.setup_remote_access)
        elif state == "scanning":
            self.status_var.set("MP3を確認してライブラリを更新しています…")
            self.set_running_controls(True, starting=True)
        elif state == "error":
            self.status_var.set("エラーが発生しました。下の内容を確認してください。")
            self.set_running_controls(False)
        elif state == "scan_completed":
            self.status_var.set("スキャンが完了しました。")
            self.set_running_controls(False)

        if self.process is not None and self.process.poll() is not None:
            if state not in {"error", "scan_completed"}:
                self.status_var.set("停止しました")
                self.set_running_controls(False)
            self.process = None

        self.root.after(700, self.poll_status)

    def poll_log(self) -> None:
        try:
            size = self.log_path.stat().st_size
            if size != self.last_log_size:
                text = self.log_path.read_text(encoding="utf-8", errors="replace")
                self.log_text.configure(state="normal")
                self.log_text.delete("1.0", "end")
                self.log_text.insert("end", text[-30000:])
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
                self.last_log_size = size
        except OSError:
            pass
        self.root.after(900, self.poll_log)

    def append_log(self, text: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", text)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def run_remote_task(self, task: Any, done: Any) -> None:
        if self.remote_busy:
            return
        self.remote_busy = True
        self.remote_setup_button.configure(state="disabled")

        def worker() -> None:
            try:
                result = task()
                error: Exception | None = None
            except Exception as exc:  # pragma: no cover - defensive UI boundary
                result = None
                error = exc
            self.root.after(0, lambda: finish(result, error))

        def finish(result: Any, error: Exception | None) -> None:
            self.remote_busy = False
            self.remote_setup_button.configure(state="normal")
            if error is not None:
                self.remote_status_var.set("外部接続の確認中にエラーが発生しました。")
                self.messagebox.showerror(APP_NAME, f"{type(error).__name__}: {error}")
                return
            done(result)

        threading.Thread(target=worker, daemon=True).start()

    def apply_remote_status(self, status: remote_access.RemoteStatus) -> None:
        if not status.installed:
            self.remote_status_var.set(
                "Tailscaleは未インストールです。『外部接続をかんたん設定』から公式ページを開けます。"
            )
            self.remote_open_button.configure(state="disabled")
            self.remote_stop_button.configure(state="disabled")
            return

        if not status.logged_in:
            self.remote_status_var.set(
                "Tailscaleはインストール済みですが、ログインが必要です。"
            )
            self.remote_open_button.configure(state="disabled")
            self.remote_stop_button.configure(state="disabled")
            return

        if status.serve_active and status.serve_url:
            self.remote_url = status.serve_url
            self.config["remoteUrl"] = self.remote_url
            self.save_config()
            remote_access.save_remote_url(self.data_root, self.remote_url)
            self.remote_status_var.set(f"外部接続は有効です：{self.remote_url}")
            self.remote_open_button.configure(state="normal")
            self.remote_stop_button.configure(state="normal")
            return

        self.remote_status_var.set(
            "Tailscaleへ接続済みです。外部接続はまだ有効になっていません。"
        )
        self.remote_open_button.configure(state="disabled")
        self.remote_stop_button.configure(state="disabled")

    def refresh_remote_status(self) -> None:
        if self.remote_busy:
            return
        self.remote_status_var.set("Tailscaleの状態を確認しています…")
        self.run_remote_task(remote_access.get_remote_status, self.apply_remote_status)

    def setup_remote_access(self) -> None:
        runtime = read_json(self.runtime_path)
        if runtime.get("state") != "running" or not health_ok(str(runtime.get("url") or "")):
            music_root = str(self.config.get("musicRoot") or "")
            if not music_root or not Path(music_root).is_dir():
                self.messagebox.showwarning(
                    APP_NAME,
                    "最初に音楽フォルダを設定し、ライブラリを開始してください。",
                )
                self.choose_music_folder(auto_start=True)
                self.auto_remote_setup = True
                return
            self.auto_remote_setup = True
            self.start_library()
            self.messagebox.showinfo(
                APP_NAME,
                "ライブラリの起動完了後に、外部接続の設定を続けます。",
            )
            return

        status = remote_access.get_remote_status()
        if not status.installed:
            if self.messagebox.askyesno(
                APP_NAME,
                "外部接続にはTailscaleが必要です。\n\n"
                "Tailscale公式のダウンロードページを開きますか？\n"
                "インストールとログイン後、もう一度このボタンを押してください。",
            ):
                remote_access.open_download_page()
            self.apply_remote_status(status)
            return

        if not status.logged_in:
            remote_access.launch_tailscale_ui()
            self.messagebox.showinfo(
                APP_NAME,
                "Windows右下のTailscaleアイコンからログインしてください。\n\n"
                "ログイン完了後、『外部接続をかんたん設定』をもう一度押します。",
            )
            self.apply_remote_status(status)
            return

        port = int(runtime.get("port") or self.config.get("port") or DEFAULT_PORT)
        self.remote_status_var.set("Tailscale Serveを設定しています…")

        def done(result: remote_access.EnableResult) -> None:
            if result.ok and result.url:
                self.remote_url = result.url
                self.config["remoteUrl"] = result.url
                self.save_config()
                remote_access.save_remote_url(self.data_root, result.url)
                self.remote_status_var.set(f"外部接続は有効です：{result.url}")
                self.remote_open_button.configure(state="normal")
                self.remote_stop_button.configure(state="normal")
                webbrowser.open(result.url)
                self.messagebox.showinfo(
                    APP_NAME,
                    "外部接続を有効にしました。\n\n"
                    f"接続URL：\n{result.url}\n\n"
                    "スマートフォンにもTailscaleを入れ、同じアカウントで接続してください。",
                )
                return

            if result.consent_url:
                webbrowser.open(result.consent_url)
                self.remote_status_var.set("Tailscaleの許可が必要です。ブラウザで許可してください。")
                self.messagebox.showinfo(
                    APP_NAME,
                    "ブラウザでTailscale Serveの利用を許可してください。\n\n"
                    "許可後、『外部接続をかんたん設定』をもう一度押します。",
                )
                return

            self.remote_status_var.set("外部接続を有効にできませんでした。")
            self.messagebox.showerror(APP_NAME, result.message or "設定に失敗しました。")

        self.run_remote_task(lambda: remote_access.enable_remote_access(port), done)

    def open_remote_access(self) -> None:
        url = remote_access.build_remote_app_url(
            self.remote_url or str(self.config.get("remoteUrl") or "")
        )
        if url:
            self.remote_url = url
            self.config["remoteUrl"] = url
            self.save_config()
            remote_access.save_remote_url(self.data_root, url)
            webbrowser.open(url)
            return
        self.refresh_remote_status()
        self.messagebox.showwarning(APP_NAME, "有効な外部接続URLが見つかりません。")

    def stop_remote_access(self) -> None:
        if not self.messagebox.askyesno(
            APP_NAME,
            "Tailscaleの外部接続を停止しますか？\n\n"
            "PC内のローカル利用は停止しません。",
        ):
            return
        self.remote_status_var.set("外部接続を停止しています…")

        def done(result: remote_access.CommandResult) -> None:
            if result.returncode == 0:
                self.remote_url = ""
                self.config.pop("remoteUrl", None)
                self.save_config()
                try:
                    (self.data_root / "remote-url.txt").unlink()
                except OSError:
                    pass
                self.remote_status_var.set("外部接続は停止しています。")
                self.remote_open_button.configure(state="disabled")
                self.remote_stop_button.configure(state="disabled")
                return
            self.remote_status_var.set("外部接続の停止に失敗しました。")
            self.messagebox.showerror(APP_NAME, result.output or "停止に失敗しました。")

        self.run_remote_task(remote_access.disable_remote_access, done)

    def open_remote_help(self) -> None:
        help_path = Path(sys.executable).resolve().parent / "REMOTE_ACCESS_USER.txt"
        if help_path.is_file() and os.name == "nt":
            os.startfile(str(help_path))  # type: ignore[attr-defined]
            return
        remote_access.open_download_page()

    def open_browser(self) -> None:
        runtime = read_json(self.runtime_path)
        url = str(runtime.get("url") or self.current_url)
        if health_ok(url):
            webbrowser.open(url)
        else:
            self.messagebox.showwarning(APP_NAME, "ライブラリは現在起動していません。")

    def open_data_folder(self) -> None:
        self.data_root.mkdir(parents=True, exist_ok=True)
        if os.name == "nt":
            os.startfile(str(self.data_root))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(["xdg-open", str(self.data_root)])

    def stop_library(self, ask: bool = False) -> bool:
        if ask and not self.messagebox.askyesno(APP_NAME, "音楽ライブラリを停止して終了しますか？"):
            return False
        runtime = read_json(self.runtime_path)
        pid = int(runtime.get("pid") or 0)
        try:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()
                try:
                    self.process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.process.kill()
            elif pid > 0 and pid != os.getpid():
                os.kill(pid, signal.SIGTERM)
        except (OSError, ProcessLookupError):
            pass
        self.process = None
        try:
            self.runtime_path.unlink()
        except OSError:
            pass
        self.current_url = ""
        self.remote_url = str(self.config.get("remoteUrl") or "")
        self.remote_busy = False
        self.auto_remote_setup = auto_remote_setup
        self.auto_remote_setup_started = False
        self.status_var.set("停止しました")
        self.set_running_controls(False)
        return True

    def on_close(self) -> None:
        runtime = read_json(self.runtime_path)
        if runtime.get("state") in {"running", "scanning"}:
            if not self.stop_library(ask=True):
                return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--music-root", default="")
    parser.add_argument("--data-root", default=str(default_data_root()))
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--scan-only", action="store_true")
    parser.add_argument("--version", action="store_true")
    parser.add_argument("--remote-setup", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.version:
        print(APP_VERSION)
        return 0
    if args.worker:
        if not args.music_root:
            print("--music-root is required", file=sys.stderr)
            return 2
        return worker_main(args)
    LauncherWindow(auto_remote_setup=args.remote_setup).run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
