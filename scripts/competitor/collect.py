# -*- coding: utf-8 -*-
"""竞品采集模块

采集阶段：从staging.json中的频道采集视频数据。
数据流：staging.json → 采集视频详情 → 更新staging.json
"""
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from core.config import ROOT, STAGING_FILE, get_competitor_api_keys
from core.api_client import YouTubeAPIClient

# 爆款视频阈值
BREAKOUT_VIEWS = 10000
BREAKOUT_RATIO = 3  # 播放量 ≥ 均值的3倍


def _tier_from_subscribers(subscribers: int) -> str:
    """按订阅数归类频道体量。"""
    subs = int(subscribers or 0)
    if subs >= 1_000_000:
        return "top"
    if subs >= 300_000:
        return "head"
    if subs >= 10_000:
        return "mid"
    if subs >= 1_000:
        return "rising"
    return "new"


def _load_registry() -> dict:
    """加载频道注册表"""
    registry_file = ROOT / "data" / "competitor_data" / "channel_registry.json"
    if registry_file.exists():
        return json.loads(registry_file.read_text())
    return {"channels": {}}


def _fetch_channel_videos(channel_id: str, max_videos: int = 10) -> list:
    """用yt-dlp获取频道视频"""
    YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")
    
    try:
        cmd = [
            YTDLP,
            f"https://www.youtube.com/channel/{channel_id}/videos",
            "--playlist-items", f"1:{max_videos}",
            "--print", "%(id)s|||%(title)s|||%(view_count)s|||%(duration)s|||%(upload_date)s|||%(like_count)s|||%(comment_count)s",
            "--cookies", str(ROOT / "cookies_new.txt"),
            "--no-download",
            "--ignore-errors",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line or "|||" not in line:
                continue
            parts = line.split("|||")
            if len(parts) < 7:
                continue
            
            vid_id, title, views, duration, upload_date, likes, comments = parts
            videos.append({
                "video_id": vid_id,
                "title": title,
                "view_count": int(views) if views.isdigit() else 0,
                "duration": int(duration) if duration.isdigit() else 0,
                "published_at": upload_date,
                "like_count": int(likes) if likes.isdigit() else 0,
                "comment_count": int(comments) if comments.isdigit() else 0,
            })
        
        return videos
        
    except Exception as e:
        print(f"    ⚠️ yt-dlp获取视频失败: {e}")
        return []


def _fetch_subscribers(channel_ids: list) -> tuple:
    """批量获取频道订阅数和地区"""
    if not channel_ids:
        return {}, {}
    
    api_keys = get_competitor_api_keys()
    if not api_keys:
        return {}, {}
    
    client = YouTubeAPIClient(api_keys=api_keys)
    subscribers = {}
    countries = {}
    
    try:
        details = client.get_channel_details(channel_ids)
        for item in details:
            cid = item["id"]
            stats = item.get("statistics", {})
            subscribers[cid] = int(stats.get("subscriberCount", 0))
            
            snippet = item.get("snippet", {})
            country = snippet.get("country", "")
            if country:
                countries[cid] = country
    except Exception as e:
        print(f"  ⚠️ 获取订阅数失败: {e}")
    
    return subscribers, countries


def collect_data(language: str = None, collect_all: bool = False, new_only: bool = False) -> list:
    """采集视频数据
    
    Args:
        language: 指定语种
        collect_all: 是否全量采集
        new_only: 是否只采集新频道
        
    Returns:
        采集的频道列表
    """
    print(f"\n📥 采集数据")
    
    # 读取 staging.json
    existing = {}
    if STAGING_FILE.exists():
        for ch in json.loads(STAGING_FILE.read_text()):
            existing[ch["channel_id"]] = ch
    
    # 选择要采集的频道
    registry = _load_registry()
    channels_by_lang = registry.get("channels", {})
    
    if collect_all:
        selected = []
        langs = [language] if language else sorted(channels_by_lang.keys())
        for lang in langs:
            selected.extend(channels_by_lang.get(lang, []))
        print(f"  全量采集: {len(selected)} 个频道")
    elif new_only:
        selected = []
        today = datetime.now().strftime("%Y-%m-%d")
        langs = [language] if language else sorted(channels_by_lang.keys())
        for lang in langs:
            ch_list = channels_by_lang.get(lang, [])
            for ch in ch_list:
                added_at = ch.get("added_at", "") or ch.get("discovered_at", "")
                if today in added_at:
                    selected.append(ch)
        print(f"  新频道采集: {len(selected)} 个频道")
    else:
        selected = []
        today_offset = int(datetime.now().strftime("%j"))
        langs = [language] if language else sorted(channels_by_lang.keys())
        per_lang = registry.get("daily_per_lang", 10)
        for lang in langs:
            ch_list = channels_by_lang.get(lang, [])
            if not ch_list:
                continue
            actual_per_lang = min(per_lang, len(ch_list))
            start = (today_offset * actual_per_lang) % len(ch_list)
            for i in range(actual_per_lang):
                idx = (start + i) % len(ch_list)
                selected.append(ch_list[idx])
        print(f"  今日轮转: {len(selected)} 个频道")
    
    if not selected:
        print("  ❌ 没有频道")
        return []
    
    # 批量获取频道订阅数和地区
    selected_ids = [ch["channel_id"] for ch in selected]
    subscribers, countries = _fetch_subscribers(selected_ids)
    print(f"  📍 获取到{len(subscribers)}个频道的订阅数, {len(countries)}个频道的地区信息")
    
    # 逐频道采集
    for i, ch in enumerate(selected):
        cid = ch["channel_id"]
        name = ch.get("name", cid)
        lang = ch.get("language", "")
        print(f"\n  [{i+1}/{len(selected)}] {name[:35]} ({lang})")
        
        # 检查是否已采集
        if cid in existing:
            print(f"    ⏭️ 已在staging.json中，跳过")
            continue
        
        videos = _fetch_channel_videos(cid, max_videos=10)
        if not videos:
            print(f"    ⚠️ 无视频数据")
            continue
        
        views = [v["view_count"] for v in videos if v.get("view_count", 0) > 0]
        avg_views = sum(views) // max(len(views), 1)
        
        # 标记爆款
        breakout = [v for v in videos
                   if v.get("view_count", 0) >= BREAKOUT_VIEWS
                   or (avg_views > 0 and v.get("view_count", 0) >= avg_views * BREAKOUT_RATIO)]
        
        # 语言检测：频道名优先 + 标题辅助（Lingua）
        from classify_languages import detect_from_titles
        video_titles = [v.get("title", "") for v in videos]
        detected_lang, lang_conf = detect_from_titles(video_titles, channel_name=name)
        if detected_lang != '未知':
            lang = detected_lang

        subscriber_count = subscribers.get(cid, ch.get("subscribers", 0) or 0)

        snapshot = {
            "channel_id": cid,
            "name": name,
            "language": lang,
            "_lang_confidence": round(lang_conf, 3),
            "country": countries.get(cid, ""),
            "subscribers": subscriber_count,
            "tier": _tier_from_subscribers(subscriber_count),
            "collected_at": datetime.now().isoformat(),
            "video_count": len(videos),
            "avg_views": avg_views,
            "videos": videos,
        }
        existing[cid] = snapshot
        
        # 增量保存到 staging.json
        STAGING_FILE.write_text(json.dumps(list(existing.values()), indent=2, ensure_ascii=False))
        print(f"    ✅ {len(videos)}视频, {len(breakout)}爆款, 均播{avg_views:,}")
        time.sleep(3)
    
    snapshots = list(existing.values())
    print(f"\n  📦 采集完成: {len(snapshots)}个频道, {sum(s.get('video_count', len(s.get('videos', []))) for s in snapshots)}个视频")
    return snapshots


if __name__ == "__main__":
    # 测试采集功能
    result = collect_data(language="英文", new_only=True)
    print(f"\n采集 {len(result)} 个频道")
