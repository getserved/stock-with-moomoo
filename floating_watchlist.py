import argparse
import math
import os
import threading
import time
import tkinter as tk
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNTIME_APPDATA = ROOT / "generated" / "runtime_appdata"
RUNTIME_APPDATA.mkdir(parents=True, exist_ok=True)
os.environ["APPDATA"] = str(RUNTIME_APPDATA)
import moomoo as ft
import pandas as pd


HOST = "127.0.0.1"
PORT = 11111
DEFAULT_CODES = ["US.MU", "US.INTC", "US.IREN", "US.RKLB", "US.BB"]
WATCHLIST_FILE = "watchlist.txt"
LOGO_PATH = "assets/hug-dragon-watch-logo.png"
PRICE_REFRESH_SECONDS = 5
INDICATOR_REFRESH_SECONDS = 300
DEFAULT_GEOMETRY = "260x300+80+80"
IDLE_ALPHA = 0.72
ACTIVE_ALPHA = 1.0
COLLAPSED_ALPHA = 0.82


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
    for col in ("close", "high", "low", "volume"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["close", "high", "low"])
    data["ema12"] = ema(data["close"], 12)
    data["ema26"] = ema(data["close"], 26)
    data["macd_dif"] = data["ema12"] - data["ema26"]
    data["macd_dea"] = ema(data["macd_dif"], 9)
    data["macd_hist"] = 2 * (data["macd_dif"] - data["macd_dea"])
    data["rsi14"] = rsi(data["close"], 14)
    data["ma20"] = data["close"].rolling(20).mean()
    data["ma50"] = data["close"].rolling(50).mean()
    data["volume_ma20"] = data["volume"].rolling(20).mean()
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


def resistance_values(data: pd.DataFrame) -> tuple[float, float]:
    recent = data.tail(80)
    if len(recent) >= 60:
        prev_high = float(recent["high"].tail(20).max())
        resistance = float(recent["high"].tail(60).max())
    elif len(recent) >= 20:
        prev_high = float(recent["high"].tail(20).max())
        resistance = prev_high
    else:
        prev_high = float(recent["high"].max())
        resistance = prev_high
    return prev_high, resistance


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


def live_price_from_snapshot(snapshot_row: pd.Series, market_us: str = "") -> tuple[float | None, str]:
    if market_us == "AFTER_HOURS_END":
        fields = (("overnight_price", "ON"), ("after_price", "AFT"), ("last_price", "REG"), ("pre_price", "PRE"))
    elif "PRE" in market_us:
        fields = (("pre_price", "PRE"), ("last_price", "REG"), ("overnight_price", "ON"), ("after_price", "AFT"))
    elif "AFTER" in market_us:
        fields = (("after_price", "AFT"), ("last_price", "REG"), ("pre_price", "PRE"), ("overnight_price", "ON"))
    elif "OVERNIGHT" in market_us or "NIGHT" in market_us:
        fields = (("overnight_price", "ON"), ("after_price", "AFT"), ("pre_price", "PRE"), ("last_price", "REG"))
    elif "OPEN" in market_us:
        fields = (("last_price", "REG"), ("pre_price", "PRE"), ("after_price", "AFT"), ("overnight_price", "ON"))
    else:
        fields = (("pre_price", "PRE"), ("overnight_price", "ON"), ("after_price", "AFT"), ("last_price", "REG"))

    for field, label in fields:
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


def fetch_live_price(quote_ctx: ft.OpenQuoteContext, code: str, market_us: str = "") -> dict:
    ret, snapshot = quote_ctx.get_market_snapshot([code])
    if ret != ft.RET_OK or snapshot.empty:
        return {"price": None, "live_source": "ERR", "open": None}

    snapshot_row = snapshot.iloc[0]
    snap_price, live_source = live_price_from_snapshot(snapshot_row, market_us)
    open_price = valid_price(snapshot_row["open_price"]) if "open_price" in snapshot_row.index else None
    return {"price": snap_price, "live_source": live_source, "open": open_price}


