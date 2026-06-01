import React, { useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownUp,
  BarChart3,
  CheckCircle2,
  Filter,
  Search,
  SlidersHorizontal,
} from "lucide-react";
import { stocks, sourceNotes } from "./data/stocks";
import apiSnapshot from "./data/apiSnapshot.json";
import "./styles.css";

const defaultWeights = {
  value: 30,
  sideways: 20,
  fundamentals: 30,
  trend: 8,
  momentum: 6,
  volume: 4,
  volatility: 6,
  timing: 12,
};

const strategyPresets = {
  balanced: {
    label: "综合平衡",
    description: "基本面、估值、低位和择时一起看，适合默认研究排序。",
    weights: defaultWeights,
  },
  fundamentals: {
    label: "基本面优先",
    description: "更重视基本面和估值，技术面只用于避免明显追高。",
    weights: { value: 35, sideways: 15, fundamentals: 40, trend: 3, momentum: 2, volume: 1, volatility: 8, timing: 6 },
  },
  entryTiming: {
    label: "买点优先",
    description: "更重视回踩观察、左侧低位和不过热的技术状态。",
    weights: { value: 18, sideways: 18, fundamentals: 20, trend: 12, momentum: 10, volume: 8, volatility: 8, timing: 24 },
  },
  deepValue: {
    label: "低估低位",
    description: "寻找PE较低、接近52周低位、没有严重技术破位的股票。",
    weights: { value: 42, sideways: 32, fundamentals: 18, trend: 2, momentum: 2, volume: 1, volatility: 2, timing: 1 },
  },
  breakout: {
    label: "突破动量",
    description: "偏向趋势向上、MACD动能增强、成交量放大的股票。",
    weights: { value: 12, sideways: 6, fundamentals: 18, trend: 24, momentum: 18, volume: 16, volatility: 2, timing: 14 },
  },
  lowRisk: {
    label: "低波动安全",
    description: "更排斥ATR高、财报临近、目标价倒挂和过热状态。",
    weights: { value: 28, sideways: 14, fundamentals: 32, trend: 5, momentum: 3, volume: 2, volatility: 22, timing: 10 },
  },
};

const weightLabels = {
  value: "估值",
  sideways: "横盘/低位",
  fundamentals: "基本面",
  trend: "趋势均线",
  momentum: "动量RSI/MACD",
  volume: "成交量",
  volatility: "波动率",
  timing: "买入时机",
};

const weightDescriptions = {
  value: "PE、Forward PE、现金流和52周价格位置的估值安全边际。",
  sideways: "是否长期横盘、接近低位，或者仍未被市场充分重估。",
  fundamentals: "收入、利润、现金流、负债和业务恶化风险。",
  trend: "价格相对MA20/50/200的位置和均线排列。",
  momentum: "RSI和MACD动能是否健康。",
  volume: "突破是否有成交量确认。",
  volatility: "ATR和布林带位置，识别过热与风险。",
  timing: "回踩观察、突破确认、左侧低位、过热等待。",
};

const glossary = {
  price: "MOOMOO API返回的当前可用价格。优先级为overnight、盘前、盘后、常规交易价格。",
  pe: "市盈率。PE越低通常代表估值越低，但亏损、周期底部或一次性利润会让PE失真。",
  forwardPe: "Forward PE是未来预期利润对应的市盈率。MOOMOO当前接口未直接提供，所以这里只保留静态研究字段或显示N/A。",
  range52w: "过去52周股价最低到最高区间，用来判断现在处在高位还是低位。",
  target: "MOOMOO分析师共识目标价，不是逐家机构明细。上行百分比=平均目标价/当前价-1。",
  event: "MOOMOO财报/重大事件时间线。若显示几天内财报，短期波动风险会更高。",
  rsi: "RSI14，相对强弱指标。一般70以上偏超买，30以下偏超卖；趋势股可以长期维持高RSI。",
  macd: "MACD柱体衡量短中期动能。动能增强偏强，空头增强偏弱。",
  volume: "Volume Ratio，当前成交量相对20日均量的倍数。大于2通常代表放量异动。",
  atr: "ATR14%，平均真实波幅占股价比例。数值越高，短期波动和止损距离越大。",
  bollinger: "布林带位置。接近上轨代表价格偏热，接近中轨或下轨更像回踩区域。",
  ma: "移动平均线。MA20/50/200分别代表短、中、长期趋势。",
  timing: "买入时机标签。它不是买入建议，只是用RSI、MACD、均线、量能、波动率判断当前更像回踩、突破还是过热。",
  score: "综合分按页面头部权重公式计算。基本面和估值权重更高，技术项主要用于择时。",
};

