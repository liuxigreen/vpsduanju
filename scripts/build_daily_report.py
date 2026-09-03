#!/usr/bin/env python3
"""build_daily_report — YouTube短剧出海情报日报生成器

数据源（全部现成，零新增采集）:
  - data/alerts_latest.json      → 爆款预警 Top5 + 24h 增量
  - data/video_views_history/    → 24h增量计算（最新两天快照）
  - data/knowledge_graph.json    → 蓝海速报（题材×语种四象限）
  - data/subtitle_analysis/p0_report.json → 字幕实证速报
  - distill/outputs/*.json       → 蒸馏规则（本周验证 Top1）

用法:
    python3 scripts/build_daily_report.py              # 输出 Markdown 到 stdout
    python3 scripts/build_daily_report.py --save       # 保存到 output/daily_report/
"""
import argparse
import json
import os
import re
import statistics
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALERTS = ROOT / "data" / "alerts_latest.json"
HISTORY = ROOT / "data" / "video_views_history"
KG = ROOT / "data" / "knowledge_graph.json"
P0 = ROOT / "data" / "subtitle_analysis" / "full_report.json"  # 2026-09-03: 全量4497聚合(v2)，兼容旧p0_report.json结构
P0_FALLBACK = ROOT / "data" / "subtitle_analysis" / "p0_report.json"
DISTILL = ROOT / "distill" / "outputs"
OUT = ROOT / "output" / "daily_report"

# 语种中文名 → code 映射
CODE_MAP = {
    "繁中": "zh-Hant", "英文": "en", "印尼": "id", "西语": "es",
    "葡萄牙": "pt", "日语": "ja", "土耳其": "tr",
    "zh-Hant": "zh-Hant", "en": "en", "id": "id", "es": "es",
    "pt": "pt", "ja": "ja", "tr": "tr",
}


def fmt(n):
    if n is None:
        return "—"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _load_json(fp):
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def calc_24h_ranking():
    """从 video_views_history 最新两天快照算 24h 增量。"""
    files = sorted(f for f in HISTORY.glob("*.json") if not f.name.startswith("_"))
    if len(files) < 2:
        return [], ""
    yday = _load_json(files[-2])
    today = _load_json(files[-1])
    meta = _load_json(HISTORY / "_meta.json")
    deltas = []
    for vid, cur in today.items():
        prev = yday.get(vid)
        if prev is None:
            continue
        d = cur - prev
        if d > 0:
            m = meta.get(vid, {})
            deltas.append({
                "video_id": vid, "title": m.get("title", ""),
                "channel": m.get("channel", ""), "language": m.get("language", ""),
                "views": cur, "delta_24h": d,
            })
    deltas.sort(key=lambda x: -x["delta_24h"])
    return deltas[:300], files[-1].stem


def build_alerts_section(alerts):
    if not alerts:
        return "**今日无预警**（基线建立后每天 08:30 自动扫描）\n"
    lines = ["🔥 **今日爆款预警 Top5**\n"]
    for a in alerts[:5]:
        t = a.get("alert_types", [])
        icon = "🚀" if "breakout" in t else "⚡" if "spike" in t else "🌱"
        lines.append(f"{icon} **{a.get('title', '(无标题)')[:50]}**")
        lines.append(f"   {a.get('channel', '')} · {a.get('language', '')} · +{fmt(a.get('delta_24h'))}/24h · 总{fmt(a.get('views'))}")
    lines.append("")
    return "\n".join(lines)


def build_ranking_section(ranking, date):
    if not ranking:
        return ""
    lines = ["📈 **24h 增量热榜 Top10**\n"]
    lines.append("| # | 标题 | 频道 | 语种 | 24h增量 | 总播放 |")
    lines.append("|---|---|---|---|---|---|")
    for i, r in enumerate(ranking[:10], 1):
        lines.append(f"| {i} | {r.get('title', '')[:40]} | {r.get('channel', '')[:20]} | "
                      f"{r.get('language', '')} | +{fmt(r['delta_24h'])} | {fmt(r.get('views'))} |")
    lines.append(f"\n> 数据日期: {date}\n")
    return "\n".join(lines)


