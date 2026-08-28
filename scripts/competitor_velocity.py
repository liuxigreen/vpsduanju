#!/usr/bin/env python3
"""
竞品频道涨速/动量计算 v2
两个指标:
  1. video_momentum 播放动量 — 近30天发布视频的日均播放(views/age), 精确整数, 最灵敏
  2. subs_velocity_weekly 订阅涨速 — tracking历史 ≥14天窗口(跨过YouTube订阅数取整分辨率)

用法:
  python3 scripts/competitor_velocity.py             # 用已存数据计算（不调API）
  python3 scripts/competitor_velocity.py --refresh   # 先拉实时数据(~520 units)再计算

输出字段(写回 competitors_channels_all.json 每个 channel 的 tracking 字典):
  - video_momentum: 近30天视频日均播放 (无近30天视频则不写)
  - momentum_videos: 参与计算的视频数
  - momentum_videos_detail: 近30天视频明细[{id,title,published_at,views,tags}] (refresh时更新)
  - subs_velocity_weekly: 订阅涨速/周 (窗口≥14天)
  - velocity_window_days / velocity_asof / velocity_updated_at

--refresh 同时: 更新 ch.subscribers + 追加今日tracking点(追加不覆盖原则)。

数据现状说明: tracking/视频数据曾停在 2026-08-20 (cron故障, 已修复);
速度类指标依赖新鲜数据, 建议 --refresh 每周跑 1-2 次。
"""
import json
import sys
import time
from datetime import datetime, date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DATA_DIR = ROOT / "data"
PANEL_DATA = DATA_DIR / "competitors_channels_all.json"
TRACKING_DIR = DATA_DIR / "competitor_tracking"

MOMENTUM_MAX_AGE_DAYS = 30   # 视频动量只看近30天发布的
SUBS_MIN_WINDOW_DAYS = 14    # 订阅窗口下限(跨过取整分辨率)
MOMENTUM_KEEP_VIDEOS = 20    # 每频道保留的动量视频明细上限


def parse_date(s):
    try:
        return date.fromisoformat(str(s)[:10])
    except (ValueError, TypeError):
        return None


# ---------------- live refresh (YouTube API) ----------------

def refresh_live_data(channels, verbose=True):
    """拉实时订阅+近30天视频。返回 {cid: [video...]}。复用 weekly_snapshot 的 API 层。"""
    from competitor_weekly_snapshot import _yt_api, fetch_channel_stats

    channel_ids = [c["channel_id"] for c in channels if c.get("channel_id")]
    today = date.today()

    # 1) 批量: 最新订阅 + uploads playlist (50/批, 1 unit)
    subs_map, _created = fetch_channel_stats(channel_ids)
    uploads_map = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i + 50]
        try:
            data = _yt_api("channels", part="contentDetails", id=",".join(batch), maxResults=50)
            for item in data.get("items", []):
                up = (item.get("contentDetails", {}).get("relatedPlaylists", {}) or {}).get("uploads")
                if up:
                    uploads_map[item["id"]] = up
            time.sleep(0.3)
        except Exception as e:
            print(f"  ⚠️ uploads批次 {i}: {e}")
    if verbose:
        print(f"  订阅: {len(subs_map)} | uploads playlist: {len(uploads_map)}")

    # 2) 每频道: 近30天视频ID+日期 (1 unit/频道)
    recent = {}   # cid -> [(video_id, published_date)]
    for n, (cid, up) in enumerate(uploads_map.items(), 1):
        try:
            data = _yt_api("playlistItems", part="contentDetails", playlistId=up,
                           maxResults=30)
            vids = []
            for item in data.get("items", []):
                cd = item.get("contentDetails", {})
                vid = cd.get("videoId")
                pub = parse_date(cd.get("videoPublishedAt"))
                if vid and pub and (today - pub).days <= MOMENTUM_MAX_AGE_DAYS:
                    vids.append((vid, pub))
            if vids:
                recent[cid] = vids
        except Exception as e:
            if verbose and n <= 3:
                print(f"  ⚠️ playlistItems {cid}: {e}")
        if n % 100 == 0 and verbose:
            print(f"  playlistItems进度: {n}/{len(uploads_map)}")
        time.sleep(0.15)

    # 3) 批量: 视频统计+标签 (50/批, 1 unit)
    all_vids = [(cid, v, p) for cid, lst in recent.items() for (v, p) in lst]
    stats_map = {}
    for i in range(0, len(all_vids), 50):
        batch = [v for _, v, _ in all_vids[i:i + 50]]
        try:
            data = _yt_api("videos", part="statistics,snippet", id=",".join(batch), maxResults=50)
            for item in data.get("items", []):
                st = item.get("statistics", {})
                sn = item.get("snippet", {})
                stats_map[item["id"]] = {
                    "views": int(st.get("viewCount", 0)),
                    "title": sn.get("title", ""),
                    "tags": sn.get("tags", []) or [],
                }
            time.sleep(0.2)
        except Exception as e:
            print(f"  ⚠️ videos批次 {i}: {e}")

    # 4) 回写: subscribers + tracking今日点 + momentum明细
    updated = 0
    today_str = today.isoformat()
    for ch in channels:
        cid = ch.get("channel_id")
        if not cid:
            continue
        if cid in subs_map:
            ch["subscribers"] = subs_map[cid]
            tk = ch.setdefault("tracking", {})
            tf = TRACKING_DIR / f"{cid}.json"
            try:
                history = json.loads(tf.read_text()) if tf.exists() else []
            except (json.JSONDecodeError, OSError):
                history = []
            if history and history[-1].get("date") == today_str:
                history[-1]["subscribers"] = subs_map[cid]
            else:
                history.append({"date": today_str, "subscribers": subs_map[cid],
                                "avg_views": ch.get("avg_views", 0)})
            tf.write_text(json.dumps(history, ensure_ascii=False, indent=2))
        vids = []
        for (vid, pub) in recent.get(cid, []):
            st = stats_map.get(vid, {})
            vids.append({"id": vid, "published_at": pub.isoformat(),
                         "views": st.get("views", 0),
                         "title": st.get("title", ""), "tags": st.get("tags", [])})
        if vids:
            tk = ch.setdefault("tracking", {})
            tk["momentum_videos_detail"] = sorted(vids, key=lambda x: x["published_at"], reverse=True)[:MOMENTUM_KEEP_VIDEOS]
            updated += 1
    if verbose:
        print(f"  实时回写: 订阅{len(subs_map)} | 动量明细{updated}")
    return recent


