# -*- coding: utf-8 -*-
"""竞品搜索模块

搜索阶段：发现新的竞品频道。
数据流：yt-dlp搜索视频 → 反查频道 → 验证 → staging.json

核心条件：14天内有 ≥ 1个破万播放的短剧视频。
"""
import json
import os
import subprocess
import time
from datetime import datetime
from pathlib import Path

from core.config import ROOT, STAGING_FILE, get_competitor_api_keys
from core.api_client import YouTubeAPIClient

# 搜索关键词（按语种）
SEARCH_QUERIES = {
    "英文": [
        "billionaire drama short",
        "CEO romance drama",
        "revenge drama short",
        "secret identity drama",
    ],
    "繁中": [
        "霸總短劇",
        "豪門恩怨短劇",
        "復仇短劇",
        "重生短劇",
    ],
    "印尼": [
        "drama pendek CEO",
        "drama pendek balas dendam",
        "drama pendek miliarder",
    ],
    "西语": [
        "drama corto millonario",
        "drama corto venganza",
        "drama corto CEO",
    ],
    "葡萄牙": [
        "drama curto bilionário",
        "drama curto vingança",
        "drama curto CEO",
    ],
}

# 最低播放量阈值
MIN_VIEWS = 10000


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


def _fetch_channel_metadata(channel_ids: list) -> tuple:
    """批量获取频道订阅数和地区。"""
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
            cid = item.get("id")
            if not cid:
                continue
            stats = item.get("statistics", {})
            if "subscriberCount" in stats:
                subscribers[cid] = int(stats.get("subscriberCount", 0))
            country = item.get("snippet", {}).get("country", "")
            if country:
                countries[cid] = country
    except Exception as e:
        print(f"  ⚠️ 获取频道订阅数失败: {e}")

    return subscribers, countries


def _load_seen() -> set:
    """加载已搜索过的频道ID"""
    seen_file = ROOT / "data" / "competitor_data" / "seen_channels.json"
    if seen_file.exists():
        return set(json.loads(seen_file.read_text()))
    return set()


def _save_seen(seen: set):
    """保存已搜索过的频道ID"""
    seen_file = ROOT / "data" / "competitor_data" / "seen_channels.json"
    seen_file.write_text(json.dumps(list(seen), ensure_ascii=False))


def _detect_language(query: str) -> str:
    """从搜索词推断语种"""
    if any(ord(c) > 0x4e00 for c in query):
        return "繁中"
    elif "drama" in query.lower():
        if "corto" in query.lower() or "millonario" in query.lower():
            return "西语"
        elif "curto" in query.lower() or "bilionário" in query.lower():
            return "葡萄牙"
        elif "pendek" in query.lower() or "CEO" in query:
            return "印尼"
        else:
            return "英文"
    return "未知"


def _is_drama_channel(name: str, description: str, video_titles: list = None) -> bool:
    """判断是否是短剧频道"""
    # 非短剧关键词
    NON_DRAMA = [
        "news", "music", "gaming", "sports", "cooking", "travel",
        "vlog", "comedy", "funny", "reaction", "review",
        "新闻", "音乐", "游戏", "体育", "美食", "旅游",
    ]
    
    text = f"{name} {description}".lower()
    for kw in NON_DRAMA:
        if kw in text:
            return False
    
    # 短剧关键词
    DRAMA = [
        "drama", "short", "episode", "series",
        "短剧", "剧情", "霸总", "豪门", "复仇", "重生",
        "CEO", "billionaire", "revenge", "romance",
    ]
    
    # 检查频道名和描述
    for kw in DRAMA:
        if kw.lower() in text:
            return True
    
    # 检查视频标题
    if video_titles:
        for title in video_titles:
            title_lower = title.lower()
            for kw in DRAMA:
                if kw.lower() in title_lower:
                    return True
    
    return False


def _is_drama_video(video: dict) -> bool:
    """判断是否是短剧视频"""
    duration = video.get("duration", 0)
    title = video.get("title", "").lower()
    tags = [t.lower() for t in video.get("tags", [])]
    
    # 时长过滤（60秒-30分钟）
    if duration < 60 or duration > 1800:
        return False
    
    # 标题/标签关键词
    DRAMA_KEYWORDS = [
        "drama", "episode", "CEO", "billionaire", "revenge", "romance",
        "霸总", "豪门", "复仇", "重生", "逆袭", "甜宠",
    ]
    
    for kw in DRAMA_KEYWORDS:
        if kw.lower() in title or kw.lower() in " ".join(tags):
            return True
    
    return False


