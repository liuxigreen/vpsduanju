#!/usr/bin/env python3
"""每日拉取 CTR 报表（YouTube Reporting API），28天滚动聚合到 yt_analytics/{slug}_ctr.json。

用法：
  python3 scripts/collect_ctr.py                 # 所有已建 job 的频道
  python3 scripts/collect_ctr.py --slug hk       # 指定频道

输出 schema:
  {
    "slug": "hk",
    "channel_id": "...",
    "collected_at": "2026-07-09T...",
    "window_days": 28,
    "date_range": {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"},
    "videos": {
      "<video_id>": {
        "impressions_28d": int,
        "ctr_28d": float,   # 展示加权平均，小数（0.15=15%）
        "days_with_data": int,
        "last_seen": "YYYY-MM-DD"
      }
    },
    "channel_totals": {
      "impressions_28d": int,
      "ctr_median_28d": float,
      "impressions_to_views_ratio": null  # 可选，由下游填
    },
    "status": "ok" | "pending"
  }

延迟约 48h；30 天前的老视频拿不到——诊断层遇到无 CTR 数据的视频，status 标"样本不足"。
"""
import json, sys, os, time, argparse, urllib.request as ur, urllib.error as ue
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from collect_yt_analytics import get_access_token  # 复用

REGISTRY = ROOT / "data" / "own" / "our_channels.json"
OUT_DIR = ROOT / "data" / "own" / "analytics"
OUT_DIR.mkdir(parents=True, exist_ok=True)

WINDOW_DAYS = 28


def list_reports(token, job_id):
    """列出 job 下所有 report metadata"""
    reports = []
    url = f"https://youtubereporting.googleapis.com/v1/jobs/{job_id}/reports?pageSize=200"
    while url:
        req = ur.Request(url)
        req.add_header("Authorization", f"Bearer {token}")
        with ur.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
        reports.extend(data.get("reports", []))
        npt = data.get("nextPageToken")
        url = (f"https://youtubereporting.googleapis.com/v1/jobs/{job_id}/reports"
               f"?pageSize=200&pageToken={npt}") if npt else None
    return reports


def download_csv(token, download_url):
    req = ur.Request(download_url)
    req.add_header("Authorization", f"Bearer {token}")
    with ur.urlopen(req, timeout=60) as resp:
        return resp.read().decode()


def parse_csv(csv_text):
    """返回 list[dict]，字段：date/channel_id/video_id/impressions/ctr"""
    lines = csv_text.splitlines()
    if not lines:
        return []
    header = lines[0].split(",")
    rows = []
    for line in lines[1:]:
        vals = line.split(",")
        if len(vals) != len(header):
            continue
        d = dict(zip(header, vals))
        try:
            d["video_thumbnail_impressions"] = int(d.get("video_thumbnail_impressions", 0))
            d["video_thumbnail_impressions_ctr"] = float(d.get("video_thumbnail_impressions_ctr", 0))
        except (ValueError, TypeError):
            continue
        rows.append(d)
    return rows


def collect_slug(slug, channel_id, job_id):
    tok = get_access_token(slug)
    if not tok:
        print(f"[{slug}] no OAuth token")
        return None
    try:
        reports = list_reports(tok, job_id)
    except ue.HTTPError as e:
        print(f"[{slug}] list_reports FAILED {e.code}: {e.read().decode()[:200]}")
        return None

    if not reports:
        print(f"[{slug}] job pending (no reports yet)")
        payload = _empty_payload(slug, channel_id, status="pending")
        _atomic_write(slug, payload)
        return payload

    # 只取最近 WINDOW_DAYS 天的报表
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=WINDOW_DAYS + 2)  # +2 缓冲，容忍延迟
    reports_recent = [r for r in reports
                      if datetime.fromisoformat(r["startTime"].replace("Z", "+00:00")) >= cutoff]
    # 按 startTime 排序
    reports_recent.sort(key=lambda r: r["startTime"])
    print(f"[{slug}] {len(reports)} total reports, {len(reports_recent)} in {WINDOW_DAYS}d window")

    # 逐 report 下载 + 聚合
    per_video = {}  # video_id -> {imp_sum, click_sum, days_set, last_date}
    for r in reports_recent:
        try:
            csv = download_csv(tok, r["downloadUrl"])
        except ue.HTTPError as e:
            print(f"[{slug}] download FAILED for {r['startTime']}: {e.code}, skip this day")
            continue
        for row in parse_csv(csv):
            vid = row.get("video_id")
            if not vid:
                continue
            imp = row["video_thumbnail_impressions"]
            ctr = row["video_thumbnail_impressions_ctr"]
            clicks = imp * ctr
            date = row.get("date", "")
            e = per_video.setdefault(vid, {"imp": 0, "clicks": 0.0, "days": set(), "last": ""})
            e["imp"] += imp
            e["clicks"] += clicks
            e["days"].add(date)
            if date > e["last"]:
                e["last"] = date

    videos_out = {}
    ctrs = []
    total_imp = 0
    for vid, e in per_video.items():
        if e["imp"] == 0:
            continue
        ctr_avg = e["clicks"] / e["imp"]
        # 日期格式 20260705 → 2026-07-05
        last = e["last"]
        last_fmt = f"{last[:4]}-{last[4:6]}-{last[6:8]}" if len(last) == 8 else last
        videos_out[vid] = {
            "impressions_28d": e["imp"],
            "ctr_28d": round(ctr_avg, 4),
            "days_with_data": len(e["days"]),
            "last_seen": last_fmt,
        }
        ctrs.append(ctr_avg)
        total_imp += e["imp"]

    start_dt = min((r["startTime"] for r in reports_recent), default="")
    end_dt = max((r["endTime"] for r in reports_recent), default="")
    payload = {
        "slug": slug,
        "channel_id": channel_id,
        "collected_at": now.isoformat(),
        "window_days": WINDOW_DAYS,
        "date_range": {"start": start_dt[:10], "end": end_dt[:10]},
        "videos": videos_out,
        "channel_totals": {
            "impressions_28d": total_imp,
            "ctr_median_28d": round(statistics.median(ctrs), 4) if ctrs else 0.0,
            "video_count": len(videos_out),
        },
        "status": "ok" if videos_out else "pending",
    }
    _atomic_write(slug, payload)
    print(f"[{slug}] OK: {len(videos_out)} videos, "
          f"total_impressions={total_imp}, median_ctr={payload['channel_totals']['ctr_median_28d']}")
    return payload


def _empty_payload(slug, channel_id, status):
    return {
        "slug": slug, "channel_id": channel_id,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "window_days": WINDOW_DAYS, "date_range": {}, "videos": {},
        "channel_totals": {"impressions_28d": 0, "ctr_median_28d": 0.0, "video_count": 0},
        "status": status,
    }


def _atomic_write(slug, payload):
    out = OUT_DIR / f"{slug}_ctr.json"
    tmp = out.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    tmp.replace(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="only this slug")
    args = ap.parse_args()

    reg = json.loads(REGISTRY.read_text())
    channels = reg if isinstance(reg, list) else reg.get("channels", [])
    for c in channels:
        slug = c.get("slug")
        if args.slug and slug != args.slug:
            continue
        job_id = c.get("ctr_job_id")
        if not job_id:
            print(f"[{slug}] no ctr_job_id, skip (run create_ctr_reporting_job.py first)")
            continue
        try:
            collect_slug(slug, c.get("channel_id", ""), job_id)
        except Exception as e:
            print(f"[{slug}] FAILED: {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
