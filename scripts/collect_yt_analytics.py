#!/usr/bin/env python3
"""YouTube Analytics 离线采集 — 每天跑一次，存本地JSON供面板读取。

用法:
  python3 scripts/collect_yt_analytics.py              # 采集所有已授权频道
  python3 scripts/collect_yt_analytics.py --slug hk     # 只采集指定频道
"""

import json, sys, os, time, logging
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("yt-analytics")

DATA_DIR = ROOT / "data" / "yt_analytics"
DATA_DIR.mkdir(parents=True, exist_ok=True)

# 复用 panel_v3.py 的 keychain 模块
sys.path.insert(0, str(ROOT / "scripts"))
import keychain_helper as kc

ACCOUNTS_FILE = Path.home() / ".hermes" / "duanju" / "accounts.json"


def load_accounts():
    if ACCOUNTS_FILE.exists():
        return json.loads(ACCOUNTS_FILE.read_text())
    return {}


def refresh_token(slug, token_data):
    """刷新 OAuth token，返回新 token 或 None"""
    import urllib.parse as up, urllib.request as ur
    client = kc.load_google_client()
    if not client:
        return None
    refresh = token_data.get("refresh_token")
    if not refresh:
        return None
    data = up.urlencode({
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": refresh,
        "grant_type": "refresh_token",
    }).encode()
    req = ur.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with ur.urlopen(req, timeout=30) as resp:
            new_token = json.loads(resp.read().decode())
        if "refresh_token" not in new_token:
            new_token["refresh_token"] = refresh
        new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
        kc.save_youtube_token(slug, new_token)
        return new_token
    except Exception as e:
        log.error(f"[{slug}] token refresh failed: {e}")
        return None


def get_access_token(slug):
    """获取有效的 access_token，过期自动刷新"""
    token_data = kc.load_youtube_token(slug)
    if not token_data:
        return None
    if token_data.get("expires_at", 0) < time.time() - 60:
        refreshed = refresh_token(slug, token_data)
        if refreshed:
            token_data = refreshed
        else:
            return None
    return token_data["access_token"]


def analytics_query(access_token, channel_id, start_date, end_date,
                    metrics, dimensions="", sort="", max_results="", filters=""):
    """调用 YouTube Analytics API"""
    import urllib.parse as up, urllib.request as ur
    params = {
        "ids": f"channel=={channel_id}",
        "startDate": start_date,
        "endDate": end_date,
        "metrics": metrics,
    }
    if dimensions:
        params["dimensions"] = dimensions
    if sort:
        params["sort"] = sort
    if max_results:
        params["maxResults"] = max_results
    if filters:
        params["filters"] = filters
    url = f"https://youtubeanalytics.googleapis.com/v2/reports?{up.urlencode(params)}"
    req = ur.Request(url)
    req.add_header("Authorization", f"Bearer {access_token}")
    with ur.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode())
    headers = [h["name"] for h in result.get("columnHeaders", [])]
    rows = result.get("rows", [])
    return {"headers": headers, "rows": rows, "count": len(rows)}


