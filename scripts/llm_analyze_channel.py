#!/usr/bin/env python3
"""
竞品频道 LLM 深度分析

用 DeepSeek V4 Pro 对单个频道做深度洞察，输出 why + what。
数据层复用 latest.json（上游共享），不重新采集。

用法：
    python3 scripts/llm_analyze_channel.py                    # 分析所有符合条件的未分析频道
    python3 scripts/llm_analyze_channel.py --channel UCxxx     # 分析指定频道
    python3 scripts/llm_analyze_channel.py --language 印尼      # 只分析某语种
    python3 scripts/llm_analyze_channel.py --all               # 强制重新分析所有
    python3 scripts/llm_analyze_channel.py --dry-run           # 只构建prompt不调LLM
"""

import json
import sys
import time
import argparse
import os
import requests
from datetime import datetime
from pathlib import Path
from collections import Counter
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
sys.stdout.reconfigure(line_buffering=True)
LATEST_FILE = DATA_DIR / "competitor_data" / "latest.json"
INSIGHT_DIR = DATA_DIR / "competitor_insights"
INSIGHT_DIR.mkdir(exist_ok=True)
TIERS_FILE = DATA_DIR / "competitor_tiers.json"
TRACKER_FILE = INSIGHT_DIR / "_llm_analyzed.json"

# DeepSeek V4 Pro config
API_URL = "https://api.edgefn.net/v1/chat/completions"
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = "DeepSeek-V4-Pro"
RPM_LIMIT = 5
CALL_INTERVAL = 60 / RPM_LIMIT + 1  # 13秒间隔，1分钟5个


def _load_api_key() -> str:
    """从环境变量或 .env 加载 API key"""
    if API_KEY:
        return API_KEY
    for env_path in [ROOT / ".env", Path.home() / ".hermes" / ".env"]:
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if "DEEPSEEK_API_KEY" in line and "=" in line:
                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                    if key:
                        return key
    return ""


def _load_tracker() -> dict:
    if TRACKER_FILE.exists():
        try:
            return json.loads(TRACKER_FILE.read_text())
        except:
            pass
    return {"analyzed": {}, "last_updated": ""}


def _save_tracker(tracker: dict):
    tracker["last_updated"] = datetime.now().isoformat()
    TRACKER_FILE.write_text(json.dumps(tracker, indent=2, ensure_ascii=False))


def _load_latest() -> list:
    if not LATEST_FILE.exists():
        return []
    return json.loads(LATEST_FILE.read_text())


def _load_tiers() -> set:
    """返回已追踪的 channel_id 集合"""
    if not TIERS_FILE.exists():
        return set()
    data = json.loads(TIERS_FILE.read_text())
    return {c["channel_id"] for c in data.get("channels", [])}


# ═══════════════════════════════════════════════
#  数据准备（Python层）
# ═══════════════════════════════════════════════

