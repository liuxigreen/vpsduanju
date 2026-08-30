#!/usr/bin/env python3
"""
竞品业务知识图谱构建 — 题材 × 语种 × 频道 × 钩子 四层关联网络

数据源: data/competitors_channels_all.json (content_tags/llm_stats/deep_analysis/tracking)
输出:   data/knowledge_graph.json (nodes/edges/matrix/genre_rank, schema_version 1.0)

节点: genre(题材) | language(语种) | channel(频道) | hook(钩子模式)
边:   channel -has_genre-> genre | channel -in_language-> language
      channel -uses_hook-> hook | genre -hot_in-> language (聚合边, weight=频道数)

用法: python3 scripts/competitor_knowledge_graph.py
"""
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PANEL_DATA = ROOT / "data" / "competitors_channels_all.json"
OUT_FILE = ROOT / "data" / "knowledge_graph.json"

TOP_CHANNELS_PER_GENRE = 12   # 每个题材保留的头部频道数
MIN_GENRE_CHANNELS = 2        # 题材至少出现在2个频道才算节点（过滤长尾噪声）
# 2026-08-30: 数据量不足的语种暂不进图谱/展示（市场未验证，等数据够再放开）
EXCLUDE_LANGS = {"德语", "泰语", "越南语", "韩语"}


def _momentum(ch):
    return (ch.get("tracking") or {}).get("video_momentum") or 0


def _subs_vel(ch):
    return (ch.get("tracking") or {}).get("subs_velocity_weekly") or 0


