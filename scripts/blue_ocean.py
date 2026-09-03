#!/usr/bin/env python3
"""blue_ocean — 蓝海雷达四象限分析（v2 字幕实证语义）

数据源: data/knowledge_graph.json schema 2.0 (matrix.cells + genre_rank)
输出: 四象限 JSON + 文本速报

matrix.cells 语义（v2）: [题材, 语种, 实证视频数n, 中位播放]
四象限定义（v2，需求侧=单条内容赚钱能力，供给侧=内容拥挤度）:
  蓝海: 高中位播放 + 低供给   → 观众爱看、内容还少，进场
  热战: 高中位播放 + 高供给   → 已被验证的热门赛道，拼执行
  荒漠: 低中位播放 + 低供给   → 双低，观察
  红海: 低中位播放 + 高供给   → 内容过剩播放平庸，规避
样本门槛: n>=5 才参与象限判定（小样本中位数不稳）。

用法:
    python3 scripts/blue_ocean.py                     # 输出文本速报
    python3 scripts/blue_ocean.py --json              # 输出四象限 JSON
    python3 scripts/blue_ocean.py --save              # 保存到 data/blue_ocean/blue_ocean.json
"""
import argparse
import json
import statistics
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KG = ROOT / "data" / "knowledge_graph.json"
OUT = ROOT / "data" / "blue_ocean"

MIN_N = 5  # cell 实证样本门槛


def fmt(n):
    if n is None:
        return "—"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def compute_quadrant(kg):
    """计算题材×语种四象限（v2: [n, median_views] 语义）。"""
    cells = kg.get("matrix", {}).get("cells", [])  # [genre, language, subtitle_n, median_views]
    if not cells:
        return {"error": "matrix.cells 为空"}
    if kg.get("schema_version") != "2.0":
        return {"error": f"需要 schema 2.0 图谱，当前 {kg.get('schema_version')!r}（先跑 competitor_knowledge_graph_v2.py）"}

    items = [{"genre": c[0], "language": c[1], "n": c[2], "median_views": c[3]}
             for c in cells if len(c) >= 4 and c[2] >= MIN_N]
    if not items:
        return {"error": f"无 n>={MIN_N} 的有效 cell"}

    med_mv = statistics.median([i["median_views"] for i in items])
    med_n = statistics.median([i["n"] for i in items])

    quadrant = {"blue_ocean": [], "hot_war": [], "desert": [], "red_sea": []}
    for i in items:
        hi_demand = i["median_views"] >= med_mv
        hi_supply = i["n"] > med_n
        key = ("hot_war" if hi_supply else "blue_ocean") if hi_demand \
            else ("red_sea" if hi_supply else "desert")
        quadrant[key].append(i)

    for q in quadrant.values():
        q.sort(key=lambda x: -x["median_views"])

    stats = {
        "total_cells": len(items),
        "min_n": MIN_N,
        "median_median_views": round(med_mv),
        "median_n": round(med_n),
        "quadrant_counts": {k: len(v) for k, v in quadrant.items()},
        "generated_at": datetime.now().isoformat(timespec="seconds"),
    }
    return {"quadrant": quadrant, "stats": stats}


def build_text_report(qdata):
    """生成文本速报版（适合日报/Telegram）。"""
    quad = qdata.get("quadrant", {})
    stats = qdata.get("stats", {})
    lines = [
        "🌊 **蓝海雷达 · 题材×语种四象限（字幕实证）**\n",
        f"分界: 中位播放 {fmt(stats.get('median_median_views'))} | 中位供给 {stats.get('median_n', '')} 条 (n≥{stats.get('min_n')})\n",
    ]

    blue = quad.get("blue_ocean", [])[:5]
    if blue:
        lines.append("🟢 **蓝海区（高播放+低供给 → 进场）**")
        for i in blue:
            lines.append(f"  • **{i['genre']}×{i['language']}** 中位播放 {fmt(i['median_views'])} 仅 {i['n']} 条实证")
        lines.append("")

    hot = quad.get("hot_war", [])[:5]
    if hot:
        lines.append("🟡 **热战区（高播放+高供给 → 拼执行）**")
        for i in hot:
            lines.append(f"  • **{i['genre']}×{i['language']}** 中位播放 {fmt(i['median_views'])} · {i['n']} 条在抢")
        lines.append("")

    red = quad.get("red_sea", [])[:3]
    if red:
        lines.append("🔴 **红海区（低播放+高供给 → 规避）**")
        for i in red:
            lines.append(f"  • **{i['genre']}×{i['language']}** 中位播放仅 {fmt(i['median_views'])} 却有 {i['n']} 条")
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
