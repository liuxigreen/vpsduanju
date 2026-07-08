#!/usr/bin/env python3
"""
feishu_bitable.py — 自有账号数据写入飞书多维表格

功能：
- 创建多维表格（自有账号日报 + 视频明细）
- 每日汇总写入自有账号日报表
- 每频道10天视频写入视频明细表

用法：
    python3 scripts/feishu_bitable.py                    # 写入今日数据
    python3 scripts/feishu_bitable.py --create           # 创建新表格
    python3 scripts/feishu_bitable.py --app-token xxx    # 指定已有表格
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(os.path.expanduser("~/.hermes/.env"))

try:
    import lark_oapi as lark
except ImportError:
    print("❌ 需要 install lark_oapi: pip install lark_oapi")
    sys.exit(1)

app_id = os.environ.get("FEISHU_APP_ID", "")
app_secret = os.environ.get("FEISHU_APP_SECRET", "")

DATA_DIR = ROOT / "data"
BITABLE_REFS = DATA_DIR / "feishu_bitable_refs.json"


def get_client():
    return lark.Client.builder().app_id(app_id).app_secret(app_secret).build()


def load_refs() -> dict:
    if BITABLE_REFS.exists():
        return json.loads(BITABLE_REFS.read_text())
    return {}


def save_refs(refs: dict):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BITABLE_REFS.write_text(json.dumps(refs, ensure_ascii=False, indent=2))


def _get_tenant_token() -> str:
    """获取 tenant_access_token"""
    import urllib.request
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    data = json.dumps({"app_id": app_id, "app_secret": app_secret}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        result = json.loads(resp.read())
    return result.get("tenant_access_token", "")


def _api_post(url: str, token: str, data: dict) -> dict:
    """POST 请求飞书 API"""
    import urllib.request
    import urllib.error
    body = json.dumps(data).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        print(f"  ❌ HTTP {e.code}: {error_body[:500]}")
        try:
            return json.loads(error_body)
        except Exception:
            return {"code": e.code, "msg": error_body[:200]}


def create_bitable() -> dict:
    """创建多维表格，返回 {app_token, daily_table_id, video_table_id}"""
    token = _get_tenant_token()

    # 创建多维表格
    result = _api_post(
        "https://open.feishu.cn/open-apis/bitable/v1/apps",
        token,
        {"name": f"自有账号分析 {datetime.now().strftime('%Y-%m-%d')}"}
    )

    if result.get("code") != 0:
        raise Exception(f"创建失败: {result.get('msg', '')}")

    app_info = result.get("data", {}).get("app", {})
    app_token = app_info.get("app_token", "")
    url = app_info.get("url", "")
    print(f"✅ 创建多维表格: {app_token}")

    # 创建自有账号日报表（含字段定义）
    token2 = _get_tenant_token()
    daily_table = _create_table(token2, app_token, "自有账号日报", DAILY_TABLE_FIELDS)
    # 创建视频明细表
    video_table = _create_table(token2, app_token, "视频明细", VIDEO_TABLE_FIELDS)

    refs = {
        "app_token": app_token,
        "daily_table_id": daily_table,
        "video_table_id": video_table,
        "created_at": datetime.now().isoformat(),
        "url": url
    }
    save_refs(refs)
    print(f"📎 链接: {url}")
    return refs


def _create_table(token: str, app_token: str, name: str, fields: list) -> str:
    """创建数据表"""
    result = _api_post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables",
        token,
        {
            "table": {
                "name": name,
                "fields": fields
            }
        }
    )
    table_id = result.get("data", {}).get("table_id", "")
    if not table_id:
        print(f"  ⚠️ 创建表 {name} 失败: {result}")
    else:
        print(f"  ✅ 创建表: {name} ({table_id})")
    return table_id


# ── 字段定义（飞书 API 格式: field_name + type）──
# type: 1=文本 2=数字 3=单选 5=日期 7=复选框 11=人员 13=电话 15=超链接 17=附件 18=单向关联 19=查找引用 20=公式 22=地理位置 1001=创建时间 1002=修改时间 1003=创建人 1004=修改人

DAILY_TABLE_FIELDS = [
    {"field_name": "日期", "type": 5},
    {"field_name": "频道", "type": 1},
    {"field_name": "运营", "type": 1},
    {"field_name": "语种", "type": 3, "property": {"options": [  # 单选
        {"name": "英文", "color": 0},
        {"name": "繁中", "color": 1},
        {"name": "西语", "color": 2},
        {"name": "葡萄牙", "color": 3},
        {"name": "印尼", "color": 4},
    ]}},
    {"field_name": "赛道", "type": 1},
    {"field_name": "订阅", "type": 2},
    {"field_name": "总播放", "type": 2},
    {"field_name": "视频数", "type": 2},
    {"field_name": "日增订阅", "type": 2},
    {"field_name": "日均播放", "type": 2},
    {"field_name": "点赞率%", "type": 2},
    {"field_name": "播订比", "type": 2},
    {"field_name": "近10均播", "type": 2},
    {"field_name": "发布频率", "type": 2},
    {"field_name": "健康状态", "type": 3, "property": {"options": [  # 单选带颜色
        {"name": "标杆", "color": 1},   # 绿
        {"name": "健康", "color": 1},   # 绿
        {"name": "转化差", "color": 4}, # 黄
        {"name": "最差", "color": 0},   # 红
        {"name": "零互动", "color": 0}, # 红
    ]}},
    {"field_name": "异常提醒", "type": 3, "property": {"options": [  # 单选
        {"name": "无", "color": 1},       # 绿
        {"name": "赞率低", "color": 0},   # 红
        {"name": "千订慢", "color": 4},   # 黄
        {"name": "需关注", "color": 0},   # 红
    ]}},
]

VIDEO_TABLE_FIELDS = [
    {"field_name": "日期", "type": 5},
    {"field_name": "频道", "type": 1},
    {"field_name": "视频标题", "type": 1},
    {"field_name": "发布时间", "type": 5},
    {"field_name": "播放量", "type": 2},
    {"field_name": "点赞数", "type": 2},
    {"field_name": "点赞率%", "type": 2},
    {"field_name": "评论数", "type": 2},
    {"field_name": "观看时长(分)", "type": 2},
    {"field_name": "平均观看时长(秒)", "type": 2},
    {"field_name": "平均观看%", "type": 2},
    {"field_name": "标签", "type": 1},
]


def _date_to_ms(date_str: str) -> int:
    """日期字符串转毫秒时间戳（飞书日期字段格式）"""
    try:
        if "T" in date_str:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        else:
            dt = datetime.strptime(date_str, "%Y-%m-%d")
        return int(dt.timestamp() * 1000)
    except Exception:
        return int(datetime.now().timestamp() * 1000)


def _detect_anomalies(ch: dict) -> list[str]:
    """检测异常（含日环比异常）"""
    alerts = []

    # 粘度异常: averageViewPercentage < 50%
    avg_pct = ch.get("avg_view_percentage", 0)
    if avg_pct and avg_pct < 50:
        alerts.append(f"粘度低({avg_pct:.0f}%)")

    # CTR异常: < 7%
    ctr = ch.get("ctr", 0)
    if ctr and ctr < 7:
        alerts.append(f"CTR低({ctr:.1f}%)")

    # 赞率异常: < 1%
    lr = ch.get("like_rate", 0)
    if lr and lr < 1:
        alerts.append(f"赞率低({lr:.2f}%)")

    # 千订天数异常: > 365天
    d1k = ch.get("days_to_1k", 0)
    if d1k and d1k > 365:
        alerts.append(f"千订慢({d1k}天)")

    # 日环比异常
    g = ch.get("growth", {})
    if g.get("has_prev"):
        if g.get("subscribers_change", 0) < 0:
            alerts.append("掉粉")
        if g.get("views_change_pct", 0) < -20:
            alerts.append("播放骤降")
        if g.get("like_rate_change", 0) < -0.5:
            alerts.append("赞率下跌")
        if g.get("videos_change", 0) == 0:
            alerts.append("未发布")

    return alerts


def clear_table(refs: dict, table_type: str = "both"):
    """清除表格数据"""
    token = _get_tenant_token()
    app_token = refs["app_token"]

    tables_to_clear = []
    if table_type in ("daily", "both"):
        tables_to_clear.append(("daily_table_id", "自有账号日报"))
    if table_type in ("video", "both"):
        tables_to_clear.append(("video_table_id", "视频明细"))

    for key, name in tables_to_clear:
        table_id = refs.get(key)
        if not table_id:
            continue

        # 获取所有记录ID
        url = f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records?page_size=500"
        result = _api_get(url, token)
        records = result.get("data", {}).get("items", [])

        if not records:
            print(f"  ℹ️ {name}: 无数据")
            continue

        # 批量删除
        record_ids = [r["record_id"] for r in records]
        delete_result = _api_post(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_delete",
            token,
            {"records": record_ids}
        )

        if delete_result.get("code") == 0:
            print(f"  🗑️ {name}: 清除 {len(record_ids)} 条记录")
        else:
            print(f"  ❌ {name} 清除失败: {delete_result.get('msg', '')}")


def _api_get(url: str, token: str) -> dict:
    """GET 请求飞书 API"""
    import urllib.request
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


def write_daily_data(refs: dict, analysis_data: dict):
    """写入自有账号日报数据（含日增量）"""
    token = _get_tenant_token()
    app_token = refs["app_token"]
    table_id = refs["daily_table_id"]
    today = datetime.now().strftime("%Y-%m-%d")

    channels = analysis_data.get("channels", [])
    records = []

    for ch in channels:
        alerts = _detect_anomalies(ch)
        # 优先用 growth 中的真实日增量
        g = ch.get("growth", {})
        has_g = g.get("has_prev", False)
        daily_sub_gain = g.get("subscribers_change", 0) if has_g else ch.get("daily_subs", 0)
        daily_view_gain = g.get("views_change", 0) if has_g else ch.get("daily_views", 0)

        # 规范化健康状态: 选项只能为 标杆/健康/转化差/最差/零互动
        raw_health = ch.get("health", "")
        VALID_HEALTH = {"标杆", "健康", "转化差", "最差", "零互动"}
        if raw_health not in VALID_HEALTH:
            # 映射 "一般" -> "健康"
            raw_health = "健康"

        # 异常提醒: 单选字段必须传 {"name": "..."} 或空
        # 只取第一个异常作为单选值，无异常传 "无"
        alert_text = "无"
        if alerts:
            # 多个异常只传第一个，因为这是单选字段
            alert_text = alerts[0]

        record = {
            "fields": {
                "日期": _date_to_ms(today),
                "频道": ch.get("name", ""),
                "运营": ch.get("operator", ""),
                "语种": ch.get("language", ""),
                "赛道": ch.get("niche", ""),
                "订阅": ch.get("subscribers", 0),
                "总播放": ch.get("total_views", 0),
                "视频数": ch.get("videos", 0),
                "日增订阅": daily_sub_gain,
                "日均播放": daily_view_gain,
                "点赞率%": ch.get("like_rate", 0),
                "播订比": ch.get("view_sub_ratio", 0),
                "近10均播": ch.get("avg_views_10", 0),
                "发布频率": ch.get("publish_freq", 0),
                "健康状态": raw_health,
                "异常提醒": alert_text,
            }
        }
        records.append(record)

    # 批量写入
    result = _api_post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
        token,
        {"records": records}
    )

    if result.get("code") == 0:
        print(f"✅ 自有账号日报: 写入 {len(records)} 条记录")
    else:
        print(f"❌ 自有账号日报写入失败: {result.get('msg', '')}")


def write_video_data(refs: dict, channel_name: str, videos: list):
    """写入单频道视频明细"""
    token = _get_tenant_token()
    app_token = refs["app_token"]
    table_id = refs["video_table_id"]
    today = datetime.now().strftime("%Y-%m-%d")

    records = []
    for v in videos[:10]:  # 最近10条
        views = v.get("views", 0)
        likes = v.get("likes", 0)
        lr = (likes / views * 100) if views > 0 else 0

        pub_date = v.get("published_at", "") or v.get("publish_date", "") or v.get("upload_date", "") or v.get("date", "")
        record = {
            "fields": {
                "日期": _date_to_ms(today),
                "频道": channel_name,
                "视频标题": v.get("title", "")[:100],
                "发布时间": _date_to_ms(pub_date) if pub_date else None,
                "播放量": views,
                "点赞数": likes,
                "点赞率%": round(lr, 2),
                "评论数": v.get("comments", 0),
                "观看时长(分)": round(v.get("watch_time_min", 0), 1),
                "平均观看时长(秒)": v.get("avg_view_duration", 0),
                "平均观看%": v.get("avg_view_percentage", 0),
                "标签": ", ".join(v.get("tags", [])[:3]),
            }
        }
        records.append(record)

    if not records:
        return

    result = _api_post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
        token,
        {"records": records}
    )

    if result.get("code") == 0:
        print(f"  ✅ {channel_name}: 写入 {len(records)} 条视频")
    else:
        print(f"  ❌ {channel_name} 视频写入失败: {result.get('msg', '')}")


def run_daily():
    """每日运行入口"""
    # 加载数据
    analysis_file = DATA_DIR / "own" / "channel_analysis_latest.json"
    if not analysis_file.exists():
        print("❌ 无分析数据，请先运行数据采集")
        return

    analysis_data = json.loads(analysis_file.read_text())

    # 加载表格引用
    refs = load_refs()
    if not refs.get("app_token"):
        print("📝 未找到多维表格，创建新表格...")
        refs = create_bitable()

    # 清除旧数据
    print("🗑️ 清除旧数据...")
    clear_table(refs, "both")

    # 写入自有账号日报
    write_daily_data(refs, analysis_data)

    # 写入视频明细（如果有）
    details = analysis_data.get("channel_details", {})
    for ch_name, ch_data in details.items():
        # 优先用 recent_videos（按发布时间倒排）
        videos = ch_data.get("recent_videos") or ch_data.get("top_videos", [])
        if videos:
            write_video_data(refs, ch_name, videos)

    print(f"\n📎 多维表格: {refs.get('url', '')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="飞书多维表格写入")
    parser.add_argument("--create", action="store_true", help="创建新表格")
    parser.add_argument("--app-token", help="使用已有表格")
    args = parser.parse_args()

    if args.create:
        create_bitable()
    elif args.app_token:
        refs = load_refs()
        refs["app_token"] = args.app_token
        save_refs(refs)
        print(f"✅ 设置 app_token: {args.app_token}")
    else:
        run_daily()