def build():
    data = json.loads(PANEL_DATA.read_text())
    channels = data.get("channels", [])

    genres = defaultdict(list)     # genre -> [channel]
    hooks = defaultdict(list)      # hook -> [channel]
    languages = defaultdict(list)  # lang -> [channel]
    cross = defaultdict(lambda: {"channels": 0, "momentum": 0})  # (genre, lang) -> agg

    for ch in channels:
        tags = [t.strip() for t in (ch.get("content_tags") or []) if t and t.strip()]
        if not tags:
            continue
        lang = (ch.get("language") or "未知").strip()
        if lang in EXCLUDE_LANGS:  # 数据量不足语种不进图（2026-08-30）
            continue
        languages[lang].append(ch)
        # 动量均摊: 频道挂N个题材, 每题材只计 1/N 动量 (消除多题材双计偏差)
        mom_share = round(_momentum(ch) / len(tags))
        for g in tags:
            genres[g].append(ch)
            cross[(g, lang)]["channels"] += 1
            cross[(g, lang)]["momentum"] += mom_share
        for h in ((ch.get("deep_analysis") or {}).get("hit_title_patterns") or []):
            h = h.strip()
            if h:
                hooks[h].append(ch)

    # ---- genre 节点 + 榜单 ----
    genre_nodes, genre_rank = [], []
    for g, chs in genres.items():
        if len(chs) < MIN_GENRE_CHANNELS:
            continue
        moms = [_momentum(c) for c in chs]
        svs = [_subs_vel(c) for c in chs]
        total_m, avg_m = sum(moms), round(sum(moms) / len(moms))
        lang_dist = defaultdict(int)
        for c in chs:
            lang_dist[(c.get("language") or "未知").strip()] += 1
        top_langs = sorted(lang_dist.items(), key=lambda x: -x[1])[:3]
        genre_nodes.append({
            "id": f"genre:{g}", "type": "genre", "label": g,
            "metrics": {
                "channels": len(chs), "momentum_total": total_m,
                "momentum_avg": avg_m, "subs_velocity_total": sum(svs),
                "momentum_nonzero": sum(1 for m in moms if m > 0),
                "top_languages": [l for l, _ in top_langs],
            },
        })
        genre_rank.append({
            "genre": g, "channels": len(chs), "momentum_total": total_m,
            "momentum_avg": avg_m, "subs_velocity_total": sum(svs),
            "top_languages": [l for l, _ in top_langs],
            "top_channels": [
                {"name": c.get("name"), "channel_id": c.get("channel_id"),
                 "url": c.get("url"), "language": c.get("language"),
                 "subscribers": c.get("subscribers"),
                 "momentum": _momentum(c), "subs_velocity": _subs_vel(c)}
                for c in sorted(chs, key=_momentum, reverse=True)[:TOP_CHANNELS_PER_GENRE]
            ],
        })
    genre_rank.sort(key=lambda x: -x["momentum_total"])

    # ---- language 节点 ----
    lang_nodes = []
    for lang, chs in languages.items():
        lang_nodes.append({
            "id": f"language:{lang}", "type": "language", "label": lang,
            "metrics": {"channels": len(chs),
                        "momentum_total": sum(_momentum(c) for c in chs)},
        })

    # ---- hook 节点 ----
    hook_nodes = []
    for h, chs in hooks.items():
        if len(chs) < MIN_GENRE_CHANNELS:
            continue
        hook_nodes.append({
            "id": f"hook:{h}", "type": "hook", "label": h,
            "metrics": {"channels": len(chs),
                        "momentum_total": sum(_momentum(c) for c in chs)},
        })
    hook_nodes.sort(key=lambda n: -n["metrics"]["channels"])

    # ---- channel 节点 + 边 ----
    channel_nodes, edges = [], []
    for ch in channels:
        tags = [t.strip() for t in (ch.get("content_tags") or []) if t and t.strip()]
        if not tags:
            continue
        cid = ch.get("channel_id")
        lang = (ch.get("language") or "未知").strip()
        if lang in EXCLUDE_LANGS:  # 与语种节点同步过滤（2026-08-30）
            continue
        mom = _momentum(ch)
        channel_nodes.append({
            "id": f"channel:{cid}", "type": "channel",
            "label": ch.get("name") or cid,
            "metrics": {"language": lang, "subscribers": ch.get("subscribers"),
                        "momentum": mom, "subs_velocity": _subs_vel(ch),
                        "genres": tags},
        })
        for g in tags:
            if f"genre:{g}" not in {n["id"] for n in genre_nodes}:
                continue
            edges.append({"source": f"channel:{cid}", "target": f"genre:{g}",
                          "type": "has_genre", "weight": mom})
        edges.append({"source": f"channel:{cid}", "target": f"language:{lang}",
                      "type": "in_language", "weight": 1})
        for h in ((ch.get("deep_analysis") or {}).get("hit_title_patterns") or []):
            h = h.strip()
            if h and f"hook:{h}" in {n["id"] for n in hook_nodes}:
                edges.append({"source": f"channel:{cid}", "target": f"hook:{h}",
                              "type": "uses_hook", "weight": 1})
    # 聚合边 genre -hot_in-> language
    genre_ids = {n["id"] for n in genre_nodes}
    for (g, lang), agg in cross.items():
        if f"genre:{g}" in genre_ids:
            edges.append({"source": f"genre:{g}", "target": f"language:{lang}",
                          "type": "hot_in", "weight": agg["channels"],
                          "momentum": agg["momentum"]})

    # ---- 题材×语种 矩阵 ----    langs sorted by channel count desc
    lang_order = [l for l, _ in sorted(languages.items(), key=lambda x: -len(x[1]))]
    genre_order = [r["genre"] for r in genre_rank]
    matrix = {
        "genres": genre_order, "languages": lang_order,
        "cells": [[g, l, cross[(g, l)]["channels"], cross[(g, l)]["momentum"]]
                  for g in genre_order for l in lang_order if (g, l) in cross],
    }

    out = {
        "schema_version": "1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "stats": {
            "channels": len(channel_nodes), "genres": len(genre_nodes),
            "languages": len(lang_nodes), "hooks": len(hook_nodes),
            "edges": len(edges),
        },
        "nodes": {"genres": genre_nodes, "languages": lang_nodes,
                  "hooks": hook_nodes, "channels": channel_nodes},
        "edges": edges,
        "genre_rank": genre_rank,
        "matrix": matrix,
    }
    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"✅ 知识图谱已生成: {OUT_FILE.name}")
    print(f"   频道 {len(channel_nodes)} | 题材 {len(genre_nodes)} | 语种 {len(lang_nodes)} | 钩子 {len(hook_nodes)} | 边 {len(edges)}")
    print("\n🔥 题材动量榜 Top10:")
    for i, r in enumerate(genre_rank[:10], 1):
        print(f"  {i}. {r['genre']:8s} {r['channels']:3d}频道 动量合计{r['momentum_total']:>8,}/天 "
              f"均{r['momentum_avg']:>7,} 主语种:{','.join(r['top_languages'])}")
    return 0


if __name__ == "__main__":
    sys.exit(build())