const apiRowsByTicker = new Map((apiSnapshot.rows || []).map((row) => [row.ticker, row]));
const staticRowsByTicker = new Map(stocks.map((stock) => [stock.ticker, stock]));

function scoreStock(stock, weights) {
  const totalWeight = Object.values(weights).reduce((sum, value) => sum + value, 0);
  const weighted =
    stock.valueScore * weights.value +
    stock.sidewaysScore * weights.sideways +
    stock.fundamentalScore * weights.fundamentals +
    trendScore(stock) * weights.trend +
    momentumScore(stock) * weights.momentum +
    volumeScore(stock) * weights.volume +
    volatilityScore(stock) * weights.volatility +
    timingScore(stock) * weights.timing;
  return Math.round(weighted / totalWeight);
}

function formulaText(weights) {
  const totalWeight = Object.values(weights).reduce((sum, value) => sum + value, 0);
  return `综合分 = (估值*${weights.value} + 横盘*${weights.sideways} + 基本面*${weights.fundamentals} + 趋势*${weights.trend} + 动量*${weights.momentum} + 量能*${weights.volume} + 波动*${weights.volatility} + 时机*${weights.timing}) / ${totalWeight}`;
}

function clamp(value, min = 0, max = 100) {
  return Math.max(min, Math.min(max, value));
}

function tech(stock) {
  return stock.apiTechnical || {};
}

function trendScore(stock) {
  const t = tech(stock);
  if (t.trendLabel === "多头排列") return 90;
  if (t.trendLabel === "短中期向上") return 76;
  if (t.trendLabel === "弱势下行") return 35;
  return stock.technicalScore || 55;
}

function momentumScore(stock) {
  const t = tech(stock);
  let score = 55;
  if (t.rsi14) {
    if (t.rsi14 >= 75) score -= 25;
    else if (t.rsi14 >= 65) score -= 10;
    else if (t.rsi14 >= 45 && t.rsi14 <= 60) score += 18;
    else if (t.rsi14 <= 30) score += 8;
  }
  if (t.macdLabel === "动能增强") score += 18;
  if (t.macdLabel === "空头增强") score -= 20;
  return clamp(score);
}

function volumeScore(stock) {
  const ratio = tech(stock).volumeRatio;
  if (!ratio) return 50;
  if (ratio >= 2) return 86;
  if (ratio >= 1.3) return 72;
  if (ratio < 0.7) return 40;
  return 56;
}

function volatilityScore(stock) {
  const t = tech(stock);
  let score = 65;
  if (t.atr14Pct >= 10) score -= 35;
  else if (t.atr14Pct >= 7) score -= 18;
  if (t.bbPosition >= 1) score -= 18;
  else if (t.bbPosition >= 0.85) score -= 8;
  else if (t.bbPosition >= 0.35 && t.bbPosition <= 0.65) score += 12;
  return clamp(score);
}

function timingScore(stock) {
  const label = tech(stock).buyTiming;
  if (label === "回踩观察") return 88;
  if (label === "左侧低位") return 80;
  if (label === "突破确认") return 74;
  if (label === "过热等待") return 30;
  return 55;
}

function withApiSnapshot(stock) {
  const api = apiRowsByTicker.get(stock.ticker);
  if (!api) return stock;
  const apiPe = api.peTtm && api.peTtm > 0 ? api.peTtm : api.pe && api.pe > 0 ? api.pe : stock.pe;
  return {
    ...stock,
    name: api.name || stock.name,
    price: api.price || stock.price,
    pe: apiPe,
    range52w: api.range52w || stock.range52w,
    candles: api.candles?.length ? api.candles : stock.candles,
    apiUpdateTime: api.updateTime,
    apiPriceSource: api.priceSource,
    analystConsensus: api.analystConsensus,
    nextEvent: api.nextEvent,
    highlights: api.highlights,
    apiTechnical: api.technical,
  };
}

