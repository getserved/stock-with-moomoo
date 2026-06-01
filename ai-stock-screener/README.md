# React Stock Screener UI / React 股票筛选界面

This folder contains the React + Vite version of the MOOMOO-powered stock screener.

这个目录包含 MOOMOO 股票筛选器的 React + Vite 版本。

## Purpose / 用途

The UI reads from `src/data/apiSnapshot.json` and displays stock candidates with:

界面读取 `src/data/apiSnapshot.json`，并展示以下信息：

- price, PE, 52-week range, and basic valuation data
- 股价、PE、52 周区间和基础估值数据

- analyst target where available from the API
- API 可用时显示机构目标价

- upcoming event timeline
- 后续重大事件时间线

- technical indicators such as RSI, MACD, moving averages, volume ratio, and ATR
- RSI、MACD、均线、成交量倍率、ATR 等技术指标

- strategy-based ranking and configurable score weights
- 基于策略的排序和可调整权重评分

## Run / 运行

Install dependencies and start Vite:

安装依赖并启动 Vite：

```bash
npm install
npm run dev
```

The default Vite script binds to:

默认 Vite 地址为：

```text
http://127.0.0.1:5173
```

If another local app is already using that port, Vite will choose another one.

如果端口已经被其他本地应用占用，Vite 会自动选择其他端口。

## Data Refresh / 数据刷新

From the repository root, run:

在仓库根目录运行：

```bash
python -X utf8 tools/fetch_moomoo_market_screener.py --universe-limit 8000 --deep-limit 200
python -X utf8 tools/render_interactive_preview.py
```

`apiSnapshot.json` is generated from MOOMOO/Futu OpenD and then consumed by this React app.

`apiSnapshot.json` 由 MOOMOO / 富途 OpenD 生成，然后由 React 应用读取。

## Ranking Logic / 排名逻辑

The screener combines fundamentals and technical signals. The default weight set emphasizes valuation, fundamentals, and entry timing:

筛选器结合基本面与技术面信号。默认权重更重视估值、基本面和买入时机：

- valuation / 估值
- sideways or low-position setup / 横盘或低位状态
- fundamentals / 基本面
- trend / 趋势
- momentum / 动量
- volume confirmation / 成交量确认
- volatility risk / 波动率风险
- entry timing / 买入时机

The UI also provides several strategy presets, so changing strategy should change the ranking order even when filters stay the same.

界面提供多个策略预设，因此即使筛选条件不变，切换策略也应该改变排序结果。

## Disclaimer / 免责声明

This app is for screening and research only. It is not financial advice, and the API output should be verified before making trading decisions.

本应用仅用于筛选和研究，不构成投资建议。交易决策前应自行核验 API 数据。
