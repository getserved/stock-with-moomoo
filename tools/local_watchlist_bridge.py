import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
WATCHLIST_FILE = ROOT / "watchlist.txt"
SELECTED_FILE = ROOT / "selected_watchlist.json"
FLOATING_PID_FILE = ROOT / "floating_watchlist.pid"
FLOATING_SCRIPT = ROOT / "floating_watchlist.py"
SNAPSHOT_FILE = ROOT / "ai-stock-screener" / "src" / "data" / "apiSnapshot.json"
UNIVERSE_FILE = ROOT / "ai-stock-screener" / "src" / "data" / "marketUniverse.json"
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


def write_json(path: Path, payload: dict) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def load_universe() -> list[dict]:
    if not UNIVERSE_FILE.exists():
        return []
    payload = json.loads(UNIVERSE_FILE.read_text(encoding="utf-8"))
    return payload.get("universe", []) if isinstance(payload, dict) else []


def find_universe_match(query: str) -> dict | None:
    text = query.strip().upper().replace("US.", "")
    if not text:
        return None
    for row in load_universe():
        code = str(row.get("stock_code") or "").upper()
        ticker = code.replace("US.", "")
        if ticker == text or code == f"US.{text}":
            return row
    for row in load_universe():
        name = str(row.get("stock_name") or "").upper()
        code = str(row.get("stock_code") or "").upper()
        if text in name or text in code:
            return row
    return None


def upsert_snapshot_row(row: dict) -> dict:
    payload = json.loads(SNAPSHOT_FILE.read_text(encoding="utf-8"))
    rows = payload.get("rows", [])
    code = row.get("code")
    replaced = False
    for index, existing in enumerate(rows):
        if existing.get("code") == code:
            rows[index] = row
            replaced = True
            break
    if not replaced:
        rows.append(row)
    payload["rows"] = sorted(rows, key=lambda item: item.get("price") or 0)
    payload["directLookup"] = {
        "updatedAt": datetime.now(timezone.utc).isoformat(),
        "lastCode": code,
        "replaced": replaced,
    }
    write_json(SNAPSHOT_FILE, payload)
    return {"replaced": replaced, "rowCount": len(rows)}


def lookup_stock(query: str) -> dict:
    match = find_universe_match(query)
    if not match:
        return {"ok": False, "error": f"{query} not found in marketUniverse"}
    code = normalize_code(str(match.get("stock_code") or query))

    runtime_appdata = ROOT / "generated" / "runtime_appdata"
    runtime_appdata.mkdir(parents=True, exist_ok=True)
    os.environ["APPDATA"] = str(runtime_appdata)

    import moomoo as ft
    from fetch_moomoo_market_screener import enrich_codes, fetch_owner_plates
    from fetch_moomoo_screener import build_highlights, fetch_analyst_consensus, fetch_kline, fetch_next_event
    import render_interactive_preview

    ft.SysConfig.enable_console_log(False)
    quote_ctx = ft.OpenQuoteContext(host="127.0.0.1", port=11111)
    try:
        rows = enrich_codes(quote_ctx, [code], None, None)
        if not rows:
            return {"ok": False, "code": code, "error": "MOOMOO snapshot returned no usable row"}
        row = rows[0]
        plates = fetch_owner_plates(quote_ctx, [code])
        plate = plates.get(code, {})
        row["industry"] = plate.get("industry", row.get("industry") or "未分类")
        row["concepts"] = plate.get("concepts", row.get("concepts") or [])
        row["theme"] = row["industry"]
        candles, technical = fetch_kline(quote_ctx, code)
        row["candles"] = candles
        row["technical"] = technical or row.get("technical", {})
        row["analystConsensus"] = fetch_analyst_consensus(quote_ctx, code)
        row["nextEvent"] = fetch_next_event(quote_ctx, code)
        row["highlights"] = build_highlights(row, row["analystConsensus"], row["nextEvent"], row.get("technical", {}))
    finally:
        quote_ctx.close()

    update = upsert_snapshot_row(row)
    render_interactive_preview.render()
    return {"ok": True, "code": code, "ticker": row.get("ticker"), "row": row, "snapshot": update}


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


def refresh_floating_if_running() -> dict:
    current = floating_status()
    if not current["running"]:
        return current | {"refreshed": False}
    stop_floating()
    time.sleep(0.25)
    restarted = start_floating()
    restarted["refreshed"] = True
    return restarted


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
        if path not in {"/watchlist", "/open-floating", "/close-floating", "/toggle-floating", "/lookup-stock"}:
            self.send_error(404)
            return
        payload = self._read_json()
        if path == "/lookup-stock":
            self._send_json(lookup_stock(str(payload.get("ticker") or payload.get("code") or "")))
            return
        codes = write_codes(payload.get("codes") or payload.get("tickers") or [])
        response = {"ok": True, "codes": codes}
        if path == "/watchlist":
            response["floating"] = refresh_floating_if_running()
        elif path == "/open-floating":
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
        print("API: /watchlist, /floating-status, /toggle-floating, /lookup-stock")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return 0
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