def prepare_channel_data(channel: dict) -> dict:
    """从 latest.json 的频道数据中提取分析所需的全部信息"""
    videos = channel.get("videos", [])

    # 按播放量降序
    def _views(v):
        return v.get("view_count", v.get("views", 0))
    videos_sorted = sorted(videos, key=_views, reverse=True)

    # 统计
    views_list = [_views(v) for v in videos_sorted if _views(v) > 0]
    avg_views = sum(views_list) / len(views_list) if views_list else 0
    max_views = max(views_list) if views_list else 0
    breakout_count = len([v for v in views_list if v >= 10000])

    # 互动率
    total_likes = sum(v.get("like_count", v.get("likes", 0)) for v in videos_sorted)
    total_comments = sum(v.get("comment_count", v.get("comments", 0)) for v in videos_sorted)
    like_rate = total_likes / sum(views_list) * 100 if sum(views_list) > 0 else 0
    comment_rate = total_comments / sum(views_list) * 100 if sum(views_list) > 0 else 0

    # 时长分布
    durations = [v.get("duration", 0) for v in videos_sorted if v.get("duration", 0) > 0]
    avg_duration = sum(durations) / len(durations) if durations else 0

    # 发布时间
    hours = []
    for v in videos_sorted:
        pa = v.get("published_at", "")
        if pa:
            try:
                dt = datetime.fromisoformat(pa.replace("Z", "+00:00"))
                hours.append(dt.hour)
            except:
                pass
    hour_dist = Counter(hours).most_common(5) if hours else []

    # 描述标签
    all_desc_tags = []
    for v in videos_sorted:
        all_desc_tags.extend(v.get("description_tags", []))
    top_desc_tags = [t for t, _ in Counter(all_desc_tags).most_common(10)]

    # 构造视频列表文本
    video_lines = []
    for i, v in enumerate(videos_sorted, 1):
        views = _views(v)
        likes = v.get("like_count", v.get("likes", 0))
        comments = v.get("comment_count", v.get("comments", 0))
        dur = v.get("duration", 0)
        title = v.get("title", "")[:100]
        published = v.get("published_at", "")[:10]
        tags = v.get("tags", [])[:5]
        desc_tags = v.get("description_tags", [])[:5]

        line = f"{i}. [{views:>10,}播放] {title}"
        if likes or comments:
            line += f"\n   👍{likes:,} 💬{comments:,}"
        if dur:
            dur = int(dur)
            mins = dur // 60
            secs = dur % 60
            line += f" ⏱{mins}:{secs:02d}"
        if published:
            line += f" 📅{published}"
        if tags:
            line += f"\n   标签: {', '.join(tags)}"
        if desc_tags:
            line += f"\n   描述标签: {', '.join(desc_tags)}"
        video_lines.append(line)

    return {
        "channel_id": channel.get("channel_id", ""),
        "name": channel.get("name", ""),
        "language": channel.get("language", "未知"),
        "country": channel.get("country", ""),
        "subscribers": channel.get("subscribers", 0),
        "original_subscribers": channel.get("original_subscribers", 0),
        "first_seen": channel.get("first_seen", ""),
        "channel_created_at": channel.get("channel_created_at", ""),
        "tier": channel.get("tier", ""),
        "video_count": channel.get("video_count", len(videos)),
        "stats": {
            "avg_views": round(avg_views),
            "max_views": max_views,
            "breakout_count": breakout_count,
            "like_rate": round(like_rate, 2),
            "comment_rate": round(comment_rate, 3),
            "avg_duration_sec": round(avg_duration),
            "top_publish_hours": hour_dist,
            "top_desc_tags": top_desc_tags,
        },
        "videos_text": "\n".join(video_lines),
        "cover_urls": [
            v.get("thumbnail", f"https://i.ytimg.com/vi/{v.get('video_id','')}/maxresdefault.jpg")
            for v in videos_sorted[:3]
            if v.get("video_id") or v.get("thumbnail")
        ],
        "recent_videos_text": _format_recent_videos(channel.get("recent_videos", [])),
    }

def _format_recent_videos(videos: list) -> str:
    """格式化最新视频列表"""
    if not videos:
        return ""
    lines = []
    for i, v in enumerate(videos, 1):
        title = v.get("title", "")[:80]
        published = v.get("published_at", "")[:10]
        lines.append(f"{i}. [{published}] {title}")
    return "\n".join(lines)


# ═══════════════════════════════════════════════
#  Prompt 构建
# ═══════════════════════════════════════════════

