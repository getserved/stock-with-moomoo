# 股票分析工作区

这个工作区包含 MOOMOO / Futu OpenD API 辅助脚本和一个本地美股筛选系统。

## 核心功能

- 从 MOOMOO API 拉取 NYSE / NASDAQ / AMEX 股票基础列表。
- 批量获取行情快照、PE / PE TTM、PB、52 周区间。
- 对候选股票计算 RSI、MACD、MA20 / MA50 / MA200、量比、ATR、布林带位置和买入时机。
- 获取 MOOMOO 分析师共识目标价和财报时间线。
- 获取所属行业和概念板块。
- 提供本地交互页面，支持策略切换、筛选器、分页和悬停注解。

## 本地查看

本地 HTTP 运行版：

```text
http://127.0.0.1:5222/preview.html
```

直接打开 HTML：

```text
C:\Users\getse\Documents\股票分析\preview.html
```

## 刷新数据

确保 MOOMOO OpenD 已启动并登录，然后运行：

```bash
python -X utf8 tools/fetch_moomoo_market_screener.py --universe-limit 8000 --deep-limit 200
python -X utf8 tools/render_interactive_preview.py
```

## 重要文件

- `ai-stock-screener/`：React + Vite 前端项目。
- `ai-stock-screener/src/data/apiSnapshot.json`：MOOMOO API 生成的数据快照。
- `tools/fetch_moomoo_market_screener.py`：全市场数据管线。
- `tools/fetch_moomoo_screener.py`：固定股票池调试管线。
- `tools/render_interactive_preview.py`：生成不依赖 Vite 的本地交互页面。
- `preview.html`：当前本地交互页面。
