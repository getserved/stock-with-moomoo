import argparse
import json
import os
import signal
import subprocess
import sys
import threading
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
WATCHLIST_FILE = ROOT / "watchlist.txt"
SELECTED_FILE = ROOT / "selected_watchlist.json"
FLOATING_PID_FILE = ROOT / "floating_watchlist.pid"
FLOATING_SCRIPT = ROOT / "floating_watchlist.py"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

floating_process: subprocess.Popen | None = None
process_lock = threading.RLock()


def normalize_code(value: str) -> str:
    text = value.strip().upper()
    if not text:
        return ""
    if "." not in text:
        text = f"US.{text}"
    return text


def load_codes() -> list[str]:
    if not WATCHLIST_FILE.exists():
        return []
    codes = []
    for line in WATCHLIST_FILE.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        code = normalize_code(line)
        if code:
            codes.append(code)
    return codes


def write_codes(codes: list[str]) -> list[str]:
    normalized = []
    seen = set()
    for item in codes:
        code = normalize_code(str(item))
        if code and code not in seen:
            normalized.append(code)
            seen.add(code)
    WATCHLIST_FILE.write_text("\n".join(normalized) + ("\n" if normalized else ""), encoding="utf-8", newline="\n")
    payload = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "codes": normalized,
        "tickers": [code.replace("US.", "") for code in normalized],
    }
    SELECTED_FILE.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized


def process_alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def saved_floating_pid() -> int | None:
    try:
        return int(FLOATING_PID_FILE.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return None


def discovered_floating_pid() -> int | None:
    if sys.platform != "win32":
        return None
    command = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'python.exe'\" | "
        "Where-Object { $_.CommandLine -match 'floating_watchlist.py' } | "
        "Select-Object -First 1 -ExpandProperty ProcessId"
    )
    try:
        output = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", command],
            cwd=str(ROOT),
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=3,
        ).strip()
    except Exception:
        return None
    try:
        return int(output.splitlines()[0])
    except (IndexError, ValueError):
        return None


def floating_status() -> dict:
    global floating_process
    with process_lock:
        pid = floating_process.pid if floating_process and floating_process.poll() is None else saved_floating_pid()
        if not process_alive(pid):
            pid = discovered_floating_pid()
        if process_alive(pid):
            FLOATING_PID_FILE.write_text(str(pid), encoding="utf-8")
            return {"running": True, "pid": pid}
        FLOATING_PID_FILE.unlink(missing_ok=True)
        floating_process = None
        return {"running": False, "pid": None}


def start_floating() -> dict:
    global floating_process
    with process_lock:
        current = floating_status()
        if current["running"]:
            return {"started": False, "pid": current["pid"], "status": "already_running", "running": True}
        floating_process = subprocess.Popen(
            [sys.executable, str(FLOATING_SCRIPT)],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        FLOATING_PID_FILE.write_text(str(floating_process.pid), encoding="utf-8")
        return {"started": True, "pid": floating_process.pid, "status": "started", "running": True}


def stop_floating() -> dict:
    global floating_process
    with process_lock:
        pid = floating_process.pid if floating_process and floating_process.poll() is None else saved_floating_pid()
        if not process_alive(pid):
            FLOATING_PID_FILE.unlink(missing_ok=True)
            floating_process = None
            return {"stopped": False, "pid": None, "status": "not_running", "running": False}
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        FLOATING_PID_FILE.unlink(missing_ok=True)
        floating_process = None
        return {"stopped": True, "pid": pid, "status": "stopped", "running": False}


def toggle_floating() -> dict:
    return stop_floating() if floating_status()["running"] else start_floating()


class BridgeHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/health":
            self._send_json({"ok": True, "service": "local_watchlist_bridge"})
            return
        if path == "/watchlist":
            self._send_json({"ok": True, "codes": load_codes()})
            return
        if path == "/floating-status":
            self._send_json({"ok": True, "floating": floating_status()})
            return
        super().do_GET()

    def do_POST(self):
        path = urlparse(self.path).path
        if path not in {"/watchlist", "/open-floating", "/close-floating", "/toggle-floating"}:
            self.send_error(404)
            return
        payload = self._read_json()
        codes = write_codes(payload.get("codes") or payload.get("tickers") or [])
        response = {"ok": True, "codes": codes}
        if path == "/open-floating":
            response["floating"] = start_floating()
        elif path == "/close-floating":
            response["floating"] = stop_floating()
        elif path == "/toggle-floating":
            response["floating"] = toggle_floating()
        self._send_json(response)

    def _read_json(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    def _send_json(self, payload: dict, status: int = 200):
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format, *args):
        return


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), BridgeHandler)
    if sys.stdout and sys.stdout.isatty():
        print(f"Bridge running at http://{args.host}:{args.port}/preview.html")
        print("API: /watchlist, /floating-status, /toggle-floating")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