def build_prompt(data: dict) -> str:
    """构建单频道分析 prompt"""
    s = data["stats"]
    subs = data["subscribers"]
    subs_display = f"{subs / 10000:.1f}万" if subs >= 10000 else f"{subs:,}"

    duration_display = f"{s['avg_duration_sec'] // 60}分{s['avg_duration_sec'] % 60}秒" if s["avg_duration_sec"] else "未知"
    hour_display = ", ".join(f"{h}点({c}次)" for h, c in s["top_publish_hours"]) if s["top_publish_hours"] else "未知"

    # 增长数据
    orig_subs = data.get("original_subscribers", 0) or 0
    first_seen = data.get("first_seen", "")
    channel_created = data.get("channel_created_at", "")
    growth = subs - orig_subs if orig_subs > 0 else 0
    multiple = round(subs / orig_subs, 1) if orig_subs > 0 else 0
    orig_display = f"{orig_subs / 10000:.1f}万" if orig_subs >= 10000 else f"{orig_subs:,}"

    # 高速增长判断
    is_fast = growth > 10000 or (multiple > 2 and orig_subs > 0)
    fast_label = "⚡高速增长" if is_fast else "常规增长"

    # 最新视频文本
    recent_videos_text = data.get("recent_videos_text", "")
    recent_section = ""
    if recent_videos_text:
        recent_section = f"""

## 最新发布视频（对比Top视频判断内容方向）
{recent_videos_text}"""

    # 字幕实证注入（开关: settings.yaml subtitle_injection.enabled；无数据自动降级为纯标题分析）
    subtitle_block = ""
    try:
        import subtitle_evidence as _se
        if _se.injection_enabled():
            _b = _se.channel_subtitle_block(data["name"], data["language"])
            if _b:
                subtitle_block = "\n" + _b + "\n"
            else:
                print(f"[subtitle_injection] 频道 {data['name']}({data['language']}) 无字幕数据，降级为纯标题分析")
        else:
            print("[subtitle_injection] 开关关闭（config/settings.yaml subtitle_injection.enabled）")
    except Exception as e:
        print(f"[subtitle_injection] 注入失败: {e}（降级为纯标题分析）")

    return f"""你是YouTube短剧市场深度分析师，擅长从原始数据中提取可落地的运营策略。

## 频道基础与增长数据
- 名称：{data['name']}
- 语种：{data['language']} | 地区：{data['country'] or '未知'}
{"- YouTube注册日期：" + channel_created if channel_created else ""}
- 频道阶段：从 {first_seen} 的 {orig_display} 订阅，增长至当前的 {subs_display}（增长 +{growth:,}，{multiple}x）。
- 层级：{data['tier']} | 总视频数：{data['video_count']}

## 统计数据
- 平均播放：{s['avg_views']:,} | 最高播放：{s['max_views']:,}
- 爆款数（≥1万播放）：{s['breakout_count']}
- 点赞率：{s['like_rate']:.2f}% | 评论率：{s['comment_rate']:.3f}%
- 平均时长：{duration_display} | 常用时段：{hour_display}
- 描述标签：{', '.join(s['top_desc_tags']) or '无'}

## 视频表现列表（按播放量降序的 Top {data['video_count']} 个）
{data['videos_text']}{recent_section}
{subtitle_block}
## 分析要求
这是一个【{fast_label}】频道。{"请重点分析其成功经验，提取可复制的方法论，包括内容策略、标题公式、封面风格、发布节奏等。" if is_fast else "请分析其运营特点和可借鉴之处。"}
{"请对比Top视频和最新视频，判断频道是在延续爆款路线还是尝试新方向。" if recent_videos_text else ""}

重要：请务必提供具体例子和详细分析，不要泛泛而谈。所有分析都要基于视频数据中的真实标题和播放量。

请输出纯JSON（不要markdown代码块、不要其他文字）：

{{
  "why": {{
    "growth_drivers": ["具体增长原因1（引用数据支撑）", "具体增长原因2", "具体增长原因3", "具体增长原因4", "具体增长原因5"],
    "audience_fit": "受众画像及其核心痛点/爽点",
    "trajectory": "频道阶段判断（起步/爆发/稳定/衰退）+ 依据"
  }},
  "what": {{
    "content_strategy": "一句话概括其核心打法",
    "top_themes": ["题材1", "题材2", "题材3", "题材4", "题材5"],
    "title_formulas": ["公式1: 具体格式（如【ENG DUB】+核心事件+反转结局+表情符号）", "公式2: 具体格式（从真实标题中提取）"],
    "hook_patterns": ["模式1名称：解释+引用具体视频标题作为例子", "模式2名称：解释+引用具体视频标题作为例子", "模式3名称：解释+例子", "模式4名称：解释+例子"],
    "cover_strategy": "封面视觉风格与排版逻辑",
    "best_performers": [
      {{"title": "视频标题", "views": 0, "why_works": "拆解成功核心要素"}}
    ],
    "actionable_insights": {{
      "copyable_tactics": ["可直接复制的运营技巧1", "可直接复制的运营技巧2"],
      "avoid_pitfalls": ["该频道踩过的坑/建议避免的操作"]
    }}
  }}
}}"""


# ═══════════════════════════════════════════════
#  LLM 调用
# ═══════════════════════════════════════════════

def call_llm(prompt: str, api_key: str) -> Optional[dict]:
    """调用 DeepSeek V4 Pro，返回解析后的 JSON"""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }

    try:
        resp = requests.post(API_URL, headers=headers, json=body, timeout=120)
    except requests.Timeout:
        print("    ❌ 请求超时(120s)")
        return None
    except Exception as e:
        print(f"    ❌ 请求异常: {e}")
        return None

    if resp.status_code != 200:
        print(f"    ❌ API {resp.status_code}: {resp.text[:200]}")
        return None

    result = resp.json()
    usage = result.get("usage", {})
    print(f"    📊 tokens: in={usage.get('prompt_tokens',0):,} out={usage.get('completion_tokens',0):,}")

    content = result["choices"][0]["message"]["content"]

    # 解析 JSON（容错：去掉可能的 markdown 代码块）
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        content = "\n".join(lines[1:])
        if content.endswith("```"):
            content = content[:-3].strip()

    try:
        return json.loads(content)
    except json.JSONDecodeError as e:
        print(f"    ❌ JSON解析失败: {e}")
        print(f"    原始输出: {content[:300]}")
        return None


# ═══════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════

