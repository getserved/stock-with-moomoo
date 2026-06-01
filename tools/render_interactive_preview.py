import html
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "ai-stock-screener" / "src" / "data" / "apiSnapshot.json"
OUT = ROOT / "preview.html"

THEMES = {
    "HPE": "AI服务器/网络",
    "BB": "QNX/Physical AI",
    "MCHP": "边缘AI/MCU",
    "VSH": "被动元件/电源链",
    "AMKR": "先进封装",
    "HPQ": "AI PC",
    "ERIC": "AI-RAN",
    "NOK": "光网络/AI-RAN",
    "PLAB": "半导体光罩",
    "PATH": "AI自动化软件",
    "CEVA": "边缘AI IP",
    "TDC": "AI数据平台",
    "DDD": "3D制造",
    "SOUN": "语音AI",
    "BBAI": "国防AI",
    "OUST": "机器人感知",
    "AVT": "元件分销",
    "AEHR": "功率测试",
    "COHU": "半导体测试",
    "VIAV": "光网络测试",
}

TIPS = {
    "price": "MOOMOO API返回的当前可用价格。优先级为overnight、盘前、盘后、常规交易价格。",
    "pe": "市盈率。PE越低通常代表估值越低，但亏损、周期底部或一次性利润会让PE失真。",
    "range52w": "过去52周最低价到最高价，用来判断现在处于高位还是低位。",
    "target": "MOOMOO分析师共识目标价，不是逐家机构明细。括号里是相对当前价格的上行或下行空间。",
    "event": "MOOMOO财报/重大事件时间线。越接近财报，短期波动风险通常越高。",
    "timing": "买入时机标签。结合RSI、MACD、均线、量能、波动率判断当前更像回踩、突破还是过热。",
    "rsi": "RSI14，相对强弱指标。一般70以上偏超买，30以下偏超卖。",
    "macd": "MACD柱体衡量短中期动能。动能增强偏强，空头增强偏弱。",
    "volume": "量比，当前成交量相对20日均量的倍数。大于2通常代表放量异动。",
    "highlight": "需要特别注意的信息，例如目标价倒挂、PE偏高、接近52周高位、近期财报、ATR波动过高。",
}

STRATEGIES = {
    "balanced": "综合平衡",
    "fundamentals": "基本面优先",
    "entry": "买点优先",
    "deepvalue": "低估低位",
    "breakout": "突破动量",
    "lowrisk": "低波动安全",
}


def fmt(value, digits=2):
    if value is None:
        return "-"
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "-"


def pe(row):
    value = row.get("peTtm") if row.get("peTtm") and row.get("peTtm") > 0 else row.get("pe")
    return "N/A" if not value or value <= 0 else f"{fmt(value, 1)}x"


def target(row):
    consensus = row.get("analystConsensus") or {}
    if not consensus.get("average"):
        return "API未提供"
    upside = (consensus["average"] / row["price"] - 1) * 100 if row.get("price") else 0
    return f"${fmt(consensus['average'])} ({upside:+.0f}%)"


def event(row):
    item = row.get("nextEvent") or {}
    if item.get("primary") is not None or item.get("secondary") is not None:
        item = item.get("primary") or {}
    if not item.get("date"):
        return "API未提供"
    prefix = f"{item.get('daysUntil')}天后" if item.get("isFuture") else f"{abs(item.get('daysUntil', 0))}天前"
    return f"{prefix} {item.get('date')} {item.get('period', '')}"


def event_secondary(row):
    item = (row.get("nextEvent") or {}).get("secondary")
    if not item:
        return "无本周已发生事件"
    return f"本周已发生：{abs(item.get('daysUntil', 0))}天前 {item.get('date')} {item.get('period', '')}"


def timing(row):
    t = row.get("technical") or {}
    label = t.get("buyTiming") or "等待"
    rsi = t.get("rsi14")
    macd = t.get("macdLabel") or "-"
    volume = t.get("volumeRatio")
    return f"{label}<small>RSI {fmt(rsi, 0)} · {html.escape(macd)} · 量 {fmt(volume, 1)}x</small>"


def tip(label, key):
    return f'<span class="term" data-tip="{html.escape(TIPS[key])}">{html.escape(label)}</span>'


