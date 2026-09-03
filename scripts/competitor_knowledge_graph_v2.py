#!/usr/bin/env python3
"""
竞品知识图谱 v2 沙箱重建 — 字幕内容实证为主轴

对比 v1 (competitor_knowledge_graph.py):
  - 题材轴: 频道content_tags(标题推断,30值含过泛词) → 字幕L1归并主轴(genre_vocab_map v1.1 规则)
  - 钩子轴: hit_title_patterns(实为题材堆叠) → 字幕8类真钩子(opening_hook.type)
  - 每个 genre/language/channel 节点新增 subtitle_* 实证字段(n/中位播放/翻译率/证据边)
  - 无字幕证据的频道: 题材边回退 channel_tag_to_l1 映射, 打 inferred 角标(前端可显示⚠️)

输出: data/knowledge_graph.json (schema_version 2.0)；--out 可指定沙箱文件
输入: data/subtitle_analysis/full_normalized.jsonl + data/competitors_channels_all.json
      + data/subtitle_analysis/genre_vocab_map.json (v1.1, 归并规则零硬编码)

用法: python3 scripts/competitor_knowledge_graph_v2.py [--out PATH]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUBS_FILE = ROOT / "data" / "subtitle_analysis" / "full_normalized.jsonl"
PANEL_DATA = ROOT / "data" / "competitors_channels_all.json"
VOCAB_FILE = ROOT / "data" / "subtitle_analysis" / "genre_vocab_map.json"
OUT_FILE = ROOT / "data" / "knowledge_graph.json"  # 现网产物；沙箱对比用 --out 覆盖

MIN_SUBTITLE_N = 20          # 题材节点最少实证视频数（不足并入观察，不进图）
TOP_GENRES_PER_CHANNEL = 5   # 每频道从字幕取前N题材
GENRE_MIN_SHARE = 0.15       # 题材需占该频道实证视频的比例阈值
EXCLUDE_LANGS = {"德语", "泰语", "越南语", "韩语"}  # 与v1一致：数据量不足语种不进图


# ── 词表归并（规则来自 genre_vocab_map.json，代码零硬编码）──
def load_vocab():
    v = json.load(open(VOCAB_FILE, encoding="utf-8"))
    assert v.get("l1_rules"), "词表缺 l1_rules，先升级 genre_vocab_map.json"
    return v


def make_normalizer(vocab):
    t2s = str.maketrans(vocab.get("t2s", {}))
    rules = [(r["pattern"], r["target"]) for r in vocab["l1_rules"]]

    def norm(g: str) -> str:
        g = (g or "").strip().translate(t2s)
        for pat, tgt in rules:
            if pat in g:
                return tgt
        return g  # 未命中：原样返回，由阈值过滤长尾
    return norm


# ── 字幕实证装配 ──
def load_subtitle_rows(norm):
    rows = []
    for line in open(SUBS_FILE, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        a = d.get("analysis") or {}
        if not a.get("genre_l1"):
            continue
        l1 = [norm(g) for g in a["genre_l1"] if isinstance(g, str)]
        l2 = [g.strip() for g in (a.get("genre_l2") or []) if isinstance(g, str) and g.strip()]
        hook = (a.get("opening_hook") or {}).get("type")
        hook_sec = (a.get("opening_hook") or {}).get("appears_at_sec")
        rows.append({
            "video_id": d.get("video_id"),
            "channel": (d.get("channel") or "").strip(),
            "language": d.get("language") or "未知",
            "views": d.get("views") or 0,
            "l1": [g for g in l1 if g],
            "l2": l2[:6],
            "hook": hook if isinstance(hook, str) else None,
            "hook_sec": hook_sec if isinstance(hook_sec, (int, float)) else None,
            "translated": bool((a.get("origin_signals") or {}).get("feels_translated")),
            "cliff": bool(a.get("ending_cliffhanger")),
            "title": (d.get("title") or "").strip(),
            "synopsis": (a.get("synopsis") or "").strip(),
            "hook_event": ((a.get("opening_hook") or {}).get("event") or "").strip(),
            "payoffs": [p if isinstance(p, str) else (p.get("type") or p.get("name") or "")
                        for p in (a.get("payoffs") or []) if isinstance(p, (str, dict))],
        })
    return rows


def make_mainliner(vocab):
    """主线四分类（感情/家庭/个人/职场），规则来自词表 mainline_rules，零硬编码。
    按 感情>家庭>个人>职场 优先序取首个命中（关键词出现在 synopsis+hook事件+payoffs 拼接文本中）。"""
    rules = vocab.get("mainline_rules") or {}
    order = ["感情", "家庭", "个人", "职场"]  # 短剧语境：家庭词常为感情线背景，个人成长优先于职场标签

    def mainline(r) -> str:
        text = r["synopsis"] + r["hook_event"] + " ".join(r["payoffs"])
        for k in order:
            if any(w in text for w in rules.get(k, [])):
                return k
        return "其他"
    return mainline


def _med(xs):
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return round(xs[m] if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2)


def _momentum(ch):
    return (ch.get("tracking") or {}).get("video_momentum") or 0


def _subs_vel(ch):
    return (ch.get("tracking") or {}).get("subs_velocity_weekly") or 0


def build(out_file: Path = OUT_FILE):
    vocab = load_vocab()
    norm = make_normalizer(vocab)
    mainline = make_mainliner(vocab)
    axis_map = vocab.get("axis_map", {})
    sub_rows = load_subtitle_rows(norm)
    for r in sub_rows:
        r["mainline"] = mainline(r)

    channels = json.loads(PANEL_DATA.read_text(encoding="utf-8")).get("channels", [])
    ch_by_name = {}
    for c in channels:
        n = (c.get("name") or "").strip()
        if n:
            ch_by_name.setdefault(n, c)  # 同名取首个

    # ---- 频道级字幕聚合 ----
    by_channel = defaultdict(list)
    for r in sub_rows:
        if r["channel"]:
            by_channel[r["channel"]].append(r)

    # ---- 字幕层 genre / hook / language 统计 ----
    g_stat = defaultdict(lambda: {"n": 0, "views": [], "langs": Counter(), "chs": set(),
                                  "hooks": Counter(), "mainlines": Counter(), "vids": [],
                                  "subs": defaultdict(lambda: {"n": 0, "views": []})})
    h_stat = defaultdict(lambda: {"n": 0, "views": [], "langs": Counter(), "chs": set(), "secs": []})
    l_stat = defaultdict(lambda: {"n": 0, "views": [], "trans": 0, "cliff": 0, "chs": set(), "genres": Counter()})
    for r in sub_rows:
        if r["language"] in EXCLUDE_LANGS:
            continue
        for g in set(r["l1"]):
            s = g_stat[g]
            s["n"] += 1
            s["views"].append(r["views"])
            s["langs"][r["language"]] += 1
            s["chs"].add(r["channel"])
            s["mainlines"][r["mainline"]] += 1
            s["vids"].append(r)
            for l2g in set(r.get("l2") or []):
                s["subs"][l2g]["n"] += 1
                s["subs"][l2g]["views"].append(r["views"])
            if r["hook"]:
                s["hooks"][r["hook"]] += 1
        if r["hook"]:
            hs = h_stat[r["hook"]]
            hs["n"] += 1
            hs["views"].append(r["views"])
            hs["langs"][r["language"]] += 1
            hs["chs"].add(r["channel"])
            if r.get("hook_sec") is not None:
                hs["secs"].append(r["hook_sec"])
        ls = l_stat[r["language"]]
        ls["n"] += 1
        ls["views"].append(r["views"])
        ls["trans"] += int(r["translated"])
        ls["cliff"] += int(r["cliff"])
        ls["chs"].add(r["channel"])
        for g in set(r["l1"]):
            ls["genres"][g] += 1

    # 题材节点阈值
    kept = {g for g, s in g_stat.items() if s["n"] >= MIN_SUBTITLE_N}
    merged_away = {g: s["n"] for g, s in g_stat.items() if g not in kept}

    # ---- genre 节点（字幕主轴 + 频道动量侧写）----
    genre_nodes, genre_rank = [], []
    for g, s in sorted(g_stat.items(), key=lambda kv: -kv[1]["n"]):
        if g not in kept:
            continue
        # 动量侧写：挂了该题材的证据频道（或推断频道）的动量
        mom_total = mom_avg = sv_total = 0
        mom_chs = []
        for cname in s["chs"]:
            c = ch_by_name.get(cname)
            if c:
                mom_total += _momentum(c)
                sv_total += _subs_vel(c)
                mom_chs.append((c, _momentum(c)))
        n_ch = len(mom_chs) or 1
        genre_nodes.append({
            "id": f"genre:{g}", "type": "genre", "label": g,
            "metrics": {
                "channels": len(s["chs"]), "momentum_total": mom_total,
                "momentum_avg": round(mom_total / n_ch), "subs_velocity_total": sv_total,
                "top_languages": [l for l, _ in s["langs"].most_common(3)],
                "subtitle_n": s["n"], "median_views": _med(s["views"]),
                "top_hooks": [h for h, _ in s["hooks"].most_common(3)],
                "axis": axis_map.get(g, "母题"),
                "mainlines": dict(s["mainlines"].most_common()),
                "evidence": "subtitle",
            },
        })
        top_vids = sorted(s["vids"], key=lambda r: -(r["views"] or 0))[:5]
        # L2 亚型：出现≥2次的剧情模式，按频次排序，带中位播放
        subtypes = [
            {"name": k, "n": v["n"], "median_views": _med(v["views"])}
            for k, v in sorted(s["subs"].items(), key=lambda kv: -kv[1]["n"])
            if v["n"] >= 2
        ][:8]
        genre_rank.append({
            "genre": g, "channels": len(s["chs"]), "momentum_total": mom_total,
            "momentum_avg": round(mom_total / n_ch), "subs_velocity_total": sv_total,
            "top_languages": [l for l, _ in s["langs"].most_common(3)],
            "subtitle_n": s["n"], "median_views": _med(s["views"]),
            "axis": axis_map.get(g, "母题"),
            "mainlines": dict(s["mainlines"].most_common()),
            "subtypes": subtypes,
            "top_videos": [
                {"title": v["title"][:80], "channel": v["channel"], "language": v["language"],
                 "views": v["views"], "hook": v["hook"], "mainline": v["mainline"],
                 "synopsis": v["synopsis"][:120]}
                for v in top_vids
            ],
            "top_channels": [
                {"name": c.get("name"), "channel_id": c.get("channel_id"), "url": c.get("url"),
                 "language": c.get("language"), "subscribers": c.get("subscribers"),
                 "momentum": m, "subs_velocity": _subs_vel(c)}
                for c, m in sorted(mom_chs, key=lambda x: -x[1])[:12]
            ],
        })

    # ---- hook 节点（字幕8类）----
    hook_nodes = []
    for h, s in sorted(h_stat.items(), key=lambda kv: -kv[1]["n"]):
        if s["n"] < MIN_SUBTITLE_N:
            continue
        secs = sorted(x for x in s["secs"] if x is not None)
        hook_nodes.append({
            "id": f"hook:{h}", "type": "hook", "label": h,
            "metrics": {"channels": len(s["chs"]), "subtitle_n": s["n"],
                        "median_views": _med(s["views"]),
                        "top_languages": [l for l, _ in s["langs"].most_common(3)],
                        "sec_p25": secs[len(secs) // 4] if secs else None,
                        "sec_median": secs[len(secs) // 2] if secs else None,
                        "sec_p75": secs[min(len(secs) * 3 // 4, len(secs) - 1)] if secs else None},
        })
    hook_ids = {n["id"] for n in hook_nodes}

    # ---- language 节点 ----
    lang_nodes = []
    for l, s in sorted(l_stat.items(), key=lambda kv: -kv[1]["n"]):
        mom_total = sum(_momentum(ch_by_name[c]) for c in s["chs"] if c in ch_by_name)
        lang_nodes.append({
            "id": f"language:{l}", "type": "language", "label": l,
            "metrics": {"channels": len(s["chs"]), "momentum_total": mom_total,
                        "subtitle_n": s["n"], "median_views": _med(s["views"]),
                        "translated_ratio": round(s["trans"] / s["n"], 2) if s["n"] else None,
                        "cliffhanger_ratio": round(s["cliff"] / s["n"], 2) if s["n"] else None,
                        "top_genres": [g for g, _ in s["genres"].most_common(6) if g in kept]},
        })

    # ---- channel 节点 + 边 ----
    # 证据频道: 字幕题材(占比阈值内)；无证据频道: content_tags 经 channel_tag_to_l1 映射(inferred)
    tag2l1 = vocab.get("channel_tag_to_l1", {})
    drop_tags = set(vocab.get("drop", []))
    channel_nodes, edges = [], []
    genre_ids = {n["id"] for n in genre_nodes}
    n_evidenced = 0
    for ch in channels:
        name = (ch.get("name") or "").strip()
        lang = (ch.get("language") or "未知").strip()
        if lang in EXCLUDE_LANGS:
            continue
        cid = ch.get("channel_id")
        mom = _momentum(ch)
        rows = by_channel.get(name, [])
        if rows:
            n_evidenced += 1
            cnt = Counter(g for r in rows for g in set(r["l1"]))
            hooks_c = Counter(r["hook"] for r in rows if r["hook"])
            share = [(g, k) for g, k in cnt.most_common() if k / len(rows) >= GENRE_MIN_SHARE]
            gs = [g for g, _ in share[:TOP_GENRES_PER_CHANNEL]]
            hs = [h for h, _ in hooks_c.most_common(3)]
            src = "subtitle"
        else:
            gs, hs = [], []
            for t in (ch.get("content_tags") or []):
                t = (t or "").strip()
                if not t or t in drop_tags:
                    continue
                m = tag2l1.get(t, norm(t))
                if m:
                    gs.append(m)
            src = "inferred"
        channel_nodes.append({
            "id": f"channel:{cid}", "type": "channel", "label": name or cid,
            "metrics": {"language": lang, "subscribers": ch.get("subscribers"),
                        "momentum": mom, "subs_velocity": _subs_vel(ch),
                        "genres": [g for g in gs if g in genre_ids],  # 只挂命中主轴的；未命中留空(前端显示—)
                        "subtitle_n": len(rows), "genre_source": src},
        })
        for g in gs:
            if f"genre:{g}" in genre_ids:
                edges.append({"source": f"channel:{cid}", "target": f"genre:{g}",
                              "type": "has_genre", "weight": mom, "evidence": src})
        edges.append({"source": f"channel:{cid}", "target": f"language:{lang}",
                      "type": "in_language", "weight": 1})
        for h in hs:
            if f"hook:{h}" in hook_ids:
                edges.append({"source": f"channel:{cid}", "target": f"hook:{h}",
                              "type": "uses_hook", "weight": 1, "evidence": "subtitle"})

    # ---- 聚合边 genre -hot_in-> language（weight=实证视频数）----
    for g, s in g_stat.items():
        if g not in kept:
            continue
        for l, n in s["langs"].items():
            if l in EXCLUDE_LANGS:
                continue
            edges.append({"source": f"genre:{g}", "target": f"language:{l}",
                          "type": "hot_in", "weight": n, "evidence": "subtitle"})

    # ---- 矩阵（cell = [实证视频数, 中位播放]，前端 v2 换 tooltip）----
    lang_order = [n["label"] for n in lang_nodes]
    genre_order = [r["genre"] for r in genre_rank]
    cells = []
    for g in genre_order:
        for l in lang_order:
            n = g_stat[g]["langs"].get(l, 0)
            if n:
                sel = [r for r in g_stat[g]["vids"] if r["language"] == l]
                vs = [r["views"] for r in sel]
                ml = Counter(r["mainline"] for r in sel).most_common(1)
                cells.append([g, l, n, _med(vs), ml[0][0] if ml else "其他"])
    matrix = {"genres": genre_order, "languages": lang_order, "cells": cells}

    out = {
        "schema_version": "2.2",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": {"subtitle_rows": len(sub_rows), "vocab_version": vocab.get("version"),
                   "merged_away_genres": dict(sorted(merged_away.items(), key=lambda x: -x[1])[:20])},
        "stats": {"channels": len(channel_nodes), "genres": len(genre_nodes),
                  "languages": len(lang_nodes), "hooks": len(hook_nodes),
                  "edges": len(edges), "evidenced_channels": n_evidenced},
        "nodes": {"genres": genre_nodes, "languages": lang_nodes,
                  "hooks": hook_nodes, "channels": channel_nodes},
        "edges": edges,
        "genre_rank": genre_rank,
        "matrix": matrix,
    }
    out_file.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 图谱v2已生成: {out_file.name}")
    print(f"   频道 {len(channel_nodes)}(实证{n_evidenced}) | 题材 {len(genre_nodes)} | "
          f"语种 {len(lang_nodes)} | 钩子 {len(hook_nodes)} | 边 {len(edges)}")
    print(f"   长尾题材被阈值过滤: {len(merged_away)} 值")
    print("\n🔥 题材榜 Top12（按实证视频数）:")
    for i, r in enumerate(genre_rank[:12], 1):
        print(f"  {i:2d}. {r['genre']:6s} 实证{r['subtitle_n']:>4}条 中位播放{r['median_views']:>8,} "
              f"{r['channels']:3d}频道 动量均{r['momentum_avg']:>7,} 主语种:{','.join(r['top_languages'])}")
    print("\n🪝 钩子榜（字幕8类）:")
    for n in hook_nodes:
        m = n["metrics"]
        print(f"  {n['label']:6s} n={m['subtitle_n']:>4} 中位播放{m['median_views']:>8,} 主语种:{','.join(m['top_languages'])}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_FILE), help="输出路径（默认覆盖现网 knowledge_graph.json）")
    args = ap.parse_args()
    sys.exit(build(Path(args.out)))
