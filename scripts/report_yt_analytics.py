#!/usr/bin/env python3
"""Read and summarize the newly collected analytics data."""
from pathlib import Path
import json, sys
from datetime import datetime

DATA_DIR = Path("data/own/analytics")

for f in sorted(DATA_DIR.iterdir()):
    if not f.suffix == ".json":
        continue
    d = json.loads(f.read_text())
    slug = d.get("slug", "?")
    ts = d.get("collected_at", "?")
    period = d.get("period", {})

    print(f"\n{'='*60}")
    print(f"📺 频道: {slug}")
    print(f"  采集时间: {ts[:19]}")
    print(f"  时间段: {period.get('start')} → {period.get('end')}")
    print(f"  频道ID: {d.get('channel_id','?')}")

    # 1. Summary
    summary = d.get("summary", {})
    if "error" in summary:
        print(f"  ❌ 汇总错误: {summary['error']}")
    elif summary.get("rows"):
        h = summary["headers"]
        row = summary["rows"][0]
        data = dict(zip(h, row))
        print(f"\n  📊 汇总:")
        print(f"     浏览: {data.get('views','?'):>10}")
        print(f"     点赞: {data.get('likes','?'):>10}")
        print(f"     评论: {data.get('comments','?'):>10}")
        print(f"     分享: {data.get('shares','?'):>10}")
        print(f"     新增订阅: {data.get('subscribersGained','?'):>10}")
        print(f"     流失订阅: {data.get('subscribersLost','?'):>10}")
        print(f"     观看分钟: {data.get('estimatedMinutesWatched','?'):>10}")
        print(f"     平均观看时长: {data.get('averageViewDuration','?'):>10.1f}s")
        print(f"     平均观看率: {data.get('averageViewPercentage','?'):>10.2f}%")

    # 2. Top videos
    top = d.get("top_videos", {})
    if "error" in top:
        print(f"  ❌ Top视频错误: {top['error']}")
    elif top.get("rows"):
        meta = d.get("video_meta", {})
        titles = meta.get("titles", {})
        th = top["headers"]
        rows = top["rows"][:10]
        print(f"\n  🏆 Top 10 视频:")
        for i, row in enumerate(rows, 1):
            rdata = dict(zip(th, row))
            vid = rdata.get("video")
            title = titles.get(vid, vid[:20] if vid else "?")
            v = rdata.get("views", "?")
            lk = rdata.get("likes", "?")
            avg = rdata.get("averageViewDuration", "?")
            avp = rdata.get("averageViewPercentage", "?")
            print(f"    {i:2d}. [{v:>8} views | ♥{lk:>5} | {avg:>6.1f}s | {avp:>5.1f}%] {title[:50]}")

    # 3. Geo
    geo = d.get("geo", {})
    if geo.get("rows"):
        print(f"\n  🌍 地域 Top 5:")
        for row in geo["rows"][:5]:
            print(f"    {row[0]}: {row[1]:>8} views")

    # 4. Traffic
    traffic = d.get("traffic", {})
    if traffic.get("rows"):
        print(f"\n  🔗 流量来源:")
        for row in traffic["rows"]:
            print(f"    {row[0]}: {row[1]:>8} views")

    # 5. Retention
    ret = d.get("retention", {})
    if ret.get("has_data"):
        print(f"\n  📈 留存 (最近{ret.get('period_days','?')}天, {ret.get('video_count','?')}个视频):")
        if ret.get("avg_retention_1pct") is not None:
            print(f"     第1秒留存: {ret['avg_retention_1pct']*100:.1f}%")
        if ret.get("avg_retention_3min") is not None:
            print(f"     3分钟留存: {ret['avg_retention_3min']*100:.1f}%")
        if ret.get("avg_retention_5min") is not None:
            print(f"     5分钟留存: {ret['avg_retention_5min']*100:.1f}%")
    else:
        print(f"\n  📈 留存: 无数据")

    # 6. Daily
    daily = d.get("daily", {})
    if daily.get("rows"):
        print(f"\n  📅 每日趋势 (首尾天):")
        if len(daily["rows"]) > 0:
            hd = daily["headers"]
            first = dict(zip(hd, daily["rows"][0]))
            last = dict(zip(hd, daily["rows"][-1]))
            print(f"    首日 {first.get('day','?')}: {first.get('views','?'):>8} views")
            print(f"    末日 {last.get('day','?')}: {last.get('views','?'):>8} views")

    # 7. Device
    device = d.get("device", [])
    if device:
        print(f"\n  📱 设备:")
        for dev in device[:5]:
            print(f"    {dev['type']}: {dev['views']:>8} views")

    # 8. Demographics
    demo = d.get("demographics", [])
    if demo:
        print(f"\n  👥 受众画像:")
        for dm in demo[:5]:
            print(f"    {dm['age']}/{dm['gender']}: {dm['pct']}%")

    print(f"{'='*60}\n")

print("✅ 采集报告完成")