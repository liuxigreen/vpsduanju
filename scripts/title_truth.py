#!/usr/bin/env python3
"""title_truth — 标题真相引擎（输入标题 → 看穿它）

核心: L0（标题关键词）× L1（字幕内容）混淆矩阵 → 标题通胀系数

输入: 任意标题
输出: 题材预测 + 通胀风险 + 同类表现

用法:
    python3 scripts/title_truth.py "CEO's Secret Baby"
    python3 scripts/title_truth.py "重生之亿万总裁追妻路"
    python3 scripts/title_truth.py --json "Only poor girl passed 99 tests among 999 CEO nanny applicants"
"""
import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
P0 = ROOT / "data" / "subtitle_analysis" / "p0_normalized.jsonl"
P0_REPORT = ROOT / "data" / "subtitle_analysis" / "p0_report.json"
LANG_MAP = ROOT / "config" / "lang_map.yaml"
GENRE_VOCAB = ROOT / "scripts" / "l1_calibration" / "genre_vocab.yaml"

# 标题关键词 → 题材（与 distill_competitors.extract_content_tags 同源）
KEYWORDS = {
    'ceo': '霸总', 'boss': '霸总', 'billionaire': '豪门', 'rich': '豪门',
    'revenge': '复仇', 'secret': '身份反转', 'pregnant': '怀孕',
    'baby': '萌宝', 'military': '军婚', 'werewolf': '狼人', 'vampire': '吸血鬼',
    'mafia': '黑帮', 'sweet': '甜宠', 'love': '爱情', 'divorce': '离婚',
    'betrayed': '背叛', 'abandoned': '弃养', 'adopted': '领养', 'orphan': '孤儿',
    'twins': '双胞胎', 'cinderella': '灰姑娘', 'fake': '假身份', 'hidden': '隐藏身份',
    'contract': '契约婚姻', 'marriage': '契约婚姻',
    '战神': '战神', '逆袭': '逆袭', '重生': '重生', '穿越': '穿越',
    '甜宠': '甜宠', '虐恋': '虐恋', '复仇': '复仇', '豪门': '豪门',
    '霸总': '霸总', '萌宝': '萌宝', '总裁': '霸总', '离婚': '离婚',
    '契约': '契约婚姻', '怀孕': '怀孕', '双胞胎': '双胞胎',
    '系统': '系统流', '神医': '神医', '赘婿': '赘婿',
    '陛下': '古装', '王爷': '古装', '王妃': '古装', '娘娘': '古装', '帝': '古装',
    # 多语种
    '계약': '契约婚姻', '재벌': '豪门', '복수': '复仇', '임신': '怀孕',
    '아기': '萌宝', '비밀': '身份反转', '회장': '霸总',
    '大富豪': '豪门', '復讐': '复仇', '契約結婚': '契约婚姻',
    '妊娠': '怀孕', '社長': '霸总', '取締役': '霸总',
    'zengin': '豪门', 'aşk': '爱情', 'intikam': '复仇', 'hamile': '怀孕',
    'gizli': '秘密身份', 'boşanma': '离婚', 'bebek': '萌宝',
}


def fmt(n):
    if n is None:
        return "—"
    if n >= 10000:
        return f"{n / 10000:.1f}万"
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def l0_extract(title):
    """从标题提取 L0 题材预测（关键词匹配）。"""
    t = title.lower()
    found = []
    for kw, label in KEYWORDS.items():
        if kw in t and label not in found:
            found.append(label)
    return found[:8]


def l1_load():
    """加载字幕内容的真实题材分布。"""
    rows = []
    if not P0.exists():
        return rows
    for line in P0.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("analysis") or {}
        rows.append({
            "title": d.get("title", ""),
            "language": d.get("language", ""),
            "views": d.get("views", 0),
            "genre_l1": a.get("genre_l1", []),
            "translated": bool((a.get("origin_signals") or {}).get("feels_translated")),
            "duration_sec": d.get("duration_sec"),
        })
    return rows


