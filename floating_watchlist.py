import argparse
import math
import threading
import time
import tkinter as tk
from datetime import date, timedelta

import moomoo as ft
import pandas as pd


HOST = "127.0.0.1"
PORT = 11111
DEFAULT_CODES = ["US.MU", "US.INTC", "US.IREN", "US.RKLB", "US.BB"]
WATCHLIST_FILE = "watchlist.txt"
LOGO_PATH = "assets/hug-dragon-watch-logo.png"
PRICE_REFRESH_SECONDS = 5
INDICATOR_REFRESH_SECONDS = 300


def normalize_code(code: str) -> str:
    text = code.strip().upper()
    if not text:
        return ""
    if "." not in text:
        return f"US.{text}"
    return text


def load_codes() -> list[str]:
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as handle:
            codes = [normalize_code(line) for line in handle if line.strip() and not line.strip().startswith("#")]
            return [code for code in codes if code]
    except FileNotFoundError:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as handle:
            handle.write("\n".join(DEFAULT_CODES) + "\n")
        return DEFAULT_CODES[:]


def ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - (100 / (1 + rs))


def add_indicators(kline: pd.DataFrame) -> pd.DataFrame:
    data = kline.copy()
    for col in ("close", "high", "low"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["close", "high", "low"])
    data["ema12"] = ema(data["close"], 12)
    data["ema26"] = ema(data["close"], 26)
    data["macd_dif"] = data["ema12"] - data["ema26"]
    data["macd_dea"] = ema(data["macd_dif"], 9)
    data["macd_hist"] = 2 * (data["macd_dif"] - data["macd_dea"])
    data["rsi14"] = rsi(data["close"], 14)
    data["ma20"] = data["close"].rolling(20).mean()
    return data


def local_lows(data: pd.DataFrame) -> pd.Series:
    lows = data["low"]
    pivots = lows[(lows.shift(2) > lows) & (lows.shift(1) > lows) & (lows.shift(-1) > lows) & (lows.shift(-2) > lows)]
    return pivots.dropna()


def support_values(data: pd.DataFrame) -> tuple[float, float]:
    recent = data.tail(80)
    pivots = local_lows(recent)
    if len(pivots) >= 2:
        prev_low = float(pivots.iloc[-1])
        support = float(pivots.tail(5).min())
    elif len(recent) >= 20:
        prev_low = float(recent["low"].tail(20).min())
        support = float(recent["low"].tail(60).min())
    else:
        prev_low = float(recent["low"].min())
        support = prev_low
    return prev_low, support


def momentum_label(hist: float, prev_hist: float) -> str:
    if hist > 0 and hist > prev_hist:
        return "多头增强"
    if hist > 0 and hist <= prev_hist:
        return "多头减弱"
    if hist < 0 and hist < prev_hist:
        return "空头增强"
    return "空头减弱"


