#!/usr/bin/env python3
"""
channel_weekly_snapshot.py — 每周频道快照 + 周环比计算 + 面板JSON生成

用法:
    python3 scripts/channel_weekly_snapshot.py              # 分析所有自有频道
    python3 scripts/channel_weekly_snapshot.py --channel UCxxx  # 分析指定频道

输出:
    data/channel_snapshots/{slug}_{YYYYMMDD}.json  — 本周快照
    data/channel_snapshots/{slug}_latest.json       — 最新快照
    data/channel_analysis_latest.json                — 面板用的汇总JSON
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def _atomic_write_json(path: Path, data: dict, indent: int = 2, ensure_ascii: bool = False) -> None:
    """原子写 JSON：写 .tmp → fsync → os.replace。避免 panel 读到截断 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)

import keychain_helper as kc
from diagnosis_engine import build_comprehensive_report, analyze_title_patterns

# 自有频道专用key: api_keys.json[1] (mtt0)
def _load_own_api_key():
    import json as _json
    fp = os.path.expanduser("~/.hermes/duanju/api_keys.json")
    try:
        keys = _json.loads(open(fp).read())
        return keys[1]  # mtt0, 自有频道专用
    except Exception:
        return os.environ.get("YOUTUBE_API_KEY", "").strip()

API_KEY = _load_own_api_key()

SNAPSHOT_DIR = ROOT / "data" / "own" / "channel_snapshots"
SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)


def api_get(path: str, params: dict) -> dict:
    import http.client, urllib.parse, ssl
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("www.googleapis.com", context=ctx, timeout=15)
    query = urllib.parse.urlencode(params)
    conn.request("GET", f"{path}?{query}")
    resp = conn.getresponse()
    return json.loads(resp.read().decode("utf-8"))


def get_channel_stats(channel_id: str) -> dict:
    """Fetch current channel stats."""
    try:
        data = api_get("/youtube/v3/channels", {
            "part": "snippet,statistics",
            "id": channel_id, "key": API_KEY
        })
        items = data.get("items", [])
        if not items:
            return {}
        ch = items[0]
        snip = ch["snippet"]
        stat = ch.get("statistics", {})
        return {
            "channel_id": channel_id,
            "name": snip.get("title", ""),
            "published_at": snip.get("publishedAt", ""),
            "country": snip.get("country", ""),
            "subscribers": int(stat.get("subscriberCount", 0)),
            "total_views": int(stat.get("viewCount", 0)),
            "total_videos": int(stat.get("videoCount", 0)),
        }
    except Exception as e:
        print(f"  ⚠️ YouTube API失败，用yt-dlp备份: {e}")
        return _get_channel_stats_ytdlp(channel_id)