def build_inflation(rows, l0_tags):
    """计算标题通胀系数：L0 标签在字幕内容中的兑现率。

    对每个 L0 标签，反查 KEYWORDS 里映射到该标签的所有关键词（含英文/多语种），
    用这些关键词在标题中匹配 → 统计这些视频的内容题材真实分布。
    """
    if not rows or not l0_tags:
        return {}
    # 标签 → 该标签的所有触发关键词
    tag_keys = defaultdict(list)
    for kw, label in KEYWORDS.items():
        tag_keys[label].append(kw)

    inflation = {}
    for tag in l0_tags:
        keys = tag_keys.get(tag, [])
        if not keys:
            continue
        # 标题包含任一关键词的视频
        matched = []
        for d in rows:
            t = d["title"].lower()
            if any(k.lower() in t for k in keys):
                matched.append(d)
        if not matched:
            continue
        n_total = len(matched)
        n_real = sum(1 for d in matched if tag in d["genre_l1"])
        # 该标签视频的真实题材分布
        real_dist = Counter()
        for d in matched:
            for g in d["genre_l1"]:
                real_dist[g] += 1
        inflation[tag] = {
            "title_mentions": n_total,
            "content_real": n_real,
            "real_top": [g for g, _ in real_dist.most_common(4)],
            "fulfillment_rate": round(n_real / n_total, 2) if n_total >= 5 else None,
            "note": "样本不足≥5" if n_total < 5 else "",
        }
    return inflation


def similar_performance(rows, l0_tags, max_n=5):
    """找与 L0 标签匹配的视频，看同类播放表现。"""
    if not rows or not l0_tags:
        return []
    similar = []
    for d in rows:
        if any(t in d["genre_l1"] for t in l0_tags) or any(t.lower()[:2] in d["title"].lower() for t in l0_tags):
            similar.append(d)
    similar.sort(key=lambda x: -(x.get("views") or 0))
    return [
        {"title": s["title"][:50], "language": s["language"], "views": s["views"],
         "genre_l1": s["genre_l1"]}
        for s in similar[:max_n]
    ]


def analyze(title):
    rows = l1_load()
    l0 = l0_extract(title)
    inflation = build_inflation(rows, l0)
    similar = similar_performance(rows, l0)

    result = {
        "title": title,
        "l0_prediction": l0,
        "inflation": inflation,
        "similar_performance": similar,
        "stats": {
            "subtitle_samples": len(rows),
            "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        },
    }
    return result


def build_text_report(r):
    lines = [
        f"# 标题真相引擎 · {r['title'][:50]}",
        "",
        f"**L0 题材预测**: {', '.join(r['l0_prediction']) if r['l0_prediction'] else '（无匹配，未知题材）'}",
        "",
    ]
    if r["inflation"]:
        lines.append("**通胀检测**")
        for tag, v in r["inflation"].items():
            if v["fulfillment_rate"] is not None:
                if v["fulfillment_rate"] >= 0.7:
                    emoji = "✅ 低通胀"
                elif v["fulfillment_rate"] >= 0.4:
                    emoji = "⚠️ 中通胀"
                else:
                    emoji = "🔴 高通胀"
                lines.append(f"  • **{tag}** {emoji}: 兑现率 {v['fulfillment_rate']:.0%}（标题{v['title_mentions']}次 → 真实{v['content_real']}次）")
            else:
                lines.append(f"  • **{tag}** ⚪ 样本不足（库内仅 {v['title_mentions']} 条含此标签）")
        lines.append("")

    if r["similar_performance"]:
        lines.append("**同类视频表现**")
        for s in r["similar_performance"]:
            lines.append(f"  • {s['title'][:40]} | {s['language']} | {fmt(s['views'])} | L1: {', '.join(s['genre_l1'][:3])}")
        lines.append("")

    lines.append(f"---\n> 字幕样本: {r['stats']['subtitle_samples']} 条")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("title", nargs="*", help="要分析的标题")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    args = ap.parse_args()

    title = " ".join(args.title) if args.title else "CEO's Secret Baby"
    r = analyze(title)

    if args.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
    else:
        print(build_text_report(r))


if __name__ == "__main__":
    main()