function fromApiRow(api) {
  const staticStock = staticRowsByTicker.get(api.ticker);
  if (staticStock) return withApiSnapshot(staticStock);
  const technical = api.technical || {};
  const pe = api.peTtm && api.peTtm > 0 ? api.peTtm : api.pe && api.pe > 0 ? api.pe : null;
  const position = technical.position52w;
  const valueScore = pe && pe <= 12 ? 90 : pe && pe <= 20 ? 76 : pe && pe <= 35 ? 58 : 35;
  const sidewaysScore = position === undefined || position === null ? 50 : position <= 0.25 ? 88 : position <= 0.55 ? 66 : 38;
  const fundamentalScore = api.analystConsensus?.average && api.price && api.analystConsensus.average > api.price ? 66 : 52;
  return {
    ticker: api.ticker,
    name: api.name || api.ticker,
    price: api.price || 0,
    pe,
    forwardPe: null,
    range52w: api.range52w || "",
    balance: "",
    theme: api.theme || "全市场筛选",
    aiThesis: "",
    fundamental: "",
    technical: "",
    risk: "",
    aiScore: 0,
    valueScore,
    sidewaysScore,
    fundamentalScore,
    technicalScore: 50,
    candles: api.candles?.length ? api.candles : [{ month: "-", open: api.price || 1, high: api.price || 1, low: api.price || 1, close: api.price || 1 }],
    apiUpdateTime: api.updateTime,
    apiPriceSource: api.priceSource,
    analystConsensus: api.analystConsensus,
    nextEvent: api.nextEvent,
    highlights: api.highlights,
    apiTechnical: technical,
  };
}

function SparkCandles({ candles }) {
  const values = candles.flatMap((candle) => [candle.high, candle.low]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const width = 168;
  const height = 64;
  const step = width / candles.length;

  return (
    <svg className="candles" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="12个月K线缩略图">
      <line x1="0" y1={height - 10} x2={width} y2={height - 10} />
      {candles.map((candle, index) => {
        const x = index * step + step / 2;
        const yHigh = 8 + ((max - candle.high) / range) * (height - 18);
        const yLow = 8 + ((max - candle.low) / range) * (height - 18);
        const yOpen = 8 + ((max - candle.open) / range) * (height - 18);
        const yClose = 8 + ((max - candle.close) / range) * (height - 18);
        const up = candle.close >= candle.open;
        const bodyY = Math.min(yOpen, yClose);
        const bodyHeight = Math.max(2, Math.abs(yClose - yOpen));
        return (
          <g key={`${candle.month}-${index}`} className={up ? "up" : "down"}>
            <line x1={x} y1={yHigh} x2={x} y2={yLow} />
            <rect x={x - 3.5} y={bodyY} width="7" height={bodyHeight} rx="1" />
          </g>
        );
      })}
    </svg>
  );
}

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return "-";
  return Number(value).toFixed(digits);
}

function formatPe(value) {
  if (!value || value <= 0) return "N/A";
  return `${formatNumber(value, 1)}x`;
}

function Term({ children, tip }) {
  return (
    <span className="term" data-tip={tip}>
      {children}
    </span>
  );
}

function targetSummary(stock) {
  const consensus = stock.analystConsensus;
  if (!consensus?.average) return "MOOMOO未提供";
  const upside = stock.price ? (consensus.average / stock.price - 1) * 100 : null;
  return `$${formatNumber(consensus.average)} / ${upside === null ? "-" : `${upside > 0 ? "+" : ""}${formatNumber(upside, 0)}%`}`;
}

function eventSummary(stock) {
  const event = stock.nextEvent?.primary || stock.nextEvent;
  if (!event?.date) return "MOOMOO未提供";
  const days = event.daysUntil;
  const prefix = event.isFuture ? `${days}天后` : `${Math.abs(days)}天前`;
  return `${prefix} · ${event.date} ${event.period || ""}`;
}

function eventSecondary(stock) {
  const secondary = stock.nextEvent?.secondary;
  if (!secondary?.date) return "无本周已发生事件";
  return `本周已发生：${Math.abs(secondary.daysUntil)}天前 · ${secondary.date} ${secondary.period || ""}`;
}