def analyze_channel(channel: dict, api_key: str, dry_run: bool = False) -> Optional[dict]:
    """分析单个频道"""
    cid = channel.get("channel_id", "")
    name = channel.get("name", cid[:12])
    lang = channel.get("language", "?")

    # 准备数据
    data = prepare_channel_data(channel)
    prompt = build_prompt(data)

    if dry_run:
        print(f"    [dry-run] prompt长度: {len(prompt)} 字符")
        return None

    # 调用 LLM
    distill = call_llm(prompt, api_key)
    if not distill:
        return None

    # 合并到现有 insight 文件（保留旧的 stats 字段，加新的 distill）
    insight_file = INSIGHT_DIR / f"channel_{cid}.json"
    existing = {}
    if insight_file.exists():
        try:
            existing = json.loads(insight_file.read_text())
        except:
            pass

    # 更新字段
    existing["llm_analysis"] = {
        "model": MODEL,
        "analyzed_at": datetime.now().isoformat(),
        "distill": distill,
        "stats": data["stats"],
    }
    # 保留旧字段兼容
    existing["channel_id"] = cid
    existing["name"] = name
    existing["language"] = lang
    existing["subscribers"] = channel.get("subscribers", 0)
    existing["tier"] = channel.get("tier", "")
    existing["url"] = f"https://www.youtube.com/channel/{cid}"
    existing["total_videos"] = data["video_count"]
    existing["avg_views"] = data["stats"]["avg_views"]

    insight_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False))

    return distill


def main():
    parser = argparse.ArgumentParser(description="竞品频道 LLM 深度分析")
    parser.add_argument("--channel", help="指定频道ID")
    parser.add_argument("--language", help="只分析某语种")
    parser.add_argument("--all", action="store_true", help="强制重新分析所有")
    parser.add_argument("--dry-run", action="store_true", help="只构建prompt不调LLM")
    parser.add_argument("--limit", type=int, default=0, help="最多分析N个频道")
    args = parser.parse_args()

    api_key = _load_api_key()
    if not api_key and not args.dry_run:
        print("❌ 未配置 DEEPSEEK_API_KEY")
        sys.exit(1)

    latest = _load_latest()
    if not latest:
        print("❌ latest.json 为空")
        sys.exit(1)

    tracked_ids = _load_tiers()
    tracker = _load_tracker()
    analyzed_ids = set(tracker.get("analyzed", {}).keys()) if not args.all else set()

    # 筛选待分析频道
    candidates = []
    skipped = 0
    for ch in latest:
        cid = ch.get("channel_id", "")

        # 指定频道
        if args.channel and cid != args.channel:
            continue

        # 指定语种
        if args.language and ch.get("language", "") != args.language:
            continue

        # 必须在追踪清单中（除非指定了 --channel）
        if not args.channel and cid not in tracked_ids:
            continue

        # 已分析过
        if cid in analyzed_ids:
            continue

        # 数据门槛：≥3视频即可分析（能被搜进来说明有热度）
        videos = ch.get("videos", [])
        if len(videos) < 3:
            skipped += 1
            continue

        candidates.append(ch)

    if skipped:
        print(f"⏳ {skipped} 个频道视频不足3个，跳过")

    if not candidates:
        print("✅ 没有需要分析的频道")
        return

    if args.limit:
        candidates = candidates[:args.limit]

    print(f"📋 待分析: {len(candidates)} 个频道")
    print(f"⏱ 间隔: {CALL_INTERVAL:.1f}秒 (RPM限制 {RPM_LIMIT})")
    print(f"{'='*50}")

    success = 0
    failed = 0

    for i, ch in enumerate(candidates, 1):
        name = ch.get("name", "?")
        lang = ch.get("language", "?")
        cid = ch.get("channel_id", "")
        print(f"\n[{i}/{len(candidates)}] [{lang}] {name}")

        distill = analyze_channel(ch, api_key, dry_run=args.dry_run)

        if distill:
            success += 1
            # 打印摘要
            why = distill.get("why", {})
            what = distill.get("what", {})
            drivers = why.get("growth_drivers", [])
            themes = what.get("top_themes", [])
            print(f"    ✅ 增长: {' | '.join(drivers[:2])}")
            print(f"    ✅ 题材: {' | '.join(themes[:3])}")

            # 更新 tracker
            tracker.setdefault("analyzed", {})[cid] = {
                "name": name,
                "language": lang,
                "analyzed_at": datetime.now().isoformat(),
            }
            _save_tracker(tracker)
        else:
            failed += 1

        # 间隔控制
        if i < len(candidates) and not args.dry_run:
            print(f"    ⏳ 等待 {CALL_INTERVAL:.0f}秒...")
            time.sleep(CALL_INTERVAL)

    print(f"\n{'='*50}")
    print(f"✅ 完成: 成功 {success}, 失败 {failed}, 总计 {len(candidates)}")


if __name__ == "__main__":
    main()
