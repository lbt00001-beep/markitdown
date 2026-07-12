from __future__ import annotations

import ctypes
import json
import logging
import multiprocessing
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen


APP_NAME = "MarkItDown Dashboard"
HOST = "127.0.0.1"
PORT = 8765
LOCAL_APP_DIR = Path(os.getenv("LOCALAPPDATA", Path.home())) / APP_NAME
RUN_DIR = LOCAL_APP_DIR / "run"
STATE_FILE = RUN_DIR / "launcher-state.json"
LOG_FILE = RUN_DIR / "app.log"
BROWSER_PROFILE = RUN_DIR / "browser-profile"


def show_error(message: str) -> None:
    ctypes.windll.user32.MessageBoxW(0, message, APP_NAME, 0x10)


def read_state() -> dict[str, Any]:
    try:
        value = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_state(state: dict[str, Any]) -> None:
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    temporary = STATE_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps(state), encoding="utf-8")
    temporary.replace(STATE_FILE)


def read_health(port: int) -> dict[str, Any] | None:
    try:
        with urlopen(f"http://{HOST}:{port}/api/health", timeout=0.8) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return payload if isinstance(payload, dict) else None
    except (OSError, URLError, ValueError):
        return None


def taskkill(pid: int) -> None:
    if pid <= 0:
        return
    subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )


def choose_port() -> int:
    for port in range(PORT, PORT + 50):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
            try:
                candidate.bind((HOST, port))
            except OSError:
                continue
            return port

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as candidate:
        candidate.bind((HOST, 0))
        return int(candidate.getsockname()[1])


def browser_profile_pids() -> list[int]:
    profile = str(BROWSER_PROFILE).replace("'", "''")
    command = (
        f"$profile='{profile}'; "
        "Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | "
        "Where-Object { $_.Name -in @('chrome.exe','msedge.exe') -and $_.CommandLine -like ('*' + $profile + '*') } | "
        "Select-Object -ExpandProperty ProcessId"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", command],
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    return [int(value) for value in completed.stdout.split() if value.isdigit()]


def close_previous_instance() -> None:
    state = read_state()
    if not state:
        return

    old_port = int(state.get("port") or PORT)
    old_instance_id = str(state.get("instance_id") or "")
    health = read_health(old_port)
    same_instance = bool(health and health.get("instance_id") == old_instance_id)

    if same_instance:
        request = Request(
            f"http://{HOST}:{old_port}/api/shutdown",
            method="POST",
            headers={"X-Shutdown-Token": str(state.get("shutdown_token") or "")},
        )
        try:
            with urlopen(request, timeout=1.5):
                pass
        except (OSError, URLError):
            pass

        for _ in range(25):
            if read_health(old_port) is None:
                break
            time.sleep(0.1)
        else:
            taskkill(int(state.get("pid") or 0))

    for browser_pid in browser_profile_pids():
        taskkill(browser_pid)

    try:
        STATE_FILE.unlink()
    except OSError:
        pass


def browser_candidates() -> list[Path]:
    program_files = Path(os.getenv("ProgramFiles", "C:/Program Files"))
    program_files_x86 = Path(os.getenv("ProgramFiles(x86)", "C:/Program Files (x86)"))
    local_app_data = Path(os.getenv("LOCALAPPDATA", ""))
    return [
        program_files / "Google/Chrome/Application/chrome.exe",
        local_app_data / "Google/Chrome/Application/chrome.exe",
        program_files / "Microsoft/Edge/Application/msedge.exe",
        program_files_x86 / "Microsoft/Edge/Application/msedge.exe",
    ]


def open_browser(url: str) -> int | None:
    browser = next((candidate for candidate in browser_candidates() if candidate.exists()), None)
    if browser is None:
        os.startfile(url)
        return None

    process = subprocess.Popen(
        [
            str(browser),
            f"--app={url}",
            f"--user-data-dir={BROWSER_PROFILE}",
            "--no-first-run",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
        close_fds=True,
    )
    return process.pid


def open_when_ready(instance_id: str, state: dict[str, Any], port: int, url: str) -> None:
    for _ in range(150):
        health = read_health(port)
        if health and health.get("instance_id") == instance_id:
            state["browser_pid"] = open_browser(url)
            write_state(state)
            return
        time.sleep(0.1)

    show_error(f"La aplicacion no pudo abrirse. Revisa el registro:\n{LOG_FILE}")


def main() -> int:
    multiprocessing.freeze_support()
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    close_previous_instance()

    port = choose_port()
    url = f"http://{HOST}:{port}"

    instance_id = secrets.token_hex(16)
    shutdown_token = secrets.token_urlsafe(32)
    os.environ["MARKITDOWN_INSTANCE_ID"] = instance_id
    os.environ["MARKITDOWN_SHUTDOWN_TOKEN"] = shutdown_token

    state: dict[str, Any] = {
        "pid": os.getpid(),
        "port": port,
        "instance_id": instance_id,
        "shutdown_token": shutdown_token,
        "browser_pid": None,
    }
    write_state(state)

    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=True,
    )

    try:
        from app.main import app
        import uvicorn

        opener = threading.Thread(
            target=open_when_ready,
            args=(instance_id, state, port, url),
            daemon=True,
        )
        opener.start()
        server = uvicorn.Server(
            uvicorn.Config(app, host=HOST, port=port, log_config=None, access_log=False)
        )
        server.run()
        return 0
    except Exception:
        logging.exception("No se pudo iniciar la aplicacion")
        show_error(f"No se pudo iniciar la aplicacion. Revisa:\n{LOG_FILE}")
        return 1
    finally:
        current = read_state()
        if current.get("instance_id") == instance_id:
            try:
                STATE_FILE.unlink()
            except OSError:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
