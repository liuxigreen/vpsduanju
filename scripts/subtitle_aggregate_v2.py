#!/usr/bin/env python3
"""subtitle_aggregate_v2 — 全量字幕分析聚合（确定性统计，无LLM）

输入:
  - data/subtitle_analysis/incoming/analyses_merged_4497.jsonl  (4497条, 本地agent回传合并)
  - data/competitors_channels_all.json + data/l1_manifest.json + p0_normalized.jsonl (title/channel元数据)

输出: data/subtitle_analysis/
  - full_normalized.jsonl   归一化数据（+title/channel/is_compilation/model_family/schema_version）
  - full_report.json        聚合指标（确定性schema）
  - full_report.md          人读报告
  - qc_report.json          质检门禁结果（放量前冻结校验）

v1→v2 变化:
  - 数据源从"旧P0+video_genres"换成单一大文件（4497条含P0 179 + P1 4318）
  - schema 补齐 synopsis/characters/distinctive_lines/evidence（v1缺失的已知缺陷）
  - 新增按 tier/model_family 切片、溯源就绪度统计
"""
import json, re, os, statistics, sys, yaml, pickle
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC_MERGED = ROOT / "data/subtitle_analysis/incoming/analyses_merged_4497.jsonl"
OUT = ROOT / "data/subtitle_analysis"
os.makedirs(OUT, exist_ok=True)

SCHEMA_VERSION = "2.0"

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

# ── 合辑双信号：标题正则 OR 时长>2h（1-2h多为多集连剪正片，不算合集 2026-09-03）──
COMP_PAT = re.compile(
    r'(第?\s*\d+\s*[-—~至到]\s*\d+\s*季|合辑|合集|全集|完整版|一口气|[Hh]e\s*\d+|'
    r'all episodes|compilation|marathon|full\s+movie|'
    r'ep[.\s]?\d+.{0,15}ep[.\s]?\d+)', re.I)

def is_compilation(title, duration_sec):
    return bool(COMP_PAT.search(title or "")) or (duration_sec or 0) > 7200

# ── 模型家族归一（38种model字符串→家族，标注实际来源不抹除）──
def model_family(m):
    m = (m or "").lower()
    if "opus" in m: return "claude-opus"
    if "sonnet" in m or "fable" in m or "haiku" in m or "claude" in m: return "claude-other"
    if "glm" in m: return "glm"
    if "gpt" in m: return "gpt"
    if "qwen" in m: return "qwen"
    if "deepseek" in m: return "deepseek"
    if "minimax" in m: return "minimax"
    if "zai" in m: return "zai_auto"
    if any(k in m for k in ("cline", "openclaw", "workbuddy", "subtitle-analyzer")): return "agent-wrapper"
    return "unknown"

# ── 元数据合并（title/channel/published_at）──
def load_meta(newids):
    meta = {}
    def walk(x):
        if isinstance(x, dict):
            vid = x.get("video_id") or x.get("id")
            if isinstance(vid, str) and vid in newids and x.get("title") and vid not in meta:
                meta[vid] = {"title": x.get("title", ""),
                             "channel": x.get("channel") or x.get("channel_name") or "",
                             "published_at": x.get("published_at") or x.get("publishedAt") or ""}
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    p = ROOT / "data/competitors_channels_all.json"
    if p.exists():
        walk(json.loads(p.read_text(encoding="utf-8")))
    p = ROOT / "data/l1_manifest.json"
    if p.exists():
        for k, v in json.loads(p.read_text(encoding="utf-8")).get("videos", {}).items():
            if k in newids and k not in meta:
                meta[k] = {"title": v.get("title", ""), "channel": v.get("channel", ""),
                           "published_at": v.get("published_at", "")}
    p = ROOT / "data/subtitle_analysis/p0_normalized.jsonl"
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            try: d = json.loads(l)
            except Exception: continue
            vid = d.get("video_id")
            if vid in newids and vid not in meta:
                meta[vid] = {"title": d.get("title", ""), "channel": d.get("channel", ""), "published_at": ""}
    # 兜底：从字幕回传txt头部提取的元数据（extract_subs_meta.py 产出，覆盖全量采集清单）
    # 注意：字段级补空——高优先源可能只有title没有channel，这里补齐空缺而不是整体跳过
    p = ROOT / "data/subtitle_analysis/incoming/video_meta.jsonl"
    if p.exists():
        for l in p.read_text(encoding="utf-8").splitlines():
            try: d = json.loads(l)
            except Exception: continue
            vid = d.get("video_id")
            if vid not in newids: continue
            if vid not in meta:
                meta[vid] = {"title": d.get("title", ""), "channel": d.get("channel", ""), "published_at": ""}
            else:
                m0 = meta[vid]
                if not m0.get("title"): m0["title"] = d.get("title", "")
                if not m0.get("channel"): m0["channel"] = d.get("channel", "")
    return meta

