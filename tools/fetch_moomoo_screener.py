import json
import math
from datetime import date, timedelta
from pathlib import Path

import moomoo as ft
import pandas as pd


HOST = "127.0.0.1"
PORT = 11111
ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "ai-stock-screener" / "src" / "data" / "apiSnapshot.json"

CODES = [
    "US.MU", "US.HPE", "US.BB", "US.MCHP", "US.VSH", "US.AMKR", "US.HPQ",
    "US.CSCO", "US.ACLS", "US.PLAB", "US.ERIC", "US.ON", "US.COHU",
    "US.ARW", "US.PATH", "US.VIAV", "US.INTC", "US.LITE", "US.NOK",
    "US.AEHR", "US.AVT", "US.OUST", "US.SOUN", "US.BBAI", "US.DDD",
    "US.CEVA", "US.TDC",
]


def clean_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def live_price(row):
    for field, source in (
        ("overnight_price", "overnight"),
        ("pre_price", "pre"),
        ("after_price", "after"),
        ("last_price", "regular"),
    ):
        if field in row.index:
            value = clean_float(row[field])
            if value and value > 0:
                return value, source
    return None, "none"


def fetch_kline(quote_ctx, code):
    end = date.today()
    start = end - timedelta(days=390)
    ret, kline, _ = quote_ctx.request_history_kline(
        code,
        start=start.isoformat(),
        end=end.isoformat(),
        ktype=ft.KLType.K_DAY,
        max_count=260,
    )
    if ret != ft.RET_OK or kline.empty:
        return [], {}

    data = kline.copy()
    for col in ("open", "high", "low", "close", "volume"):
        data[col] = pd.to_numeric(data[col], errors="coerce")
    data = data.dropna(subset=["open", "high", "low", "close"])
    if data.empty:
        return [], {}

    monthly = data.tail(252).copy()
    monthly["month"] = pd.to_datetime(monthly["time_key"]).dt.strftime("%b")
    monthly["ym"] = pd.to_datetime(monthly["time_key"]).dt.to_period("M")
    candles = []
    for _, frame in monthly.groupby("ym"):
        candles.append(
            {
                "month": str(frame["month"].iloc[-1]),
                "open": round(float(frame["open"].iloc[0]), 4),
                "high": round(float(frame["high"].max()), 4),
                "low": round(float(frame["low"].min()), 4),
                "close": round(float(frame["close"].iloc[-1]), 4),
            }
        )

    close = data["close"]
    high = data["high"]
    low = data["low"]
    volume = data["volume"] if "volume" in data else pd.Series(dtype=float)
    high_52w = float(data["high"].tail(252).max())
    low_52w = float(data["low"].tail(252).min())
    latest = float(close.iloc[-1])
    position_52w = (latest - low_52w) / (high_52w - low_52w) if high_52w > low_52w else None

    ma20 = close.rolling(20).mean()
    ma50 = close.rolling(50).mean()
    ma200 = close.rolling(200).mean()
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    macd_hist = macd - macd_signal

    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rsi = 100 - (100 / (1 + gain / loss.replace(0, pd.NA)))

    bb_mid = ma20
    bb_std = close.rolling(20).std()
    bb_upper = bb_mid + 2 * bb_std
    bb_lower = bb_mid - 2 * bb_std
    bb_position = (latest - float(bb_lower.iloc[-1])) / (float(bb_upper.iloc[-1]) - float(bb_lower.iloc[-1])) if pd.notna(bb_upper.iloc[-1]) and float(bb_upper.iloc[-1]) != float(bb_lower.iloc[-1]) else None

    prev_close = close.shift(1)
    tr = pd.concat([(high - low), (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    atr_pct = float(atr14.iloc[-1]) / latest * 100 if pd.notna(atr14.iloc[-1]) and latest else None

    volume_ratio = None
    if not volume.empty and len(volume.dropna()) >= 20:
        avg_volume20 = volume.rolling(20).mean().iloc[-1]
        if pd.notna(avg_volume20) and avg_volume20 > 0:
            volume_ratio = float(volume.iloc[-1] / avg_volume20)

    ma20_value = float(ma20.iloc[-1]) if pd.notna(ma20.iloc[-1]) else None
    ma50_value = float(ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else None
    ma200_value = float(ma200.iloc[-1]) if pd.notna(ma200.iloc[-1]) else None
    rsi14 = float(rsi.iloc[-1]) if pd.notna(rsi.iloc[-1]) else None
    macd_hist_value = float(macd_hist.iloc[-1]) if pd.notna(macd_hist.iloc[-1]) else None
    macd_hist_prev = float(macd_hist.iloc[-2]) if len(macd_hist) >= 2 and pd.notna(macd_hist.iloc[-2]) else None

    dist_ma20 = (latest / ma20_value - 1) * 100 if ma20_value else None
    dist_ma50 = (latest / ma50_value - 1) * 100 if ma50_value else None
    dist_ma200 = (latest / ma200_value - 1) * 100 if ma200_value else None

    trend_label = "中性"
    if ma20_value and ma50_value and ma200_value and latest > ma20_value > ma50_value > ma200_value:
        trend_label = "多头排列"
    elif ma20_value and ma50_value and latest > ma20_value > ma50_value:
        trend_label = "短中期向上"
    elif ma20_value and ma50_value and latest < ma20_value < ma50_value:
        trend_label = "弱势下行"

    macd_label = "中性"
    if macd_hist_value is not None and macd_hist_prev is not None:
        if macd_hist_value > 0 and macd_hist_value > macd_hist_prev:
            macd_label = "动能增强"
        elif macd_hist_value > 0:
            macd_label = "动能放缓"
        elif macd_hist_value < 0 and macd_hist_value < macd_hist_prev:
            macd_label = "空头增强"
        else:
            macd_label = "空头收敛"

    buy_timing = "等待"
    if rsi14 and rsi14 > 70 or (dist_ma20 is not None and dist_ma20 > 15) or (position_52w is not None and position_52w > 0.9):
        buy_timing = "过热等待"
    elif trend_label in ("多头排列", "短中期向上") and macd_label == "动能增强" and volume_ratio and volume_ratio > 1.3:
        buy_timing = "突破确认"
    elif rsi14 and 35 <= rsi14 <= 55 and dist_ma20 is not None and -5 <= dist_ma20 <= 3:
        buy_timing = "回踩观察"
    elif rsi14 and rsi14 < 35 and position_52w is not None and position_52w < 0.35:
        buy_timing = "左侧低位"

    technical = {
        "close": round(latest, 4),
        "high52FromKline": round(high_52w, 4),
        "low52FromKline": round(low_52w, 4),
        "ma20": round(ma20_value, 4) if ma20_value is not None else None,
        "ma50": round(ma50_value, 4) if ma50_value is not None else None,
        "ma200": round(ma200_value, 4) if ma200_value is not None else None,
        "distanceMa20Pct": round(dist_ma20, 2) if dist_ma20 is not None else None,
        "distanceMa50Pct": round(dist_ma50, 2) if dist_ma50 is not None else None,
        "distanceMa200Pct": round(dist_ma200, 2) if dist_ma200 is not None else None,
        "position52w": round(position_52w, 4) if position_52w is not None else None,
        "rsi14": round(rsi14, 2) if rsi14 is not None else None,
        "macdHist": round(macd_hist_value, 4) if macd_hist_value is not None else None,
        "macdLabel": macd_label,
        "volumeRatio": round(volume_ratio, 2) if volume_ratio is not None else None,
        "bbPosition": round(bb_position, 4) if bb_position is not None else None,
        "atr14Pct": round(atr_pct, 2) if atr_pct is not None else None,
        "trendLabel": trend_label,
        "buyTiming": buy_timing,
    }
    return candles[-12:], technical


def fetch_analyst_consensus(quote_ctx, code):
    ret, data = quote_ctx.get_research_analyst_consensus(code)
    if ret != ft.RET_OK or not isinstance(data, dict):
        return None
    return {
        "highest": clean_float(data.get("highest")),
        "average": clean_float(data.get("average")),
        "lowest": clean_float(data.get("lowest")),
        "rating": clean_float(data.get("rating")),
        "total": clean_float(data.get("total")),
        "buyPct": clean_float(data.get("buy")),
        "holdPct": clean_float(data.get("hold")),
        "sellPct": clean_float(data.get("sell")),
        "updateTime": data.get("update_time_str"),
    }


def fetch_next_event(quote_ctx, code):
    ret, data = quote_ctx.get_financials_earnings_price_history(code)
    if ret != ft.RET_OK or data is None or data.empty:
        return None

    today = pd.Timestamp(date.today())
    frame = data.copy()
    frame["event_date"] = pd.to_datetime(frame["pub_trading_day_str"], errors="coerce")
    frame = frame.dropna(subset=["event_date"])
    if frame.empty:
        return None

    def event_payload(event):
        event_date = event["event_date"]
        days = int((event_date - today).days)
        return {
            "type": "earnings",
            "period": str(event.get("period_text", "")),
            "date": event_date.strftime("%Y-%m-%d"),
            "time": str(event.get("pub_time_str", "")),
            "daysUntil": days,
            "isFuture": days >= 0,
            "predictedMovePct": clean_float(event.get("predict_vola_ratio_newest")),
            "predictedMoveValue": clean_float(event.get("predict_vola_val_newest")),
        }

    future = frame[frame["event_date"] >= today]
    next_event = event_payload(future.sort_values("event_date").iloc[0]) if not future.empty else None

    recent = frame[(frame["event_date"] < today) & (frame["event_date"] >= today - pd.Timedelta(days=7))]
    recent_event = event_payload(recent.sort_values("event_date").iloc[-1]) if not recent.empty else None

    return {
        "primary": next_event,
        "secondary": recent_event,
    }


def build_highlights(row, consensus, event, technical):
    highlights = []
    price = row.get("price")
    pe = row.get("peTtm") if row.get("peTtm") and row.get("peTtm") > 0 else row.get("pe")
    position = technical.get("position52w") if technical else None

    if pe and pe > 35:
        highlights.append({"level": "risk", "text": f"PE偏高 {pe:.1f}x"})
    elif pe and pe > 0 and pe <= 15:
        highlights.append({"level": "good", "text": f"PE低 {pe:.1f}x"})
    if consensus and consensus.get("average") and price:
        upside = (consensus["average"] / price - 1) * 100
        if upside < -10:
            highlights.append({"level": "risk", "text": f"目标价低于现价 {upside:.0f}%"})
        elif upside > 20:
            highlights.append({"level": "good", "text": f"目标价上行 {upside:.0f}%"})
    primary_event = event.get("primary") if isinstance(event, dict) else event
    if primary_event and primary_event.get("isFuture") and primary_event.get("daysUntil") is not None and primary_event["daysUntil"] <= 14:
        highlights.append({"level": "watch", "text": f"{primary_event['daysUntil']}天内财报"})
    if position is not None and position >= 0.85:
        highlights.append({"level": "watch", "text": "接近52周高位"})
    elif position is not None and position <= 0.25:
        highlights.append({"level": "good", "text": "接近52周低位"})
    if technical:
        rsi14 = technical.get("rsi14")
        dist_ma20 = technical.get("distanceMa20Pct")
        volume_ratio = technical.get("volumeRatio")
        atr_pct = technical.get("atr14Pct")
        buy_timing = technical.get("buyTiming")
        if rsi14 and rsi14 >= 70:
            highlights.append({"level": "risk", "text": f"RSI超买 {rsi14:.0f}"})
        elif rsi14 and rsi14 <= 30:
            highlights.append({"level": "good", "text": f"RSI超卖 {rsi14:.0f}"})
        if dist_ma20 and dist_ma20 > 15:
            highlights.append({"level": "risk", "text": f"高于MA20 {dist_ma20:.0f}%"})
        if volume_ratio and volume_ratio >= 2:
            highlights.append({"level": "watch", "text": f"放量 {volume_ratio:.1f}x"})
        if atr_pct and atr_pct >= 8:
            highlights.append({"level": "watch", "text": f"ATR高 {atr_pct:.1f}%"})
        if buy_timing in ("回踩观察", "左侧低位"):
            highlights.append({"level": "good", "text": buy_timing})
        elif buy_timing in ("过热等待",):
            highlights.append({"level": "risk", "text": buy_timing})
        elif buy_timing in ("突破确认",):
            highlights.append({"level": "watch", "text": buy_timing})
    return highlights[:5]


def main():
    ft.SysConfig.enable_console_log(False)
    quote_ctx = ft.OpenQuoteContext(host=HOST, port=PORT)
    try:
        ret, snapshot = quote_ctx.get_market_snapshot(CODES)
        if ret != ft.RET_OK:
            raise RuntimeError(snapshot)

        rows = []
        for _, row in snapshot.iterrows():
            code = str(row["code"])
            ticker = code.replace("US.", "")
            price, source = live_price(row)
            candles, technical = fetch_kline(quote_ctx, code)
            high_52w = clean_float(row.get("highest52weeks_price")) or technical.get("high52FromKline")
            low_52w = clean_float(row.get("lowest52weeks_price")) or technical.get("low52FromKline")
            pe = clean_float(row.get("pe_ratio"))
            pe_ttm = clean_float(row.get("pe_ttm_ratio"))

            rows.append(
                row_data := {
                    "ticker": ticker,
                    "code": code,
                    "name": str(row.get("name", "")),
                    "price": round(price, 4) if price else None,
                    "priceSource": source,
                    "lastPrice": clean_float(row.get("last_price")),
                    "prePrice": clean_float(row.get("pre_price")),
                    "afterPrice": clean_float(row.get("after_price")),
                    "overnightPrice": clean_float(row.get("overnight_price")),
                    "updateTime": str(row.get("update_time", "")),
                    "pe": round(pe, 4) if pe is not None else None,
                    "peTtm": round(pe_ttm, 4) if pe_ttm is not None else None,
                    "pb": clean_float(row.get("pb_ratio")),
                    "range52w": f"{low_52w:.2f}-{high_52w:.2f}" if low_52w and high_52w else "",
                    "candles": candles,
                    "technical": technical,
                }
            )
            row_data["analystConsensus"] = fetch_analyst_consensus(quote_ctx, code)
            row_data["nextEvent"] = fetch_next_event(quote_ctx, code)
            row_data["highlights"] = build_highlights(row_data, row_data["analystConsensus"], row_data["nextEvent"], technical)

        payload = {
            "source": "moomoo OpenD API",
            "host": HOST,
            "port": PORT,
            "generatedAt": pd.Timestamp.now().isoformat(timespec="seconds"),
            "rows": rows,
        }
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {OUTPUT}")
        print(pd.DataFrame(rows)[["ticker", "price", "priceSource", "pe", "peTtm", "range52w", "updateTime"]].to_string(index=False))
    finally:
        quote_ctx.close()


if __name__ == "__main__":
    main()
