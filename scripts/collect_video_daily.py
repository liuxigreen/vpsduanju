#!/usr/bin/env python3
"""
竞品视频级每日采集 + 增量计算 + 爆款预警
=========================================
数据流:
  1. watchlist = competitors_channels_all.json 里所有频道的 momentum_videos_detail + videos_detail 视频ID
  2. videos.list 批量拉当前播放量 (~109 units/天)
  3. 与昨日快照 diff → views_delta_24h (视频级24h播放增量)
  4. 存 data/video_views_history/{date}.json (滚动保留 N days)
  5. 预警规则 → data/alerts_latest.json → 面板 + Telegram推送

预警规则:
  - breakout:  新视频(≤7天)累计 views ≥ BREAKOUT_NEW_VIEWS
  - spike:     24h增量 ≥ SPIKE_ABS 且相对自身日均增幅 ≥ SPIKE_RATIO (或首日数据直接看绝对值)
  - early_rise: 发布≤3天 且 24h增量 ≥ EARLY_RISE_VIEWS (起量信号)

面板API: panel_v3.py /api/competitor-alerts 读 alerts_latest.json + video_views_history 最新两天
Telegram: --notify 直接推 (cron 每日调用)

用法:
  python3 scripts/collect_video_daily.py            # 采集+计算+写预警文件
  python3 scripts/collect_video_daily.py --notify   # 同上 + Telegram推送预警摘要
  python3 scripts/collect_video_daily.py --no-fetch # 不调API, 用已有快照重算
"""
import json
import sys
import time
import argparse
from pathlib import Path
from datetime import datetime, timedelta

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DATA_DIR = ROOT / "data"
PANEL_DATA = DATA_DIR / "competitors_channels_all.json"
HISTORY_DIR = DATA_DIR / "video_views_history"
ALERTS_FILE = DATA_DIR / "alerts_latest.json"
HISTORY_DIR.mkdir(exist_ok=True)

API_KEYS_FILE = Path.home() / ".hermes" / "duanju" / "api_keys.json"
API_KEY_FILE = Path.home() / ".hermes" / "duanju" / "api_key.txt"

# 预警阈值
BREAKOUT_NEW_AGE_DAYS = 7
BREAKOUT_NEW_VIEWS = 50_000
SPIKE_ABS = 100_000          # 24h增量绝对值门槛
SPIKE_RATIO = 3.0            # 相对基线增幅(需要≥3天历史才启用)
EARLY_RISE_AGE_DAYS = 3
EARLY_RISE_VIEWS = 10_000
HISTORY_KEEP_DAYS = 45       # 滚动保留天数

# ── YouTube API ──
def _load_keys():
    keys = []
    if API_KEYS_FILE.exists():
        try:
            keys = json.loads(API_KEYS_FILE.read_text())
        except Exception:
            pass
    if not keys and API_KEY_FILE.exists():
        k = API_KEY_FILE.read_text().strip()
        if k:
            keys = [k]
    if not keys:
        raise RuntimeError("No YouTube API key")
    return keys

_KEY_ROTATE = {"i": 0}

def _yt_api(endpoint: str, **params) -> dict:
    keys = _load_keys()
    import httpx
    url = f"https://www.googleapis.com/youtube/v3/{endpoint}"
    for attempt in range(len(keys)):
        params["key"] = keys[(_KEY_ROTATE["i"] + attempt) % len(keys)]
        try:
            resp = httpx.get(url, params=params, timeout=30)
            if resp.status_code == 403 and "quotaExceeded" in resp.text:
                continue  # 轮换下一个key
            resp.raise_for_status()
            _KEY_ROTATE["i"] = (_KEY_ROTATE["i"] + attempt) % len(keys)
            return resp.json()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                continue
            raise
    raise RuntimeError("All API keys exhausted")

