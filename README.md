# Stock Screener With MOOMOO / 富途牛牛股票筛选器

This repository contains a local stock-screening workflow powered by the MOOMOO/Futu OpenD API. It scans the US stock universe, enriches candidates with fundamentals and technical indicators, and renders an interactive local preview page.

本仓库是一个基于 MOOMOO / 富途 OpenD API 的本地股票筛选系统。它会扫描美股股票池，补充基本面和技术面数据，并生成一个可交互的本地预览页面。

## What It Does / 功能

- Pulls US stock data from MOOMOO OpenD for NYSE, NASDAQ, and AMEX.
- 从 MOOMOO OpenD 拉取 NYSE、NASDAQ、AMEX 的美股数据。

- Screens stocks by price, PE, 52-week position, RSI, trend, volatility, and event timeline.
- 按股价、PE、52 周位置、RSI、趋势、波动率和重大事件时间线进行筛选。

- Supports multiple ranking strategies: balanced, fundamentals-first, entry timing, deep value, breakout, and low risk.
- 支持多种排序策略：综合平衡、基本面优先、买点优先、低估低位、突破动量、低波动安全。

- Generates an interactive `preview.html` page that can be opened locally or served by a simple HTTP server.
- 生成可交互的 `preview.html`，既可以本地打开，也可以通过简单 HTTP 服务访问。

## Local Preview / 本地预览

When the local preview server is running, open:

本地预览服务启动后，打开：

```text
http://127.0.0.1:5223/preview.html
```

You can also open the generated file directly:

也可以直接打开生成的文件：

```text
<repo>\preview.html
```

## Floating Watchlist Bridge / 悬浮持股窗

The preview page includes a `我的持股` area. Start the local bridge first:

预览页包含 `我的持股` 区域。先启动本地 bridge：

```bash
python -X utf8 tools/local_watchlist_bridge.py --port 8765
```

Then open the preview page, add or remove tickers, and click `开启悬浮窗` / `关闭悬浮窗`. The browser sends the selected tickers to `http://127.0.0.1:8765`, the bridge writes `watchlist.txt` and `selected_watchlist.json`, then toggles `floating_watchlist.py`.

然后打开预览页，添加或删除 ticker，点击 `开启悬浮窗` / `关闭悬浮窗`。浏览器会把选中的股票发送到 `http://127.0.0.1:8765`，bridge 会写入 `watchlist.txt` 和 `selected_watchlist.json`，再切换 `floating_watchlist.py`。

`selected_watchlist.json` and `floating_watchlist.pid` are local runtime files and are intentionally ignored by Git.

`selected_watchlist.json` 和 `floating_watchlist.pid` 是本地运行时文件，已加入 Git 忽略。

Floating watchlist highlights:

悬浮窗更新重点：

- Short signal labels now use human-readable wording such as `强势上行`, `偏强上行`, `上行回踩`, `回踩观察`, and `区间观察`.
- 技术信号现在使用更直观的短语，例如 `强势上行`、`偏强上行`、`上行回踩`、`回踩观察`、`区间观察`。
- Hovering a watchlist row shows a compact technical tooltip with RSI, MACD, moving-average state, volume context, support, breakout, stop-loss, and a left-side or right-side entry suggestion.
- 鼠标悬停在悬浮窗单行上，会显示简短技术分析，包括 RSI、MACD、均线状态、量能、支撑位、突破位、止损位，以及左侧或右侧的观察建议。
- If a stock has a live quote but MOOMOO refuses K-line data because of quota limits, the row stays visible and expands with a K-line error message.
- 如果某只股票还能拿到实时价格，但 MOOMOO 因历史 K 线额度不足拒绝返回 K 线，该股票仍会保留在列表中，并在展开时显示 K 线错误提示。
- The floating window is semi-transparent by default, becomes opaque while hovered or focused, and dims again after losing focus.
- 悬浮窗默认半透明，悬停或获得焦点时变为不透明，失去焦点后再恢复半透明。

## Refresh Data / 刷新数据

Start MOOMOO/Futu OpenD first, then run:

