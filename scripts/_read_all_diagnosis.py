#!/usr/bin/env python3
"""Read all channel diagnosis latest files and summarize key metrics."""
import json
from pathlib import Path

ROOT = Path("/home/ubuntu/duanju")
DIAG_DIR = ROOT / "data" / "own" / "channel_diagnosis"

for f in sorted(DIAG_DIR.glob("*_latest.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    name = d.get("channel_name", f.stem.replace("_latest",""))
    summary = d.get("summary", {})
    channel = d.get("channel", {})
    channel_llm = d.get("channel_llm", {})
    videos = d.get("video_scores", [])
    skipped = d.get("skipped", [])
    retention = d.get("retention_data")
    
    # Top issues from channel_llm
    top_issues = channel_llm.get("issues", summary.get("top_issues", []))
    bottleneck = channel_llm.get("bottleneck", "")
    health_score = channel_llm.get("health_score", summary.get("avg_score", 0))
    
    # Per-video issues summary
    heavy_issues = [v for v in videos if v.get("needs_optimization", False)]
    cover_issues = [v for v in videos if v.get("cover_synergy", {}).get("anti_patterns", [])]
    
    # Quadrant distribution
    quadrants = {}
    for v in videos:
        q = v.get("quadrant", "未分类")
        quadrants[q] = quadrants.get(q, 0) + 1
    
    # AGGREGATE: title pattern analysis
    title_agg = d.get("title_aggregation", {})
    cover_agg = d.get("cover_aggregation", {})
    
    print(f"\n{'='*70}")
    print(f"📺 {name}")
    print(f"{'='*70}")
    print(f"  均分: {summary.get('avg_score', 'N/A')}/10")
    print(f"  Total videos diagnosed: {summary.get('total_videos', len(videos))}")
    print(f"  需优化: {heavy_issues and len(heavy_issues) or summary.get('needs_optimization', 0)} 条")
    print(f"  订阅: {channel.get('subscribers', 'N/A')} | 总播放: {channel.get('total_views', 'N/A')}")
    print(f"  加权赞率: {summary.get('avg_like_rate', 'N/A')}%")
    
    # Quadrant
    if quadrants:
        print(f"  象限分布: {json.dumps(quadrants, ensure_ascii=False)}")
    
    # Retention
    if retention and retention.get("has_data"):
        print(f"  留存: 1%处={retention.get('avg_retention_1pct', 'N/A')} | 3min={retention.get('avg_retention_3min', 'N/A')} | 5min={retention.get('avg_retention_5min', 'N/A')}")
    
    # Title aggregation
    if title_agg:
        sd = title_agg.get("skeleton_distribution", {})
        md = title_agg.get("mode_distribution", {})
        print(f"  骨架分布: {json.dumps(sd, ensure_ascii=False)}")
        print(f"  Mode分布: {json.dumps(md, ensure_ascii=False)}")
        print(f"  钩子命中率: {title_agg.get('hook_hit_rate', 'N/A')}")
        print(f"  多骨架率: {title_agg.get('multi_skeleton_rate', 'N/A')}")
        print(f"  低效组合率: {title_agg.get('inefficient_pairing_rate', 'N/A')}")
        ctr = title_agg.get("contrarian", {})
        if ctr:
            print(f"  反惯例占比: {ctr.get('ratio', 'N/A')} | 均分: {ctr.get('avg_score', 'N/A')}")
    
    # Cover aggregation
    if cover_agg:
        print(f"  封面: 人物={cover_agg.get('avg_figure','N/A')} 情绪={cover_agg.get('avg_emotion','N/A')} 道具={cover_agg.get('avg_props','N/A')} 文字={cover_agg.get('avg_text','N/A')} 协同={cover_agg.get('avg_synergy','N/A')}")
        print(f"  反模式率: {cover_agg.get('anti_pattern_rate', 'N/A')}")
    
    # Issues
    if top_issues:
        print(f"  ⚠️ Issues ({len(top_issues)}条):")
        for i, issue in enumerate(top_issues[:5], 1):
            if isinstance(issue, dict):
                print(f"    {i}. [{issue.get('severity','info')}] {issue.get('issue', issue.get('category',''))}")
                if issue.get('action'):
                    print(f"       动作: {issue.get('action')}")
            else:
                print(f"    {i}. {issue}")
    
    # Bottleneck
    if bottleneck:
        print(f"  🔴 瓶颈: {bottleneck}")
    
    # Optimized titles
    opt_titles = d.get("optimized_titles", [])
    if opt_titles:
        print(f"  💡 优化标题推荐 ({len(opt_titles)}条):")
        for ot in opt_titles[:3]:
            print(f"    - {ot.get('title','')} (score={ot.get('score','')}) [{ot.get('skeleton','')}]")
    
    # Skipped dimensions
    if skipped:
        print(f"  ⏭️ 跳过: {skipped}")
    
    # Head video details
    top_vids = sorted(videos, key=lambda x: x.get("views", 0), reverse=True)[:3]
    print(f"  📈 Top 3视频:")
    for v in top_vids:
        print(f"    {v.get('views',0):>8}播放 | {v.get('score',0):.1f}分 | {v.get('title','')[:60]}")

print(f"\n{'='*70}")
print("✅ 报告完毕")