# ---------------- computation ----------------

def compute_video_momentum(videos_detail, today):
    """近30天发布视频的日均播放均值。返回 (momentum, n) 或 (None, 0)。"""
    if not isinstance(videos_detail, list):
        return None, 0
    dailies = []
    for v in videos_detail:
        if not isinstance(v, dict):
            continue
        pub = parse_date(v.get("published_at"))
        views = v.get("views") or 0
        if not pub or views <= 0:
            continue
        age = (today - pub).days
        if age > MOMENTUM_MAX_AGE_DAYS:
            continue
        dailies.append(views / max(age, 1))
    if not dailies:
        return None, 0
    return round(sum(dailies) / len(dailies)), len(dailies)


def compute_subs_velocity(tracking_history):
    """订阅涨速: 最新有效点 vs ≥14天前最近点。返回 dict 或 None。"""
    if not isinstance(tracking_history, list):
        return None
    pts = []
    for rec in tracking_history:
        if not isinstance(rec, dict):
            continue
        d = parse_date(rec.get("date"))
        subs = rec.get("subscribers") or 0
        if d and subs > 0:
            pts.append((d, subs))
    if len(pts) < 2:
        return None
    pts.sort(key=lambda x: x[0])
    last_d, last_subs = pts[-1]
    candidates = [p for p in pts if (last_d - p[0]).days >= SUBS_MIN_WINDOW_DAYS]
    if not candidates:
        return None
    prev_d, prev_subs = candidates[-1]
    days = (last_d - prev_d).days
    if days <= 0:
        return None
    return {
        "subs_velocity_weekly": round((last_subs - prev_subs) / days * 7),
        "velocity_window_days": days,
        "velocity_asof": last_d.isoformat(),
    }


def compute_all(verbose=True):
    if not PANEL_DATA.exists():
        print(f"❌ {PANEL_DATA} 不存在")
        return 0
    today = date.today()
    data = json.loads(PANEL_DATA.read_text())
    channels = data.get("channels", [])
    n_momentum = n_subs = 0
    for ch in channels:
        cid = ch.get("channel_id")
        if not cid:
            continue
        tk = ch.setdefault("tracking", {})
        tk["velocity_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        # 1) 播放动量（精确、领先指标）
        m, n = compute_video_momentum(tk.get("momentum_videos_detail") or [], today)
        if m is not None:
            tk["video_momentum"] = m
            tk["momentum_videos"] = n
            n_momentum += 1
        else:
            tk.pop("video_momentum", None)
            tk.pop("momentum_videos", None)

        # 2) 订阅涨速（≥14天窗口）
        tf = TRACKING_DIR / f"{cid}.json"
        v = None
        if tf.exists():
            try:
                v = compute_subs_velocity(json.loads(tf.read_text()))
            except (json.JSONDecodeError, OSError):
                v = None
        if v:
            tk.update(v)
            n_subs += 1
        else:
            for k in ("subs_velocity_weekly", "velocity_window_days", "velocity_asof"):
                tk.pop(k, None)

    PANEL_DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    if verbose:
        print(f"✅ 动量/涨速计算完成: 播放动量 {n_momentum}/{len(channels)} | 订阅涨速 {n_subs}/{len(channels)}")
        ranked = sorted((c for c in channels if c.get("tracking", {}).get("video_momentum")),
                        key=lambda c: c["tracking"]["video_momentum"], reverse=True)
        print("\n🚀 播放动量 Top10:")
        for i, ch in enumerate(ranked[:10], 1):
            t = ch["tracking"]
            print(f"  {i}. {ch.get('name','?')[:26]:28s} {t['video_momentum']}/天 "
                  f"({t['momentum_videos']}条近30天) 订阅{ch.get('subscribers',0)} {ch.get('language','')}")
        ranked2 = sorted((c for c in channels if c.get("tracking", {}).get("subs_velocity_weekly")),
                         key=lambda c: c["tracking"]["subs_velocity_weekly"], reverse=True)
        print("\n📈 订阅涨速 Top5:")
        for i, ch in enumerate(ranked2[:5], 1):
            t = ch["tracking"]
            print(f"  {i}. {ch.get('name','?')[:26]:28s} +{t['subs_velocity_weekly']}/周 "
                  f"(窗口{t['velocity_window_days']}天, 截至{t['velocity_asof']})")
    return 0


if __name__ == "__main__":
    if not PANEL_DATA.exists():
        print(f"❌ {PANEL_DATA} 不存在")
        sys.exit(1)
    data = json.loads(PANEL_DATA.read_text())
    chs = data.get("channels", [])
    if "--refresh" in sys.argv:
        print("🔄 拉取实时数据 (YouTube API ~520 units)...")
        refresh_live_data(chs)
        PANEL_DATA.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    sys.exit(compute_all())
