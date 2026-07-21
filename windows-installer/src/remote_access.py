#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

TAILSCALE_DOWNLOAD_URL = "https://tailscale.com/download/windows"
TAILSCALE_ADMIN_MACHINES_URL = "https://login.tailscale.com/admin/machines"
EXPECTED_SERVE_SCHEME = "https://"
REMOTE_APP_PATH = "/music-library-search.html"


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    output: str


@dataclass(frozen=True)
class RemoteStatus:
    installed: bool
    logged_in: bool
    backend_state: str
    serve_active: bool
    serve_url: str
    tailscale_path: str
    detail: str = ""


@dataclass(frozen=True)
class EnableResult:
    ok: bool
    url: str = ""
    message: str = ""
    consent_url: str = ""


def _decode_output(data: bytes) -> str:
    for encoding in ("utf-8", "cp932", "mbcs"):
        try:
            return data.decode(encoding)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _creation_flags() -> int:
    if os.name != "nt":
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0))


def find_tailscale_executable() -> Path | None:
    found = shutil.which("tailscale.exe") or shutil.which("tailscale")
    if found:
        return Path(found).resolve()

    candidates: list[Path] = []
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Tailscale" / "tailscale.exe")

    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def find_tailscale_ui() -> Path | None:
    cli = find_tailscale_executable()
    candidates: list[Path] = []
    if cli:
        candidates.append(cli.parent / "tailscale-ipn.exe")
    for env_name in ("ProgramFiles", "ProgramFiles(x86)"):
        base = os.environ.get(env_name)
        if base:
            candidates.append(Path(base) / "Tailscale" / "tailscale-ipn.exe")
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def run_tailscale(arguments: list[str], timeout: float = 25.0) -> CommandResult:
    executable = find_tailscale_executable()
    if not executable:
        return CommandResult(127, "Tailscale is not installed.")

    try:
        completed = subprocess.run(
            [str(executable), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            creationflags=_creation_flags(),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = _decode_output(exc.stdout or b"")
        return CommandResult(124, output + "\nCommand timed out.")
    except OSError as exc:
        return CommandResult(126, f"{type(exc).__name__}: {exc}")

    return CommandResult(completed.returncode, _decode_output(completed.stdout or b""))


def parse_backend_state(status_json: str) -> str:
    try:
        data: Any = json.loads(status_json)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    value = data.get("BackendState")
    return str(value or "")


def parse_serve_url(text: str) -> str:
    match = re.search(r"https://[A-Za-z0-9.-]+(?:/)?", text)
    return match.group(0).rstrip("/") if match else ""


def build_remote_app_url(base_url: str) -> str:
    """Return the complete browser URL for the music-library page."""
    cleaned = str(base_url or "").strip().rstrip("/")
    if not cleaned:
        return ""
    if cleaned.endswith(REMOTE_APP_PATH):
        return cleaned
    return cleaned + REMOTE_APP_PATH


def parse_consent_url(text: str) -> str:
    urls = re.findall(r"https://[^\s<>'\"]+", text)
    for url in urls:
        cleaned = url.rstrip(".,);]")
        if ".ts.net" not in cleaned:
            return cleaned
    return ""


def get_remote_status() -> RemoteStatus:
    executable = find_tailscale_executable()
    if not executable:
        return RemoteStatus(False, False, "NotInstalled", False, "", "")

    status_result = run_tailscale(["status", "--json"], timeout=12.0)
    backend_state = parse_backend_state(status_result.output)
    logged_in = status_result.returncode == 0 and backend_state.casefold() == "running"

    serve_result = run_tailscale(["serve", "status"], timeout=12.0)
    serve_url = build_remote_app_url(parse_serve_url(serve_result.output))
    serve_active = serve_result.returncode == 0 and bool(serve_url)

    detail_parts = []
    if status_result.returncode != 0:
        detail_parts.append(status_result.output.strip())
    if serve_result.returncode != 0 and serve_result.output.strip():
        detail_parts.append(serve_result.output.strip())

    return RemoteStatus(
        installed=True,
        logged_in=logged_in,
        backend_state=backend_state or "Unknown",
        serve_active=serve_active,
        serve_url=serve_url,
        tailscale_path=str(executable),
        detail="\n".join(part for part in detail_parts if part),
    )


def enable_remote_access(port: int) -> EnableResult:
    status = get_remote_status()
    if not status.installed:
        return EnableResult(False, message="Tailscaleがインストールされていません。")
    if not status.logged_in:
        return EnableResult(False, message="Tailscaleへのログインが必要です。")

    result = run_tailscale(["serve", "--bg", str(int(port))], timeout=30.0)
    if result.returncode != 0:
        return EnableResult(
            False,
            message=result.output.strip() or "Tailscale Serveを有効にできませんでした。",
            consent_url=parse_consent_url(result.output),
        )

    current = get_remote_status()
    url = current.serve_url or build_remote_app_url(parse_serve_url(result.output))
    if not url:
        return EnableResult(
            False,
            message="外部接続は有効になりましたが、HTTPS URLを取得できませんでした。",
        )
    return EnableResult(True, url=url, message="外部接続を有効にしました。")


def disable_remote_access() -> CommandResult:
    return run_tailscale(["serve", "off"], timeout=20.0)


def launch_tailscale_ui() -> bool:
    ui = find_tailscale_ui()
    if not ui:
        return False
    try:
        subprocess.Popen([str(ui)], creationflags=_creation_flags())
        return True
    except OSError:
        return False


def open_download_page() -> None:
    webbrowser.open(TAILSCALE_DOWNLOAD_URL)


def open_admin_machines_page() -> None:
    webbrowser.open(TAILSCALE_ADMIN_MACHINES_URL)


def save_remote_url(data_root: Path, url: str) -> Path:
    path = data_root / "remote-url.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    normalized = build_remote_app_url(url)
    path.write_text(normalized + "\n", encoding="utf-8")
    return path
