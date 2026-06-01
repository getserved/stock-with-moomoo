import argparse
import json
from pathlib import Path

import moomoo as ft
import pandas as pd

from fetch_moomoo_screener import (
    HOST,
    PORT,
    OUTPUT,
    build_highlights,
    clean_float,
    fetch_analyst_consensus,
    fetch_kline,
    fetch_next_event,
    live_price,
)


ROOT = Path(__file__).resolve().parents[1]
META_OUTPUT = ROOT / "ai-stock-screener" / "src" / "data" / "marketUniverse.json"
WATCHLIST = ROOT / "watchlist.txt"


def make_filter(field, min_value=None, max_value=None, sort=None, filter_cls=ft.SimpleFilter):
    item = filter_cls()
    item.stock_field = field
    item.filter_min = min_value
    item.filter_max = max_value
    item.sort = sort
    return item


def stock_filter_page(quote_ctx, filters, begin, num):
    ret, data = quote_ctx.get_stock_filter(ft.Market.US, filters, begin=begin, num=num)
    if ret != ft.RET_OK:
        raise RuntimeError(data)
    _, total, rows = data
    parsed = []
    for item in rows:
        row = {}
        text = str(item)
        for part in text.split("  "):
            if ":" in part:
                key, value = part.strip().split(":", 1)
                row[key.strip()] = value.strip()
        exchange = row.get("exchange_type", "")
        if row.get("stock_code") and ("NASDAQ" in exchange or "NYSE" in exchange or "AMEX" in exchange):
            parsed.append(row)
    return total, parsed


def fetch_universe(quote_ctx, args):
    ret, data = quote_ctx.get_stock_basicinfo(ft.Market.US, ft.SecurityType.STOCK)
    if ret != ft.RET_OK:
        raise RuntimeError(data)
    frame = data.copy()
    frame = frame[
        (frame["delisting"] == False)
        & (frame["exchange_type"].isin(["US_NASDAQ", "US_NYSE", "US_AMEX"]))
        & (frame["code"].astype(str).str.match(r"^US\.[A-Z.]+$"))
    ]
    rows = frame[["code", "name", "exchange_type"]].rename(columns={"code": "stock_code", "name": "stock_name"}).to_dict("records")
    return rows[: args.universe_limit]