function highlightsFor(stock) {
  if (stock.highlights?.length) return stock.highlights;
  const highlights = [];
  if (stock.price > 90) highlights.push({ level: "watch", text: "接近100上限" });
  if (stock.pe && stock.pe > 35) highlights.push({ level: "risk", text: "PE偏高" });
  return highlights;
}

function StockRow({ stock, rank, score }) {
  const t = tech(stock);
  return (
    <tr>
      <td className="rank-cell">#{rank}</td>
      <td className="stock-cell">
        <strong>{stock.ticker}</strong>
        <span>{stock.name}</span>
      </td>
      <td className="theme-cell">{stock.theme}</td>
      <td>
        <strong>${formatNumber(stock.price)}</strong>
        <span className="subtle">{stock.apiPriceSource || "static"}</span>
      </td>
      <td>
        <strong>{formatPe(stock.pe)}</strong>
        <span className="subtle term-inline" data-tip={glossary.forwardPe}>Fwd {stock.forwardPe ? `${formatNumber(stock.forwardPe, 1)}x` : "N/A"}</span>
      </td>
      <td>{stock.range52w}</td>
      <td className="target-cell">
        <strong>{targetSummary(stock)}</strong>
        <span className="subtle">
          {stock.analystConsensus?.total
            ? `${formatNumber(stock.analystConsensus.total, 0)}家 · ${stock.analystConsensus.updateTime}`
            : "共识目标价"}
        </span>
      </td>
      <td className="event-cell">
        <strong>{eventSummary(stock)}</strong>
        <span className="subtle">
          {stock.nextEvent?.primary?.predictedMovePct ? `预期波动 ${formatNumber(stock.nextEvent.primary.predictedMovePct, 1)}%` : eventSecondary(stock)}
        </span>
      </td>
      <td className="tech-cell">
        <strong className="term-inline" data-tip={glossary.timing}>{t.buyTiming || "等待"}</strong>
        <span className="subtle">
          <span className="term-inline" data-tip={glossary.rsi}>RSI {formatNumber(t.rsi14, 0)}</span> · <span className="term-inline" data-tip={glossary.macd}>{t.macdLabel || "MACD -"}</span> · <span className="term-inline" data-tip={glossary.volume}>量 {formatNumber(t.volumeRatio, 1)}x</span>
        </span>
      </td>
      <td className="mini-chart"><SparkCandles candles={stock.candles} /></td>
      <td className="highlight-cell">
        <div className="highlight-wrap">
          {highlightsFor(stock).map((item, index) => (
            <span className={`highlight ${item.level}`} key={`${stock.ticker}-${index}`}>{item.text}</span>
          ))}
          {!highlightsFor(stock).length && <span className="highlight neutral">无明显警报</span>}
        </div>
      </td>
      <td className="score-cell">{score}</td>
    </tr>
  );
}

