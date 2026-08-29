#!/usr/bin/env python3
"""
拉取高增长频道的早期视频（最早3条）

只对增长>1万的频道拉取，用 playlistItems.list 按位置取前3条（最旧的）。
数据存到 competitors_channels_all.json 的 early_videos 字段。

用法：python3 scripts/fetch_early_videos.py
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DATA_DIR = ROOT / "data"
PANEL_DATA = DATA_DIR / "competitors_channels_all.json"
API_KEY_FILE = Path.home() / ".hermes" / "duanju" / "api_key.txt"
API_KEYS_FILE = Path.home() / ".hermes" / "duanju" / "api_keys.json"

import httpx

def _load_keys():
    keys = []
    if API_KEYS_FILE.exists():
        try:
            keys = json.loads(API_KEYS_FILE.read_text())
        except:
            pass
    if not keys and API_KEY_FILE.exists():
        k = API_KEY_FILE.read_text().strip()
        if k:
            keys = [k]
    return keys

def _yt_api(endpoint, **params):
    keys = _load_keys()
    if not keys:
        raise RuntimeError("No API key")
    params["key"] = keys[0]
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    resp = httpx.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()

def fetch_early_videos(channel_id: str, max_results: int = 3) -> list:
    """获取频道最早的N条视频"""
    # uploads playlist = UU + channel_id[2:]
    playlist_id = "UU" + channel_id[2:]
    
    try:
        data = _yt_api("playlistItems",
                       part="snippet,contentDetails",
                       playlistId=playlist_id,
                       maxResults=max_results)
    except Exception as e:
        return []
    
    videos = []
    for item in data.get("items", []):
        snippet = item.get("snippet", {})
        content = item.get("contentDetails", {})
        video_id = content.get("videoId", "")
        if not video_id:
            continue
        videos.append({
            "video_id": video_id,
            "title": snippet.get("title", ""),
            "published_at": snippet.get("publishedAt", ""),
            "thumbnail": snippet.get("thumbnails", {}).get("medium", {}).get("url", ""),
        })
    return videos

def main():
    with open(PANEL_DATA) as f:
        data = json.load(f)
    
    channels = data.get("channels", [])
    
    # 筛选增长>1万且没有early_videos的频道
    targets = []
    for ch in channels:
        g = ch.get("tracking", {}).get("subs_change_baseline", 0) or 0
        if g >= 10000 and not ch.get("early_videos"):
            targets.append(ch)
    
    print(f"📊 拉取早期视频")
    print(f"  目标频道: {len(targets)} (增长>1万)")
    
    fetched = 0
    failed = 0
    
    for i, ch in enumerate(targets, 1):
        cid = ch["channel_id"]
        name = ch.get("name", cid[:12])
        growth = ch.get("tracking", {}).get("subs_change_baseline", 0)
        
        videos = fetch_early_videos(cid, max_results=3)
        
        if videos:
            ch["early_videos"] = videos
            earliest = videos[0].get("published_at", "")[:10]
            print(f"  [{i}/{len(targets)}] {name}: +{growth:,} → 最早视频 {earliest} ({len(videos)}条)")
            fetched += 1
        else:
            print(f"  [{i}/{len(targets)}] {name}: 获取失败")
            failed += 1
        
        # 保存进度（每10个）
        if i % 10 == 0:
            with open(PANEL_DATA, "w") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        
        time.sleep(0.2)
    
    # 最终保存
    with open(PANEL_DATA, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 统计
    has_early = sum(1 for ch in channels if ch.get("early_videos"))
    
    print(f"\n✅ 完成:")
    print(f"  成功: {fetched}, 失败: {failed}")
    print(f"  总计有early_videos: {has_early}/{len(channels)}")
    print(f"  API消耗: ~{len(targets)} units")

if __name__ == "__main__":
    main()
