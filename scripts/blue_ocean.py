#!/usr/bin/env python3
"""blue_ocean — 蓝海雷达四象限分析

数据源: data/knowledge_graph.json (matrix.cells + genre_rank)
输出: 四象限 JSON + 文本速报

四象限定义:
  蓝海: 高动量 + 低供给 (建议进场)
  热战: 高动量 + 高供给 (拼执行)
  荒漠: 低动量 + 低供给 (观察)
  红海: 低动量 + 高供给 (规避)

用法:
    python3 scripts/blue_ocean.py                     # 输出文本速报
    python3 scripts/blue_ocean.py --json              # 输出四象限 JSON
    python3 scripts/blue_ocean.py --save              # 保存到 data/blue_ocean/
"""
import argparse
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KG = ROOT / "data" / "knowledge_graph.json"
OUT = ROOT / "data" / "blue_ocean"


def fmt(n):
    if n is None:
        return "—"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def compute_quadrant(kg):
    """计算题材×语种四象限。"""
    cells = kg.get("matrix", {}).get("cells", [])  # [genre, language, channel_count, momentum]
    genre_rank = kg.get("genre_rank", [])

    if not cells:
        return {"error": "matrix.cells 为空"}

    # 提取所有 (genre, lang) 组合的供给和动量
    items = []
    for c in cells:
        if len(c) < 4:
            continue
        g, l, cnt, mom = c[0], c[1], c[2], c[3]
        items.append({"genre": g, "language": l, "channels": cnt, "momentum": mom})

    if not items:
        return {"error": "无有效数据"}

    # 中位数分界
    mom_vals = [i["momentum"] for i in items]
    ch_vals = [i["channels"] for i in items]
    med_mom = statistics.median(mom_vals) if mom_vals else 0
    med_ch = statistics.median(ch_vals) if ch_vals else 0

    quadrant = {"blue_ocean": [], "hot_war": [], "desert": [], "red_sea": []}
    for i in items:
        if i["momentum"] >= med_mom and i["channels"] <= med_ch:
            quadrant["blue_ocean"].append(i)
        elif i["momentum"] >= med_mom and i["channels"] > med_ch:
            quadrant["hot_war"].append(i)
        elif i["momentum"] < med_mom and i["channels"] <= med_ch:
            quadrant["desert"].append(i)
        else:
            quadrant["red_sea"].append(i)

    # 各象限排序
    for q in quadrant:
        quadrant[q].sort(key=lambda x: -x["momentum"])

    # 统计
    stats = {
        "total_cells": len(items),
        "median_momentum": round(med_mom),
        "median_channels": round(med_ch),
        "quadrant_counts": {k: len(v) for k, v in quadrant.items()},
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }

    return {"quadrant": quadrant, "stats": stats}


def build_text_report(qdata):
    """生成文本速报版（适合日报/Telegram）。"""
    quad = qdata.get("quadrant", {})
    stats = qdata.get("stats", {})
    lines = [
        "🌊 **蓝海雷达 · 题材×语种四象限**\n",
        f"分界: 中位动量 {fmt(stats.get('median_momentum'))} | 中位频道数 {stats.get('median_channels', '')} 个\n",
    ]

    blue = quad.get("blue_ocean", [])[:5]
    if blue:
        lines.append("🟢 **蓝海区（高动量+低供给 → 进场）**")
        for i in blue[:5]:
            lines.append(f"  • **{i['genre']}×{i['language']}** 动量 {fmt(i['momentum'])} 仅 {i['channels']} 频道")
        lines.append("")

    hot = quad.get("hot_war", [])[:5]
    if hot:
        lines.append("🟡 **热战区（高动量+高供给 → 拼执行）**")
        for i in hot[:5]:
            lines.append(f"  • **{i['genre']}×{i['language']}** 动量 {fmt(i['momentum'])} {i['channels']} 频道在抢")
        lines.append("")

    red = quad.get("red_sea", [])[:3]
    if red:
        lines.append("🔴 **红海区（低动量+高供给 → 规避）**")
        for i in red[:3]:
            lines.append(f"  • **{i['genre']}×{i['language']}** 动量 {fmt(i['momentum'])} 却有 {i['channels']} 频道")
        lines.append("")

    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true", help="输出 JSON 格式")
    ap.add_argument("--save", action="store_true", help="保存到 data/blue_ocean/")
    args = ap.parse_args()

    kg = json.loads(KG.read_text(encoding="utf-8"))
    qdata = compute_quadrant(kg)

    if "error" in qdata:
        print(f"❌ {qdata['error']}")
        return

    if args.save:
        OUT.mkdir(parents=True, exist_ok=True)
        fp = OUT / "blue_ocean.json"
        fp.write_text(json.dumps(qdata, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"✅ 保存到 {fp}")

    if args.json:
        print(json.dumps(qdata, ensure_ascii=False, indent=1))
    else:
        print(build_text_report(qdata))


if __name__ == "__main__":
    main()