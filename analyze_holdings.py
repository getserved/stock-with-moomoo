import argparse
from datetime import date, timedelta

import moomoo as ft
import pandas as pd


HOST = "127.0.0.1"
PORT = 11111


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
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    data["high"] = pd.to_numeric(data["high"], errors="coerce")
    data["low"] = pd.to_numeric(data["low"], errors="coerce")
    data["ema12"] = ema(data["close"], 12)
    data["ema26"] = ema(data["close"], 26)
    data["macd_dif"] = data["ema12"] - data["ema26"]
    data["macd_dea"] = ema(data["macd_dif"], 9)
    data["macd_hist"] = 2 * (data["macd_dif"] - data["macd_dea"])
    data["rsi14"] = rsi(data["close"], 14)
    data["ma20"] = data["close"].rolling(20).mean()
    data["ma50"] = data["close"].rolling(50).mean()
    return data


def support_resistance(data: pd.DataFrame) -> tuple[float, float]:
    recent = data.tail(60)
    support = float(recent["low"].rolling(5, center=True).min().dropna().tail(20).min())
    resistance = float(recent["high"].rolling(5, center=True).max().dropna().tail(20).max())
    return support, resistance


def signal(row: pd.Series, prev: pd.Series, support: float, resistance: float) -> str:
    close = float(row["close"])
    rsi_value = float(row["rsi14"])
    macd_hist = float(row["macd_hist"])
    prev_hist = float(prev["macd_hist"])

    notes = []
    if rsi_value >= 70:
        notes.append("RSI偏热")
    elif rsi_value <= 30:
        notes.append("RSI偏冷")
    else:
        notes.append("RSI中性")

    if macd_hist > 0 and macd_hist > prev_hist:
        notes.append("MACD动能增强")
    elif macd_hist < 0 and macd_hist < prev_hist:
        notes.append("MACD动能转弱")
    else:
        notes.append("MACD动能钝化")

    if close <= support * 1.03:
        notes.append("接近支撑")
    elif close >= resistance * 0.97:
        notes.append("接近压力")

    return "；".join(notes)


def get_positions() -> list[str]:
    codes = set()
    firms = [
        ft.SecurityFirm.FUTUINC,
        ft.SecurityFirm.FUTUAU,
        ft.SecurityFirm.FUTUSG,
        ft.SecurityFirm.FUTUSECURITIES,
        ft.SecurityFirm.NONE,
    ]
    markets = [ft.TrdMarket.US, ft.TrdMarket.HK]
    envs = [ft.TrdEnv.REAL, ft.TrdEnv.SIMULATE]

    for firm in firms:
        for market in markets:
            ctx = ft.OpenSecTradeContext(
                filter_trdmarket=market,
                security_firm=firm,
                host=HOST,
                port=PORT,
            )
            try:
                for env in envs:
                    ret, positions = ctx.position_list_query(trd_env=env)
                    if ret == ft.RET_OK and not positions.empty and "code" in positions:
                        for code in positions["code"].dropna().astype(str):
                            codes.add(code)
            finally:
                ctx.close()

    return sorted(codes)


def analyze_code(quote_ctx: ft.OpenQuoteContext, code: str) -> dict:
    end = date.today()
    start = end - timedelta(days=260)
    ret, kline, _ = quote_ctx.request_history_kline(
        code,
        start=start.isoformat(),
        end=end.isoformat(),
        ktype=ft.KLType.K_DAY,
        max_count=200,
    )
    if ret != ft.RET_OK or kline.empty:
        return {"code": code, "error": str(kline)}

    data = add_indicators(kline)
    support, resistance = support_resistance(data)
    latest = data.iloc[-1]
    previous = data.iloc[-2]
    close = float(latest["close"])

    return {
        "code": code,
        "name": latest.get("name", ""),
        "close": round(close, 2),
        "rsi14": round(float(latest["rsi14"]), 2),
        "macd_dif": round(float(latest["macd_dif"]), 4),
        "macd_dea": round(float(latest["macd_dea"]), 4),
        "macd_hist": round(float(latest["macd_hist"]), 4),
        "ma20": round(float(latest["ma20"]), 2),
        "ma50": round(float(latest["ma50"]), 2),
        "support": round(support, 2),
        "resistance": round(resistance, 2),
        "downside_to_support_pct": round((close / support - 1) * 100, 2),
        "upside_to_resistance_pct": round((resistance / close - 1) * 100, 2),
        "signal": signal(latest, previous, support, resistance),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codes", nargs="*", help="Stock codes, for example US.AAPL US.NVDA")
    args = parser.parse_args()

    ft.SysConfig.enable_console_log(False)
    codes = args.codes or get_positions()
    if not codes:
        print("No positions were exposed by OpenD. Pass codes manually, for example:")
        print("python analyze_holdings.py --codes US.AAPL US.NVDA")
        return 2

    quote_ctx = ft.OpenQuoteContext(host=HOST, port=PORT)
    try:
        rows = [analyze_code(quote_ctx, code) for code in codes]
    finally:
        quote_ctx.close()

    result = pd.DataFrame(rows)
    print(result.to_string(index=False))
    return 0 if "error" not in result.columns else 1


if __name__ == "__main__":
    raise SystemExit(main())