先启动 MOOMOO / 富途 OpenD，然后运行：

```bash
python -X utf8 tools/fetch_moomoo_market_screener.py --universe-limit 8000 --deep-limit 200
python -X utf8 tools/fetch_theme_news.py --lookback-hours 48 --max-records 20 --provider both
python -X utf8 tools/render_interactive_preview.py
```

The first command fetches market data and writes `ai-stock-screener/src/data/apiSnapshot.json`.

第一条命令会拉取市场数据，并写入 `ai-stock-screener/src/data/apiSnapshot.json`。

The second command adds no-key theme news from GDELT and Google News RSS, then maps concrete events back to stocks by direct company mention or negative sector shock.

第二条命令会用 GDELT 和 Google News RSS 拉取无需 API key 的主题新闻，并按公司直接命中或负面产业冲击把具体事件映射回股票。

The third command rebuilds the interactive `preview.html`.

第三条命令会重新生成交互式 `preview.html`。

## Preset Screening Combos / 常用筛选组合

The preview page includes one-click screening presets in a fixed filter dock. Presets only change filter conditions; they do not switch the active ranking strategy. Presets are multi-select filters: presets in the same group are OR conditions, presets across different groups are AND conditions, and selecting none disables preset filtering.

预览页面在固定筛选面板里提供一键筛选组合。组合只改变筛选条件，不会切换当前排序策略。组合支持复选：同一组内是 OR，不同组之间是 AND，全部不选则不启用组合筛选。

The same table also has quick list modes:

同一个表格还提供快速列表模式：

- Fundamental/event shock selloff
  Reuses current-row fields such as 52-week drawdown, low 52-week position, negative PE, risk highlights, analyst target downside, and near-term events. It is a proxy list, not a separate news feed.

  基本面/事件冲击大跌：复用当前行已有字段，例如 52 周高点回撤、52 周低位、负 PE、风险高亮、机构目标价倒挂、近期事件。这是推断列表，不是新的新闻接口。

- Upcoming earnings/events
  Reuses `nextEvent.primary.daysUntil` and sorts rows by nearest future event first.

  财报/重大事件临近：复用 `nextEvent.primary.daysUntil`，按未来事件由近到远排序。

- News/event driven
  Reuses `themeNewsFeed` from `tools/fetch_theme_news.py`, but industry/theme heat no longer adds ranking points by itself. AI, semiconductor, space, and quantum terms only decide which stocks are eligible for a related news pool. The event score comes from concrete article terms such as explosion, failure, anomaly, investigation, contract, approval, funding, earnings, SEC filings, price shock, near-term events, and unusual volume.

  新闻/事件驱动：复用 `tools/fetch_theme_news.py` 写入的 `themeNewsFeed`，但行业/主题热度本身不再加排序分。AI、半导体、太空、量子只负责判断股票是否进入相关新闻池。事件分来自具体新闻词和市场反应，例如爆炸、失败、异常、调查、合同、获批、融资、财报、SEC 公告、价格冲击、临近事件和成交量异常。

  The table shows an explicit event score column. Hovering over the score shows the scoring formula and the actual reasons that contributed to that row. Related articles appear in the highlight column as blue `新闻` tags; hovering those tags shows source, title, and link.

  表格会单独显示 `事件分`。鼠标悬停在分数上会显示评分公式和该股票实际触发原因。相关新闻会在高亮列里以蓝色 `新闻` 标签显示，悬停后可以看到来源、标题和链接。

  Event score formula:

  事件分公式：

  ```text
  news event terms up to 60
  + price shock up to 35
  + SEC filings up to 35
  + earnings / conference within 7 days 12
  + unusual volume 10
  - small-cap penalty 8
  ```

  ```text
  新闻事件词最高60分
  + 价格冲击最高35分
  + SEC公告最高35分
  + 7天内财报/会议12分
  + 放量10分
  - 小市值惩罚8分
  ```