# ── watchlist 构建 ──
def build_watchlist() -> dict:
    """video_id -> {title, channel_id, channel_name, language, published_at}"""
    data = json.loads(PANEL_DATA.read_text())
    watch = {}
    for ch in data.get("channels", []):
        cid = ch.get("channel_id", "")
        seen = set()
        for v in (ch.get("tracking") or {}).get("momentum_videos_detail") or []:
            vid = v.get("id")
            if vid and vid not in seen:
                seen.add(vid)
                watch[vid] = {
                    "title": v.get("title", ""), "channel_id": cid,
                    "channel": ch.get("name", ""), "language": ch.get("language", ""),
                    "published_at": v.get("published_at", ""),
                }
        for v in ch.get("videos_detail") or []:
            vid = v.get("video_id") or v.get("id")
            if vid and vid not in seen:
                seen.add(vid)
                watch[vid] = {
                    "title": v.get("title", ""), "channel_id": cid,
                    "channel": ch.get("name", ""), "language": ch.get("language", ""),
                    "published_at": v.get("published_at", ""),
                }
    return watch

def fetch_current_views(video_ids: list) -> dict:
    """批量拉当前播放量, 50/批"""
    result = {}
    ids = list(video_ids)
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        try:
            data = _yt_api("videos", part="statistics", id=",".join(batch), maxResults=50)
            for item in data.get("items", []):
                result[item["id"]] = int(item.get("statistics", {}).get("viewCount", 0))
            time.sleep(0.15)
        except Exception as e:
            print(f"  ⚠️ videos批次 {i}: {e}")
        if (i // 50) % 20 == 19:
            print(f"  进度: {i + 50}/{len(ids)}")
    return result

# ── 历史快照 ──
def load_history(days: int = HISTORY_KEEP_DAYS) -> dict:
    """date_str -> {video_id: views}, 只保留最近 days 天"""
    out = {}
    for f in sorted(HISTORY_DIR.glob("*.json")):
        if f.name.startswith("_"):
            continue  # 跳过 _meta.json 等内部文件
        ds = f.stem
        try:
            datetime.strptime(ds, "%Y-%m-%d")
        except ValueError:
            continue
        out[ds] = json.loads(f.read_text())
    # 清理过期
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    for ds in list(out):
        if ds < cutoff:
            (HISTORY_DIR / f"{ds}.json").unlink()
            del out[ds]
    return out

# ── 增量 + 预警 ──
def compute_deltas_and_alerts(today: str, watch: dict):
    history = load_history()
    dates = sorted(history.keys())
    if today not in history:
        print(f"⚠️ 今日快照缺失(采集失败或--no-fetch且无文件)")
    if len(dates) < 2:
        print(f"📦 历史快照仅{len(dates)}天, 首日只建基线, 预警明天开始")
        if today in history:
            return [], len(dates)
        return [], len(dates)

    today_snap = history.get(today, {})
    # 基线 = 昨日快照 (24h增量)
    yday = dates[-2] if dates[-1] == today else dates[-1]
    yday_snap = history[yday]
    y2 = dates[-3] if len(dates) >= 3 and dates[-2] == yday else None
    y2_snap = history.get(y2, {}) if y2 else {}
    span_days = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(yday, "%Y-%m-%d")).days or 1

    alerts = []
    n_delta = 0
    for vid, cur_views in today_snap.items():
        meta = watch.get(vid)
        if not meta:
            continue
        prev = yday_snap.get(vid)
        if prev is None:
            continue
        delta = cur_views - prev
        if delta <= 0:
            continue
        n_delta += 1
        pub = meta.get("published_at", "")
        try:
            age = (datetime.strptime(today, "%Y-%m-%d") - datetime.strptime(pub[:10], "%Y-%m-%d")).days
        except ValueError:
            age = 999
        # 基线日均 (前一天相对前二天)
        base_daily = None
        if y2 and y2_snap.get(vid) is not None:
            base_daily = max((prev - y2_snap[vid]) / max(span_days - 1, 1), 0)
        alert = {
            "video_id": vid, "title": meta["title"], "channel": meta["channel"],
            "channel_id": meta["channel_id"], "language": meta["language"],
            "published_at": pub, "age_days": age,
            "views": cur_views, "delta_24h": delta,
            "baseline_daily": round(base_daily) if base_daily is not None else None,
        }
        reasons = []
        if age <= BREAKOUT_NEW_AGE_DAYS and cur_views >= BREAKOUT_NEW_VIEWS:
            reasons.append("breakout")
        if delta >= SPIKE_ABS and (base_daily is None or delta >= base_daily * SPIKE_RATIO):
            reasons.append("spike")
        if age <= EARLY_RISE_AGE_DAYS and delta >= EARLY_RISE_VIEWS:
            reasons.append("early_rise")
        if reasons:
            alert["alert_types"] = reasons
            alerts.append(alert)

    alerts.sort(key=lambda a: -a["delta_24h"])
    print(f"📊 增量计算: {n_delta}视频有增量, 预警 {len(alerts)} 条")
    return alerts, len(dates)