def technical_signal(latest: pd.Series, previous: pd.Series, price: float) -> dict:
    hist = float(latest["macd_hist"])
    prev_hist = float(previous["macd_hist"])
    rsi14 = float(latest["rsi14"])
    ma20 = valid_price(latest.get("ma20"))
    ma50 = valid_price(latest.get("ma50"))
    volume = valid_price(latest.get("volume"))
    volume_ma20 = valid_price(latest.get("volume_ma20"))
    volume_ratio = volume / volume_ma20 if volume and volume_ma20 else None

    score = 0
    reasons = []
    trend = "震荡"
    ma_note = "均线未明"
    macd_note = "MACD中性"
    rsi_note = f"RSI {rsi14:.1f}"
    volume_note = "量能平稳"
    if ma20 and ma50:
        if price > ma20 > ma50:
            trend = "升"
            ma_note = "多头均线"
        elif price < ma20 < ma50:
            trend = "跌"
            ma_note = "空头均线"
        elif ma20 > ma50 and price < ma20:
            trend = "升中回踩"
            ma_note = "多头回踩 MA20"
        elif ma20 < ma50 and price > ma20:
            trend = "跌中反弹"
            ma_note = "反弹挑战 MA20"
    if ma20 and ma50 and price > ma20 > ma50:
        score += 35
        reasons.append("多头均线")
    elif ma20 and ma50 and price < ma20 < ma50:
        score -= 25
        reasons.append("空头均线")
    if prev_hist <= 0 < hist:
        score += 30
        reasons.append("MACD翻红")
        macd_note = "MACD翻红"
    elif hist > 0 and hist > prev_hist:
        score += 25
        reasons.append("MACD增强")
        macd_note = "MACD柱体增强"
    elif hist < 0 and hist < prev_hist:
        score -= 12
        reasons.append("MACD走弱")
        macd_note = "MACD走弱"
    elif hist < 0:
        macd_note = "MACD仍在零轴下"
    else:
        macd_note = "MACD在零轴上"
    if 45 <= rsi14 <= 68:
        score += 18
        reasons.append("RSI健康")
        rsi_note = f"RSI {rsi14:.1f} 健康"
    elif rsi14 > 72:
        score -= 18
        reasons.append("RSI过热")
        rsi_note = f"RSI {rsi14:.1f} 过热"
    elif rsi14 < 35:
        rsi_note = f"RSI {rsi14:.1f} 偏弱"
    if volume_ratio and volume_ratio >= 1.5:
        score += 14
        reasons.append(f"放量{volume_ratio:.1f}x")
        volume_note = f"放量 {volume_ratio:.1f}x"
    elif volume_ratio and volume_ratio <= 0.8:
        volume_note = f"缩量 {volume_ratio:.1f}x"

    if score >= 65:
        label = f"强多头-{trend}"
        alert = True
    elif score >= 45:
        label = f"转强-{trend}"
        alert = True
    elif score <= -15:
        label = f"转弱-{trend}"
        alert = False
    else:
        label = f"观察-{trend}"
        alert = False
    return {
        "score": max(0, round(score, 1)),
        "label": label,
        "trend": trend,
        "reasons": reasons[:4],
        "ma_note": ma_note,
        "macd_note": macd_note,
        "rsi_note": rsi_note,
        "volume_note": volume_note,
        "volume_ratio": round(volume_ratio, 2) if volume_ratio else None,
        "alert": alert,
    }


