#!/usr/bin/env python3
"""select_alert_batch — 增量批选片（跑字幕分析的队列）

口径：爆款预警 ∪ 24h增量热榜TopN，剔除已在内容库的视频，按24h增量降序，默认日批30条。
输出: data/alert_sub_batch/manifest_{date}.json
      {date, items:[{video_id,title,channel,language,views,delta_24h,source,alert_types}]}
用法: python3 scripts/select_alert_batch.py [--top 100] [--limit 30] [--out 路径]
"""
import json
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALERTS = ROOT / "data/alerts_latest.json"
LIB_INDEX = ROOT / "data/subtitle_analysis/library_index.json"
OUT_DIR = ROOT / "data/alert_sub_batch"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=100, help="热榜取前N")
    ap.add_argument("--limit", type=int, default=30, help="日批上限")
    ap.add_argument("--out", default="", help="输出路径覆盖")
    args = ap.parse_args()

    d = json.load(open(ALERTS, encoding="utf-8"))
    lib = {}
    if LIB_INDEX.exists():
        for x in json.load(open(LIB_INDEX, encoding="utf-8")):
            lib[x.get("video_id")] = True

    pool = {}
    for a in d.get("alerts") or []:
        vid = a.get("video_id")
        if not vid or vid in pool:
            continue
        pool[vid] = {
            "video_id": vid, "title": a.get("title", ""), "channel": a.get("channel", ""),
            "language": a.get("language", ""), "views": a.get("views", 0),
            "delta_24h": a.get("delta_24h", 0),
            "source": "alert", "alert_types": a.get("alert_types") or [],
        }
    for r in (d.get("ranking") or [])[: args.top]:
        vid = r.get("video_id")
        if not vid or vid in pool:
            continue
        pool[vid] = {
            "video_id": vid, "title": r.get("title", ""), "channel": r.get("channel", ""),
            "language": r.get("language", ""), "views": r.get("views", 0),
            "delta_24h": r.get("delta_24h", 0), "source": "ranking", "alert_types": [],
        }

    fresh = [x for x in pool.values() if x["video_id"] not in lib]
    fresh.sort(key=lambda x: -x["delta_24h"])
    batch = fresh[: args.limit]

    from datetime import datetime
    date = datetime.now().strftime("%Y-%m-%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = Path(args.out) if args.out else OUT_DIR / f"manifest_{date}.json"
    out.write_text(json.dumps({
        "date": date, "count": len(batch),
        "pool_total": len(pool), "already_in_library": len(pool) - len(fresh),
        "items": batch,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"池 {len(pool)}（预警∪热榜Top{args.top}）| 已在库剔除 {len(pool) - len(fresh)} | "
          f"本批 {len(batch)} 条 → {out}")


if __name__ == "__main__":
    main()
