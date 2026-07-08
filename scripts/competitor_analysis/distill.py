# -*- coding: utf-8 -*-
"""竞品频道分析模块

从latest.json筛选+分析+生成面板数据。
数据流：latest.json → competitor_insights/ → competitors_channels_all.json

主要功能：
- filter_by_tier(): 按tier筛选频道
- track_daily(): 每日追踪订阅+播放量
- analyze_single_channel(): 单频道深度分析
- update_panel_data(): 更新面板数据
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

from core.config import (
    ROOT, LATEST_FILE, TIERS_FILE, PANEL_DATA_FILE,
    COMPETITOR_INSIGHTS_DIR, COMPETITOR_TRACKING_DIR
)

# 复用原有脚本的分析函数
sys.path.insert(0, str(ROOT / "scripts"))

# 导入原有脚本的核心函数
from distill_competitors import (
    TIER_DEFS,
    extract_content_tags,
    analyze_single_channel,
    update_panel_data,
    filter_by_tier,
    track_daily,
)


def distill_competitors(language: str = None, pick_new: bool = True, per_lang: int = 1):
    """竞品频道分析主函数
    
    Args:
        language: 指定语种
        pick_new: 是否只分析新频道
        per_lang: 每语种分析数量
    """
    print(f"📋 开始竞品频道分析")
    
    # 1. 五层筛选
    selected = filter_by_tier()
    if not selected:
        print("❌ latest.json 为空或不存在")
        return
    
    # 2. 每日追踪
    track_daily(selected)
    
    # 3. 逐频道深度分析（只分析未分析过的）
    from distill_competitors import _load_tracker, _save_tracker, load_snapshots_for_channel, load_enriched_for_channel
    
    tracker = _load_tracker()
    analyzed_ids = set(tracker.get("analyzed", {}).keys())
    
    channels_to_analyze = []
    skipped_insufficient = 0
    for lang, channels in selected.items():
        if language and lang != language:
            continue
        for ch in channels:
            cid = ch.get("channel_id", "")
            if cid in analyzed_ids:
                continue
            # 新频道：≥3视频即可分析
            snapshot = load_snapshots_for_channel(cid)
            videos = snapshot.get("videos", []) if snapshot else []
            if len(videos) < 3:
                skipped_insufficient += 1
                continue
            channels_to_analyze.append(ch)
    
    if skipped_insufficient:
        print(f"  ⏳ {skipped_insufficient} 个新频道数据不足（<5视频或均播<1000），只追踪不分析")
    
    if channels_to_analyze:
        print(f"\n🔍 逐频道深度分析 ({len(channels_to_analyze)} 个新频道)")
        for ch in channels_to_analyze:
            cid = ch["channel_id"]
            name = ch.get("name", cid[:12])
            lang = ch.get("language", "?")
            print(f"\n  📺 [{lang}] {name[:40]}")
            
            snapshot = load_snapshots_for_channel(cid)
            if not snapshot:
                print(f"    ⚠️ 无快照数据，跳过")
                continue
            
            enriched = load_enriched_for_channel(cid)
            result = analyze_single_channel(ch, snapshot, enriched or None)
            
            channel_file = COMPETITOR_INSIGHTS_DIR / f"channel_{cid}.json"
            channel_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            
            tier = result.get("tier", "?")
            avg = result.get("avg_views", 0)
            va = result.get("video_analysis", {})
            bc = va.get("breakout_count", 0)
            tags = "、".join(result.get("content_tags", [])) or "未分类"
            print(f"    ✅ [{tier}] {result.get('total_videos', 0)}视频, 均播{avg:,}, 爆款{bc}, {tags}")
            
            tracker.setdefault("analyzed", {})[cid] = {
                "name": name,
                "language": lang,
                "analyzed_at": datetime.now().isoformat(),
            }
            time.sleep(0.5)
        
        _save_tracker(tracker)
    else:
        print(f"\n  ℹ️ 所有筛选频道都已分析过，只做追踪")
    
    # 4. 更新面板数据
    update_panel_data()
    
    print(f"\n{'='*50}")
    print(f"✅ 完成")
    print(f"{'='*50}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="竞品频道分析")
    parser.add_argument("--language", type=str, help="指定语种")
    parser.add_argument("--all", action="store_true", help="全量分析")
    args = parser.parse_args()
    
    if args.all:
        distill_competitors(language=args.language, pick_new=False, per_lang=999)
    else:
        distill_competitors(language=args.language)
