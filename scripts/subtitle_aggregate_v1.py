#!/usr/bin/env python3
"""subtitle_aggregate_v1 — 字幕分析结果聚合（确定性统计，无LLM）

多源合并：
  - (旧) ~/duanju/output/subtitle_task/results_p0.jsonl   — P0 旧格式（189条）
  - (新) ~/duanju/data/video_genres/*.json                 — L1校准新格式（含 norm_genre）
归一化统一到 genre_vocab 单一来源。

输出: ~/duanju/data/subtitle_analysis/
  - p0_normalized.jsonl      规范化数据（+is_compilation, hook map, L1归并）
  - p0_report.json           全部聚合指标（确定性 schema）
  - subtitle_graph_trial.json 试验版视频层知识图谱
  - p0_trial_report.md       人读报告
"""
import json, re, os, statistics, sys, yaml
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_OLD = ROOT / "output/subtitle_task/results_p0.jsonl"
SRC_GENRES = ROOT / "data/video_genres"
OUT = ROOT / "data/subtitle_analysis"
os.makedirs(OUT, exist_ok=True)

# ── 归一化（统一到 genre_vocab 单一来源）──
VOCAB_PATH = ROOT / "scripts/l1_calibration/genre_vocab.yaml"
_vocab = None


def _get_vocab():
    global _vocab
    if _vocab is None:
        _vocab = yaml.safe_load(VOCAB_PATH.read_text(encoding="utf-8"))
    return _vocab


def norm_genre(label):
    """别名归一化；非题材词返回 None。"""
    if not label:
        return None
    s = label.strip()
    v = _get_vocab()
    alias = v.get("alias", {})
    s = alias.get(s, alias.get(s.lower(), s))
    ns = v.get("non_genre", [])
    if s in ns or s.lower() in [x.lower() for x in ns]:
        return None
    return s


# ── 合辑双信号：标题正则 OR 时长>1h ──
COMP_PAT = re.compile(
    r'(第?\s*\d+\s*[-—~至到]\s*\d+\s*季|合辑|合集|全集|完整版|一口气|[Hh]e\s*\d+|'
    r'all episodes|compilation|marathon|full\s+movie|'
    r'ep[.\s]?\d+.{0,15}ep[.\s]?\d+)', re.I)


def is_compilation(title, duration_sec):
    return bool(COMP_PAT.search(title or "")) or (duration_sec or 0) > 7200


# ── 读取旧 P0 格式 ──
def load_old():
    rows = []
    if not SRC_OLD.exists():
        return rows
    for line in SRC_OLD.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("analysis") or {}
        if not a.get("genre_l1") and not a.get("genre_l1_emergent"):
            continue
        # 归一化 genre_l1
        raw_l1 = a.get("genre_l1", [])
        raw_l1_em = a.get("genre_l1_emergent", [])
        normed = []
        for g in list(raw_l1) + list(raw_l1_em):
            ng = norm_genre(g)
            if ng and ng not in normed:
                normed.append(ng)
        dur = d.get("duration_sec")
        rows.append({
            "video_id": d["video_id"],
            "title": d.get("title", ""),
            "channel": d.get("channel", ""),
            "language": d.get("language", d.get("lang", "")),
            "lang_code": d.get("lang_code", ""),
            "views": d.get("views", 0),
            "duration_sec": dur,
            "is_compilation": is_compilation(d.get("title"), dur),
            "analysis": {
                "genre_l1": normed or raw_l1,
                "genre_l1_emergent": a.get("genre_l1_emergent", []),
                "genre_l2": a.get("genre_l2", []),
                "genre_l2_emergent": a.get("genre_l2_emergent", []),
                "payoffs": a.get("payoffs", []),
                "opening_hook": a.get("opening_hook", {}),
                "ending_cliffhanger": a.get("ending_cliffhanger", {}),
                "reversal_density": a.get("reversal_density"),
                "key_reveals": a.get("key_reveals", []),
                "origin_signals": a.get("origin_signals", {}),
                "confidence": a.get("confidence"),
            },
        })
    return rows


