# 美股基本面 + 技术面筛选系统

这是一个基于 MOOMOO / Futu OpenD API 的本地研究面板，用来从美股市场中筛选股票，并按基本面、估值、价格位置和技术面择时排序。

当前版本不再限定 AI 产业，也不再限定股价 100 美元以内。系统会从 MOOMOO API 获取 NYSE / NASDAQ / AMEX 普通股基础列表，再拉取行情快照、PE、52 周区间、技术指标、分析师共识目标价、财报时间线和所属行业/概念。

## 筛选逻辑

综合分默认由以下维度加权：

- 估值：PE / PE TTM、目标价相对现价等。
- 基本面：当前用分析师共识、盈利状态和风险提示作为代理，后续可扩展财务报表字段。
- 横盘/低位：52 周位置、是否接近高位或低位。
- 趋势均线：MA20 / MA50 / MA200、均线排列、价格距离均线。
- 动量：RSI14、MACD 柱体方向。
- 成交量：成交量相对 20 日均量的倍数。
- 波动率：ATR14%、布林带位置。
- 买入时机：回踩观察、突破确认、左侧低位、过热等待、等待。

默认权重：

- 估值 30
- 基本面 30
- 横盘/低位 20
- 趋势均线 8
- 动量 RSI/MACD 6
- 成交量 4
- 波动率 6
- 买入时机 12

## 策略预设

本地页面提供多个排序策略：

- 综合平衡：基本面、估值、低位和择时一起看。
- 基本面优先：更重视基本面和估值，技术面只避免明显追高。
- 买点优先：更重视回踩观察、突破确认和不过热的技术状态。
- 低估低位：寻找低 PE、低位、偏左侧的股票。
- 突破动量：偏向趋势向上、MACD 动能增强、成交量放大的股票。
- 低波动安全：更排斥 ATR 高、目标价倒挂和过热状态。

## 筛选器

本地运行页支持：

- 价格范围
- PE 范围
- RSI 范围
- 行业/主题
- 买入时机
- 高亮类型：机会、观察、风险

页面每页显示 20 行，筛选和排序仍作用于全量已加载数据。

## 数据管线

主要脚本：

- `tools/fetch_moomoo_market_screener.py`：全市场 API 管线。通过 `get_stock_basicinfo` 获取 NYSE / NASDAQ / AMEX 股票列表，批量 `get_market_snapshot` 获取行情，再对筛选结果补 K 线、分析师共识、财报时间线和所属行业/概念。
- `tools/fetch_moomoo_screener.py`：固定列表版本，适合调试 watchlist 或指定股票。
- `tools/render_interactive_preview.py`：生成可本地运行的 `preview.html`，不依赖 Vite。

当前 `apiSnapshot.json` 是生成后的前端数据快照。

## 运行

### MOOMOO OpenD

先确保 OpenD 在本机运行，默认连接：

```text
127.0.0.1:11111
```

刷新全市场数据：

```bash
python -X utf8 tools/fetch_moomoo_market_screener.py --universe-limit 8000 --deep-limit 200
python -X utf8 tools/render_interactive_preview.py
```

### 本地运行版

当前机器没有可用的 npm/npx，所以 Vite 暂时不是默认运行方式。可以用本地 HTTP 服务查看生成的交互页：

```text
http://127.0.0.1:5222/preview.html
```

也可以直接打开：

```text
C:\Users\getse\Documents\股票分析\preview.html
```

### React + Vite

如果 Node/npm 环境可用，可以运行：

```bash
npm install
npm run dev
```

项目目录：

```text
ai-stock-screener
```