function App() {
  const [query, setQuery] = useState("");
  const [sortBy, setSortBy] = useState("score");
  const [strategy, setStrategy] = useState("balanced");
  const [weights, setWeights] = useState(defaultWeights);
  const [filters, setFilters] = useState({
    minPrice: "",
    maxPrice: "",
    minPe: "",
    maxPe: "",
    minRsi: "",
    maxRsi: "",
    theme: "all",
    timing: "all",
    alert: "all",
  });

  const enrichedStocks = useMemo(() => {
    const apiRows = apiSnapshot.rows || [];
    if (apiRows.length) return apiRows.map(fromApiRow);
    return stocks.map(withApiSnapshot);
  }, []);
  const themes = useMemo(() => {
    const values = enrichedStocks.map((stock) => stock.theme.split("/")[0].trim()).filter(Boolean);
    return ["all", ...Array.from(new Set(values)).sort()];
  }, [enrichedStocks]);

  const setFilter = (key, value) => {
    setFilters((current) => ({ ...current, [key]: value }));
  };

  const passesFilters = (stock) => {
    const t = tech(stock);
    const peValue = stock.pe && stock.pe > 0 ? stock.pe : null;
    const price = stock.price;
    if (filters.minPrice !== "" && price < Number(filters.minPrice)) return false;
    if (filters.maxPrice !== "" && price > Number(filters.maxPrice)) return false;
    if (filters.minPe !== "" && (!peValue || peValue < Number(filters.minPe))) return false;
    if (filters.maxPe !== "" && (!peValue || peValue > Number(filters.maxPe))) return false;
    if (filters.minRsi !== "" && (!t.rsi14 || t.rsi14 < Number(filters.minRsi))) return false;
    if (filters.maxRsi !== "" && (!t.rsi14 || t.rsi14 > Number(filters.maxRsi))) return false;
    if (filters.theme !== "all" && !stock.theme.startsWith(filters.theme)) return false;
    if (filters.timing !== "all" && t.buyTiming !== filters.timing) return false;
    if (filters.alert !== "all") {
      const levels = highlightsFor(stock).map((item) => item.level);
      if (!levels.includes(filters.alert)) return false;
    }
    return true;
  };

  const ranked = useMemo(() => {
    return enrichedStocks
      .filter(passesFilters)
      .filter((stock) => {
        const text = `${stock.ticker} ${stock.name} ${stock.theme}`.toLowerCase();
        return text.includes(query.toLowerCase());
      })
      .map((stock) => ({ ...stock, totalScore: scoreStock(stock, weights) }))
      .sort((a, b) => {
        if (sortBy === "price") return a.price - b.price;
        if (sortBy === "forwardPe") return (a.forwardPe || 999) - (b.forwardPe || 999);
        if (sortBy === "ai") return trendScore(b) - trendScore(a);
        return b.totalScore - a.totalScore;
      })
      .slice(0, 20);
  }, [enrichedStocks, filters, query, sortBy, weights]);

  const updateWeight = (key, value) => {
    setStrategy("custom");
    setWeights((current) => ({ ...current, [key]: Number(value) }));
  };

  const applyStrategy = (key) => {
    setStrategy(key);
    setWeights(strategyPresets[key].weights);
    setSortBy("score");
  };

  return (
    <main>
      <header className="app-header">
        <div>
          <span className="eyebrow"><Filter size={15} /> AI under-$100 screener</span>
          <h1>AI低价股筛选系统</h1>
          <p>
            默认筛选股价低于100美元，并用MOOMOO API覆盖价格、PE、52周区间、机构共识目标价和财报时间线。
            排名只看基本面、估值和技术面，不再给AI主题加分。
          </p>
        </div>
        <div className="logic-panel">
          <h2><SlidersHorizontal size={18} /> 排序公式</h2>
          <p className="formula">{formulaText(weights)}</p>
          <p className="formula-note">
            每个维度原始分为0-100。调高某个权重，该维度对综合分影响更大；权重总和会自动作为分母。
          </p>
        </div>
      </header>

      <section className="weight-console">
        <div className="weight-console-head">
          <div>
            <h2>权重调整</h2>
            <p>先选策略，再按需要微调滑杆；列表会按新的综合分重排。</p>
          </div>
          <button type="button" onClick={() => applyStrategy("balanced")}>恢复默认</button>
        </div>
        <div className="strategy-grid">
          {Object.entries(strategyPresets).map(([key, preset]) => (
            <button
              className={strategy === key ? "active" : ""}
              key={key}
              type="button"
              onClick={() => applyStrategy(key)}
            >
              <strong>{preset.label}</strong>
              <span>{preset.description}</span>
            </button>
          ))}
          {strategy === "custom" && (
            <button className="active" type="button">
              <strong>自定义</strong>
              <span>你手动调整后的权重组合。</span>
            </button>
          )}
        </div>
        <div className="weights">
          {Object.entries(weights).map(([key, value]) => (
            <label key={key} title={weightDescriptions[key]}>
              <span>{weightLabels[key]}</span>
              <input type="range" min="0" max="50" value={value} onChange={(event) => updateWeight(key, event.target.value)} />
              <strong>{value}</strong>
            </label>
          ))}
        </div>
      </section>

      <section className="toolbar">
        <label className="search">
          <Search size={17} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="搜索 ticker / 公司 / 主题" />
        </label>
        <label className="select">
          <ArrowDownUp size={17} />
          <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
            <option value="score">综合评分</option>
            <option value="forwardPe">Forward PE 低到高</option>
            <option value="price">价格低到高</option>
            <option value="ai">技术趋势</option>
          </select>
        </label>
      </section>

      <section className="filter-panel">
        <div className="filter-field">
          <span>价格</span>
          <input value={filters.minPrice} onChange={(event) => setFilter("minPrice", event.target.value)} placeholder="最低" type="number" />
          <input value={filters.maxPrice} onChange={(event) => setFilter("maxPrice", event.target.value)} placeholder="最高" type="number" />
        </div>
        <div className="filter-field">
          <span>PE</span>
          <input value={filters.minPe} onChange={(event) => setFilter("minPe", event.target.value)} placeholder="最低" type="number" />
          <input value={filters.maxPe} onChange={(event) => setFilter("maxPe", event.target.value)} placeholder="最高" type="number" />
        </div>
        <div className="filter-field">
          <span>RSI</span>
          <input value={filters.minRsi} onChange={(event) => setFilter("minRsi", event.target.value)} placeholder="最低" type="number" />
          <input value={filters.maxRsi} onChange={(event) => setFilter("maxRsi", event.target.value)} placeholder="最高" type="number" />
        </div>
        <label className="filter-select">
          <span>行业/主题</span>
          <select value={filters.theme} onChange={(event) => setFilter("theme", event.target.value)}>
            {themes.map((theme) => <option value={theme} key={theme}>{theme === "all" ? "全部" : theme}</option>)}
          </select>
        </label>
        <label className="filter-select">
          <span>买入时机</span>
          <select value={filters.timing} onChange={(event) => setFilter("timing", event.target.value)}>
            <option value="all">全部</option>
            <option value="回踩观察">回踩观察</option>
            <option value="突破确认">突破确认</option>
            <option value="左侧低位">左侧低位</option>
            <option value="过热等待">过热等待</option>
            <option value="等待">等待</option>
          </select>
        </label>
        <label className="filter-select">
          <span>高亮类型</span>
          <select value={filters.alert} onChange={(event) => setFilter("alert", event.target.value)}>
            <option value="all">全部</option>
            <option value="good">机会</option>
            <option value="watch">观察</option>
            <option value="risk">风险</option>
          </select>
        </label>
        <button type="button" onClick={() => setFilters({ minPrice: "", maxPrice: "", minPe: "", maxPe: "", minRsi: "", maxRsi: "", theme: "all", timing: "all", alert: "all" })}>清除筛选</button>
      </section>

      <section className="summary">
        <div><CheckCircle2 size={18} /><strong>股票池：</strong>不再限制100美元以下，你可以用筛选器自己设价格范围。</div>
        <div><Activity size={18} /><strong>排名逻辑：</strong>AI主题已移除，综合分只来自基本面、估值和技术择时。</div>
        <div><BarChart3 size={18} /><strong>高亮：</strong>目标价倒挂、PE偏高、接近52周高位、近期财报会自动标记。</div>
      </section>

      <section className="table-panel">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>股票</th>
              <th>行业/主题</th>
              <th><Term tip={glossary.price}>价格</Term></th>
              <th><Term tip={`${glossary.pe} ${glossary.forwardPe}`}>估值</Term></th>
              <th><Term tip={glossary.range52w}>52周</Term></th>
              <th><Term tip={glossary.target}>机构估价</Term></th>
              <th><Term tip={glossary.event}>重大时间线</Term></th>
              <th><Term tip={glossary.timing}>买入时机</Term></th>
              <th><Term tip="12个月迷你K线，绿色为上涨月，红色为下跌月。">K线</Term></th>
              <th>高亮</th>
              <th><Term tip={glossary.score}>分</Term></th>
            </tr>
          </thead>
          <tbody>
            {ranked.map((stock, index) => (
              <StockRow key={stock.ticker} stock={stock} rank={index + 1} score={stock.totalScore} />
            ))}
          </tbody>
        </table>
      </section>

      <footer>
        <strong>数据说明：</strong> {sourceNotes} 当前行情覆盖来自 {apiSnapshot.source}，生成时间 {apiSnapshot.generatedAt}。
      </footer>
    </main>
  );
}

createRoot(document.getElementById("root")).render(<App />);