def _fetch_channel_videos_ytdlp(channel_id: str, max_videos: int = 10, top_n: int = 5) -> list:
    """用yt-dlp获取频道最新视频"""
    YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")
    COOKIES = os.path.expanduser("~/duanju/cookies.txt")
    
    try:
        cmd = [
            YTDLP,
            f"https://www.youtube.com/channel/{channel_id}/videos",
            "--playlist-items", f"1:{max_videos}",
            "--print", "%(id)s|||%(title)s|||%(view_count)s|||%(duration)s|||%(upload_date)s",
            "--cookies", COOKIES,
            "--no-download",
            "--ignore-errors",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        
        videos = []
        for line in result.stdout.strip().split("\n"):
            if not line or "|||" not in line:
                continue
            parts = line.split("|||")
            if len(parts) < 5:
                continue
            
            vid_id, title, views, duration, upload_date = parts
            videos.append({
                "video_id": vid_id,
                "title": title,
                "view_count": int(views) if views.isdigit() else 0,
                "duration": int(duration) if duration.isdigit() else 0,
                "published_at": upload_date,
            })
        
        # 按播放量排序，取前 top_n
        videos.sort(key=lambda x: x.get("view_count", 0), reverse=True)
        return videos[:top_n]
        
    except Exception as e:
        print(f"    ⚠️ yt-dlp获取视频失败: {e}")
        return []


def discover_channels(limit: int = 10, language: str = None) -> list:
    """搜索新频道
    
    Args:
        limit: 最大发现频道数
        language: 指定语种，None表示全部
        
    Returns:
        发现的频道列表
    """
    seen = _load_seen()
    found = {}  # channel_id -> info
    
    print(f"🔍 搜索新频道 (目标{limit}个)")
    
    # 选择搜索词
    queries = []
    if language:
        queries = SEARCH_QUERIES.get(language, [])
    else:
        for lang_queries in SEARCH_QUERIES.values():
            queries.extend(lang_queries)
    
    for query in queries:
        if len(found) >= limit * 3:
            break
        
        try:
            # yt-dlp搜索视频（14天内破万播放）
            YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")
            COOKIES = os.path.expanduser("~/duanju/cookies.txt")
            
            cmd = [
                YTDLP,
                f"ytsearch20:{query}",
                "--flat-playlist",
                "--dateafter", "today-2weeks",
                "--match-filters", f"view_count>={MIN_VIEWS} & view_count<=500000",
                "--print", "%(channel_id)s|||%(channel)s|||%(title)s|||%(view_count)s",
                "--cookies", COOKIES,
                "--no-download",
                "--ignore-errors",
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            for line in result.stdout.strip().split("\n"):
                if not line or "|||" not in line:
                    continue
                
                parts = line.split("|||")
                if len(parts) < 4:
                    continue
                
                cid, ch_name, title, views = parts[0], parts[1], parts[2], parts[3]
                
                # 跳过无效ID
                if not cid or cid == "NA" or cid in seen or cid in found:
                    continue
                
                # 快速过滤非短剧
                if not _is_drama_channel(ch_name, ""):
                    continue
                
                found[cid] = {
                    "channel_id": cid,
                    "name": ch_name,
                    "language": _detect_language(query),
                    "discovered_at": datetime.now().isoformat(),
                    "_source_video": title[:100] if title else "",
                }
            
            time.sleep(0.5)
            
        except Exception as e:
            print(f"  ⚠️ 搜索异常 ({query[:20]}): {e}")
    
    if not found:
        print("  ❌ 未找到新频道")
        return []
    
    # 验证：获取频道最新视频
    verified = []
    for cid, info in list(found.items())[:limit * 2]:
        try:
            videos = _fetch_channel_videos_ytdlp(cid, max_videos=10, top_n=5)
            
            if not videos:
                continue
            
            # 二次验证：视频标题必须含短剧关键词
            video_titles = [v.get("title", "") for v in videos]
            if not _is_drama_channel(info["name"], "", video_titles):
                continue
            
            # 核心条件：有破万播放的短剧视频
            breakout = [v for v in videos
                       if v.get("view_count", 0) >= MIN_VIEWS
                       and _is_drama_video(v)]
            
            if len(breakout) >= 1:
                info["breakout_count"] = len(breakout)
                info["total_videos"] = len(videos)
                info["avg_views"] = sum(v.get("view_count", 0) for v in videos) // max(len(videos), 1)
                info["max_views"] = max(v.get("view_count", 0) for v in videos)
                verified.append(info)
                print(f"  ✅ {info['name'][:30]} — {len(breakout)}个爆款, 最高{info['max_views']:,}")
            else:
                print(f"  ⏭️ {info['name'][:30]} — 无破万视频，跳过")
                
        except Exception as e:
            print(f"  ⚠️ 验证失败: {e}")
        time.sleep(0.3)
    
    # 保存到 staging.json
    verified = verified[:limit]
    if verified:
        subscribers, countries = _fetch_channel_metadata([info["channel_id"] for info in verified])
        for info in verified:
            cid = info["channel_id"]
            subscriber_count = subscribers.get(cid, info.get("subscribers", 0) or 0)
            info["subscribers"] = subscriber_count
            if countries.get(cid):
                info["country"] = countries[cid]
            info["tier"] = _tier_from_subscribers(subscriber_count)

        # 更新已搜索记录
        seen.update(info["channel_id"] for info in verified)
        _save_seen(seen)
        
        # 写入 staging.json
        existing_staging = []
        if STAGING_FILE.exists():
            existing_staging = json.loads(STAGING_FILE.read_text())
        existing_ids = {ch["channel_id"] for ch in existing_staging}
        
        new_channels = [ch for ch in verified if ch["channel_id"] not in existing_ids]
        if new_channels:
            existing_staging.extend(new_channels)
            STAGING_FILE.write_text(json.dumps(existing_staging, ensure_ascii=False, indent=2))
            print(f"  📦 发现 {len(new_channels)} 个新频道 → staging.json")
        else:
            print(f"  ⚠️ 所有频道已在 staging.json 中")
    
    return verified


if __name__ == "__main__":
    # 测试搜索功能
    result = discover_channels(limit=5, language="英文")
    print(f"\n发现 {len(result)} 个频道")