def save_alerts(alerts: list, n_days_history: int):
    out = {
        "schema_version": "1.0",
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "history_days": n_days_history,
        "thresholds": {
            "breakout": f"≤{BREAKOUT_NEW_AGE_DAYS}天且≥{BREAKOUT_NEW_VIEWS:,}播放",
            "spike": f"24h增量≥{SPIKE_ABS:,}" + (f"且≥基线{SPIKE_RATIO}x" ),
            "early_rise": f"发布≤{EARLY_RISE_AGE_DAYS}天且24h增量≥{EARLY_RISE_VIEWS:,}",
        },
        "alerts": alerts[:100],
    }
    ALERTS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"💾 预警已写入 {ALERTS_FILE.name} ({len(out['alerts'])}条)")

# ── Telegram ──
def notify_telegram(alerts: list):
    if not alerts:
        print("📭 无预警, 不推送")
        return
    token = None
    env_file = Path.home() / ".hermes" / ".env"
    if env_file.exists():
        for line in env_file.read_text().split("\n"):
            if line.startswith("TELEGRAM_BOT_TOKEN="):
                token = line.split("=", 1)[1].strip()
                break
    if not token:
        print("⚠️ 无TELEGRAM_BOT_TOKEN, 跳过推送")
        return
    top = alerts[:10]
    lines = ["🔔 竞品爆款预警 Top10", ""]
    type_icon = {"breakout": "🚀", "spike": "⚡", "early_rise": "🌱"}
    for a in top:
        icons = "".join(type_icon.get(t, "•") for t in a["alert_types"])
        lines.append(
            f"{icons} +{a['delta_24h']:,}/24h · {a['views']:,}总\n"
            f"「{a['title'][:46]}」\n"
            f"{a['channel']} · {a['language']} · {a['age_days']}天前发"
        )
        lines.append("")
    import requests
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": "6305628029", "text": "\n".join(lines), "disable_web_page_preview": True},
        timeout=15)
    print("📨 Telegram推送:", "OK" if resp.ok else f"FAIL {resp.status_code}")

# ── main ──
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--notify", action="store_true", help="推送Telegram预警")
    ap.add_argument("--no-fetch", action="store_true", help="不调API, 只重算")
    args = ap.parse_args()

    today = datetime.now().strftime("%Y-%m-%d")
    watch = build_watchlist()
    print(f"📋 watchlist: {len(watch)} 视频")

    if not args.no_fetch:
        views = fetch_current_views(list(watch.keys()))
        print(f"🌐 拉到 {len(views)} 视频播放量")
        (HISTORY_DIR / f"{today}.json").write_text(json.dumps(views, ensure_ascii=False))
        # 同时存视频元数据索引(去重合并, 面板详情用)
        meta_file = HISTORY_DIR / "_meta.json"
        old = json.loads(meta_file.read_text()) if meta_file.exists() else {}
        old.update(watch)
        meta_file.write_text(json.dumps(old, ensure_ascii=False))

    alerts, n_days = compute_deltas_and_alerts(today, watch)
    save_alerts(alerts, n_days)
    if args.notify:
        notify_telegram(alerts)

if __name__ == "__main__":
    main()
