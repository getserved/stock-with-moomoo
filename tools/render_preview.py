from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "generated" / "ai_stock_screener_preview.png"
OUT.parent.mkdir(exist_ok=True)


def pick_font(size, bold=False):
    names = [
        "C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
    ]
    for name in names:
        if Path(name).exists():
            return ImageFont.truetype(name, size)
    return ImageFont.load_default()


F12 = pick_font(12)
F13 = pick_font(13)
F14 = pick_font(14)
F15 = pick_font(15)
F16 = pick_font(16)
F18 = pick_font(18, True)
F20 = pick_font(20, True)
F24 = pick_font(24, True)
F42 = pick_font(42, True)


def make_image():
    width, height = 1440, 1200
    img = Image.new("RGB", (width, height), "#f4f7f8")
    d = ImageDraw.Draw(img)

    def rr(xy, fill, outline=None, r=8, w=1):
        d.rounded_rectangle(xy, radius=r, fill=fill, outline=outline, width=w)

    def txt(x, y, value, fill="#17212b", font=F14):
        d.text((x, y), value, fill=fill, font=font)

    def wrap(value, max_chars):
        lines, current = [], ""
        for ch in value:
            current += ch
            if len(current) >= max_chars and ch in " ，,。/":
                lines.append(current.strip())
                current = ""
        if current:
            lines.append(current.strip())
        return lines[:3]

    margin = 24
    rr((margin, 24, 900, 310), "#13272c")
    for i in range(18):
        x = 60 + i * 48
        d.line((x, 60, x + 80, 140), fill="#31545a", width=2)
        d.ellipse((x + 76, 136, x + 84, 144), fill="#73b8ad")
    for i in range(10):
        d.line((80, 260 - i * 18, 860, 250 - i * 12), fill="#29464d", width=1)
    rr((58, 206, 250, 235), "#244149", "#77979c")
    txt(74, 212, "AI under-$100 screener", "#ffffff", F13)
    txt(58, 246, "AI 低价股筛选系统", "#ffffff", F42)
    txt(60, 292, "五维评分：AI相关性、估值、横盘/低位、基本面、K线形态。", "#dce8e9", F16)

    rr((924, 24, 1416, 310), "#ffffff", "#dde6e8")
    txt(948, 50, "筛选逻辑", "#17212b", F20)
    logic = [
        "1. 限定股价低于 100 美元，业务连接 AI 软件、基建、边缘 AI 或供应链。",
        "2. 估值优先看 Forward PE，其次看 PE、现金流和负债。",
        "3. 横盘分来自 52 周位置和市场是否长期忽视。",
        "4. 基本面看收入、利润、现金流和业务是否恶化。",
        "5. K线看底部抬高、箱体突破和短期过热。",
    ]
    y = 86
    for line in logic:
        txt(948, y, line, "#46545f", F15)
        y += 38

    rr((24, 330, 1416, 390), "#ffffff", "#dde6e8")
    rr((42, 344, 1120, 376), "#eef4f5", "#d7e1e3")
    txt(58, 351, "搜索 ticker / 公司 / 主题", "#667681", F14)
    rr((1140, 344, 1396, 376), "#eef4f5", "#d7e1e3")
    txt(1158, 351, "排序：综合评分", "#17212b", F14)

    rr((24, 404, 1416, 480), "#ffffff", "#dde6e8")
    weights = [("AI 相关性", 25), ("估值", 25), ("横盘/低位", 20), ("基本面", 20), ("K线形态", 10)]
    for i, (label, value) in enumerate(weights):
        x = 48 + i * 270
        txt(x, 420, label, "#46545f", F13)
        d.line((x, 452, x + 200, 452), fill="#e5ecee", width=7)
        d.line((x, 452, x + value * 5, 452), fill="#147b73", width=7)
        txt(x + 214, 443, str(value), "#17212b", F14)

    rr((24, 494, 1416, 565), "#ffffff", "#dde6e8")
    txt(48, 516, "优先候选：BB、MCHP、VSH、INTC、HPE 更符合低价/横盘/重估。", "#46545f", F15)
    txt(535, 516, "过热警告：NOK AI 逻辑硬，但近期已重估。", "#46545f", F15)
    txt(980, 516, "K线：重点看区间位置和突破/筑底状态。", "#46545f", F15)

    stocks = [
        (
            "1",
            "HPE",
            "Hewlett Packard Enterprise",
            "$45.38",
            "76",
            "AI 服务器 / 网络 / 私有云基础设施",
            "Forward PE 约 11x，AI服务器和网络受益，估值低但毛利不高。",
            "从长期 15-20 平台向上突破，24-25 不破则形态偏强。",
            [18, 19, 22, 24, 26, 28, 31, 35, 38, 41, 43, 45.38],
            [76, 84, 74, 69, 76],
        ),
        (
            "2",
            "BB",
            "BlackBerry",
            "$9.70",
            "66",
            "QNX 车载软件 / 工业 Physical AI / 安全通信",
            "QNX 质量高，但股价快速拉升后不再是低 PE 逻辑。",
            "多年低位后快速突破，8-9 美元已接近近期高位。",
            [3.1, 3.3, 3.0, 3.2, 3.7, 3.5, 3.9, 4.4, 5.2, 6.0, 6.7, 9.70],
            [74, 52, 72, 62, 74],
        ),
        (
            "3",
            "MCHP",
            "Microchip Technology",
            "$95.00",
            "75",
            "MCU / 模拟芯片 / 边缘 AI / 工业汽车",
            "周期低位，库存修复中；毛利好但债务要盯。",
            "50-70 区间筑底，站回 70 右侧确认更清楚。",
            [84, 79, 71, 66, 60, 64, 69, 72, 81, 88, 96, 95],
            [67, 78, 86, 74, 70],
        ),
        (
            "4",
            "VSH",
            "Vishay Intertechnology",
            "$53.05",
            "75",
            "被动元件 / 功率半导体 / AI 电源链",
            "估值低、资产负债表稳，AI纯度低但电源链有受益。",
            "12-20 区间长期反复，突破 21-22 才算摆脱低估陷阱。",
            [14, 16, 18, 22, 28, 34, 38, 42, 47, 51, 55, 53.05],
            [54, 86, 92, 73, 69],
        ),
    ]

    def candle_chart(x, y, w, h, values):
        mn = min(values) * 0.94
        mx = max(values) * 1.06
        rng = mx - mn
        rr((x, y, x + w, y + h), "#f4f7f8", "#e0e7e9")
        step = w / len(values)
        for index, value in enumerate(values):
            cx = x + index * step + step / 2
            previous = values[index - 1] if index else value * 0.98
            high = max(value, previous) * 1.05
            low = min(value, previous) * 0.95

            def yy(price):
                return y + 8 + (mx - price) / rng * (h - 18)

            color = "#17806f" if value >= previous else "#c74747"
            d.line((cx, yy(high), cx, yy(low)), fill=color, width=2)
            top = min(yy(previous), yy(value))
            body = max(3, abs(yy(previous) - yy(value)))
            rr((cx - 4, top, cx + 4, top + body), color, r=1)

    card_w, card_h = 684, 285
    for index, stock in enumerate(stocks):
        col, row = index % 2, index // 2
        x = 24 + col * (card_w + 24)
        y = 584 + row * (card_h + 20)
        rank, ticker, name, price, score, theme, fundamental, technical, values, bars = stock
        rr((x, y, x + card_w, y + card_h), "#ffffff", "#dbe4e6")
        txt(x + 18, y + 18, "#" + rank, "#61717c", F16)
        txt(x + 58, y + 12, ticker, "#10272b", F24)
        txt(x + 130, y + 18, price, "#147b73", F16)
        rr((x + 592, y + 18, x + 658, y + 84), "#edf8f6", "#cfe0df")
        txt(x + 610, y + 28, score, "#17212b", F24)
        txt(x + 606, y + 56, "综合分", "#61717c", F12)
        txt(x + 18, y + 52, name, "#17212b", F18)
        txt(x + 18, y + 78, theme, "#4b5a64", F14)

        metrics = [("PE", "低/周期"), ("Forward PE", "偏低"), ("1年区间", "低位"), ("负债/现金", "可控")]
        for metric_index, (label, value) in enumerate(metrics):
            mx = x + 18 + metric_index * 158
            my = y + 108
            rr((mx, my, mx + 148, my + 52), "#f5f8f9", "#e1e8ea")
            txt(mx + 9, my + 8, label, "#667681", F12)
            txt(mx + 9, my + 27, value, "#147b73", F14)

        txt(x + 18, y + 176, "基本面", "#17212b", F15)
        for line_index, line in enumerate(wrap(fundamental, 26)):
            txt(x + 18, y + 200 + line_index * 20, line, "#4b5a64", F13)
        txt(x + 350, y + 176, "K线分析", "#17212b", F15)
        for line_index, line in enumerate(wrap(technical, 24)):
            txt(x + 350, y + 200 + line_index * 20, line, "#4b5a64", F13)

        candle_chart(x + 18, y + 228, 170, 42, values)
        bx, by = x + 210, y + 233
        for bar_index, value in enumerate(bars):
            yy = by + bar_index * 8
            d.line((bx, yy, bx + 260, yy), fill="#e5ecee", width=5)
            d.line((bx, yy, bx + value * 2.6, yy), fill="#147b73", width=5)

    return img


if __name__ == "__main__":
    make_image().save(OUT)
    print(OUT)