# ── 读取合并文件 + 归一化 ──
def load_rows():
    rows, bad = [], 0
    raws = [json.loads(l) for l in SRC_MERGED.read_text(encoding="utf-8").splitlines() if l.strip()]
    newids = {r["video_id"] for r in raws}
    meta = load_meta(newids)
    for r in raws:
        try:
            a = r.get("analysis") or {}
            if not a.get("genre_l1") and not a.get("genre_l1_emergent"):
                continue
            normed = []
            for g in list(a.get("genre_l1", [])) + list(a.get("genre_l1_emergent", [])):
                ng = norm_genre(g)
                if ng and ng not in normed:
                    normed.append(ng)
            m = meta.get(r["video_id"], {})
            dur = r.get("duration_sec")
            title = m.get("title", "")
            rows.append({
                "schema_version": SCHEMA_VERSION,
                "video_id": r["video_id"],
                "title": title,
                "channel": m.get("channel", ""),
                "published_at": m.get("published_at", ""),
                "language": r.get("lang", ""),
                "lang_code": r.get("lang_code", ""),
                "views": r.get("views", 0),
                "duration_sec": dur,
                "tier": r.get("tier", ""),
                "model": r.get("model", ""),
                "model_family": model_family(r.get("model", "")),
                "has_meta": bool(m),
                "is_compilation": is_compilation(title, dur),
                "analysis": {
                    "genre_l1": normed or a.get("genre_l1", []),
                    "genre_l1_emergent": a.get("genre_l1_emergent", []),
                    "genre_l2": a.get("genre_l2", []),
                    "genre_l2_emergent": a.get("genre_l2_emergent", []),
                    "payoffs": a.get("payoffs", []),
                    "synopsis": a.get("synopsis"),
                    "characters": a.get("characters", []),
                    "distinctive_lines": a.get("distinctive_lines", []),
                    "evidence": a.get("evidence", {}),
                    "opening_hook": a.get("opening_hook", {}),
                    "ending_cliffhanger": a.get("ending_cliffhanger", {}),
                    "reversal_density": a.get("reversal_density"),
                    "key_reveals": a.get("key_reveals", []),
                    "origin_signals": a.get("origin_signals", {}),
                    "confidence": a.get("confidence"),
                },
            })
        except Exception:
            bad += 1
    return rows, bad

# ── 质检门禁（放量前冻结校验）──
def qc(rows):
    n = len(rows)
    def rate(f): return round(sum(1 for d in rows if f(d)) / n, 4) if n else 0
    checks = {
        "n": n,
        "unique_video_ids": len({d["video_id"] for d in rows}),
        "has_title": rate(lambda d: bool(d["title"])),
        "has_synopsis": rate(lambda d: isinstance(d["analysis"].get("synopsis"), str) and len(d["analysis"]["synopsis"]) >= 20),
        "has_characters": rate(lambda d: len([c for c in d["analysis"].get("characters", []) if isinstance(c, dict) and c.get("name")]) >= 2),
        "has_distinctive_lines": rate(lambda d: len([x for x in d["analysis"].get("distinctive_lines", []) if isinstance(x, str) and len(x.strip()) >= 5]) >= 2),
        "has_evidence_quotes": rate(lambda d: sum(1 for v in (d["analysis"].get("evidence") or {}).values() if isinstance(v, str) and len(v.strip()) >= 5) >= 3),
        "has_hook": rate(lambda d: bool((d["analysis"].get("opening_hook") or {}).get("type"))),
        "meta_coverage": rate(lambda d: d["has_meta"]),
    }
    gates = {
        "schema_fields_present": checks["has_synopsis"] >= 0.95 and checks["has_characters"] >= 0.95 and checks["has_distinctive_lines"] >= 0.95,
        "evidence_enforced": checks["has_evidence_quotes"] >= 0.95,
        "pass": checks["has_synopsis"] >= 0.95 and checks["has_characters"] >= 0.95 and checks["has_distinctive_lines"] >= 0.95 and checks["has_evidence_quotes"] >= 0.95,
    }
    return {"checks": checks, "gates": gates}

