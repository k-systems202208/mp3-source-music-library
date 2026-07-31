from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import launcher


# A browser page URL and a server root URL must both resolve to the same
# health endpoint. Queries and fragments must not leak into the endpoint.
assert launcher.build_health_url(
    "http://127.0.0.1:8765/music-library-search.html"
) == "http://127.0.0.1:8765/api/health"
assert launcher.build_health_url(
    "http://127.0.0.1:8765/"
) == "http://127.0.0.1:8765/api/health"
assert launcher.build_health_url(
    "https://music.example.ts.net/music-library-search.html?x=1#player"
) == "https://music.example.ts.net/api/health"
assert launcher.build_health_url("") == ""
assert launcher.build_health_url("not-a-url") == ""

requested_urls: list[str] = []
original_urlopen = launcher.urllib.request.urlopen


class FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def fake_urlopen(url: str, timeout: float):
    requested_urls.append(url)
    assert timeout == 1.0
    return FakeResponse()


try:
    launcher.urllib.request.urlopen = fake_urlopen
    assert launcher.health_ok(
        "http://127.0.0.1:8765/music-library-search.html"
    )
finally:
    launcher.urllib.request.urlopen = original_urlopen

assert requested_urls == ["http://127.0.0.1:8765/api/health"]


class StatusVar:
    def __init__(self) -> None:
        self.value = ""

    def set(self, value: str) -> None:
        self.value = value


class DummyLauncher:
    pass


with tempfile.TemporaryDirectory() as temp_dir:
    dummy = DummyLauncher()
    dummy.runtime_path = Path(temp_dir) / "runtime.json"
    dummy.process = None
    dummy.current_url = "http://127.0.0.1:8765/music-library-search.html"
    dummy.config = {"remoteUrl": "https://music.example.ts.net/music-library-search.html"}
    dummy.remote_url = ""
    dummy.remote_busy = True
    dummy.auto_remote_setup = True
    dummy.auto_remote_setup_started = True
    dummy.status_var = StatusVar()
    dummy.controls = None

    def set_running_controls(running: bool, starting: bool = False) -> None:
        dummy.controls = (running, starting)

    dummy.set_running_controls = set_running_controls

    assert launcher.LauncherWindow.stop_library(dummy, ask=False)
    assert dummy.process is None
    assert dummy.current_url == ""
    assert dummy.remote_url == dummy.config["remoteUrl"]
    assert dummy.remote_busy is False
    assert dummy.auto_remote_setup is False
    assert dummy.auto_remote_setup_started is False
    assert dummy.status_var.value == "停止しました"
    assert dummy.controls == (False, False)

html_source = (SRC / "music-library-search.html").read_text(encoding="utf-8")
assert "start-music-library.bat" not in html_source
assert "管理画面へ戻り" in html_source
assert "スタートメニューの「自宅音楽ライブラリ」" in html_source

print("Launcher stability regression tests passed.")
