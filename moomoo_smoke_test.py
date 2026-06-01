import sys

import moomoo as ft


DEFAULT_CODES = ["US.AAPL", "US.TSLA", "US.NVDA"]


def main() -> int:
    codes = sys.argv[1:] or DEFAULT_CODES
    ft.SysConfig.enable_console_log(False)

    quote_ctx = ft.OpenQuoteContext(host="127.0.0.1", port=11111)
    try:
        print(f"conn_id: {quote_ctx.get_sync_conn_id()}")

        ret, state = quote_ctx.get_global_state()
        print(f"global_state_ret: {ret}")
        print(
            "status:",
            state.get("program_status_type"),
            "qot_logined:",
            state.get("qot_logined"),
            "trd_logined:",
            state.get("trd_logined"),
        )
        if ret != ft.RET_OK:
            print(state)
            return 1

        ret, snapshot = quote_ctx.get_market_snapshot(codes)
        print(f"snapshot_ret: {ret}")
        if ret != ft.RET_OK:
            print(snapshot)
            return 1

        columns = [col for col in ["code", "name", "last_price", "price_spread", "update_time"] if col in snapshot.columns]
        print(snapshot[columns].to_string(index=False))
        return 0
    finally:
        quote_ctx.close()


if __name__ == "__main__":
    raise SystemExit(main())