def fmt(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "-"
    try:
        if math.isnan(float(value)):
            return "-"
    except (TypeError, ValueError):
        return "-"
    return f"{float(value):.{digits}f}"


def valid_price(value: object) -> float | None:
    price = pd.to_numeric(value, errors="coerce")
    if pd.notna(price) and float(price) > 0:
        return float(price)
    return None


def live_price_from_snapshot(snapshot_row: pd.Series) -> tuple[float | None, str]:
    # Prefer extended-session prices when available. Moomoo exposes these
    # separately from regular-session last_price.
    for field, label in (
        ("overnight_price", "ON"),
        ("pre_price", "PRE"),
        ("after_price", "AFT"),
        ("last_price", "REG"),
    ):
        if field in snapshot_row.index:
            price = valid_price(snapshot_row[field])
            if price is not None:
                return price, label
    return None, "-"


def cn_source(source: object) -> str:
    return {
        "ON": "夜",
        "PRE": "盘前",
        "AFT": "盘后",
        "REG": "盘中",
        "DAY": "日",
        "ERR": "错",
    }.get(str(source), str(source))


def fetch_live_price(quote_ctx: ft.OpenQuoteContext, code: str) -> dict:
    ret, snapshot = quote_ctx.get_market_snapshot([code])
    if ret != ft.RET_OK or snapshot.empty:
        return {"price": None, "live_source": "ERR", "open": None}

    snapshot_row = snapshot.iloc[0]
    snap_price, live_source = live_price_from_snapshot(snapshot_row)
    open_price = valid_price(snapshot_row["open_price"]) if "open_price" in snapshot_row.index else None
    return {"price": snap_price, "live_source": live_source, "open": open_price}


def analyze_one(quote_ctx: ft.OpenQuoteContext, code: str) -> dict:
    end = date.today()
    start = end - timedelta(days=280)
    ret, kline, _ = quote_ctx.request_history_kline(
        code,
        start=start.isoformat(),
        end=end.isoformat(),
        ktype=ft.KLType.K_DAY,
        max_count=220,
    )
    if ret != ft.RET_OK or kline.empty:
        return {"code": code, "error": str(kline)}

    data = add_indicators(kline)
    if len(data) < 35:
        return {"code": code, "error": "not enough kline data"}

    latest = data.iloc[-1]
    previous = data.iloc[-2]
    prev_low, support = support_values(data)

    price = float(latest["close"])
    live = fetch_live_price(quote_ctx, code)
    live_source = live["live_source"]
    open_price = live["open"]
    if live["price"] is not None:
        price = live["price"]

    hist = float(latest["macd_hist"])
    prev_hist = float(previous["macd_hist"])
    rsi14 = float(latest["rsi14"])
    hist_series = [float(value) for value in data["macd_hist"].dropna().tail(36)]

    close = float(latest["close"])
    return {
        "code": code.replace("US.", ""),
        "price": price,
        "live_source": live_source,
        "close": close,
        "open": open_price,
        "rsi": rsi14,
        "momentum": momentum_label(hist, prev_hist),
        "hist": hist,
        "hist_series": hist_series,
        "prev_low": prev_low,
        "support": support,
        "support_gap": (price / support - 1) * 100 if support else None,
        "updated": time.strftime("%H:%M:%S"),
    }


def fetch_rows(codes: list[str], cached_rows: dict[str, dict] | None = None, force_indicators: bool = True) -> list[dict]:
    ft.SysConfig.enable_console_log(False)
    quote_ctx = ft.OpenQuoteContext(host=HOST, port=PORT)
    try:
        cached_rows = cached_rows or {}
        rows = []
        for code in codes:
            short_code = code.replace("US.", "")
            cached = cached_rows.get(short_code)
            if cached and not force_indicators and "error" not in cached:
                row = dict(cached)
                live = fetch_live_price(quote_ctx, code)
                if live["price"] is not None:
                    row["price"] = live["price"]
                    row["live_source"] = live["live_source"]
                    row["open"] = live["open"]
                    if row.get("support"):
                        row["support_gap"] = (row["price"] / row["support"] - 1) * 100
                    row["updated"] = time.strftime("%H:%M:%S")
                rows.append(row)
            else:
                rows.append(analyze_one(quote_ctx, code))
        return rows
    finally:
        quote_ctx.close()


class FloatingWatchlist:
    def __init__(self) -> None:
        self.transparent_color = "#ff00ff"
        self.shell_bg = "#2f3437"
        self.root = tk.Tk()
        self.root.title("Moomoo 盯盘")
        self.root.geometry("260x180+80+80")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.72)
        self.root.configure(bg=self.transparent_color)
        self.root.attributes("-transparentcolor", self.transparent_color)
        self.root.minsize(230, 140)

        self.status = tk.StringVar(value="Starting...")
        self.refreshing = False
        self.expanded: set[str] = set()
        self.rows_frame: tk.Frame | None = None
        self.rows_canvas: tk.Canvas | None = None
        self.rows_window: int | None = None
        self.controls_frame: tk.Frame | None = None
        self.shell_canvas: tk.Canvas | None = None
        self.content_frame: tk.Frame | None = None
        self.content_window: int | None = None
        self.indicator_cache: dict[str, dict] = {}
        self.last_indicator_refresh = 0.0
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_start_width = 0
        self.resize_start_height = 0
        self.collapsed = False
        self.expanded_geometry = ""
        self.collapse_edge = "left"
        self.toggle_tab: tk.Button | None = None
        self.logo_img = self._load_logo()

        self._build_ui()
        self.root.after(150, self.refresh)

    def _build_ui(self) -> None:
        self.shell_canvas = tk.Canvas(self.root, bg=self.transparent_color, highlightthickness=0)
        self.shell_canvas.pack(fill="both", expand=True)
        self.content_frame = tk.Frame(self.shell_canvas, bg=self.shell_bg)
        self.content_window = self.shell_canvas.create_window((6, 6), window=self.content_frame, anchor="nw")
        self.shell_canvas.bind("<Configure>", self._on_shell_configure)
        self._bind_drag(self.shell_canvas)

        self.rows_canvas = tk.Canvas(self.content_frame, bg=self.shell_bg, highlightthickness=0)
        self.rows_canvas.pack(fill="both", expand=True, padx=5, pady=(5, 1))
        self.rows_frame = tk.Frame(self.rows_canvas, bg=self.shell_bg)
        self.rows_window = self.rows_canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind("<Configure>", self._on_rows_configure)
        self.rows_canvas.bind("<Configure>", self._on_canvas_configure)
        self._bind_scroll(self.rows_canvas)
        self._bind_drag(self.rows_canvas)

        self.controls_frame = tk.Frame(self.content_frame, bg="#3d4545")

        if self.logo_img is not None:
            logo = tk.Label(self.controls_frame, image=self.logo_img, bg="#3d4545")
            logo.pack(side="left", padx=(0, 4))
            self._bind_drag(logo)

        status = tk.Label(self.controls_frame, textvariable=self.status, bg="#3d4545", fg="#d7ddd7", anchor="w", font=("Microsoft YaHei UI", 7))
        status.pack(side="left", fill="x", expand=True)
        self._bind_drag(status)

        refresh_btn = tk.Button(self.controls_frame, text="刷", command=self.refresh, bg="#596a6c", fg="#f1f3ee", relief="flat", padx=5, pady=0, font=("Microsoft YaHei UI", 7))
        refresh_btn.pack(side="right", padx=(4, 0))

        close_btn = tk.Button(self.controls_frame, text="×", command=self.root.destroy, bg="#7b6260", fg="#f5eeee", relief="flat", padx=5, pady=0, font=("Segoe UI", 8))
        close_btn.pack(side="right", padx=(4, 0))

        self._bind_drag(self.root)
        self._bind_drag(self.rows_frame)
        self.root.bind("<Motion>", self._maybe_show_controls)
        self.root.bind("<Leave>", self._hide_controls)
        self.root.bind("<ButtonPress-1>", self._maybe_resize_start, add="+")
        self.root.bind("<B1-Motion>", self._maybe_resize_motion, add="+")
        self.root.after(400, self._show_controls)
        self.root.after(3500, self._hide_controls)

        self.toggle_tab = tk.Button(
            self.root,
            text="‹",
            command=self._toggle_collapse,
            bg="#596a6c",
            fg="#f1f3ee",
            relief="flat",
            padx=3,
            pady=0,
            font=("Segoe UI", 8, "bold"),
        )
        self.toggle_tab.place(x=0, y=46, width=16, height=42)

    def refresh(self) -> None:
        if self.refreshing:
            return
        self.refreshing = True
        codes = load_codes()
        self.status.set(f"Refreshing {', '.join(code.replace('US.', '') for code in codes)} ...")
        threading.Thread(target=self._refresh_worker, args=(codes,), daemon=True).start()

    def _refresh_worker(self, codes: list[str]) -> None:
        try:
            now = time.time()
            force_indicators = now - self.last_indicator_refresh >= INDICATOR_REFRESH_SECONDS
            rows = fetch_rows(codes, self.indicator_cache, force_indicators=force_indicators)
            if force_indicators:
                self.last_indicator_refresh = now
            self.indicator_cache = {str(row["code"]): row for row in rows if "code" in row and "error" not in row}
            self.root.after(0, lambda: self._apply_rows(rows))
        except Exception as exc:
            self.root.after(0, lambda: self._set_error(exc))

    def _apply_rows(self, rows: list[dict]) -> None:
        self._last_rows = rows
        assert self.rows_frame is not None
        for child in self.rows_frame.winfo_children():
            child.destroy()

        for row in rows:
            if "error" in row:
                self._build_row(
                    {
                        "code": row["code"],
                        "price": None,
                        "live_source": "ERR",
                        "close": None,
                        "open": None,
                        "error": str(row["error"])[:60],
                    },
                    "bear",
                )
                continue

            rsi_value = float(row["rsi"])
            if rsi_value >= 70:
                state = "hot"
            elif rsi_value <= 30:
                state = "cold"
            elif float(row.get("hist", 0)) >= 0:
                state = "bull"
            else:
                state = "bear"
            self._build_row(row, state)
        self.status.set(f"{time.strftime('%H:%M:%S')} | 价{PRICE_REFRESH_SECONDS}s / 指标{INDICATOR_REFRESH_SECONDS // 60}分")
        self.refreshing = False
        self.root.after(PRICE_REFRESH_SECONDS * 1000, self.refresh)

    def _build_row(self, row: dict, state: str) -> None:
        assert self.rows_frame is not None
        bg_map = {
            "hot": "#8b6f72",
            "cold": "#6c7f93",
            "bull": "#6f7f77",
            "bear": "#8a7b64",
        }
        bg = bg_map[state]
        fg = "#fbfaf6"
        muted = "#e0ded5"
        code = str(row["code"])
        is_open = code in self.expanded
        row_height = 46 if not is_open else 112

        card_width = max(self.rows_frame.winfo_width() - 2, 248)
        frame = tk.Canvas(self.rows_frame, height=row_height, bg=self.shell_bg, highlightthickness=0)
        frame.pack(fill="x", pady=2)
        self._bind_drag(frame)
        self._bind_scroll(frame)
        self._round_rect(frame, 1, 1, card_width, row_height - 1, 9, fill=bg, outline="")

        frame.create_text(8, 12, text=("▾ " if is_open else "▸ ") + code, fill=fg, anchor="w", font=("Segoe UI", 7, "bold"))

        source = cn_source(row.get("live_source", "-"))
        frame.create_text(84, 13, text=fmt(row.get("price")), fill=fg, anchor="w", font=("Segoe UI", 11, "bold"))
        frame.create_text(198, 12, text=source, fill=muted, anchor="w", font=("Microsoft YaHei UI", 6, "bold"))

        lower_label, lower_value = self._lower_price(row)
        frame.create_text(84, 31, text=f"{lower_label} {lower_value}", fill=muted, anchor="w", font=("Microsoft YaHei UI", 6))

        if is_open:
            self._draw_macd_chart(frame, row.get("hist_series", []), bg, x=8, y=42, width=card_width - 16, height=34)
            frame.create_text(8, 84, text=self._details_text(row), fill=fg, anchor="nw", font=("Microsoft YaHei UI", 8))

        def toggle(_event: tk.Event) -> None:
            if code in self.expanded:
                self.expanded.remove(code)
            else:
                self.expanded.add(code)
            self._apply_rows(getattr(self, "_last_rows", []))

        frame.bind("<Button-1>", toggle)
        frame.bind("<B1-Motion>", self._drag_motion, add="+")
        frame.bind("<Motion>", self._maybe_show_controls, add="+")

    def _lower_price(self, row: dict) -> tuple[str, str]:
        if row.get("live_source") == "REG":
            return "开", fmt(row.get("open"))
        return "收", fmt(row.get("close"))

    def _details_text(self, row: dict) -> str:
        if "error" in row:
            return str(row["error"])
        return (
            f"RSI {fmt(row.get('rsi'), 1)}  "
            f"{row.get('momentum')} {fmt(row.get('hist'), 2)}\n"
            f"前低 {fmt(row.get('prev_low'))}  支撑 {fmt(row.get('support'))}  距支撑 {fmt(row.get('support_gap'), 1)}%"
        )

    def _round_rect(self, canvas: tk.Canvas, x0: int, y0: int, x1: int, y1: int, radius: int, **kwargs: object) -> None:
        points = [
            x0 + radius, y0,
            x1 - radius, y0,
            x1, y0,
            x1, y0 + radius,
            x1, y1 - radius,
            x1, y1,
            x1 - radius, y1,
            x0 + radius, y1,
            x0, y1,
            x0, y1 - radius,
            x0, y0 + radius,
            x0, y0,
        ]
        canvas.create_polygon(points, smooth=True, **kwargs)

    def _draw_macd_chart(self, canvas: tk.Canvas, values: object, bg: str, x: int = 0, y: int = 0, width: int | None = None, height: int = 38) -> None:
        if not isinstance(values, list) or not values:
            return
        width = width or max(canvas.winfo_width(), 220)
        mid = height // 2
        max_abs = max(abs(float(value)) for value in values) or 1.0
        bar_gap = 1
        bar_width = max(2, int((width - 8) / max(len(values), 1)) - bar_gap)

        canvas.create_line(x + 3, y + mid, x + width - 3, y + mid, fill="#e0ded5", width=1)
        for index, value in enumerate(values):
            value = float(value)
            x0 = x + 4 + index * (bar_width + bar_gap)
            x1 = x0 + bar_width
            y_bar = y + mid - int((value / max_abs) * (mid - 4))
            color = "#b7c6a3" if value >= 0 else "#c79691"
            canvas.create_rectangle(x0, min(y + mid, y_bar), x1, max(y + mid, y_bar), fill=color, outline="")

        latest = float(values[-1])
        label = f"MACD {latest:.2f}"
        canvas.create_text(x + width - 5, y + 3, text=label, fill="#fbfaf6", anchor="ne", font=("Segoe UI", 7, "bold"))

    def _set_error(self, exc: Exception) -> None:
        self.status.set(f"错误: {exc}")
        self.refreshing = False
        self.root.after(PRICE_REFRESH_SECONDS * 1000, self.refresh)

    def _on_shell_configure(self, event: tk.Event) -> None:
        if self.shell_canvas is None or self.content_window is None:
            return
        self.shell_canvas.delete("shell_bg")
        self._round_rect(
            self.shell_canvas,
            0,
            0,
            max(event.width - 1, 20),
            max(event.height - 1, 20),
            16,
            fill=self.shell_bg,
            outline="",
            tags="shell_bg",
        )
        self.shell_canvas.tag_lower("shell_bg")
        self.shell_canvas.itemconfigure(self.content_window, width=max(event.width - 12, 20), height=max(event.height - 12, 20))

    def _on_rows_configure(self, _event: tk.Event) -> None:
        if self.rows_canvas is not None:
            self.rows_canvas.configure(scrollregion=self.rows_canvas.bbox("all"))

    def _on_canvas_configure(self, event: tk.Event) -> None:
        if self.rows_canvas is not None and self.rows_window is not None:
            self.rows_canvas.itemconfigure(self.rows_window, width=event.width)

    def _bind_scroll(self, widget: tk.Widget) -> None:
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")

    def _on_mousewheel(self, event: tk.Event) -> None:
        if self.rows_canvas is None:
            return
        self.rows_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _show_controls(self, _event: tk.Event | None = None) -> None:
        if self.collapsed:
            return
        if self.controls_frame is None or self.content_frame is None:
            return
        self.root.attributes("-alpha", 1.0)
        width = max(self.content_frame.winfo_width() - 12, 120)
        self.controls_frame.place(x=6, y=4, width=width, height=26)
        self.controls_frame.lift()
        if self.shell_canvas is not None:
            self.shell_canvas.delete("resize_hint")
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            self.shell_canvas.create_text(w - 12, h - 12, text="◢", fill="#d7ddd7", anchor="center", font=("Segoe UI", 8), tags="resize_hint")

    def _maybe_show_controls(self, event: tk.Event) -> None:
        pointer_y = self.root.winfo_pointery() - self.root.winfo_rooty()
        if pointer_y <= 22:
            self._show_controls(event)
        elif self.controls_frame is not None and self.controls_frame.winfo_ismapped():
            if pointer_y > 34:
                self._hide_controls()

    def _hide_controls(self, event: tk.Event | None = None) -> None:
        if self.collapsed:
            return
        if self.controls_frame is None:
            return
        if event is not None:
            x = self.root.winfo_pointerx()
            y = self.root.winfo_pointery()
            left = self.root.winfo_rootx()
            top = self.root.winfo_rooty()
            right = left + self.root.winfo_width()
            bottom = top + self.root.winfo_height()
            if left <= x <= right and top <= y <= bottom:
                return
        self.controls_frame.place_forget()
        if self.shell_canvas is not None:
            self.shell_canvas.delete("resize_hint")
        self.root.attributes("-alpha", 0.72)

    def _load_logo(self) -> tk.PhotoImage | None:
        try:
            return tk.PhotoImage(file=LOGO_PATH).subsample(54, 54)
        except tk.TclError:
            return None

    def _bind_drag(self, widget: tk.Widget) -> None:
        widget.bind("<ButtonPress-1>", self._drag_start, add="+")
        widget.bind("<B1-Motion>", self._drag_motion, add="+")

    def _drag_start(self, event: tk.Event) -> None:
        if self._is_resize_zone(event.x_root, event.y_root):
            return
        self.drag_start_x = event.x_root - self.root.winfo_x()
        self.drag_start_y = event.y_root - self.root.winfo_y()

    def _drag_motion(self, event: tk.Event) -> None:
        if self._is_resize_zone(event.x_root, event.y_root):
            return
        self.root.geometry(f"+{event.x_root - self.drag_start_x}+{event.y_root - self.drag_start_y}")

    def _is_resize_zone(self, x_root: int, y_root: int) -> bool:
        return (
            x_root >= self.root.winfo_rootx() + self.root.winfo_width() - 18
            and y_root >= self.root.winfo_rooty() + self.root.winfo_height() - 18
        )

    def _maybe_resize_start(self, event: tk.Event) -> None:
        if self.collapsed:
            self.resizing = False
            return
        if not self._is_resize_zone(event.x_root, event.y_root):
            self.resizing = False
            return
        self.resizing = True
        self.resize_start_x = event.x_root
        self.resize_start_y = event.y_root
        self.resize_start_width = self.root.winfo_width()
        self.resize_start_height = self.root.winfo_height()

    def _maybe_resize_motion(self, event: tk.Event) -> None:
        if not getattr(self, "resizing", False):
            return
        new_width = max(230, self.resize_start_width + event.x_root - self.resize_start_x)
        new_height = max(140, self.resize_start_height + event.y_root - self.resize_start_y)
        self.root.geometry(f"{new_width}x{new_height}+{self.root.winfo_x()}+{self.root.winfo_y()}")

    def _toggle_collapse(self) -> None:
        if self.toggle_tab is None:
            return
        if not self.collapsed:
            self.expanded_geometry = self.root.geometry()
            self.collapsed = True
            self._hide_controls()
            self.root.attributes("-alpha", 0.82)
            width = self.root.winfo_width()
            height = self.root.winfo_height()
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            screen_width = self.root.winfo_screenwidth()
            top_score = max(0, 90 - y)
            left_score = max(0, 130 - x)
            right_score = max(0, x + width - (screen_width - 130))
            if top_score >= left_score and top_score >= right_score and top_score > 0:
                self.collapse_edge = "top"
                self.root.geometry(f"{width}x{height}+{x}+{-height + 22}")
                self.toggle_tab.configure(text="∨")
                self.toggle_tab.place(x=max(12, width // 2 - 21), y=height - 22, width=42, height=22)
            elif right_score > left_score:
                self.collapse_edge = "right"
                self.root.geometry(f"{width}x{height}+{screen_width - 22}+{y}")
                self.toggle_tab.configure(text="‹")
                self.toggle_tab.place(x=0, y=max(12, height // 2 - 21), width=22, height=42)
            else:
                self.collapse_edge = "left"
                self.root.geometry(f"{width}x{height}+{-width + 22}+{y}")
                self.toggle_tab.configure(text="›")
                self.toggle_tab.place(x=width - 22, y=max(12, height // 2 - 21), width=22, height=42)
        else:
            self.collapsed = False
            if self.expanded_geometry:
                self.root.geometry(self.expanded_geometry)
            else:
                self.root.geometry("260x180+80+80")
            self.root.attributes("-alpha", 1.0)
            self.toggle_tab.configure(text="‹")
            self.toggle_tab.place(x=0, y=46, width=16, height=42)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Print one refresh to terminal instead of opening the window")
    args = parser.parse_args()

    if args.once:
        for row in fetch_rows(load_codes()):
            print(row)
        return 0

    FloatingWatchlist().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
