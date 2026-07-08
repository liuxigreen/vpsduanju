#!/usr/bin/env python3
"""Report channel diagnosis results in a human-readable format."""
import json

OUTPUT_FILE = "output/channel_diagnosis_report_20260629.txt"

files = {
    "追劇姐妹 (hk/繁中)": "data/own/channel_diagnosis/追劇姐妹_latest.json",
    "Apocalyptic Films (en_global/en)": "data/own/channel_diagnosis/Apocalyptic_Films_latest.json",
    "DramaCipher (id/印尼)": "data/own/channel_diagnosis/DramaCipher_latest.json",
    "Luna Drama Estudio (es_latam/西语)": "data/own/channel_diagnosis/Luna_Drama_Estudio_latest.json",
    "DramaVerve (br/葡萄牙)": "data/own/channel_diagnosis/DramaVerve_latest.json",
    "Moonlit Drama Studio (en)": "data/own/channel_diagnosis/Moonlit_Drama_Studio_latest.json",
}

lines = []

def add(line=""):
    lines.append(line)

for name, path in files.items():
    try:
        with open(path) as f:
            data = json.load(f)
    except Exception as e:
        add(f"\n{'='*60}")
        add(f"📊 {name}")
        add(f"{'='*60}")
        add(f"  ❌ 读取失败: {e}")
        continue

    ch = data.get("channel", {})
    scored = data.get("video_scores", [])
    summary = data.get("summary", {})
    ch_llm = data.get("channel_llm", {})

    if scored:
        scores = [v.get("score", 0) for v in scored if v.get("score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        need_opt = sum(1 for v in scored if v.get("needs_optimization", False))
        total = len(scored)
    else:
        avg_score, need_opt, total = 0.0, 0, 0

    add(f"\n{'='*60}")
    add(f"📊 {name}")
    add(f"{'='*60}")
    add(f"  订阅: {ch.get('subscribers', '?')} | 总播放: {ch.get('total_views', 0):,} | 视频数: {ch.get('total_videos', '?')}")
    add(f"  均分: {avg_score:.1f}/10 | 需优化: {need_opt}/{total}")

    # Summary
    if summary:
        ds = summary.get("diagnosis_summary", summary.get("summary", ""))
        if ds:
            add(f"  诊断摘要: {ds[:300]}")
        ht = summary.get("health_trend", summary.get("health", ""))
        if ht:
            add(f"  健康趋势: {ht}")

    # Channel LLM (strategy)
    if ch_llm:
        hs = ch_llm.get("health_score") or ch_llm.get("overall_health") or ch_llm.get("score")
        grade = ch_llm.get("grade", "")
        grade_str = f" {grade}" if grade else ""
        if hs:
            add(f"  健康度: {hs}/10{grade_str}")
        else:
            # Can also be in summary
            pass

        # Strategy/recommendations
        strat = ch_llm.get("strategy") or ch_llm.get("recommendations") or ch_llm.get("suggestions") or ch_llm.get("strategic_advice")
        if isinstance(strat, list) and strat:
            add(f"  战略建议:")
            for s in strat[:5]:
                if isinstance(s, dict):
                    text = s.get("action") or s.get("title") or s.get("suggestion") or str(s)
                else:
                    text = str(s)
                add(f"    • {text[:150]}")
                if len(str(s)) > 150:
                    add(f"      ...(截断)")
        elif isinstance(strat, str) and len(strat) > 10:
            add(f"  战略: {strat[:300]}")

        # Issues/problems
        issues = ch_llm.get("issues") or ch_llm.get("problems") or ch_llm.get("weaknesses") or []
        if isinstance(issues, list) and issues:
            add(f"  问题:")
            for i in issues[:5]:
                if isinstance(i, dict):
                    text = i.get("issue") or i.get("title") or i.get("problem") or str(i)
                else:
                    text = str(i)
                add(f"    • {text[:150]}")

        # Strengths
        strengths = ch_llm.get("strengths") or ch_llm.get("advantages") or []
        if isinstance(strengths, list) and strengths:
            add(f"  优势:")
            for s in strengths[:3]:
                if isinstance(s, dict):
                    text = s.get("strength") or s.get("title") or str(s)
                else:
                    text = str(s)
                add(f"    ✔ {text[:150]}")

    # Top/bottom videos
    if scored:
        sorted_up = sorted(scored, key=lambda x: x.get("score", 0))
        sorted_down = sorted(scored, key=lambda x: x.get("score", 0), reverse=True)

        add(f"\n  最低分 (需优先优化):")
        for v in sorted_up[:3]:
            s = v.get("score", 0)
            views = v.get("views", 0)
            title = v.get("title", "")[:70]
            add(f"    [{s:.1f}] {views:>6}播放 | {title}")

        add(f"\n  最高分 (标杆):")
        for v in sorted_down[:3]:
            s = v.get("score", 0)
            views = v.get("views", 0)
            title = v.get("title", "")[:70]
            add(f"    [{s:.1f}] {views:>6}播放 | {title}")

    add(f"\n  诊断时间: {data.get('diagnosed_at', '?')}")

add(f"\n\n{'='*60}")
add(f"📈 频道综合排名 (按健康度/均分)")
add(f"{'='*60}")

# Build ranking data
rankings = []
for name, path in files.items():
    try:
        with open(path) as f:
            data = json.load(f)
        ch = data.get("channel", {})
        scored = data.get("video_scores", [])
        ch_llm = data.get("channel_llm", {})
        
        scores = [v.get("score", 0) for v in scored if v.get("score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0
        
        hs = ch_llm.get("health_score") or ch_llm.get("overall_health") or ch_llm.get("score") or 0
        grade = ch_llm.get("grade", "")
        
        subs = ch.get("subscribers", 0)
        views = ch.get("total_views", 0)
        
        rankings.append((name, avg_score, hs, grade, subs, views))
    except:
        rankings.append((name, 0, 0, "", 0, 0))

rankings.sort(key=lambda x: (x[2] or 0) if x[2] else x[1], reverse=True)

for i, (name, avg, hs, grade, subs, views) in enumerate(rankings):
    gs = f" {grade}" if grade else ""
    add(f"  {i+1}. {name}")
    add(f"     均分: {avg:.1f}/10 | 健康度: {hs}/10{gs} | 订阅: {subs} | 总播放: {views:,}")

result = "\n".join(lines)
print(result)

with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
    f.write(result)

print(f"\n\n✅ 报告已保存: {OUTPUT_FILE}")