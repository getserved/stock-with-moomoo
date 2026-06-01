import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
API = ROOT / "ai-stock-screener" / "src" / "data" / "apiSnapshot.json"
OUT = ROOT / "generated" / "ai_stock_screener_preview.png"

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


def font(size, bold=False):
    for path in [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


F12, F13, F14, F16, F20, F28 = font(12), font(13), font(14), font(16), font(20, True), font(28, True)


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
    c = row.get("analystConsensus") or {}
    if not c.get("average"):
        return "API未提供"
    upside = (c["average"] / row["price"] - 1) * 100 if row.get("price") else 0
    return f"${fmt(c['average'])} ({upside:+.0f}%)"


def event(row):
    e = row.get("nextEvent") or {}
    if e.get("primary") is not None or e.get("secondary") is not None:
        e = e.get("primary") or {}
    if not e.get("date"):
        return "API未提供"
    prefix = f"{e.get('daysUntil')}天后" if e.get("isFuture") else f"{abs(e.get('daysUntil', 0))}天前"
    return f"{prefix} {e.get('date')} {e.get('period', '')}"


def timing(row):
    t = row.get("technical") or {}
    label = t.get("buyTiming") or "等待"
    rsi = t.get("rsi14")
    macd = t.get("macdLabel") or "-"
    if rsi is None:
        return label
    return f"{label} RSI {rsi:.0f} {macd[:4]}"


def draw():
    payload = json.loads(API.read_text(encoding="utf-8"))
    rows = [r for r in payload["rows"] if r.get("price") is not None and r["price"] <= 100][:20]

    width, height = 1600, 1080
    img = Image.new("RGB", (width, height), "#f4f7f8")
    d = ImageDraw.Draw(img)

    def rr(xy, fill, outline=None, r=8):
        d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline)

    def text(x, y, value, fill="#17212b", f=F14):
        d.text((x, y), value, fill=fill, font=f)

    rr((24, 24, 1576, 160), "#13272c")
    text(52, 46, "低价股基本面 + 技术面筛选系统 - MOOMOO API 列表版", "#ffffff", F28)
    text(52, 86, f"行情/PE/52周/机构共识/财报时间线来自 {payload['source']} · {payload['generatedAt']}", "#dce8e9", F14)
    text(52, 120, "排序公式：不再包含AI主题权重；基本面/估值为主，技术面拆成趋势、动量、量能、波动率、买入时机。", "#dce8e9", F14)
    text(52, 142, "术语：RSI=相对强弱，70以上偏超买；MACD=趋势动能；ATR=平均波幅；MA=移动平均线。", "#dce8e9", F13)

    rr((24, 190, 1576, 1038), "#ffffff", "#dbe4e6")
    headers = ["#", "股票", "行业/主题", "价格", "PE", "52周", "机构估价", "重大时间线", "买入时机", "高亮"]
    xs = [44, 90, 205, 330, 420, 505, 640, 810, 1020, 1160]
    widths = [38, 100, 130, 90, 80, 145, 175, 220, 390]
    d.rectangle((24, 190, 1576, 236), fill="#eef4f5")
    for x, h in zip(xs, headers):
        text(x, 204, h, "#46545f", F14)

    y = 246
    row_h = 41
    for idx, row in enumerate(rows, 1):
        if idx % 2 == 0:
            d.rectangle((24, y - 6, 1576, y + row_h - 8), fill="#fbfcfc")
        d.line((24, y + row_h - 8, 1576, y + row_h - 8), fill="#e7edef")
        values = [
            f"#{idx}",
            row["ticker"],
            THEMES.get(row["ticker"], row.get("name", ""))[:16],
            f"${fmt(row.get('price'))}",
            pe(row),
            row.get("range52w", ""),
            target(row),
            event(row),
            timing(row),
        ]
        for x, value in zip(xs[:-1], values):
            text(x, y, value, "#17212b" if value != row["ticker"] else "#10272b", F14 if value != row["ticker"] else F16)

        hx = xs[-1]
        for item in (row.get("highlights") or [])[:3]:
            label = item.get("text", "")
            level = item.get("level", "neutral")
            color = {"risk": "#fff0f0", "watch": "#fff8e4", "good": "#edf8f3"}.get(level, "#f5f8f9")
            edge = {"risk": "#e8bbbb", "watch": "#ead69d", "good": "#b9ddd4"}.get(level, "#d6e1e3")
            fg = {"risk": "#9a3535", "watch": "#765000", "good": "#126451"}.get(level, "#46545f")
            box_w = min(122, max(72, len(label) * 12))
            rr((hx, y - 3, hx + box_w, y + 25), color, edge)
            text(hx + 8, y + 3, label[:10], fg, F12)
            hx += box_w + 8
        y += row_h

    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT)
    print(OUT)


if __name__ == "__main__":
    draw()
