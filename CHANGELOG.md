# Changelog / 版本更新

## v0.4.0 - 2026-06-04

- Added floating watchlist signal labels that use short human-readable wording such as `强势上行`, `偏强上行`, `上行回踩`, and `回踩观察`.
- 新增悬浮窗技术信号短语化显示，例如 `强势上行`、`偏强上行`、`上行回踩`、`回踩观察`，不再只显示抽象分数标签。

- Added hover tooltip analysis for each floating-watchlist row with RSI, MACD, moving-average, volume, support, breakout, and stop-loss guidance.
- 新增悬停提示，显示 RSI、MACD、均线、量能、支撑位、突破位与止损建议。

- Added fallback rendering for stocks that have live price but no K-line quota, including a visible K-line error message instead of silently dropping rows.
- 对有实时价但拿不到历史 K 线额度的股票，新增可见错误提示，不再让后续股票消失。

- Updated floating window focus behavior: idle is semi-transparent, hover/focus becomes opaque, and blur returns to semi-transparent.
- 更新悬浮窗透明度行为：平时半透明，悬停或获得焦点时不透明，失焦后恢复半透明。

- Improved bridge refresh behavior so saving holdings refreshes the floating watchlist immediately when it is already running.
- 改进 bridge 刷新逻辑：保存持股时，如果悬浮窗已经开启，会立即刷新内容。
