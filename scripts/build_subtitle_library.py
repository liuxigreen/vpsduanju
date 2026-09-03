#!/usr/bin/env python3
"""build_subtitle_library — 内容库索引构建（确定性，无LLM）

输入: data/subtitle_analysis/full_normalized.jsonl （v2聚合产物, ~4481条）
输出:
  data/subtitle_analysis/library_index.json    列表索引（每条~300B，供分页/过滤）
  data/subtitle_analysis/library_details.json  详情库（完整 analysis，按 video_id 索引）

面板消费: /api/subtitle-library（过滤分页走索引）、/api/subtitle-detail（查详情库）。
内存预算: index ~1.5MB + details ~15MB，cached_json_read 常驻可接受。
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/subtitle_analysis/full_normalized.jsonl"
OUT_INDEX = ROOT / "data/subtitle_analysis/library_index.json"
OUT_DETAILS = ROOT / "data/subtitle_analysis/library_details.json"


def model_family(m):
    m = (m or "").lower()
    for k in ("claude", "zai", "glm", "qwen", "deepseek", "gpt", "minimax"):
        if k in m:
            return k
    return "other"


def build():
    index, details = [], {}
    for line in open(SRC, encoding="utf-8"):
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
        vid = d.get("video_id") or ""
        if not vid or vid in details:
            continue
        hook = a.get("opening_hook") or {}
        origin = a.get("origin_signals") or {}
        l1 = [g for g in a.get("genre_l1", []) if isinstance(g, str)]
        l2 = [g for g in a.get("genre_l2", []) if isinstance(g, str)]
        views = d.get("views") or 0
        dur = d.get("duration_sec") or 0
        index.append({
            "video_id": vid,
            "title": (d.get("title") or "")[:80],
            "channel": (d.get("channel") or "")[:40],
            "language": d.get("language") or "",
            "lang_code": d.get("lang_code") or "",
            "views": views,
            "duration_min": round(dur / 60) if dur else None,
            "tier": d.get("tier") or "",
            "model_family": d.get("model_family") or model_family(d.get("model")),
            "l1": l1[:4],
            "l2": l2[:4],
            "hook": hook.get("type") if isinstance(hook.get("type"), str) else None,
            "hook_sec": hook.get("appears_at_sec") if isinstance(hook.get("appears_at_sec"), (int, float)) else None,
            "translated": bool(origin.get("feels_translated")),
            "confidence": a.get("confidence"),
            "is_compilation": bool(d.get("is_compilation")),
        })
        details[vid] = {
            "video_id": vid,
            "title": d.get("title") or "",
            "channel": d.get("channel") or "",
            "language": d.get("language") or "",
            "lang_code": d.get("lang_code") or "",
            "views": views,
            "duration_sec": dur or None,
            "tier": d.get("tier") or "",
            "model_family": d.get("model_family") or model_family(d.get("model")),
            "synopsis": (a.get("synopsis") or "").strip(),
            "l1": l1,
            "l2": l2,
            "hook": {"type": hook.get("type"), "event": hook.get("event"),
                     "sec": hook.get("appears_at_sec") if isinstance(hook.get("appears_at_sec"), (int, float)) else None},
            "key_reveals": [{"event": (k or {}).get("event"), "at_sec": (k or {}).get("at_sec")}
                            for k in (a.get("key_reveals") or []) if isinstance(k, dict)],
            "characters": [{"name": (c or {}).get("name"), "role": (c or {}).get("role")}
                           for c in (a.get("characters") or []) if isinstance(c, dict) and c.get("name")][:8],
            "distinctive_lines": [x for x in (a.get("distinctive_lines") or []) if isinstance(x, str)][:6],
            "evidence": a.get("evidence") or {},
            "translated": bool(origin.get("feels_translated")),
            "origin_reason": (origin.get("reason") or "").strip(),
            "confidence": a.get("confidence"),
        }
    index.sort(key=lambda x: -(x["views"] or 0))
    OUT_INDEX.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
    OUT_DETAILS.write_text(json.dumps(details, ensure_ascii=False), encoding="utf-8")
    print(f"index={len(index)} details={len(details)}")
    print(f"  -> {OUT_INDEX.name} {OUT_INDEX.stat().st_size // 1024}KB, "
          f"{OUT_DETAILS.name} {OUT_DETAILS.stat().st_size // 1024 // 1024}MB")


if __name__ == "__main__":
    build()