def collect_channel(slug, channel_id, access_token, period=30):
    """采集一个频道的全部 Analytics 数据"""
    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - timedelta(days=period)).strftime("%Y-%m-%d")
    report = {"slug": slug, "period": {"start": start_date, "end": end_date},
              "channel_id": channel_id, "collected_at": datetime.utcnow().isoformat() + "Z"}

    # 1. 汇总
    try:
        report["summary"] = analytics_query(access_token, channel_id, start_date, end_date,
            "views,likes,comments,shares,subscribersGained,subscribersLost,"
            "estimatedMinutesWatched,averageViewDuration,averageViewPercentage")
    except Exception as e:
        log.error(f"[{slug}] summary error: {e}")
        report["summary"] = {"error": str(e)}

    # 2. 每日趋势
    try:
        report["daily"] = analytics_query(access_token, channel_id, start_date, end_date,
            "views,likes,estimatedMinutesWatched,averageViewDuration,averageViewPercentage",
            dimensions="day")
    except Exception as e:
        log.error(f"[{slug}] daily error: {e}")
        report["daily"] = {"error": str(e)}

    # 3. Top 视频（加 subscribersGained/Lost 用于订阅转化率）
    try:
        top = analytics_query(access_token, channel_id, start_date, end_date,
            "views,likes,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,"
            "subscribersGained,subscribersLost",
            dimensions="video", sort="-views", max_results="50")
        # 补充视频标题+发布日期（发布日期用于留存90天约束）
        video_ids = [row[0] for row in top.get("rows", []) if row]
        if video_ids:
            try:
                import urllib.request as ur
                vid_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={','.join(video_ids)}"
                vid_req = ur.Request(vid_url)
                vid_req.add_header("Authorization", f"Bearer {access_token}")
                with ur.urlopen(vid_req, timeout=15) as resp:
                    vid_data = json.loads(resp.read().decode())
                title_map = {v["id"]: v["snippet"]["title"] for v in vid_data.get("items", [])}
                thumb_map = {v["id"]: v["snippet"]["thumbnails"]["default"]["url"] for v in vid_data.get("items", [])}
                published_map = {v["id"]: v["snippet"].get("publishedAt", "") for v in vid_data.get("items", [])}
                report["video_meta"] = {"titles": title_map, "thumbnails": thumb_map, "published": published_map}
            except Exception:
                report["video_meta"] = {}
        report["top_videos"] = top
    except Exception as e:
        log.error(f"[{slug}] top_videos error: {e}")
        report["top_videos"] = {"error": str(e)}

    # 4. 地域
    try:
        report["geo"] = analytics_query(access_token, channel_id, start_date, end_date,
            "views,estimatedMinutesWatched", dimensions="country", sort="-views", max_results="10")
    except Exception as e:
        log.error(f"[{slug}] geo error: {e}")
        report["geo"] = {"error": str(e)}

    # 5. 流量来源
    try:
        report["traffic"] = analytics_query(access_token, channel_id, start_date, end_date,
            "views,estimatedMinutesWatched", dimensions="insightTrafficSourceType", sort="-views")
    except Exception as e:
        log.error(f"[{slug}] traffic error: {e}")
        report["traffic"] = {"error": str(e)}

    # 6. 受众画像（年龄×性别）
    try:
        raw_demo = analytics_query(access_token, channel_id, start_date, end_date,
            "viewerPercentage", dimensions="ageGroup,gender").get("rows", [])
        total_minutes = 0
        if report.get("summary") and report["summary"].get("rows"):
            summary_row = report["summary"]["rows"][0]
            summary_headers = report["summary"].get("headers", [])
            if "estimatedMinutesWatched" in summary_headers:
                total_minutes = summary_row[summary_headers.index("estimatedMinutesWatched")] or 0
        report["demographics"] = [
            {"age": r[0], "gender": r[1], "pct": round(r[2], 1),
             "est_minutes": round(total_minutes * r[2] / 100)}
            for r in raw_demo if len(r) >= 3 and r[2] > 0.5
        ]
    except Exception as e:
        log.error(f"[{slug}] demographics error: {e}")
        report["demographics"] = []

    # 7. 设备类型
    try:
        raw_device = analytics_query(access_token, channel_id, start_date, end_date,
            "views,estimatedMinutesWatched", dimensions="deviceType", sort="-views").get("rows", [])
        report["device"] = [
            {"type": r[0], "views": r[1], "minutes": round(r[2])}
            for r in raw_device if len(r) >= 3
        ]
    except Exception as e:
        log.error(f"[{slug}] device error: {e}")
        report["device"] = []

    report["subtitle_lang"] = []
    report["age_gender_watch"] = []

    # 8. 分段留存曲线（逐视频 audienceWatchRatio）
    # 约束：仅「近90天发布 + 播放量Top30」；断点续传；失败标记；不阻塞
    try:
        top_rows = report.get("top_videos", {}).get("rows", [])
        published_map = report.get("video_meta", {}).get("published", {})
        # 90 天发布过滤
        now = datetime.utcnow()
        def is_recent(vid):
            pub = published_map.get(vid, "")
            if not pub:
                return True  # 无发布日期视为近期，宁多勿少
            try:
                pub_dt = datetime.fromisoformat(pub.replace("Z", "+00:00")).replace(tzinfo=None)
                return (now - pub_dt).days <= 90
            except Exception:
                return True
        eligible = [row for row in top_rows if is_recent(row[0])][:30]  # Top30
        skipped_count = len(top_rows) - len(eligible)

        # 断点续传：读进度文件
        progress_file = DATA_DIR / f"{slug}_retention_progress.json"
        if progress_file.exists():
            progress = json.loads(progress_file.read_text())
            done_set = set(progress.get("done_video_ids", []))
            existing_videos = progress.get("videos", [])
            failed_set = set(progress.get("failed_video_ids", []))
            log.info(f"[{slug}] 留存断点续传: 已完成 {len(done_set)}, 失败 {len(failed_set)}")
        else:
            done_set, existing_videos, failed_set = set(), [], set()

        retention_videos = list(existing_videos)
        for row in eligible:
            vid_id, views = row[0], row[1]
            if vid_id in done_set or vid_id in failed_set:
                continue
            # metrics 顺序: views[1],likes[2],estimatedMinutesWatched[3],averageViewDuration[4],averageViewPercentage[5],...
            avg_dur = row[4] if len(row) > 4 else 0       # averageViewDuration（秒）
            avg_pct = row[5] if len(row) > 5 else 0       # averageViewPercentage（%）
            est_duration = (avg_dur or 0) / ((avg_pct or 1) / 100) if avg_pct else 0

            # 单视频重试1次
            success = False
            for attempt in range(2):
                try:
                    ret = analytics_query(access_token, channel_id, start_date, end_date,
                        "audienceWatchRatio", dimensions="elapsedVideoTimeRatio",
                        sort="elapsedVideoTimeRatio", filters=f"video=={vid_id}")
                    ret_rows = ret.get("rows", [])
                    if not ret_rows:
                        success = True  # 空数据也算完成，不重试
                        break
                    retention_1pct = retention_3min = retention_5min = None
                    min_ret = {"ratio": 1.0, "value": 1.0}
                    for rr in ret_rows:
                        ratio, value = rr[0], rr[1]
                        if ratio <= 0.01:
                            retention_1pct = value
                        if est_duration > 0 and ratio <= 180 / est_duration:
                            retention_3min = value
                        if est_duration > 0 and ratio <= 300 / est_duration:
                            retention_5min = value
                        if value < min_ret["value"]:
                            min_ret = {"ratio": round(ratio, 2), "value": round(value, 3)}
                    rebounds = []
                    prev = 1.0
                    for rr in ret_rows:
                        if rr[1] > prev * 1.05:
                            rebounds.append({"ratio": round(rr[0], 2), "value": round(rr[1], 3)})
                        prev = rr[1]
                    retention_videos.append({
                        "video_id": vid_id, "views": views,
                        "avg_view_pct": round(avg_pct or 0, 1),
                        "avg_view_duration": round(avg_dur or 0),
                        "est_duration": round(est_duration),
                        "retention_1pct": round(retention_1pct, 3) if retention_1pct else None,
                        "retention_3min": round(retention_3min, 3) if retention_3min else None,
                        "retention_5min": round(retention_5min, 3) if retention_5min else None,
                        "min_retention": min_ret,
                        "rebounds": rebounds,
                    })
                    done_set.add(vid_id)
                    success = True
                    break
                except Exception as e:
                    if attempt == 1:
                        log.warning(f"[{slug}] retention failed for {vid_id}: {e}")
                        failed_set.add(vid_id)
                    time.sleep(1)
            # 写进度（每完成一条就更新，允许中途 kill）
            progress_file.write_text(json.dumps({
                "done_video_ids": sorted(done_set),
                "failed_video_ids": sorted(failed_set),
                "videos": retention_videos,
            }, ensure_ascii=False, indent=2))
            time.sleep(0.5)

        if retention_videos:
            valid_1 = [v["retention_1pct"] for v in retention_videos if v.get("retention_1pct")]
            valid_3 = [v["retention_3min"] for v in retention_videos if v.get("retention_3min")]
            valid_5 = [v["retention_5min"] for v in retention_videos if v.get("retention_5min")]
            report["retention"] = {
                "has_data": True, "period_days": period,
                "video_count": len(retention_videos),
                "skipped_count": skipped_count,  # 超出90天/Top30 被跳过的数量
                "failed_count": len(failed_set),
                "failed_video_ids": sorted(failed_set),
                "avg_retention_1pct": round(sum(valid_1)/len(valid_1), 3) if valid_1 else None,
                "avg_retention_3min": round(sum(valid_3)/len(valid_3), 3) if valid_3 else None,
                "avg_retention_5min": round(sum(valid_5)/len(valid_5), 3) if valid_5 else None,
                "videos": retention_videos,
            }
        else:
            report["retention"] = {"has_data": False, "skipped_count": skipped_count,
                                    "failed_count": len(failed_set)}
        # 全部完成 → 删除进度文件
        if progress_file.exists() and not (set(v[0] for v in eligible) - done_set - failed_set):
            progress_file.unlink()
            log.info(f"[{slug}] 留存全部完成，删除进度文件")
    except Exception as e:
        log.error(f"[{slug}] retention error: {e}")
        report["retention"] = {"has_data": False, "error": str(e)}

    return report


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", help="只采集指定频道")
    parser.add_argument("--period", type=int, default=30, help="天数(默认30)")
    args = parser.parse_args()

    accounts = load_accounts()
    if not accounts:
        log.error("无已保存账号")
        return

    targets = {args.slug: accounts[args.slug]} if args.slug and args.slug in accounts else accounts
    results = {}

    for slug, info in targets.items():
        if not info.get("channel_id"):
            log.warning(f"[{slug}] 无 channel_id，跳过")
            continue

        log.info(f"[{slug}] 开始采集...")
        token = get_access_token(slug)
        if not token:
            log.error(f"[{slug}] token 无效，跳过")
            results[slug] = {"error": "token invalid"}
            continue

        try:
            report = collect_channel(slug, info["channel_id"], token, args.period)
            out_file = DATA_DIR / f"{slug}.json"
            # 原子写：先写 .tmp，成功后 rename（下游只读完成态）
            tmp_file = out_file.with_suffix(".json.tmp")
            tmp_file.write_text(json.dumps(report, ensure_ascii=False, indent=2))
            tmp_file.replace(out_file)
            log.info(f"[{slug}] ✅ 已保存 → {out_file}")
            results[slug] = "ok"
        except Exception as e:
            log.error(f"[{slug}] ❌ 采集失败: {e}")
            results[slug] = {"error": str(e)}

        time.sleep(2)  # 频道间间隔

    # 汇总
    ok = sum(1 for v in results.values() if v == "ok")
    fail = len(results) - ok
    log.info(f"采集完成: {ok} 成功, {fail} 失败")
    print(json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