- AI / semiconductor theme
  Looks for theme keywords such as AI, artificial intelligence, semiconductor, software, data, cloud, robotics, optical network, and AI-RAN.

  AI / 半导体主题：按 AI、人工智能、半导体、软件、数据、云、机器人、光网络、AI-RAN 等关键词过滤。

- Space and quantum themes
  The fixed preset dock includes separate AI, space/satellite, and quantum filters. Market cap is controlled only by the manual market-cap filter.

  太空和量子主题：固定筛选面板里单独提供 AI、太空/卫星、量子三个条件。市值只由手动市值筛选器控制。

- Minimum market cap
  The manual filter uses million USD as the unit, so `300` means 300 million USD.

  最小市值：手动筛选器用“百万美元”为单位，所以 `300` 代表 3 亿美元。

- Long consolidation with low volume
  Looks for neutral RSI, lower 52-week position, and volume ratio below the breakout threshold.

  长时间横盘缩量：寻找 RSI 中性、52 周位置偏低、成交量没有明显放大的潜在蓄势标的。

- Pullback entry
  Focuses on stocks tagged as pullback watch or left-side low setup.

  回踩买点：聚焦系统标记为回踩观察或左侧低位的股票。

- Deep value near lows
  Combines lower PE, lower 52-week position, and non-overheated RSI.

  低估低位：结合较低 PE、较低 52 周位置和不过热 RSI。

- Volume-confirmed breakout
  Requires higher volume ratio and a healthy, not extremely overbought RSI range.

  突破放量：要求成交量放大，并让 RSI 处于偏强但不过热的区间。

- Low-volatility value
  Combines lower ATR, reasonable PE, and non-overheated RSI.

  低波动价值：结合较低 ATR、合理 PE 和不过热 RSI，适合作为稳健观察池。

## Project Layout / 项目结构

- `tools/fetch_moomoo_market_screener.py`
  Full-market MOOMOO data pipeline. It builds the US stock universe, fetches snapshots, enriches selected stocks with K-line, analyst, event, and industry data.

  全市场 MOOMOO 数据管线。它会构建美股股票池，抓取行情快照，并给部分股票补充 K 线、机构评级、事件和行业数据。

- `tools/fetch_moomoo_screener.py`
  Shared helpers for price selection, K-line indicators, analyst consensus, event lookup, and highlight generation.

  通用工具函数，包括价格选择、K 线指标、机构估价、事件查询和高亮信息生成。

- `tools/render_interactive_preview.py`
  Builds the standalone interactive HTML preview.

  生成独立可交互的 HTML 预览页面。

- `tools/local_watchlist_bridge.py`
  Local HTTP bridge used by `preview.html` to save the selected holdings and open the floating watchlist window.

  本地 HTTP bridge，供 `preview.html` 保存选中的持股并开启悬浮持股窗。

- `tools/fetch_theme_news.py`
  Pulls no-key theme news from GDELT and Google News RSS, writes `themeNewsFeed`, and attaches `themeNews`, `eventDrivenScore`, `eventDrivenReasons`, and `priceChangePct` to matching rows.

  从 GDELT 和 Google News RSS 拉取无需 API key 的主题新闻，写入 `themeNewsFeed`，并把 `themeNews`、`eventDrivenScore`、`eventDrivenReasons`、`priceChangePct` 附加到匹配股票。

- `ai-stock-screener/`
  React + Vite version of the screener UI.

  React + Vite 版本的筛选器界面。

- `preview.html`
  Generated local preview page.

  已生成的本地预览页面。

## Notes / 注意事项

- This project expects MOOMOO/Futu OpenD to be available at `127.0.0.1:11111`.
- 本项目默认 MOOMOO / 富途 OpenD 运行在 `127.0.0.1:11111`。

- The output is a research aid, not investment advice.
- 输出内容仅用于研究辅助，不构成投资建议。

- `analyze_holdings.py` can query local trading-account positions through OpenD. It does not contain credentials, but avoid publishing account-derived output.
- `analyze_holdings.py` 可以通过 OpenD 查询本地交易账户持仓。脚本本身不包含密码，但不要公开由账户数据生成的结果。