def analyze_one(quote_ctx: ft.OpenQuoteContext, code: str) -> dict:
    end = date.today()
    start = end - timedelta(days=280)
    live = fetch_live_price(quote_ctx, code, getattr(quote_ctx, "_market_us", ""))
    ret, kline, _ = quote_ctx.request_history_kline(
        code,
        start=start.isoformat(),
        end=end.isoformat(),
        ktype=ft.KLType.K_DAY,
        max_count=220,
    )
    if ret != ft.RET_OK or kline.empty:
        kline_error = str(kline)[:120] if ret != ft.RET_OK else "K线返回为空"
        row = {
            "code": code.replace("US.", ""),
            "price": live["price"],
            "live_source": live["live_source"],
            "open": live["open"],
            "close": None,
            "kline_error": kline_error,
            "updated": time.strftime("%H:%M:%S"),
            "signal": {"score": 0, "label": "无K线", "reasons": [kline_error], "alert": False},
        }
        if live["price"] is None:
            row["error"] = str(kline)[:80]
        return row

    data = add_indicators(kline)
    if len(data) < 35:
        return {"code": code, "error": "not enough kline data"}

    latest = data.iloc[-1]
    previous = data.iloc[-2]
    prev_low, support = support_values(data)
    prev_high, resistance = resistance_values(data)

    price = float(latest["close"])
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
        "prev_high": prev_high,
        "support": support,
        "resistance": resistance,
        "support_gap": (price / support - 1) * 100 if support else None,
        "breakout_gap": (resistance / price - 1) * 100 if resistance and price else None,
        "signal": technical_signal(latest, previous, price),
        "updated": time.strftime("%H:%M:%S"),
    }