# ── 聚合 ──
def med(xs):
    num = []
    for x in xs:
        if x is None: continue
        try: num.append(float(x))
        except (TypeError, ValueError): continue
    return round(statistics.median(num), 2) if num else None

def by_slice(rows, keyfn):
    out = defaultdict(lambda: {"n": 0, "views": [], "durs": [], "comp": 0,
                               "translated": 0, "cliff": 0, "rev": [], "conf": [],
                               "hook_sec": [], "l1": Counter(), "l2": Counter()})
    for d in rows:
        k = keyfn(d)
        o = out[k]
        a = d["analysis"]
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
        for g in a.get("genre_l1", []): o["l1"][g] += 1
        for g in a.get("genre_l2", []): o["l2"][g] += 1
    res = {}
    for k, o in out.items():
        res[str(k)] = {
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
    return res

def grp_stats(rows, keyfn):
    g = defaultdict(list)
    for d in rows:
        for k in keyfn(d):
            if not isinstance(k, (str, int, float)): continue  # payoffs 等字段可能混入 dict，跳过
            g[k].append(d.get("views", 0))
    return {k: {"n": len(v), "median_views": med(v), "total_views": sum(v)}
            for k, v in sorted(g.items(), key=lambda x: -sum(x[1]))}

# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

rows, bad = load_rows()
qc_res = qc(rows)

with open(OUT / "full_normalized.jsonl", "w", encoding="utf-8") as f:
    for d in rows:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

lang_stats = by_slice(rows, lambda d: d["language"])
tier_stats = by_slice(rows, lambda d: d["tier"])
mfam_stats = by_slice(rows, lambda d: d["model_family"])

genre_stats = grp_stats(rows, lambda d: d["analysis"].get("genre_l1", []))
genre_l2_stats = grp_stats(rows, lambda d: d["analysis"].get("genre_l2", []))
hook_stats = grp_stats(rows, lambda d: [((d["analysis"].get("opening_hook") or {}).get("type") or "其他")])
payoff_stats = grp_stats(rows, lambda d: (d["analysis"] or {}).get("payoffs", []))

co = Counter()
for d in rows:
    for g1 in d["analysis"].get("genre_l1", []):
        for g2 in d["analysis"].get("genre_l2", []):
            co[f"{g1}×{g2}"] += 1
cooc = dict(co.most_common(20))

l2c = Counter()
for d in rows:
    for g in d["analysis"].get("genre_l2", []):
        l2c[g] += 1

# emergent 题材（词表外自创）汇总
em1, em2 = Counter(), Counter()
for d in rows:
    for g in d["analysis"].get("genre_l1_emergent", []): em1[g] += 1
    for g in d["analysis"].get("genre_l2_emergent", []): em2[g] += 1

def _num(x):
    try: return float(x)
    except (TypeError, ValueError): return None

hook_secs = [v for d in rows
             for h in [d["analysis"].get("opening_hook") or {}]
             for v in [_num(h.get("appears_at_sec"))] if v is not None]
hs = sorted(hook_secs)
hook_speed = {"n": len(hs), "median_sec": med(hs),
              "p25": hs[len(hs)//4] if hs else None,
              "p75": hs[3*len(hs)//4] if hs else None}

pos = []
for d in rows:
    dur = d.get("duration_sec") or 0
    if not dur: continue
    for kr in d["analysis"].get("key_reveals", []):
        s = kr.get("at_sec")
        if s is not None and 0 <= s <= dur:
            pos.append(s / dur)
reveal_timing = {"n": len(pos),
                 "pct_first_quarter": round(sum(1 for p in pos if p < 0.25) / len(pos), 2) if pos else None,
                 "pct_first_half": round(sum(1 for p in pos if p < 0.5) / len(pos), 2) if pos else None,
                 "pct_last_half": round(sum(1 for p in pos if p >= 0.5) / len(pos), 2) if pos else None}

# 溯源就绪度（v3 指纹搜索的输入完备率，按语种）
trace_ready = {}
for lg in {d["language"] for d in rows}:
    sub = [d for d in rows if d["language"] == lg and (d["analysis"].get("origin_signals") or {}).get("feels_translated")]
    n = len(sub) or 1
    trace_ready[lg] = {
        "translated_n": len(sub),
        "with_lines": round(sum(1 for d in sub if len(d["analysis"].get("distinctive_lines", [])) >= 2) / n, 2),
        "with_named_chars": round(sum(1 for d in sub if len([c for c in d["analysis"].get("characters", []) if isinstance(c, dict) and c.get("name")]) >= 1) / n, 2),
    }

report = {
    "pipeline_version": "subtitle_aggregate_v2",
    "schema_version": SCHEMA_VERSION,
    "generated_at": datetime.now().isoformat(timespec="seconds"),
    "input": {"merged": str(SRC_MERGED), "bad_lines_dropped": bad},
    "rows": len(rows),
    "qc": qc_res,
    "model_family_counts": dict(Counter(d["model_family"] for d in rows).most_common()),
    "tier_counts": dict(Counter(d["tier"] for d in rows)),
    "lang_stats": lang_stats,
    "tier_stats": tier_stats,
    "model_family_stats": mfam_stats,
    "genre_l1_stats": genre_stats,
    "genre_l2_stats": dict(list(genre_l2_stats.items())[:40]),
    "hook_type_stats": hook_stats,
    "payoff_stats_top15": dict(list(payoff_stats.items())[:15]),
    "genre_l1_x_l2_cooccur_top20": cooc,
    "genre_l2_top30": dict(l2c.most_common(30)),
    "emergent_l1_top15": dict(em1.most_common(15)),
    "emergent_l2_top15": dict(em2.most_common(15)),
    "hook_speed": hook_speed,
    "reveal_timing": reveal_timing,
    "trace_readiness": trace_ready,
    "compilation": {
        "n": sum(1 for d in rows if d["is_compilation"]),
        "ratio": round(sum(1 for d in rows if d["is_compilation"]) / len(rows), 3),
        "median_views_comp": med([d["views"] for d in rows if d["is_compilation"]]),
        "median_views_single": med([d["views"] for d in rows if not d["is_compilation"]]),
    },
    "lang_genre_matrix": {k: v["top_l1"] for k, v in lang_stats.items()},
}

json.dump(report, open(OUT / "full_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump(qc_res, open(OUT / "qc_report.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# ── 人读报告 ──
md = [f"# 字幕分析全量聚合报告 v2（rows={len(rows)}）",
      f"> pipeline: subtitle_aggregate_v2 @ {report['generated_at']} — 确定性统计，无LLM",
      f"> 输入: analyses_merged_4497.jsonl（坏行丢弃 {bad}）", ""]

md.append("## 0. 质检门禁")
for k, v in qc_res["checks"].items(): md.append(f"- {k}: {v}")
md.append(f"- **gates: {qc_res['gates']}**")

md.append("\n## 1. 语种市场画像")
md.append("| 语种 | n | 中位播放 | 中位时长 | 合辑率 | 翻译剧率 | 结尾悬念率 | 反转/10min | 钩子出现(s) |")
md.append("|---|---|---|---|---|---|---|---|---|")
for k, v in sorted(lang_stats.items(), key=lambda x: -x[1]["n"]):
    mv = f"{v['median_views']:,}" if v["median_views"] else "-"
    md.append(f"| {k} | {v['n']} | {mv} | {v['median_duration_min']}m | "
              f"{v['compilation_ratio']:.0%} | {v['translated_ratio']:.0%} | {v['cliffhanger_ratio']:.0%} | "
              f"{v['median_reversal_per10min']} | {v['median_hook_at_sec']} |")

md.append("\n## 2. Tier / 模型家族")
md.append(f"- tier: {report['tier_counts']}")
md.append(f"- model_family: {report['model_family_counts']}")
md.append("\n| 切片 | n | 中位播放 | 翻译剧率 | 中位conf |")
md.append("|---|---|---|---|---|")
for name, st in (("tier", tier_stats), ("model_family", mfam_stats)):
    for k, v in st.items():
        mv = f"{v['median_views']:,}" if v["median_views"] else "-"
        md.append(f"| {name}:{k} | {v['n']} | {mv} | {v['translated_ratio']:.0%} | {v['median_confidence']} |")

md.append("\n## 3. L1 题材 × 播放量 Top20")
md.append("| 题材 | n | 中位播放 | 总播放 |")
md.append("|---|---|---|---|")
for k, v in list(genre_stats.items())[:20]:
    md.append(f"| {k} | {v['n']} | {v['median_views']:,} | {v['total_views']:,} |")

md.append("\n## 4. 开场钩子类型 × 播放量")
md.append("| 钩子类型 | n | 中位播放 | 总播放 |")
md.append("|---|---|---|---|")
for k, v in hook_stats.items():
    md.append(f"| {k} | {v['n']} | {v['median_views']:,} | {v['total_views']:,} |")
md.append(f"\n钩子出现速度: 中位 {hook_speed['median_sec']}s（P25={hook_speed['p25']}s / P75={hook_speed['p75']}s, n={hook_speed['n']}）")
md.append(f"关键反转时间: 前1/4 {reveal_timing['pct_first_quarter']} · 前半 {reveal_timing['pct_first_half']} · 后半 {reveal_timing['pct_last_half']}（n={reveal_timing['n']}）")

md.append("\n## 5. L1×L2 共现 Top20")
md.append("```")
for k in cooc: md.append(f"  {k}: {cooc[k]}")
md.append("```")

md.append("\n## 6. L2 题材 Top30")
md.append("```")
for k, c in l2c.most_common(30): md.append(f"  {k}: {c}")
md.append("```")

md.append("\n## 7. Emergent 题材（词表外自创，供词表迭代）")
md.append(f"- L1: {dict(em1.most_common(15))}")
md.append(f"- L2: {dict(em2.most_common(15))}")

md.append("\n## 8. 溯源就绪度（v3 输入完备率，仅翻译剧）")
md.append("| 语种 | 翻译剧n | 有distinctive_lines≥2 | 有角色名 |")
md.append("|---|---|---|---|")
for k, v in sorted(trace_ready.items(), key=lambda x: -x[1]["translated_n"]):
    md.append(f"| {k} | {v['translated_n']} | {v['with_lines']:.0%} | {v['with_named_chars']:.0%} |")

md.append("\n## 9. 合辑信号")
c = report["compilation"]
md.append(f"- 双信号(标题正则 OR 时长>1h): 合辑 {c['n']}/{len(rows)} ({c['ratio']:.0%})")
md.append(f"- 合辑中位播放 {c['median_views_comp']:,} vs 单剧 {c['median_views_single']:,}")
_miss = round((1 - qc_res["checks"]["meta_coverage"]) * 100, 1)
if _miss > 1:
    md.append(f"- ⚠️ 无title的条目（元数据缺失 {_miss}%）合辑判定只靠时长")

open(OUT / "full_report.md", "w", encoding="utf-8").write("\n".join(md))

print(f"rows={len(rows)} bad={bad} qc_pass={qc_res['gates']['pass']}")
print(f"outputs: full_normalized.jsonl / full_report.json / qc_report.json / full_report.md")