def snapshot_chunks(quote_ctx, codes, chunk_size=80):
    frames = []
    failed = []
    for start in range(0, len(codes), chunk_size):
        chunk = codes[start : start + chunk_size]
        ret, snapshot = quote_ctx.get_market_snapshot(chunk)
        if ret == ft.RET_OK and snapshot is not None and not snapshot.empty:
            frames.append(snapshot)
        elif len(chunk) > 1:
            small_frames, small_failed = snapshot_chunks(quote_ctx, chunk, chunk_size=max(1, len(chunk) // 2))
            frames.extend(small_frames)
            failed.extend(small_failed)
        else:
            failed.extend(chunk)
    if frames:
        return [pd.concat(frames, ignore_index=True)], failed
    return [], failed


def enrich_codes(quote_ctx, codes, min_volume=None, min_market_cap=None):
    frames, failed = snapshot_chunks(quote_ctx, codes)
    if not frames:
        return []
    snapshot = frames[0]

    rows = []
    for _, item in snapshot.iterrows():
        code = str(item["code"])
        ticker = code.replace("US.", "")
        price, source = live_price(item)
        high_52w = clean_float(item.get("highest52weeks_price"))
        low_52w = clean_float(item.get("lowest52weeks_price"))
        position_52w = (price - low_52w) / (high_52w - low_52w) if price and high_52w and low_52w and high_52w > low_52w else None
        technical = {
            "position52w": round(position_52w, 4) if position_52w is not None else None,
            "buyTiming": "待深度分析",
        }
        pe = clean_float(item.get("pe_ratio"))
        pe_ttm = clean_float(item.get("pe_ttm_ratio"))
        volume = clean_float(item.get("volume"))
        market_cap = clean_float(item.get("total_market_val"))
        if price is None or price < 0.5:
            continue
        if min_volume is not None and volume is not None and volume < min_volume:
            continue
        if min_market_cap is not None and market_cap is not None and market_cap < min_market_cap:
            continue
        row_data = {
            "ticker": ticker,
            "code": code,
            "name": str(item.get("name", "")),
            "price": round(price, 4) if price else None,
            "priceSource": source,
            "lastPrice": clean_float(item.get("last_price")),
            "prePrice": clean_float(item.get("pre_price")),
            "afterPrice": clean_float(item.get("after_price")),
            "overnightPrice": clean_float(item.get("overnight_price")),
            "updateTime": str(item.get("update_time", "")),
            "pe": round(pe, 4) if pe is not None else None,
            "peTtm": round(pe_ttm, 4) if pe_ttm is not None else None,
            "pb": clean_float(item.get("pb_ratio")),
            "range52w": f"{low_52w:.2f}-{high_52w:.2f}" if low_52w and high_52w else "",
            "candles": [],
            "technical": technical,
            "theme": "全市场筛选",
        }
        row_data["analystConsensus"] = None
        row_data["nextEvent"] = None
        row_data["highlights"] = build_highlights(row_data, None, None, technical)
        rows.append(row_data)
    return rows


def fetch_owner_plates(quote_ctx, codes):
    result = {}
    for start in range(0, len(codes), 80):
        chunk = codes[start : start + 80]
        ret, data = quote_ctx.get_owner_plate(chunk)
        if ret != ft.RET_OK or data is None or data.empty:
            continue
        for code, group in data.groupby("code"):
            industry = group[group["plate_type"].astype(str).eq("INDUSTRY")]
            concept = group[group["plate_type"].astype(str).eq("CONCEPT")]
            result[code] = {
                "industry": str(industry.iloc[0]["plate_name"]) if not industry.empty else "未分类",
                "concepts": [str(value) for value in concept["plate_name"].head(3).tolist()],
            }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--min-price", type=float, default=0.5)
    parser.add_argument("--max-price", type=float, default=2000)
    parser.add_argument("--min-pe", type=float, default=None)
    parser.add_argument("--max-pe", type=float, default=None)
    parser.add_argument("--min-volume", type=float, default=None)
    parser.add_argument("--max-volume", type=float, default=None)
    parser.add_argument("--min-market-cap", type=float, default=None)
    parser.add_argument("--max-market-cap", type=float, default=None)
    parser.add_argument("--universe-limit", type=int, default=500)
    parser.add_argument("--deep-limit", type=int, default=80)
    args = parser.parse_args()

    ft.SysConfig.enable_console_log(False)
    quote_ctx = ft.OpenQuoteContext(host=HOST, port=PORT)
    try:
        must_include = set()
        if WATCHLIST.exists():
            for line in WATCHLIST.read_text(encoding="utf-8").splitlines():
                text = line.strip().upper()
                if text and not text.startswith("#"):
                    must_include.add(text if "." in text else f"US.{text}")
        must_include.update({"US.MU", "US.NVDA", "US.AMD", "US.INTC", "US.BB", "US.NOK"})
        universe = fetch_universe(quote_ctx, args)
        codes = list(dict.fromkeys([*sorted(must_include), *[row["stock_code"] for row in universe]]))
        rows = enrich_codes(quote_ctx, codes, args.min_volume, args.min_market_cap)
        present = {row["code"] for row in rows}
        missing = sorted(code for code in must_include if code not in present)
        if missing:
            extra_rows = enrich_codes(quote_ctx, missing, None, None)
            print(f"Forced include rows: {[row['code'] for row in extra_rows]}")
            rows.extend(extra_rows)
        present = {row["code"] for row in rows}
        if "US.MU" not in present:
            mu_rows = enrich_codes(quote_ctx, ["US.MU"], None, None)
            print(f"Forced MU rows: {[row['code'] for row in mu_rows]}")
            rows.extend(mu_rows)
        rows = sorted(rows, key=lambda item: item.get("price") or 0)
        deep_candidates = rows[: args.deep_limit]
        plates = fetch_owner_plates(quote_ctx, [row["code"] for row in deep_candidates])
        for row_data in deep_candidates:
            code = row_data["code"]
            plate = plates.get(code, {})
            row_data["industry"] = plate.get("industry", "未分类")
            row_data["concepts"] = plate.get("concepts", [])
            row_data["theme"] = row_data["industry"]
            candles, technical = fetch_kline(quote_ctx, code)
            row_data["candles"] = candles
            row_data["technical"] = technical or row_data.get("technical", {})
            row_data["analystConsensus"] = fetch_analyst_consensus(quote_ctx, code)
            row_data["nextEvent"] = fetch_next_event(quote_ctx, code)
            row_data["highlights"] = build_highlights(row_data, row_data["analystConsensus"], row_data["nextEvent"], row_data.get("technical", {}))
        payload = {
            "source": "moomoo OpenD API full-market stock_filter",
            "host": HOST,
            "port": PORT,
            "generatedAt": pd.Timestamp.now().isoformat(timespec="seconds"),
            "filterArgs": vars(args),
            "universeCount": len(universe),
            "deepCount": len(rows),
            "rows": rows,
        }
        OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        META_OUTPUT.write_text(json.dumps({"universe": universe[: args.universe_limit]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Universe rows: {len(universe)}; deep rows: {len(rows)}")
        print(f"Wrote {OUTPUT}")
    finally:
        quote_ctx.close()


if __name__ == "__main__":
    main()
