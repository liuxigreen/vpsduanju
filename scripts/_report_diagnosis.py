#!/usr/bin/env python3
"""Extract diagnosis results from all channel diagnosis files."""
import json

files = {
    "追劇姐妹 (hk/繁中)": "data/own/channel_diagnosis/追劇姐妹_latest.json",
    "Apocalyptic Films (en_global/en)": "data/own/channel_diagnosis/Apocalyptic_Films_latest.json",
    "DramaCipher (id/印尼)": "data/own/channel_diagnosis/DramaCipher_latest.json",
    "Luna Drama Estudio (es_latam/西语)": "data/own/channel_diagnosis/Luna_Drama_Estudio_latest.json",
    "DramaVerve (br/葡萄牙)": "data/own/channel_diagnosis/DramaVerve_latest.json",
    "Moonlit Drama Studio (en)": "data/own/channel_diagnosis/Moonlit_Drama_Studio_latest.json",
}

report = {}
for name, path in files.items():
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        report[name] = {"error": str(e)}
        continue

    ch = data.get("channel", {})
    # Inspect actual top keys to find scored videos
    top_keys = [k for k in data.keys()]
    scored = data.get("scored_videos", data.get("videos", []))
    if not scored or not isinstance(scored, list):
        for k in top_keys:
            v = data[k]
            if isinstance(v, list) and len(v) > 0:
                if isinstance(v[0], dict) and "score" in v[0]:
                    scored = v
                    break
    print(f"  [{name}] keys={top_keys} scored={len(scored) if scored else 0}", file=__import__('sys').stderr)

    if scored:
        scores = [v.get("score", 0) for v in scored if v.get("score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        need_opt = sum(1 for v in scored if v.get("needs_optimization", False))
        total = len(scored)
    else:
        avg_score, need_opt, total = 0.0, 0, 0

    strategy = data.get("strategy", {})
    health = None
    grade = ""
    if strategy:
        health = strategy.get("health_score") or strategy.get("overall_health")
        grade = strategy.get("grade", "")

    issues = data.get("channel_issues", data.get("issues", []))

    # Top/bottom 3
    low3 = []
    high3 = []
    if scored:
        sorted_up = sorted(scored, key=lambda x: x.get("score", 0))
        sorted_down = sorted(scored, key=lambda x: x.get("score", 0), reverse=True)
        low3 = [{"score": round(v.get("score", 0), 1), "views": v.get("views", 0), "title": v.get("title", "")[:50]} for v in sorted_up[:3]]
        high3 = [{"score": round(v.get("score", 0), 1), "views": v.get("views", 0), "title": v.get("title", "")[:50]} for v in sorted_down[:3]]

    # Also get summary and channel_llm (strategy) data
    summary = data.get("summary", {})
    ch_llm = data.get("channel_llm", {})

    report[name] = {
        "subscribers": ch.get("subscribers", "?"),
        "total_views": ch.get("total_views", 0),
        "total_videos": ch.get("total_videos", "?"),
        "avg_score": round(avg_score, 1),
        "need_optimization": need_opt,
        "total_scored": total,
        "summary": summary,
        "channel_llm": ch_llm,
        "health": health,
        "grade": grade,
        "issues": [i.get("issue", i.get("title", str(i))) if isinstance(i, dict) else str(i) for i in issues[:5]],
        "lowest_3": low3,
        "highest_3": high3,
        "diagnosed_at": data.get("diagnosed_at", "")
    }

print(json.dumps(report, ensure_ascii=False, indent=2))