def _get_channel_stats_ytdlp(channel_id: str) -> dict:
    """yt-dlp备份：获取频道订阅数和基本信息"""
    import subprocess
    YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")
    
    try:
        # 用yt-dlp获取频道主页信息
        cmd = [
            YTDLP,
            f"https://www.youtube.com/channel/{channel_id}",
            "--print", "%(channel)s|||%(channel_follower_count)s|||%(channel_id)s",
            "--cookies-from-browser", "chrome",
            "--no-download",
            "--ignore-errors",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        for line in result.stdout.strip().split("\n"):
            if "|||" in line:
                parts = line.split("|||")
                if len(parts) >= 2:
                    name = parts[0]
                    subs = int(parts[1]) if parts[1] and parts[1] != "NA" else 0
                    return {
                        "channel_id": channel_id,
                        "name": name,
                        "subscribers": subs,
                        "total_views": 0,  # yt-dlp无法获取
                        "total_videos": 0,  # yt-dlp无法获取
                        "source": "ytdlp",
                    }
    except Exception as e:
        print(f"  ❌ yt-dlp也失败: {e}")
    
    return {}


def get_video_stats(channel_id: str, max_results: int = 15, days: int = 14, order: str = "viewCount") -> list:
    """Fetch video stats: YouTube API viewCount order, recent 14 days, up to 15 videos."""
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        search = api_get("/youtube/v3/search", {
            "part": "id", "channelId": channel_id,
            "maxResults": str(max_results), "order": order,
            "type": "video", "key": API_KEY,
            "publishedAfter": cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')
        })
        # 检查API错误（配额耗尽等）
        if "error" in search:
            raise RuntimeError(f"API error: {search['error'].get('code', '?')}")
        video_ids = [i["id"]["videoId"] for i in search.get("items", [])]
        if not video_ids:
            return []

        videos = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            vdata = api_get("/youtube/v3/videos", {
                "part": "snippet,statistics,contentDetails",
                "id": ",".join(batch), "key": API_KEY
            })
            for v in vdata.get("items", []):
                snip = v["snippet"]
                stat = v.get("statistics", {})
                desc = snip.get("description", "")
                import re
                desc_tags = re.findall(r'#([\w]+)', desc) if desc else []
                videos.append({
                    "video_id": v["id"],
                    "title": snip.get("title", ""),
                    "published_at": snip.get("publishedAt", ""),
                    "views": int(stat.get("viewCount", 0)),
                    "likes": int(stat.get("likeCount", 0)),
                    "comments": int(stat.get("commentCount", 0)),
                    "duration": v.get("contentDetails", {}).get("duration", ""),
                    "description": desc[:500],
                    "description_tags": desc_tags[:20],
                    "thumbnail": snip.get("thumbnails", {}).get("high", {}).get("url", ""),
                })
        return videos
    except Exception as e:
        print(f"  ⚠️ YouTube API失败，用yt-dlp备份: {e}")
        return _get_video_stats_ytdlp(channel_id, max_results)


def _get_video_stats_ytdlp(channel_id: str, max_results: int = 15) -> list:
    """yt-dlp备份：获取频道最近视频数据"""
    import subprocess, re
    YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")

    try:
        # 第一步：用flat-playlist获取视频ID列表
        cmd_ids = [
            YTDLP,
            f"https://www.youtube.com/channel/{channel_id}/videos",
            "--flat-playlist",
            "--print", "%(id)s",
            "--playlist-end", str(max_results),
            "--cookies-from-browser", "chrome",
            "--no-download",
            "--ignore-errors",
        ]
        r1 = subprocess.run(cmd_ids, capture_output=True, text=True, timeout=30)
        video_ids = [l.strip() for l in r1.stdout.strip().split("\n") if l.strip() and l.strip() != "NA"]

        if not video_ids:
            return []

        # 第二步：逐个获取视频详情（不加--flat-playlist才能拿到view_count等）
        videos = []
        for vid in video_ids[:max_results]:
            try:
                cmd_v = [
                    YTDLP,
                    f"https://www.youtube.com/watch?v={vid}",
                    "--print", "%(id)s|||%(title)s|||%(upload_date)s|||%(view_count)s|||%(like_count)s|||%(comment_count)s|||%(duration)s|||%(thumbnail)s|||%(description)s",
                    "--cookies-from-browser", "chrome",
                    "--no-download",
                    "--ignore-errors",
                ]
                rv = subprocess.run(cmd_v, capture_output=True, text=True, timeout=20)
                line = rv.stdout.strip()
                if "|||" not in line:
                    continue
                parts = line.split("|||")
                if len(parts) < 8:
                    continue
                vid_id, title, upload_date, views, likes, comments, duration, thumbnail = parts[:8]
                desc = parts[8] if len(parts) > 8 else ""
                desc_tags = re.findall(r'#([\w]+)', desc) if desc else []

                pub_at = ""
                if upload_date and upload_date != "NA":
                    try:
                        pub_at = f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"
                    except:
                        pub_at = upload_date

                videos.append({
                    "video_id": vid_id if vid_id != "NA" else vid,
                    "title": title if title != "NA" else "",
                    "published_at": pub_at,
                    "views": int(views) if views and views != "NA" else 0,
                    "likes": int(likes) if likes and likes != "NA" else 0,
                    "comments": int(comments) if comments and comments != "NA" else 0,
                    "duration": duration if duration != "NA" else "",
                    "description": desc[:500] if desc != "NA" else "",
                    "description_tags": desc_tags[:20],
                    "thumbnail": thumbnail if thumbnail != "NA" else "",
                })
            except Exception:
                continue

        return videos
    except Exception as e:
        print(f"  ❌ yt-dlp也失败: {e}")
        return []


def _recent_videos(videos: list, limit: int = 10) -> list:
    """Return the latest videos by published_at, newest first."""
    result = []
    for v in videos or []:
        published = v.get("published_at", "")
        if not published:
            continue
        try:
            datetime.fromisoformat(str(published).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            continue
        result.append(v)
    result.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return result[:limit]


# Backward-compatible name for callers that used an older helper name.
def _recent_month_videos(videos: list, days: int = 14) -> list:
    return _recent_videos(videos, limit=15)


def parse_duration(dur: str) -> int:
    """ISO 8601 duration to seconds."""
    import re
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur)
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def analyze_title_patterns(videos: list) -> dict:
    """Title pattern analysis."""
    import re
    if not videos:
        return {}

    lengths = [len(v["title"]) for v in videos]
    emoji_videos = [v for v in videos if re.search(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\u2764\uFE0F⭐🌟❤️]', v["title"])]

    # Length buckets
    short = [v for v in videos if len(v["title"]) <= 40]
    medium = [v for v in videos if 40 < len(v["title"]) <= 60]
    long = [v for v in videos if 60 < len(v["title"]) <= 80]
    xlong = [v for v in videos if len(v["title"]) > 80]

    def avg_lr(vids):
        if not vids:
            return 0
        total_likes = sum(v["likes"] for v in vids)
        total_views = sum(v["views"] for v in vids)
        return total_likes / max(total_views, 1) * 100

    return {
        "avg_length": sum(lengths)/len(lengths) if lengths else 0,
        "emoji_ratio": len(emoji_videos)/len(videos) if videos else 0,
        "length_performance": {
            "short_40": {"count": len(short), "avg_like_rate": round(avg_lr(short), 2)},
            "medium_60": {"count": len(medium), "avg_like_rate": round(avg_lr(medium), 2)},
            "long_80": {"count": len(long), "avg_like_rate": round(avg_lr(long), 2)},
            "xlong_80+": {"count": len(xlong), "avg_like_rate": round(avg_lr(xlong), 2)},
        }
    }


def analyze_posting_pattern(videos: list) -> dict:
    """Posting time analysis."""
    from collections import Counter
    if not videos:
        return {}

    weekdays = Counter()
    hours = Counter()
    for v in videos:
        try:
            dt = datetime.fromisoformat(v["published_at"].replace("Z", "+00:00"))
            weekdays[dt.strftime("%A")] += 1
            hours[dt.hour] += 1
        except (ValueError, KeyError):
            pass

    return {
        "by_weekday": dict(weekdays.most_common()),
        "by_hour": {str(k): v for k, v in hours.most_common()},
    }


def analyze_duration_impact(videos: list) -> dict:
    """Duration vs performance analysis."""
    if not videos:
        return {}

    buckets = {"<5min": [], "5-30min": [], "30-60min": [], "1-2hr": [], "2hr+": []}
    for v in videos:
        secs = parse_duration(v["duration"])
        mins = secs / 60
        if mins < 5:
            buckets["<5min"].append(v)
        elif mins < 30:
            buckets["5-30min"].append(v)
        elif mins < 60:
            buckets["30-60min"].append(v)
        elif mins < 120:
            buckets["1-2hr"].append(v)
        else:
            buckets["2hr+"].append(v)

    result = {}
    for label, vids in buckets.items():
        if not vids:
            continue
        views = [v["views"] for v in vids]
        result[label] = {
            "count": len(vids),
            "avg_views": sum(views)//len(views),
            "avg_like_rate": round(sum(v["likes"] for v in vids) / max(sum(v["views"] for v in vids), 1) * 100, 2),
        }
    return result


def _video_view_change(prev_videos: list, curr_videos: list) -> int:
    """用视频级播放量差值计算真实每日播放变化（绕过频道级viewCount缓存）。"""
    prev_map = {v['video_id']: v.get('views', 0) for v in prev_videos}
    total = 0
    for v in curr_videos:
        vid = v.get('video_id', '')
        curr_views = v.get('views', 0)
        prev_views = prev_map.get(vid, 0)
        total += max(0, curr_views - prev_views)
    return total


def compute_growth(slug: str, current: dict) -> dict:
    """Compare with yesterday's snapshot (daily comparison)."""
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y%m%d")
    prev_path = SNAPSHOT_DIR / f"{slug}_{yesterday}.json"

    if not prev_path.exists():
        # Fallback: find the most recent dated snapshot before today
        today_str = datetime.now().strftime("%Y%m%d")
        prev_files = sorted(SNAPSHOT_DIR.glob(f"{slug}_*.json"), reverse=True)
        prev_files = [f for f in prev_files if "latest" not in f.name and today_str not in f.name]
        if not prev_files:
            return {"has_prev": False, "message": "首次采集，无历史对比"}
        prev_path = prev_files[0]

    try:
        prev = json.loads(prev_path.read_text())
    except Exception:
        return {"has_prev": False, "message": "历史数据读取失败"}

    prev_info = prev.get("channel_stats", {})
    curr_info = current.get("channel_stats", {})

    # Calculate actual days between snapshots
    try:
        prev_date = prev_path.stem.split("_")[-1]
        prev_dt = datetime.strptime(prev_date, "%Y%m%d")
        days_diff = max((datetime.now() - prev_dt).days, 1)
    except Exception:
        days_diff = 1

    sub_change = curr_info.get("subscribers", 0) - prev_info.get("subscribers", 0)
    # 用视频级播放量差值（频道级viewCount有严重缓存延迟）
    view_change = _video_view_change(prev.get("videos", []), current.get("videos", []))
    video_change = curr_info.get("total_videos", 0) - prev_info.get("total_videos", 0)

    # Like rate change (from videos, weighted average)
    prev_videos = prev.get("videos", [])
    curr_videos = current.get("videos", [])
    prev_total_likes = sum(v["likes"] for v in prev_videos if v.get("views",0)>0)
    prev_total_views = sum(v["views"] for v in prev_videos if v.get("views",0)>0)
    prev_lr = prev_total_likes / max(prev_total_views, 1) * 100
    curr_total_likes = sum(v["likes"] for v in curr_videos if v.get("views",0)>0)
    curr_total_views = sum(v["views"] for v in curr_videos if v.get("views",0)>0)
    curr_lr = curr_total_likes / max(curr_total_views, 1) * 100

    return {
        "has_prev": True,
        "prev_date": prev_path.stem.split("_")[-1],
        "days_diff": days_diff,
        "subscribers_change": sub_change,
        "subscribers_change_pct": round(sub_change / max(prev_info.get("subscribers", 1), 1) * 100, 2),
        "views_change": view_change,
        "views_change_pct": round(view_change / max(prev_info.get("total_views", 1), 1) * 100, 2),
        "videos_change": video_change,
        "like_rate_prev": round(prev_lr, 2),
        "like_rate_curr": round(curr_lr, 2),
        "like_rate_change": round(curr_lr - prev_lr, 2),
        "daily_sub_growth": round(sub_change / max(days_diff, 1), 1),
        "daily_view_growth": round(view_change / max(days_diff, 1), 0),
    }


def compute_weekly_growth(slug: str, current: dict) -> dict:
    """Compare with snapshot from 7 days ago (weekly comparison)."""
    week_ago = (datetime.now() - timedelta(days=7)).strftime("%Y%m%d")
    prev_path = SNAPSHOT_DIR / f"{slug}_{week_ago}.json"

    if not prev_path.exists():
        # Fallback: find the closest snapshot 5-9 days ago
        today_str = datetime.now().strftime("%Y%m%d")
        target_date = datetime.now() - timedelta(days=7)
        prev_files = sorted(SNAPSHOT_DIR.glob(f"{slug}_*.json"), reverse=True)
        prev_files = [f for f in prev_files if "latest" not in f.name and today_str not in f.name]
        best = None
        best_diff = 999
        for f in prev_files:
            try:
                d = f.stem.split("_")[-1]
                dt = datetime.strptime(d, "%Y%m%d")
                diff = abs((target_date - dt).days)
                if diff < best_diff:
                    best_diff = diff
                    best = f
            except Exception:
                continue
        if best and best_diff <= 4:  # within 4 days of target
            prev_path = best
        else:
            return {"has_weekly": False, "message": "无7天前数据"}

    try:
        prev = json.loads(prev_path.read_text())
    except Exception:
        return {"has_weekly": False, "message": "历史数据读取失败"}

    prev_info = prev.get("channel_stats", {})
    curr_info = current.get("channel_stats", {})

    try:
        prev_date = prev_path.stem.split("_")[-1]
        prev_dt = datetime.strptime(prev_date, "%Y%m%d")
        days_diff = max((datetime.now() - prev_dt).days, 1)
    except Exception:
        days_diff = 7

    sub_change = curr_info.get("subscribers", 0) - prev_info.get("subscribers", 0)
    # 用视频级播放量差值（频道级viewCount有严重缓存延迟）
    view_change = _video_view_change(prev.get("videos", []), current.get("videos", []))
    video_change = curr_info.get("total_videos", 0) - prev_info.get("total_videos", 0)

    return {
        "has_weekly": True,
        "prev_date": prev_path.stem.split("_")[-1],
        "days_diff": days_diff,
        "subscribers_change": sub_change,
        "subscribers_change_pct": round(sub_change / max(prev_info.get("subscribers", 1), 1) * 100, 2),
        "views_change": view_change,
        "views_change_pct": round(view_change / max(prev_info.get("total_views", 1), 1) * 100, 2),
        "videos_change": video_change,
    }


def build_panel_json(all_reports: list) -> dict:
    """Build the comprehensive panel JSON with all data."""
    channels = []
    channel_details = {}

    # Load registry for metadata
    registry_path = ROOT / "data" / "own" / "our_channels.json"
    registry_map = {}
    if registry_path.exists():
        try:
            reg = json.loads(registry_path.read_text())
            for ch in reg.get("channels", []):
                registry_map[ch.get("channel_id", "")] = ch
        except Exception:
            pass

    for report in all_reports:
        info = report.get("channel_stats", {})
        videos = report.get("videos", [])  # all videos for panel display and health assessment
        growth = report.get("growth", {})
        title_analysis = report.get("title_analysis", {})
        posting = report.get("posting_pattern", {})
        duration = report.get("duration_impact", {})

        # Calculate derived metrics
        created = info.get("published_at", "")
        if created:
            created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days = (datetime.now(timezone.utc) - created_dt).days
        else:
            days = 0

        views_list = [v["views"] for v in videos]
        likes_list = [v["likes"] for v in videos]
        like_rates = [v["likes"]/v["views"]*100 if v["views"]>0 else 0 for v in videos]
        top10 = sorted(videos, key=lambda x: x["views"], reverse=True)[:10]
        avg_top10 = sum(v["views"] for v in top10) // max(len(top10), 1)
        # 面板近期视频：同一批采集数据，按发布时间倒排（采集源已限制最近14天最多15条）
        recent_videos = _recent_videos(videos, limit=15)

        # Health assessment
        avg_lr = sum(like_rates)/len(like_rates) if like_rates else 0
        if avg_lr >= 3.0:
            health = "标杆"
        elif avg_lr >= 1.5:
            health = "健康"
        elif avg_lr >= 1.0:
            health = "一般"
        elif avg_lr >= 0.5:
            health = "转化差"
        else:
            health = "零互动"

        slug = info.get("name", "unknown").replace(" ", "_")[:20]

        # Fill metadata from registry
        ch_id = info.get("channel_id", "")
        reg_info = registry_map.get(ch_id, {})

        channels.append({
            "name": info.get("name", ""),
            "channel_id": info.get("channel_id", ""),  # P1-4: 补 channel_id，防 name 漂移导致 OAuth 数据错配
            "operator": reg_info.get("operator", ""),
            "operator_type": reg_info.get("operator_type", ""),
            "language": reg_info.get("language_cn", reg_info.get("language", "")),
            "country": info.get("country", ""),
            "niche": reg_info.get("niche", ""),
            "market": reg_info.get("market", ""),
            "created": created[:10] if created else "",
            "days": days,
            "subscribers": info.get("subscribers", 0),
            "total_views": info.get("total_views", 0),
            "videos": info.get("total_videos", 0),
            "daily_subs": round(info.get("subscribers", 0) / max(days, 1), 1),
            "view_sub_ratio": round(info.get("total_views", 0) / max(info.get("subscribers", 1), 1), 1),
            "avg_views_10": avg_top10,
            "like_rate": round(avg_lr, 2),
            "health": health,
            # 新增指标
            "publish_freq": round(info.get("total_videos", 0) / max(days, 1), 2),
            "daily_views": round(info.get("total_views", 0) / max(days, 1)),
            "avg_views_per_video": round(info.get("total_views", 0) / max(info.get("total_videos", 1), 1)),
            "days_to_1k": round((1000 - info.get("subscribers", 0)) / max(info.get("subscribers", 0) / max(days, 1), 0.1)) if info.get("subscribers", 0) < 1000 else 0,
            # 日环比数据
            "growth": growth,
            # 周环比数据
            "weekly_growth": report.get("weekly_growth", {}),
        })

        # Build issues - use engine diagnostics if available
        diagnostics = report.get("diagnostics", [])
        issues = []
        if diagnostics:
            # Use engine-generated diagnostics
            issues = diagnostics
        else:
            # Fallback to simple diagnostics
            if avg_lr < 1.0:
                issues.append({"severity": "critical", "category": "互动率", "issue": f"点赞率极低 {avg_lr:.2f}%", "detail": "低于行业基准1.5%", "action": "优化标题+封面，增加互动引导"})
            elif avg_lr < 1.5:
                issues.append({"severity": "major", "category": "互动率", "issue": f"点赞率偏低 {avg_lr:.2f}%", "detail": "", "action": "增加CTA引导"})

        channel_details[info.get("name", "")] = {
            "issues": issues,
            "top_videos": [{"video_id": v.get("video_id", ""), "title": v["title"][:60], "views": v["views"], "likes": v["likes"], "comments": v.get("comments", 0), "thumbnail": v.get("thumbnail", ""), "published_at": v.get("published_at", "")} for v in top10],
            "recent_videos": [{"video_id": v.get("video_id", ""), "title": v["title"][:60], "views": v["views"], "likes": v["likes"], "comments": v.get("comments", 0), "thumbnail": v.get("thumbnail", ""), "published_at": v.get("published_at", "")} for v in recent_videos],
            "growth": growth,
            "title_analysis": report.get("title_analysis", title_analysis),
            "posting_pattern": posting,
            "duration_impact": duration,
            "view_distribution": report.get("view_distribution", {}),
            "engagement_funnel": report.get("engagement_funnel", {}),
            "content_consistency": report.get("content_consistency", {}),
            "seo_analysis": report.get("seo_analysis", {}),
        }

    return {
        "report_date": datetime.now().strftime("%Y-%m-%d"),
        "channels": channels,
        "channel_details": channel_details,
    }




def _refresh_token(slug: str, token_data: dict) -> dict | None:
    """刷新OAuth token"""
    import urllib.request, urllib.parse
    
    client = kc.load_google_client()
    if not client:
        return None
    
    refresh_token = token_data.get('refresh_token')
    if not refresh_token:
        return None
    
    data = urllib.parse.urlencode({
        'client_id': client['client_id'],
        'client_secret': client['client_secret'],
        'refresh_token': refresh_token,
        'grant_type': 'refresh_token',
    }).encode()
    
    req = urllib.request.Request('https://oauth2.googleapis.com/token', data=data, method='POST')
    req.add_header('Content-Type', 'application/x-www-form-urlencoded')
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            new_token = json.loads(resp.read().decode())
        if 'refresh_token' not in new_token:
            new_token['refresh_token'] = refresh_token
        new_token['expires_at'] = time.time() + new_token.get('expires_in', 3600)
        new_token['refreshed_at'] = datetime.now(timezone.utc).isoformat() + 'Z'
        kc.save_youtube_token(slug, new_token)
        print(f'  ✅ Token已刷新: {slug}')
        return new_token
    except Exception as e:
        print(f'  ⚠️ Token刷新失败: {e}')
        return None


def _fetch_analytics(channel_id: str) -> dict:
    """从 YouTube Analytics API 拉取 OAuth 数据（已授权频道）。"""
    import urllib.request, urllib.parse

    accounts_path = Path.home() / '.hermes' / 'duanju' / 'accounts.json'
    if not accounts_path.exists():
        return {}

    # 找到 channel_id 对应的 slug
    accounts = json.loads(accounts_path.read_text())
    slug = None
    for s, info in accounts.items():
        if info.get('channel_id') == channel_id:
            slug = s
            break
    if not slug:
        return {}

    token = kc.load_youtube_token(slug)
    if not token:
        return {}
    
    # Token过期时自动刷新
    if token.get('expires_at', 0) < time.time() - 60:
        refreshed = _refresh_token(slug, token)
        if refreshed:
            token = refreshed
        else:
            print(f'  ⚠️ Token过期且刷新失败: {slug}')
            return {}

    access_token = token['access_token']
    end_d = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    start_d = (datetime.now(timezone.utc) - timedelta(days=30)).strftime('%Y-%m-%d')

    def _query(metrics, dimensions='', sort='', max_results=''):
        params = {'ids': f'channel=={channel_id}', 'startDate': start_d, 'endDate': end_d, 'metrics': metrics}
        if dimensions: params['dimensions'] = dimensions
        if sort: params['sort'] = sort
        if max_results: params['maxResults'] = max_results
        url = f'https://youtubeanalytics.googleapis.com/v2/reports?{urllib.parse.urlencode(params)}'
        req = urllib.request.Request(url)
        req.add_header('Authorization', f'Bearer {access_token}')
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode())

    analytics = {'period': '30d', 'slug': slug}

    # 1. 互动指标
    try:
        d = _query('views,likes,comments,shares')
        cols = [c['name'] for c in d['columnHeaders']]
        row = d.get('rows', [[]])[0] if d.get('rows') else []
        for c, v in zip(cols, row):
            analytics[c] = v
    except Exception as e:
        print(f'  ⚠️ 互动指标: {e}')

    # 2. 留存+观看时长
    try:
        d = _query('averageViewPercentage,averageViewDuration,estimatedMinutesWatched')
        cols = [c['name'] for c in d['columnHeaders']]
        row = d.get('rows', [[]])[0] if d.get('rows') else []
        for c, v in zip(cols, row):
            analytics[c] = v
    except Exception as e:
        print(f'  ⚠️ 留存指标: {e}')

    # 3. 订阅变化
    try:
        d = _query('subscribersGained,subscribersLost')
        cols = [c['name'] for c in d['columnHeaders']]
        row = d.get('rows', [[]])[0] if d.get('rows') else []
        for c, v in zip(cols, row):
            analytics[c] = v
    except Exception as e:
        print(f'  ⚠️ 订阅指标: {e}')

    # 4. 流量来源
    try:
        d = _query('views', 'insightTrafficSourceType', '-views')
        sources = {}
        for r in d.get('rows', []):
            sources[r[0]] = r[1]
        analytics['traffic_sources'] = sources
        total = sum(sources.values())
        analytics['traffic_ratios'] = {k: round(v / total * 100, 1) for k, v in sources.items()} if total > 0 else {}
    except Exception as e:
        print(f'  ⚠️ 流量来源: {e}')

    # 5. 地域分布
    try:
        d = _query('views', 'country', '-views', '10')
        geo = {}
        for r in d.get('rows', []):
            geo[r[0]] = r[1]
        analytics['geo'] = geo
    except Exception as e:
        print(f'  ⚠️ 地域: {e}')

    # 6. 受众画像
    try:
        d = _query('viewerPercentage', 'ageGroup,gender')
        demo = []
        for r in d.get('rows', []):
            if r[2] > 0.5:  # 只保留 >0.5% 的
                demo.append({'age': r[0], 'gender': r[1], 'pct': round(r[2], 1)})
        analytics['demographics'] = demo
    except Exception as e:
        print(f'  ⚠️ 受众画像: {e}')

    return analytics


def analyze_channel(channel_id: str) -> dict:
    """Full analysis for one channel."""
    print(f"  📊 获取频道统计...")
    stats = get_channel_stats(channel_id)
    if not stats:
        return {"error": f"Channel {channel_id} not found"}

    print(f"  🎬 获取视频数据...")
    videos = get_video_stats(channel_id)

    print(f"  📝 分析标题模式...")
    title_analysis = analyze_title_patterns(videos)

    print(f"  📅 分析发布节奏...")
    posting = analyze_posting_pattern(videos)

    print(f"  ⏱️ 分析时长影响...")
    duration = analyze_duration_impact(videos)

    # 获取频道语言，加载对应的蒸馏数据
    distill = None
    registry_path = ROOT / "data" / "own" / "our_channels.json"
    if registry_path.exists():
        try:
            registry = json.loads(registry_path.read_text())
            for ch in registry.get("channels", []):
                if ch.get("channel_id") == channel_id:
                    lang = ch.get("language", "").lower()
                    # 映射语言代码
                    lang_map = {"en": "en", "es": "es", "pt": "葡萄牙", "id": "id", "繁中": "繁中", "zh": "zh-CN"}
                    lang_code = lang_map.get(lang, lang)
                    distill_path = Path.home() / ".hermes" / "profiles" / "duanju" / "knowledge" / lang_code / "distill.json"
                    if distill_path.exists():
                        distill = json.loads(distill_path.read_text(encoding="utf-8"))
                        print(f"  📚 加载蒸馏数据: {lang_code}")
                    break
        except Exception as e:
            print(f"  ⚠️ 加载蒸馏数据失败: {e}")

    report = {
        "channel_stats": stats,
        "videos": videos,
        "title_analysis": title_analysis,
        "posting_pattern": posting,
        "duration_impact": duration,
        "analyzed_at": datetime.now().isoformat(),
    }

    # OAuth Analytics（已授权频道）
    print(f"  🔐 获取OAuth Analytics...")
    analytics = _fetch_analytics(channel_id)
    if analytics:
        report["analytics"] = analytics
        print(f"     ✅ {analytics.get('slug', '?')}: {analytics.get('views', 0):,} 播放, 留存 {analytics.get('averageViewPercentage', 0)}%")
    else:
        print(f"     ⏭️ 未授权或无数据")

    print(f"  🔍 运行深度诊断...")
    report = build_comprehensive_report(report, distill=distill)

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser(description="频道周快照")
    parser.add_argument("--channel", help="频道ID")
    args = parser.parse_args()

    today = datetime.now().strftime("%Y%m%d")

    if args.channel:
        channel_ids = [args.channel]
    else:
        # 优先读 our_channels.json 注册表
        registry_path = ROOT / "data" / "own" / "our_channels.json"
        if registry_path.exists():
            registry = json.loads(registry_path.read_text())
            channel_ids = [ch["channel_id"] for ch in registry.get("channels", []) if ch.get("channel_id")]
            print(f"📋 从注册表加载 {len(channel_ids)} 个频道")
        else:
            # Fallback: keychain accounts
            accounts = kc.list_accounts() if hasattr(kc, 'list_accounts') else {}
            channel_ids = [info.get("channel_id") for info in accounts.values() if info.get("channel_id")]
        if not channel_ids:
            print("❌ 没有已授权频道，用 --channel UCxxx 指定")
            sys.exit(1)

    all_reports = []
    for ch_id in channel_ids:
        print(f"\n{'='*40}")
        print(f"分析频道: {ch_id}")

        report = analyze_channel(ch_id)
        if "error" in report:
            print(f"  ❌ {report['error']}")
            continue

        slug = report["channel_stats"]["name"].replace(" ", "_")[:20]

        # Compute growth
        print(f"  📈 计算日环比...")
        report["growth"] = compute_growth(slug, report)
        print(f"  📈 计算周环比...")
        report["weekly_growth"] = compute_weekly_growth(slug, report)

        # Save snapshot
        snap_path = SNAPSHOT_DIR / f"{slug}_{today}.json"
        # P1-3: 原子写快照，避免 panel 读到截断 JSON
        _atomic_write_json(snap_path, report)
        latest_path = SNAPSHOT_DIR / f"{slug}_latest.json"
        _atomic_write_json(latest_path, report)
        print(f"  💾 快照已保存: {snap_path}")

        all_reports.append(report)

    # Build panel JSON
    if all_reports:
        panel_data = build_panel_json(all_reports)
        panel_path = ROOT / "data" / "own" / "channel_analysis_latest.json"
        # P1-3: 原子写 channel_analysis_latest.json（面板核心数据，高频被读）
        _atomic_write_json(panel_path, panel_data)
        print(f"\n✅ 面板数据已更新: {panel_path}")
        print(f"   {len(panel_data['channels'])} 个频道, 报告日期: {panel_data['report_date']}")


if __name__ == "__main__":
    main()