def build_blue_ocean_section(kg):
    """蓝海速报：动量增速 vs 频道供给 → 四象限速判。"""
    genres = kg.get("genre_rank", [])
    matrix = kg.get("matrix", {})
    cells = matrix.get("cells", [])  # [genre, lang, channel_count, momentum]

    supply = {}
    for c in cells:
        g, l, cnt, mom = c[0], c[1], c[2], c[3] if len(c) > 3 else 0
        supply[(g, l)] = {"channels": cnt, "momentum": mom}

    if not genres:
        # 从 cells 算
        if not supply:
            return ""
        med_mom = statistics.median([v["momentum"] for v in supply.values()]) if supply else 0
        lines = ["🌊 **蓝海速报**\n"]
        blue = {k: v for k, v in supply.items()
                if v["momentum"] > med_mom and v["channels"] <= 5}
        for (g, l), v in sorted(blue.items(), key=lambda x: -x[1]["momentum"])[:5]:
            lines.append(f"• **{g}×{l}** 动量 {fmt(v['momentum'])} 仅 {v['channels']} 频道 → 蓝海")
        if not blue:
            lines.append("• 当前无显著蓝海信号")
        lines.append("")
        return "\n".join(lines)

    # 用 genre_rank 的 momentum_avg
    med_mom = statistics.median([g.get("momentum_avg", 0) for g in genres]) if genres else 0
    lines = ["🌊 **蓝海速报**\n"]
    blue = []
    for g in genres:
        gn = g["genre"]
        avg_mom = g.get("momentum_avg", 0)
        ch_cnt = g["channels"]
        if avg_mom > med_mom and ch_cnt <= 10:
            top_lang = (g.get("top_languages") or ["?"])[0]
            blue.append((gn, top_lang, avg_mom, ch_cnt))
    for gn, tl, mom, cnt in sorted(blue, key=lambda x: -x[2])[:5]:
        lines.append(f"• **{gn}×{tl}** 动量 {fmt(mom)} 仅 {cnt} 频道 → 蓝海")
    if not blue:
        lines.append("• 当前无显著蓝海信号")
    lines.append("")
    return "\n".join(lines)


def build_subtitle_section(p0):
    ls = p0.get("lang_stats", {})
    if not ls:
        return ""
    lines = ["🎬 **字幕内容实证速报**\n"]
    lines.append("| 语种 | 样本 | 翻译剧率 | 合辑率 | 中位时长 | 中位播放 | 钩子中位(s) | 反转/10min |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for lang, s in sorted(ls.items(), key=lambda x: -x[1].get("n", 0)):
        lines.append(f"| {lang} | {s.get('n', 0)} | {s.get('translated_ratio', 0):.0%} | "
                      f"{s.get('compilation_ratio', 0):.0%} | {s.get('median_duration_min', '')}m | "
                      f"{fmt(s.get('median_views'))} | {s.get('median_hook_at_sec', '')}s | "
                      f"{s.get('median_reversal_per10min', '')} |")
    lines.append("")
    return "\n".join(lines)


def build_distill_section():
    """从蒸馏规则中挑一条本周验证过的规则。"""
    files = sorted(DISTILL.glob("distilled-rules-*.json"))
    if not files:
        return ""
    # 随机挑一条英文的
    en = next((f for f in files if "英文" in f.name), files[0])
    try:
        rules = json.loads(en.read_text(encoding="utf-8"))
        if "how" in rules and isinstance(rules["how"], list) and rules["how"]:
            rule = rules["how"][0]
            name = rule.get("name", "通用规则")
            template = (rule.get("template") or "")[:120]
            reason = (rule.get("why_it_works") or "")[:100]
            return f"✅ **本周验证的蒸馏规则**\n**{name}**\n> {template}\n\n{reason}\n\n"
    except Exception:
        pass
    return ""


def build_report():
    alerts_data = _load_json(ALERTS)
    alerts = alerts_data.get("alerts", [])
    kg = _load_json(KG)
    p0 = _load_json(P0) or _load_json(P0_FALLBACK)
    ranking, rank_date = calc_24h_ranking()

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# 📊 YouTube 短剧出海情报 · {today}",
        "",
        build_alerts_section(alerts),
        build_ranking_section(ranking, rank_date),
        build_blue_ocean_section(kg),
        build_subtitle_section(p0),
        build_distill_section(),
        "---",
        f"> 自动生成 · 数据来源: alerts_latest + knowledge_graph + p0_report + distill",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--save", action="store_true", help="保存到 output/daily_report/")
    ap.add_argument("--telegram", action="store_true", help="输出 Telegram 精简版")
    args = ap.parse_args()

    report = build_report()

    if args.telegram:
        # Telegram 版：压缩内容，去掉表格的纯文本格式
        lines = report.split("\n")
        out = []
        in_table = False
        for l in lines:
            if l.startswith("| ") and l.count("|") > 3:
                in_table = True
                if not l.startswith("| ---"):
                    out.append(l)
            else:
                if in_table and l.strip():
                    out.append(l)
                in_table = False
                if not in_table:
                    out.append(l)
        report = "\n".join(out)

    if args.save:
        OUT.mkdir(parents=True, exist_ok=True)
        fp = OUT / f"daily_report_{datetime.now().strftime('%Y%m%d')}.md"
        fp.write_text(report, encoding="utf-8")
        print(f"✅ 保存到 {fp}")
    else:
        print(report)


if __name__ == "__main__":
    main()