# ── 读取新 L1 校准格式 ──
def load_new():
    rows = []
    files = sorted(SRC_GENRES.glob("*.json"))
    for fp in files:
        if fp.name.endswith(".raw.txt"):
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("_status") not in ("ok", "ok_with_issues"):
            continue
        dur = d.get("duration_sec")
        rows.append({
            "video_id": d["video_id"],
            "title": d.get("title", ""),
            "channel": d.get("channel", ""),
            "language": d.get("language", ""),
            "views": d.get("daily_views", 0),
            "duration_sec": dur,
            "is_compilation": is_compilation(d.get("title"), dur),
            "analysis": {
                "genre_l1": d.get("genre_l1", []),
                "genre_l1_emergent": d.get("genre_l1_emergent", []),
                "genre_l2": d.get("genre_l2", []),
                "genre_l2_emergent": d.get("genre_l2_emergent", []),
                "payoffs": d.get("payoffs", []),
                "opening_hook": d.get("opening_hook", {}),
                "ending_cliffhanger": d.get("ending_cliffhanger", {}),
                "reversal_density": d.get("reversal_density"),
                "key_reveals": d.get("key_reveals", []),
                "origin_signals": {"feels_translated": d.get("feels_translated", False)},
                "confidence": d.get("confidence"),
            },
        })
    return rows


# ── 合并去重：新数据优先 ──
def merge_rows(old, new):
    by_id = {}
    for d in new:
        by_id[d["video_id"]] = d
    for d in old:
        vid = d["video_id"]
        if vid not in by_id:
            by_id[vid] = d
    merged = list(by_id.values())
    print(f"  old={len(old)} new={len(new)} merged={len(merged)}")
    return merged


# ── 聚合 ──
def med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 2) if xs else None


def by_lang(rows):
    out = defaultdict(lambda: {"n": 0, "views": [], "durs": [], "comp": 0,
                               "translated": 0, "cliff": 0, "rev": [], "conf": [],
                               "hook_sec": [], "l1": Counter(), "l2": Counter()})
    for d in rows:
        a = d["analysis"]
        k = d["language"]
        o = out[k]
        o["n"] += 1
        o["views"].append(d.get("views", 0))
        o["durs"].append(d.get("duration_sec"))
        o["comp"] += int(d["is_compilation"])
        o["translated"] += int(bool((a.get("origin_signals") or {}).get("feels_translated")))
        o["cliff"] += int(bool((a.get("ending_cliffhanger") or {}).get("present")))
        o["rev"].append(a.get("reversal_density"))
        o["conf"].append(a.get("confidence"))
        h = a.get("opening_hook") or {}
        if h.get("appears_at_sec") is not None:
            o["hook_sec"].append(h["appears_at_sec"])
        for g in a.get("genre_l1", []):
            o["l1"][g] += 1
        for g in a.get("genre_l2", []):
            o["l2"][g] += 1
    return out


def grp_stats(rows, keyfn):
    g = defaultdict(list)
    for d in rows:
        for k in keyfn(d):
            g[k].append(d.get("views", 0))
    return {k: {"n": len(v), "median_views": med(v), "total_views": sum(v)}
            for k, v in sorted(g.items(), key=lambda x: -sum(x[1]))}


# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

old = load_old()
new = load_new()
norm_rows = merge_rows(old, new)

# 多源输出（覆盖写，防重复累积）
with open(OUT / "p0_normalized.jsonl", "w", encoding="utf-8") as f:
    for d in norm_rows:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

# ── 聚合报告 ──
lang_stats = {}
for k, o in by_lang(norm_rows).items():
    lang_stats[k] = {
        "n": o["n"],
        "median_views": med(o["views"]),
        "median_duration_min": round(med(o["durs"]) / 60, 1) if o["durs"] else None,
        "compilation_ratio": round(o["comp"] / o["n"], 2),
        "translated_ratio": round(o["translated"] / o["n"], 2),
        "cliffhanger_ratio": round(o["cliff"] / o["n"], 2),
        "median_reversal_per10min": med(o["rev"]),
        "median_confidence": med(o["conf"]),
        "median_hook_at_sec": med(o["hook_sec"]),
        "top_l1": dict(o["l1"].most_common(6)),
        "top_l2": dict(o["l2"].most_common(8)),
    }