def fetch_rows(codes: list[str], cached_rows: dict[str, dict] | None = None, force_indicators: bool = True) -> list[dict]:
    ft.SysConfig.enable_console_log(False)
    quote_ctx = ft.OpenQuoteContext(host=HOST, port=PORT)
    try:
        state_ret, state = quote_ctx.get_global_state()
        quote_ctx._market_us = state.get("market_us", "") if state_ret == ft.RET_OK else ""
        cached_rows = cached_rows or {}
        rows = []
        for code in codes:
            short_code = code.replace("US.", "")
            cached = cached_rows.get(short_code)
            if cached and not force_indicators and "error" not in cached:
                row = dict(cached)
                live = fetch_live_price(quote_ctx, code, getattr(quote_ctx, "_market_us", ""))
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
        self.root.geometry(DEFAULT_GEOMETRY)
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", IDLE_ALPHA)
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
        self.active_filters: set[str] = set()
        self.filter_buttons: dict[str, tk.Button] = {}
        self.indicator_cache: dict[str, dict] = {}
        self.alerted_signals: set[str] = set()
        self.last_indicator_refresh = 0.0
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_start_width = 0
        self.resize_start_height = 0
        self.collapsed = False
        self.pointer_inside = False
        self.has_focus = False
        self.expanded_geometry = ""
        self.collapse_edge = "left"
        self.toggle_tab: tk.Button | None = None
        self.logo_img = self._load_logo()
        self.tooltip_window: tk.Toplevel | None = None
        self.tooltip_label: tk.Label | None = None

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

        for key, label in (("hot", "热"), ("cold", "冷"), ("bull", "多"), ("bear", "空")):
            button = tk.Button(
                self.controls_frame,
                text=label,
                command=lambda filter_key=key: self._toggle_filter(filter_key),
                bg="#4a5453",
                fg="#efece3",
                relief="flat",
                padx=3,
                pady=0,
                font=("Microsoft YaHei UI", 7),
            )
            button.pack(side="right", padx=(3, 0))
            self.filter_buttons[key] = button

        refresh_btn = tk.Button(self.controls_frame, text="刷", command=self.refresh, bg="#596a6c", fg="#f1f3ee", relief="flat", padx=5, pady=0, font=("Microsoft YaHei UI", 7))
        refresh_btn.pack(side="right", padx=(4, 0))

        close_btn = tk.Button(self.controls_frame, text="×", command=self.root.destroy, bg="#7b6260", fg="#f5eeee", relief="flat", padx=5, pady=0, font=("Segoe UI", 8))
        close_btn.pack(side="right", padx=(4, 0))

        self._bind_drag(self.root)
        self._bind_drag(self.rows_frame)
        self.root.bind("<Motion>", self._maybe_show_controls)
        self.root.bind("<Enter>", self._on_pointer_enter, add="+")
        self.root.bind("<Leave>", self._on_pointer_leave, add="+")
        self.root.bind("<FocusIn>", self._on_focus_in, add="+")
        self.root.bind("<FocusOut>", self._on_focus_out, add="+")
        self.root.bind("<ButtonPress-1>", self._activate_window, add="+")
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

        signal_alerts = []
        for row in rows:
            if row.get("error"):
                self._build_row(
                    {
                        "code": row["code"],
                        "price": row.get("price"),
                        "live_source": row.get("live_source", "ERR"),
                        "close": row.get("close"),
                        "open": row.get("open"),
                        "error": str(row["error"])[:60],
                        "kline_error": row.get("kline_error"),
                        "signal": row.get("signal", {"label": "错误", "score": 0, "reasons": [], "alert": False}),
                    },
                    "neutral" if row.get("kline_error") else "bear",
                )
                continue

            state = self._row_state(row)
            if self.active_filters and state not in self.active_filters:
                continue
            self._build_row(row, state)
            signal = row.get("signal") or {}
            if signal.get("alert") and str(row.get("code")) not in self.alerted_signals:
                self.alerted_signals.add(str(row.get("code")))
                signal_alerts.append(f"{row.get('code')} {signal.get('label')} {signal.get('score')}")
                self.root.bell()
        if signal_alerts:
            self.status.set("技术信号: " + " | ".join(signal_alerts[:3]))
        else:
            self.status.set(f"{time.strftime('%H:%M:%S')} | 价{PRICE_REFRESH_SECONDS}s / 指标{INDICATOR_REFRESH_SECONDS // 60}分")
        self.refreshing = False
        self.root.after(PRICE_REFRESH_SECONDS * 1000, self.refresh)

    def _row_state(self, row: dict) -> str:
        rsi = row.get("rsi")
        hist = row.get("hist")
        if rsi is None or hist is None:
            return "neutral"
        rsi_value = float(rsi)
        if rsi_value >= 70:
            return "hot"
        if rsi_value <= 30:
            return "cold"
        if float(hist) >= 0:
            return "bull"
        return "bear"

    def _toggle_filter(self, key: str) -> None:
        if key in self.active_filters:
            self.active_filters.remove(key)
        else:
            self.active_filters.add(key)
        self._sync_filter_buttons()
        self._apply_rows(getattr(self, "_last_rows", []))

    def _sync_filter_buttons(self) -> None:
        colors = {
            "hot": "#8b6f72",
            "cold": "#6c7f93",
            "bull": "#6f7f77",
            "bear": "#8a7b64",
        }
        for key, button in self.filter_buttons.items():
            if key in self.active_filters:
                button.configure(bg=colors[key], fg="#fbfaf6")
            else:
                button.configure(bg="#4a5453", fg="#efece3")

    def _build_row(self, row: dict, state: str) -> None:
        assert self.rows_frame is not None
        bg_map = {
            "hot": "#8b6f72",
            "cold": "#6c7f93",
            "bull": "#6f7f77",
            "bear": "#8a7b64",
            "neutral": "#697174",
        }
        bg = bg_map.get(state, bg_map["neutral"])
        fg = "#fbfaf6"
        muted = "#e0ded5"
        code = str(row["code"])
        is_open = code in self.expanded
        row_height = 46 if not is_open else (172 if row.get("kline_error") else 130)

        card_width = max(self.rows_frame.winfo_width() - 2, 248)
        frame = tk.Canvas(self.rows_frame, height=row_height, bg=self.shell_bg, highlightthickness=0)
        frame.pack(fill="x", pady=2)
        self._bind_drag(frame)
        self._bind_scroll(frame)
        self._round_rect(frame, 1, 1, card_width, row_height - 1, 9, fill=bg, outline="")

        frame.create_text(8, 11, text=("▾ " if is_open else "▸ ") + code, fill=fg, anchor="w", font=("Segoe UI", 7, "bold"))

        source = cn_source(row.get("live_source", "-"))
        frame.create_text(84, 13, text=fmt(row.get("price")), fill=fg, anchor="w", font=("Segoe UI", 11, "bold"))
        frame.create_text(198, 12, text=source, fill=muted, anchor="w", font=("Microsoft YaHei UI", 6, "bold"))
        frame.create_text(card_width - 8, row_height - 8, text=str(row.get("updated", ""))[-8:], fill=muted, anchor="se", font=("Segoe UI", 6))

        lower_label, lower_value = self._lower_price(row)
        frame.create_text(84, 31, text=f"{lower_label} {lower_value}", fill=muted, anchor="w", font=("Microsoft YaHei UI", 6))
        signal = row.get("signal") or {}
        signal_text = self._signal_badge(row)
        signal_color = "#fbfaf6" if signal.get("alert") else muted
        frame.create_text(8, 30, text=signal_text, fill=signal_color, anchor="w", font=("Microsoft YaHei UI", 6, "bold"))

        if is_open:
            if row.get("kline_error"):
                alert_fg = "#e7b0aa"
                frame.create_text(8, 84, text=self._details_text(row), fill=fg, anchor="nw", font=("Microsoft YaHei UI", 8))
                frame.create_oval(8, 120, 24, 136, outline=alert_fg, width=2)
                frame.create_text(16, 128, text="!", fill=alert_fg, anchor="center", font=("Segoe UI", 9, "bold"))
                frame.create_text(
                    30,
                    118,
                    text=f"K线错误：{row.get('kline_error')}",
                    fill=alert_fg,
                    anchor="nw",
                    width=card_width - 40,
                    font=("Microsoft YaHei UI", 7, "bold"),
                )
            else:
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
        frame.bind("<Enter>", lambda event, tooltip_row=dict(row): self._show_tooltip(event, tooltip_row), add="+")
        frame.bind("<Leave>", self._hide_tooltip, add="+")
        frame.bind("<ButtonPress-1>", self._hide_tooltip, add="+")

    def _lower_price(self, row: dict) -> tuple[str, str]:
        if row.get("live_source") == "REG":
            return "开", fmt(row.get("open"))
        return "收", fmt(row.get("close"))

    def _details_text(self, row: dict) -> str:
        if "error" in row:
            return str(row["error"])
        if row.get("kline_error"):
            return (
                f"现价 {fmt(row.get('price'))}  来源 {cn_source(row.get('live_source', '-'))}\n"
                f"开 {fmt(row.get('open'))}  收 {fmt(row.get('close'))}"
            )
        return (
            f"RSI {fmt(row.get('rsi'), 1)}  "
            f"{row.get('momentum')} {fmt(row.get('hist'), 2)}\n"
            f"前低 {fmt(row.get('prev_low'))}  支撑 {fmt(row.get('support'))}  距支撑 {fmt(row.get('support_gap'), 1)}%\n"
            f"信号 {self._signal_text(row)}"
        )

    def _signal_badge(self, row: dict) -> str:
        signal = row.get("signal") or {}
        score = float(signal.get("score") or 0)
        trend = str(signal.get("trend") or "震荡")
        if row.get("kline_error"):
            return "K线待补"
        if trend == "升" and score >= 60:
            return "强势上行"
        if trend == "升" and score >= 45:
            return "偏强上行"
        if trend == "升中回踩" and score >= 30:
            return "上行回踩"
        if trend == "升中回踩":
            return "回踩观察"
        if trend == "跌中反弹":
            return "反弹观察"
        if trend == "跌" and score <= 20:
            return "弱势下行"
        if trend == "跌":
            return "偏弱下行"
        return "区间观察"

    def _signal_text(self, row: dict) -> str:
        signal = row.get("signal") or {}
        reasons = " / ".join(signal.get("reasons") or [])
        return f"{self._signal_badge(row)}  技术综合评分 {fmt(signal.get('score'), 0)}  {reasons}".strip()

    def _trade_hint(self, row: dict) -> str:
        if row.get("kline_error"):
            return "建议：等 K 线恢复后再判断买点。"
        support = row.get("support") or row.get("prev_low")
        resistance = row.get("resistance") or row.get("prev_high")
        stop = support * 0.97 if support else None
        trend = str((row.get("signal") or {}).get("trend") or "震荡")
        badge = self._signal_badge(row)
        if trend in {"升", "升中回踩"}:
            return (
                f"建议：左侧看支撑 {fmt(support)}，右侧看突破 {fmt(resistance)}，"
                f"止损位 {fmt(stop)}。当前偏向 {badge}。"
            )
        if trend in {"跌", "跌中反弹"}:
            return (
                f"建议：先观察突破 {fmt(resistance)} 再追高，或等回踩支撑 {fmt(support)}，"
                f"止损位 {fmt(stop)}。"
            )
        return f"建议：区间内先观察支撑 {fmt(support)} 与突破位 {fmt(resistance)}。"

    def _tooltip_text(self, row: dict) -> str:
        signal = row.get("signal") or {}
        if row.get("kline_error"):
            return (
                f"{row.get('code')}  {self._signal_badge(row)}\n"
                f"K线错误：{row.get('kline_error')}\n"
                f"{self._trade_hint(row)}"
            )
        return (
            f"{row.get('code')}  {self._signal_badge(row)}\n"
            f"RSI：{signal.get('rsi_note', '-')}\n"
            f"MACD：{signal.get('macd_note', '-')}\n"
            f"均线：{signal.get('ma_note', '-')}\n"
            f"量能：{signal.get('volume_note', '-')}\n"
            f"{self._trade_hint(row)}"
        )

    def _show_tooltip(self, event: tk.Event, row: dict) -> None:
        self._hide_tooltip()
        self.tooltip_window = tk.Toplevel(self.root)
        self.tooltip_window.overrideredirect(True)
        self.tooltip_window.attributes("-topmost", True)
        self.tooltip_window.configure(bg="#f3eee6")
        x = event.x_root + 12
        y = event.y_root + 12
        self.tooltip_window.geometry(f"+{x}+{y}")
        self.tooltip_label = tk.Label(
            self.tooltip_window,
            text=self._tooltip_text(row),
            justify="left",
            anchor="nw",
            bg="#f3eee6",
            fg="#243237",
            padx=10,
            pady=8,
            wraplength=250,
            font=("Microsoft YaHei UI", 8),
        )
        self.tooltip_label.pack()

    def _hide_tooltip(self, _event: tk.Event | None = None) -> None:
        if self.tooltip_window is not None:
            self.tooltip_window.destroy()
            self.tooltip_window = None
            self.tooltip_label = None

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
        self._set_active_alpha()
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
        self._dim_if_idle()

    def _set_active_alpha(self) -> None:
        self.root.attributes("-alpha", ACTIVE_ALPHA)

    def _dim_if_idle(self) -> None:
        if self.pointer_inside or self.has_focus:
            self._set_active_alpha()
            return
        self.root.attributes("-alpha", COLLAPSED_ALPHA if self.collapsed else IDLE_ALPHA)

    def _activate_window(self, _event: tk.Event | None = None) -> None:
        self.pointer_inside = True
        self.has_focus = True
        try:
            self.root.focus_force()
        except tk.TclError:
            pass
        self._set_active_alpha()

    def _on_pointer_enter(self, event: tk.Event | None = None) -> None:
        self.pointer_inside = True
        self._set_active_alpha()
        self._maybe_show_controls(event) if event is not None else None

    def _on_pointer_leave(self, event: tk.Event | None = None) -> None:
        self.pointer_inside = False
        self._hide_controls(event)
        self.root.after(120, self._dim_if_idle)

    def _on_focus_in(self, _event: tk.Event | None = None) -> None:
        self.has_focus = True
        self._set_active_alpha()

    def _on_focus_out(self, _event: tk.Event | None = None) -> None:
        self.has_focus = False
        self.root.after(120, self._dim_if_idle)

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
            self.root.attributes("-alpha", COLLAPSED_ALPHA)
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
                self.root.geometry(DEFAULT_GEOMETRY)
            self._set_active_alpha()
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