def render():
    payload = json.loads(API.read_text(encoding="utf-8"))
    rows = [row for row in payload["rows"] if row.get("price") is not None]
    themes = sorted({row.get("industry") or row.get("theme") or "未分类" for row in rows})
    body = []
    for index, row in enumerate(rows, 1):
        tech = row.get("technical") or {}
        consensus = row.get("analystConsensus") or {}
        pe_value = row.get("peTtm") if row.get("peTtm") and row.get("peTtm") > 0 else row.get("pe")
        target_upside = (consensus.get("average") / row["price"] - 1) * 100 if consensus.get("average") and row.get("price") else 0
        position = tech.get("position52w")
        atr = tech.get("atr14Pct") or 99
        rsi = tech.get("rsi14") or 50
        volume = tech.get("volumeRatio") or 1
        timing_label = tech.get("buyTiming") or "等待"
        value_score = 100 if pe_value and 0 < pe_value <= 12 else 76 if pe_value and pe_value <= 20 else 45 if pe_value and pe_value <= 35 else 20
        low_score = 90 if position is not None and position <= 0.25 else 70 if position is not None and position <= 0.55 else 35
        timing_score = {"回踩观察": 90, "左侧低位": 82, "突破确认": 76, "过热等待": 20}.get(timing_label, 55)
        momentum_score = 85 if volume >= 1.5 and 45 <= rsi <= 68 else 50
        risk_score = max(0, 100 - atr * 8)
        fundamental_proxy = 75 if target_upside > 15 else 55 if target_upside > -10 else 25
        scores = {
            "balanced": value_score * 0.3 + low_score * 0.2 + fundamental_proxy * 0.25 + timing_score * 0.25,
            "fundamentals": value_score * 0.45 + fundamental_proxy * 0.4 + risk_score * 0.15,
            "entry": timing_score * 0.45 + risk_score * 0.2 + low_score * 0.2 + momentum_score * 0.15,
            "deepvalue": value_score * 0.55 + low_score * 0.35 + risk_score * 0.1,
            "breakout": momentum_score * 0.45 + timing_score * 0.3 + risk_score * 0.1 + fundamental_proxy * 0.15,
            "lowrisk": risk_score * 0.45 + value_score * 0.25 + fundamental_proxy * 0.2 + timing_score * 0.1,
        }
        theme_value = row.get("industry") or row.get("theme") or "未分类"
        concept_text = " / ".join((row.get("concepts") or [])[:2])
        highlights = "".join(
            f'<span class="tag {html.escape(item.get("level", "neutral"))}" data-tip="{html.escape(TIPS["highlight"])}">{html.escape(item.get("text", ""))}</span>'
            for item in (row.get("highlights") or [])[:5]
        )
        body.append(
            f"""
            <tr data-balanced="{scores['balanced']:.3f}" data-fundamentals="{scores['fundamentals']:.3f}" data-entry="{scores['entry']:.3f}" data-deepvalue="{scores['deepvalue']:.3f}" data-breakout="{scores['breakout']:.3f}" data-lowrisk="{scores['lowrisk']:.3f}" data-price="{row.get('price') or ''}" data-pe="{pe_value or ''}" data-rsi="{rsi}" data-theme="{html.escape(theme_value)}" data-timing="{html.escape(timing_label)}" data-alerts="{html.escape(' '.join(item.get('level','') for item in (row.get('highlights') or [])))}">
              <td>#{index}</td>
              <td><strong>{html.escape(row["ticker"])}</strong><small>{html.escape(row.get("name", ""))}</small></td>
              <td>{html.escape(theme_value)}<small>{html.escape(concept_text)}</small></td>
              <td><strong>${fmt(row.get("price"))}</strong><small>{html.escape(row.get("priceSource", ""))}</small></td>
              <td>{pe(row)}</td>
              <td>{html.escape(row.get("range52w", ""))}</td>
              <td>{target(row)}</td>
              <td>{event(row)}<small>{html.escape(event_secondary(row))}</small></td>
              <td class="timing">{timing(row)}</td>
              <td><div class="tags">{highlights or '<span class="tag">无明显警报</span>'}</div></td>
            </tr>
            """
        )

    html_text = f"""<!doctype html>
<html lang="zh-Hans">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AI低价股筛选系统</title>
  <style>
    :root {{ font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif; color: #17212b; background: #f4f7f8; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; padding: 18px; }}
    header {{ background:#13272c; color:#fff; border-radius:8px; padding:22px 28px; margin-bottom:16px; }}
    h1 {{ margin:0 0 8px; font-size:28px; letter-spacing:0; }}
    p {{ margin:0; color:#dce8e9; line-height:1.65; }}
    .panel {{ background:#fff; border:1px solid #dbe4e6; border-radius:8px; overflow:auto; }}
    .strategies {{ display:grid; grid-template-columns:repeat(6,minmax(0,1fr)); gap:10px; margin:0 0 14px; }}
    .strategies button {{ min-height:48px; border:1px solid #d7e1e3; border-radius:8px; background:#fff; color:#17212b; font-weight:800; cursor:pointer; }}
    .strategies button.active {{ border-color:#147b73; background:#edf8f6; color:#0d625c; box-shadow:inset 0 0 0 1px #147b73; }}
    .filters {{ display:grid; grid-template-columns:repeat(6,minmax(0,1fr)) auto; gap:10px; margin:0 0 14px; padding:14px; background:#fff; border:1px solid #dde6e8; border-radius:8px; }}
    .field {{ display:grid; grid-template-columns:1fr 1fr; gap:6px; }}
    .field.select {{ grid-template-columns:1fr; }}
    .field span {{ grid-column:1/-1; color:#596974; font-size:12px; font-weight:800; }}
    .field input,.field select {{ min-width:0; height:36px; border:1px solid #d7e1e3; border-radius:8px; background:#eef4f5; padding:8px; }}
    .filters button {{ align-self:end; min-height:36px; border:1px solid #cfe0df; border-radius:8px; background:#edf8f6; color:#0d625c; font-weight:800; cursor:pointer; }}
    .pager {{ display:flex; align-items:center; gap:10px; margin:0 0 14px; }}
    .pager button {{ min-height:36px; padding:8px 12px; border:1px solid #cfe0df; border-radius:8px; background:#edf8f6; color:#0d625c; font-weight:800; cursor:pointer; }}
    .pager span {{ color:#46545f; font-size:13px; }}
    table {{ width:100%; min-width:1260px; border-collapse:separate; border-spacing:0; }}
    th,td {{ padding:12px 10px; border-bottom:1px solid #e7edef; text-align:left; vertical-align:middle; font-size:14px; }}
    th {{ position:sticky; top:0; background:#eef4f5; color:#46545f; z-index:2; }}
    tr:hover {{ background:#f8fbfb; }}
    small {{ display:block; margin-top:3px; color:#667681; font-size:12px; }}
    .term, .tag {{ position:relative; cursor:help; }}
    .term {{ text-decoration:underline; text-decoration-style:dotted; text-underline-offset:3px; }}
    .term::after, .tag::after {{ content:attr(data-tip); display:none; position:absolute; left:0; bottom:calc(100% + 8px); z-index:10; width:max-content; max-width:330px; padding:9px 10px; border-radius:8px; background:#10272b; color:#fff; font-size:12px; line-height:1.5; box-shadow:0 12px 28px rgba(16,39,43,.2); }}
    .term:hover::after, .tag:hover::after {{ display:block; }}
    .tags {{ display:flex; flex-wrap:wrap; gap:6px; max-width:390px; }}
    .tag {{ display:inline-flex; min-height:26px; align-items:center; padding:4px 8px; border-radius:8px; border:1px solid #d6e1e3; background:#f5f8f9; color:#46545f; font-size:12px; font-weight:800; }}
    .tag.good {{ border-color:#b9ddd4; background:#edf8f3; color:#126451; }}
    .tag.watch {{ border-color:#ead69d; background:#fff8e4; color:#765000; }}
    .tag.risk {{ border-color:#e8bbbb; background:#fff0f0; color:#9a3535; }}
    .timing strong {{ display:block; }}
  </style>
</head>
<body>
  <header>
    <h1>低价股基本面 + 技术面筛选系统</h1>
    <p>数据来自 {html.escape(payload["source"])} · 生成时间 {html.escape(payload["generatedAt"])}。不再限制100美元以下；你可以用筛选器自己控制价格、PE、RSI、行业和买入时机。为避免卡顿，当前页面每页显示20行。</p>
  </header>
  <section class="strategies">
    {"".join(f'<button data-strategy="{key}" class="{"active" if key == "balanced" else ""}">{label}</button>' for key, label in STRATEGIES.items())}
  </section>
  <section class="filters">
    <label class="field"><span>价格</span><input id="minPrice" type="number" placeholder="最低"><input id="maxPrice" type="number" placeholder="最高"></label>
    <label class="field"><span>PE</span><input id="minPe" type="number" placeholder="最低"><input id="maxPe" type="number" placeholder="最高"></label>
    <label class="field"><span>RSI</span><input id="minRsi" type="number" placeholder="最低"><input id="maxRsi" type="number" placeholder="最高"></label>
    <label class="field select"><span>行业/主题</span><select id="theme"><option value="">全部</option>{"".join(f'<option value="{html.escape(theme)}">{html.escape(theme)}</option>' for theme in themes)}</select></label>
    <label class="field select"><span>买入时机</span><select id="timing"><option value="">全部</option><option>回踩观察</option><option>突破确认</option><option>左侧低位</option><option>过热等待</option><option>等待</option></select></label>
    <label class="field select"><span>高亮类型</span><select id="alert"><option value="">全部</option><option value="good">机会</option><option value="watch">观察</option><option value="risk">风险</option></select></label>
    <button id="clearFilters" type="button">清除</button>
  </section>
  <section class="pager">
    <button id="prevPage" type="button">上一页</button>
    <button id="nextPage" type="button">下一页</button>
    <span id="pageInfo">第1页</span>
  </section>
  <section class="panel">
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>股票</th>
          <th>行业/主题</th>
          <th>{tip("价格", "price")}</th>
          <th>{tip("PE", "pe")}</th>
          <th>{tip("52周", "range52w")}</th>
          <th>{tip("机构估价", "target")}</th>
          <th>{tip("重大时间线", "event")}</th>
          <th>{tip("买入时机", "timing")}</th>
          <th>{tip("高亮", "highlight")}</th>
        </tr>
      </thead>
      <tbody>
        {"".join(body)}
      </tbody>
    </table>
  </section>
  <script>
    const tbody = document.querySelector("tbody");
    const buttons = [...document.querySelectorAll("[data-strategy]")];
    const allRows = [...tbody.querySelectorAll("tr")];
    const pageSize = 20;
    let currentPage = 1;
    let currentStrategy = "balanced";
    let currentVisible = [];
    function passes(row) {{
      const num = (id) => {{
        const value = document.getElementById(id).value;
        return value === "" ? null : Number(value);
      }};
      const price = Number(row.dataset.price);
      const pe = row.dataset.pe === "" ? null : Number(row.dataset.pe);
      const rsi = row.dataset.rsi === "" ? null : Number(row.dataset.rsi);
      const minPrice = num("minPrice"), maxPrice = num("maxPrice");
      const minPe = num("minPe"), maxPe = num("maxPe");
      const minRsi = num("minRsi"), maxRsi = num("maxRsi");
      const theme = document.getElementById("theme").value;
      const timing = document.getElementById("timing").value;
      const alert = document.getElementById("alert").value;
      if (minPrice !== null && price < minPrice) return false;
      if (maxPrice !== null && price > maxPrice) return false;
      if (minPe !== null && (pe === null || pe < minPe)) return false;
      if (maxPe !== null && (pe === null || pe > maxPe)) return false;
      if (minRsi !== null && (rsi === null || rsi < minRsi)) return false;
      if (maxRsi !== null && (rsi === null || rsi > maxRsi)) return false;
      if (theme && row.dataset.theme !== theme) return false;
      if (timing && row.dataset.timing !== timing) return false;
      if (alert && !row.dataset.alerts.includes(alert)) return false;
      return true;
    }}
    function applyStrategy(key) {{
      currentStrategy = key;
      currentVisible = allRows.filter(passes).sort((a, b) => Number(b.dataset[key]) - Number(a.dataset[key]));
      const maxPage = Math.max(1, Math.ceil(currentVisible.length / pageSize));
      currentPage = Math.min(currentPage, maxPage);
      renderPage();
      buttons.forEach((button) => button.classList.toggle("active", button.dataset.strategy === key));
    }}
    function renderPage() {{
      [...tbody.querySelectorAll("tr")].forEach((row) => row.remove());
      const maxPage = Math.max(1, Math.ceil(currentVisible.length / pageSize));
      currentPage = Math.max(1, Math.min(currentPage, maxPage));
      const start = (currentPage - 1) * pageSize;
      currentVisible.slice(start, start + pageSize).forEach((row, index) => {{
        row.children[0].textContent = "#" + (start + index + 1);
        row.style.display = "";
        tbody.appendChild(row);
      }});
      document.getElementById("pageInfo").textContent = `第${{currentPage}}页 / 共${{maxPage}}页 · ${{currentVisible.length}}只`;
    }}
    buttons.forEach((button) => button.addEventListener("click", () => applyStrategy(button.dataset.strategy)));
    ["minPrice","maxPrice","minPe","maxPe","minRsi","maxRsi","theme","timing","alert"].forEach(id => document.getElementById(id).addEventListener("input", () => {{ currentPage = 1; applyStrategy(currentStrategy); }}));
    document.getElementById("clearFilters").addEventListener("click", () => {{
      ["minPrice","maxPrice","minPe","maxPe","minRsi","maxRsi"].forEach(id => document.getElementById(id).value = "");
      ["theme","timing","alert"].forEach(id => document.getElementById(id).value = "");
      applyStrategy(currentStrategy);
    }});
    document.getElementById("prevPage").addEventListener("click", () => {{ currentPage -= 1; renderPage(); }});
    document.getElementById("nextPage").addEventListener("click", () => {{ currentPage += 1; renderPage(); }});
    applyStrategy("balanced");
  </script>
</body>
</html>
"""
    OUT.write_text(html_text, encoding="utf-8")
    print(OUT)


if __name__ == "__main__":
    render()