genre_stats = grp_stats(norm_rows, lambda d: d["analysis"].get("genre_l1", []))
hook_stats = grp_stats(norm_rows, lambda d: [((d["analysis"].get("opening_hook") or {}).get("type") or "其他")])
payoff_stats = grp_stats(norm_rows, lambda d: (d["analysis"] or {}).get("payoffs", []))

co = Counter()
for d in norm_rows:
    for g1 in d["analysis"].get("genre_l1", []):
        for g2 in d["analysis"].get("genre_l2", []):
            co[f"{g1}×{g2}"] += 1
cooc = dict(co.most_common(15))

l2c = Counter()
for d in norm_rows:
    for g in d["analysis"].get("genre_l2", []):
        l2c[g] += 1

hook_secs = [h.get("appears_at_sec") for d in norm_rows
             for h in [d["analysis"].get("opening_hook") or {}] if h.get("appears_at_sec") is not None]
hook_speed = {"n": len(hook_secs), "median_sec": med(hook_secs),
              "p25": sorted(hook_secs)[len(hook_secs) // 4] if hook_secs else None,
              "p75": sorted(hook_secs)[3 * len(hook_secs) // 4] if hook_secs else None}

pos = []
for d in norm_rows:
    dur = d.get("duration_sec") or 0
    if not dur:
        continue
    for kr in d["analysis"].get("key_reveals", []):
        s = kr.get("at_sec")
        if s is not None and 0 <= s <= dur:
            pos.append(s / dur)
reveal_timing = {"n": len(pos),
                 "pct_first_quarter": round(sum(1 for p in pos if p < 0.25) / len(pos), 2) if pos else None,
                 "pct_first_half": round(sum(1 for p in pos if p < 0.5) / len(pos), 2) if pos else None,
                 "pct_last_half": round(sum(1 for p in pos if p >= 0.5) / len(pos), 2) if pos else None}

lang_genre_matrix = {k: v["top_l1"] for k, v in lang_stats.items()}

report = {
    "pipeline_version": "subtitle_aggregate_v1",
    "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    "input": {"old": str(SRC_OLD), "new": str(SRC_GENRES)},
    "rows": len(norm_rows),
    "lang_stats": lang_stats,
    "genre_l1_stats": genre_stats,
    "hook_type_stats": hook_stats,
    "payoff_stats_top15": dict(list(payoff_stats.items())[:15]),
    "genre_l1_x_l2_cooccur_top15": cooc,
    "genre_l2_top25": dict(l2c.most_common(25)),
    "hook_speed": hook_speed,
    "reveal_timing": reveal_timing,
    "compilation": {
        "n": sum(1 for d in norm_rows if d["is_compilation"]),
        "ratio": round(sum(1 for d in norm_rows if d["is_compilation"]) / len(norm_rows), 3),
        "median_views_comp": med([d["views"] for d in norm_rows if d["is_compilation"]]),
        "median_views_single": med([d["views"] for d in norm_rows if not d["is_compilation"]]),
    },
    "lang_genre_matrix": lang_genre_matrix,
}

# ── 试验版视频层图谱 ──
nodes, edges = [], []
node_ids = set()


def add_node(nid, ntype, label, **metrics):
    if nid in node_ids:
        return
    node_ids.add(nid)
    nodes.append({"id": nid, "type": ntype, "label": label, "metrics": metrics})


for d in norm_rows:
    a = d["analysis"]
    vid_node = f"video:{d['video_id']}"
    add_node(vid_node, "video", d["title"][:60], lang=d["language"],
             views=d.get("views", 0), is_compilation=d["is_compilation"])
    add_node(f"language:{d['language']}", "language", d["language"])
    edges.append({"source": vid_node, "target": f"language:{d['language']}",
                  "type": "in_language", "weight": d.get("views", 0)})
    for g in a.get("genre_l1", []):
        add_node(f"genre:{g}", "genre", g)
        edges.append({"source": vid_node, "target": f"genre:{g}",
                      "type": "has_genre", "weight": d.get("views", 0)})
    ht = (a.get("opening_hook") or {}).get("type") or "其他"
    add_node(f"hook:{ht}", "hook", ht)
    edges.append({"source": vid_node, "target": f"hook:{ht}",
                  "type": "opens_with", "weight": d.get("views", 0)})

for pair, c in co.most_common(60):
    g1, g2 = pair.split("×")
    if f"genre:{g1}" in node_ids and f"genre:{g2}" in node_ids:
        edges.append({"source": f"genre:{g1}", "target": f"genre:{g2}",
                      "type": "cooccur", "weight": c})

graph = {"schema_version": "trial-0.1", "generated_at": report["generated_at"],
         "stats": {"videos": len(norm_rows), "nodes": len(nodes), "edges": len(edges)},
         "nodes": nodes, "edges": edges}

# ── 落盘 ──
json.dump(report, open(OUT / "p0_report.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)
json.dump(graph, open(OUT / "subtitle_graph_trial.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1)

# ── 人读报告 ──
md = [f"# 字幕分析聚合报告（rows={len(norm_rows)}）",
      f"> pipeline: subtitle_aggregate_v1 @ {report['generated_at']} — 确定性统计，无LLM",
      f"> 多源合并: old={len(old)} new={len(new)}", ""]

md.append("## 1. 语种市场画像")
md.append("| 语种 | n | 中位播放 | 中位时长 | 合辑率 | 翻译剧率 | 结尾悬念率 | 反转/10min | 钩子出现(s) |")
md.append("|---|---|---|---|---|---|---|---|---|")
for k, v in sorted(lang_stats.items(), key=lambda x: -x[1]["n"]):
    md.append(f"| {k} | {v['n']} | {v['median_views']:,} | {v['median_duration_min']}m | "
              f"{v['compilation_ratio']:.0%} | {v['translated_ratio']:.0%} | {v['cliffhanger_ratio']:.0%} | "
              f"{v['median_reversal_per10min']} | {v['median_hook_at_sec']} |")

md.append("\n## 2. L1 题材 × 播放量")
md.append("| 题材 | n | 中位播放 | 总播放 |")
md.append("|---|---|---|---|")
for k, v in list(genre_stats.items())[:18]:
    md.append(f"| {k} | {v['n']} | {v['median_views']:,} | {v['total_views']:,} |")

md.append("\n## 3. 开场钩子类型 × 播放量")
md.append("| 钩子类型 | n | 中位播放 | 总播放 |")
md.append("|---|---|---|---|")
for k, v in hook_stats.items():
    md.append(f"| {k} | {v['n']} | {v['median_views']:,} | {v['total_views']:,} |")
md.append(f"\n钩子出现速度: 中位 {hook_speed['median_sec']}s（P25={hook_speed['p25']}s / P75={hook_speed['p75']}s, n={hook_speed['n']}）")
md.append(f"关键反转时间: 前1/4 {reveal_timing['pct_first_quarter']} · 前半 {reveal_timing['pct_first_half']} · 后半 {reveal_timing['pct_last_half']}（n={reveal_timing['n']}）")

md.append("\n## 4. L1×L2 共现 Top15")
md.append("```")
for k in cooc:
    md.append(f"  {k}: {cooc[k]}")
md.append("```")

md.append("\n## 5. Payoff Top15")
md.append("| payoff | n | 中位播放 |")
md.append("|---|---|---|")
for k, v in list(payoff_stats.items())[:15]:
    md.append(f"| {k} | {v['n']} | {v['median_views']:,} |")

md.append("\n## 6. L2 题材 Top25")
md.append("```")
for k, c in l2c.most_common(25):
    md.append(f"  {k}: {c}")
md.append("```")

md.append("\n## 7. 合辑信号")
c = report["compilation"]
md.append(f"- 双信号(标题正则 OR 时长>1h): 合辑 {c['n']}/{len(norm_rows)} ({c['ratio']:.0%})")
md.append(f"- 合辑中位播放 {c['median_views_comp']:,} vs 单剧 {c['median_views_single']:,}")

md.append("\n## 8. 试验版图谱")
md.append(f"- nodes={graph['stats']['nodes']} edges={graph['stats']['edges']} → `subtitle_graph_trial.json`")

open(OUT / "p0_trial_report.md", "w", encoding="utf-8").write("\n".join(md))
print(f"✅ OK — rows={len(norm_rows)} graph_nodes={len(nodes)} graph_edges={len(edges)}")