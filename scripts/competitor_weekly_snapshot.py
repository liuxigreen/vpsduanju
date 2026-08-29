#!/usr/bin/env python3
"""
竞品频道周数据采集 — 追加不覆盖

每次运行：
1. 从YouTube API拉取所有竞品频道的最新订阅数
2. 追加到 tracking/{channel_id}.json（不覆盖历史）
3. 更新 competitors_channels_all.json 中的 subscribers 字段
4. 保存周快照到 data/competitor_weekly/

用法：
    python3 scripts/competitor_weekly_snapshot.py
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DATA_DIR = ROOT / "data"
PANEL_DATA = DATA_DIR / "competitors_channels_all.json"
TRACKING_DIR = DATA_DIR / "competitor_tracking"
WEEKLY_DIR = DATA_DIR / "competitor_weekly"
TRACKING_DIR.mkdir(exist_ok=True)
WEEKLY_DIR.mkdir(exist_ok=True)

API_KEY_FILE = Path.home() / ".hermes" / "duanju" / "api_key.txt"
API_KEYS_FILE = Path.home() / ".hermes" / "duanju" / "api_keys.json"

def _yt_api(endpoint: str, **params) -> dict:
    """YouTube Data API v3"""
    # 加载API key（兼容多key轮换）
    keys = []
    if API_KEYS_FILE.exists():
        try:
            keys = json.loads(API_KEYS_FILE.read_text())
        except:
            pass
    if not keys and API_KEY_FILE.exists():
        key = API_KEY_FILE.read_text().strip()
        if key:
            keys = [key]
    if not keys:
        raise RuntimeError(f"API Key not found: {API_KEYS_FILE} or {API_KEY_FILE}")
    import httpx
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    params["key"] = keys[0]
    resp = httpx.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_channel_stats(channel_ids: list) -> tuple:
    """批量获取订阅数+频道注册日期（50个/次，1 unit/次）"""
    result = {}
    created_dates = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        try:
            data = _yt_api("channels", part="statistics,snippet", id=",".join(batch), maxResults=50)
            for item in data.get("items", []):
                cid = item["id"]
                subs = int(item.get("statistics", {}).get("subscriberCount", 0))
                result[cid] = subs
                published = item.get("snippet", {}).get("publishedAt", "")
                if published:
                    created_dates[cid] = published[:10]
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ 批次 {i}-{i+50} 失败: {e}")
    return result, created_dates


def main():
    today = datetime.now().strftime("%Y-%m-%d")
    print(f"📊 竞品周数据采集 — {today}")

    # 加载当前数据
    if not PANEL_DATA.exists():
        print("❌ competitors_channels_all.json 不存在")
        return

    with open(PANEL_DATA) as f:
        data = json.load(f)

    channels = data.get("channels", [])
    channel_ids = [ch["channel_id"] for ch in channels if ch.get("channel_id")]
    print(f"  频道数: {len(channel_ids)}")

    # 拉取最新订阅数
    print(f"  拉取订阅数+注册日期...")
    subs_map, created_dates = fetch_channel_stats(channel_ids)
    print(f"  获取到: {len(subs_map)} 个频道")

    # 更新tracking和JSON
    updated = 0
    for ch in channels:
        cid = ch.get("channel_id")
        if not cid or cid not in subs_map:
            continue

        new_subs = subs_map[cid]
        old_subs = ch.get("subscribers", 0)

        # 追加到tracking文件
        tracking_file = TRACKING_DIR / f"{cid}.json"
        history = []
        if tracking_file.exists():
            try:
                history = json.loads(tracking_file.read_text())
            except:
                history = []

        # 检查今天是否已记录
        if history and history[-1].get("date") == today:
            # 更新最后一条
            history[-1]["subscribers"] = new_subs
        else:
            history.append({
                "date": today,
                "subscribers": new_subs,
                "avg_views": ch.get("avg_views", 0),
            })

        tracking_file.write_text(json.dumps(history, indent=2, ensure_ascii=False))

        # 更新JSON中的subscribers
        ch["subscribers"] = new_subs
        
        # 更新频道注册日期（首次获取后不再更新）
        if cid in created_dates and not ch.get("channel_created_at"):
            ch["channel_created_at"] = created_dates[cid]

        # 更新tracking字段（周增长）
        ch.setdefault("tracking", {})
        # 找上周的数据（7天前或最近的记录）
        week_ago = None
        for rec in reversed(history[:-1]):
            if rec.get("date", "") <= today and rec.get("subscribers", 0) > 0:
                week_ago = rec
                break
        if week_ago:
            ch["tracking"]["subs_change_week"] = new_subs - week_ago["subscribers"]
        ch["tracking"]["subs_change_day"] = new_subs - old_subs if old_subs > 0 else 0

        # 更新原始增长 (v1.1.2: tracking 字段可能为 None, 必须先 setdefault)
        ch.setdefault("tracking", {})
        if ch.get("original_subscribers"):
            ch["tracking"]["subs_change_original"] = new_subs - ch["original_subscribers"]

        updated += 1

    # 保存更新后的JSON
    with open(PANEL_DATA, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    # 保存周快照
    snapshot_file = WEEKLY_DIR / f"snapshot_{today}.json"
    snapshot = {
        "date": today,
        "channel_count": len(channels),
        "channels": [
            {
                "channel_id": ch["channel_id"],
                "name": ch.get("name", ""),
                "language": ch.get("language", ""),
                "subscribers": ch.get("subscribers", 0),
                "original_subscribers": ch.get("original_subscribers"),
                "first_seen": ch.get("first_seen", ""),
            }
            for ch in channels
        ]
    }
    snapshot_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    print(f"\n✅ 完成:")
    print(f"  更新频道: {updated}")
    print(f"  快照: {snapshot_file}")
    print(f"  API消耗: ~{(len(channel_ids) + 49) // 50} units")


if __name__ == "__main__":
    main()
