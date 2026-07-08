#!/usr/bin/env python3
"""Apocalyptic Films 频道完整YouTube诊断分析"""
import sys, json, time, os
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from edgefn_models import call_for_task, parse_json_response

WORKDIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(WORKDIR)

# ── 1. 加载数据 ──
with open("data/own/channel_snapshots/Apocalyptic_Films_latest.json") as f:
    snapshot = json.load(f)
with open("data/own/channel_diagnosis/Apocalyptic_Films_covers.json") as f:
    covers_data = json.load(f)
with open("knowledge/en/distill.json") as f:
    distill = json.load(f)

videos = snapshot["videos"]
channel_stats = snapshot["channel_stats"]
analytics = snapshot.get("analytics", {})

# 封面分析建立索引
covers_map = {}
for c in covers_data.get("details", []):
    covers_map[c["video_id"]] = c

# 蒸馏知识摘要
distill_summary = json.dumps({
    "title_skeletons": [s["name"] for s in distill["how"]["title_skeletons"]],
    "hook_types": list(distill["how"]["hook_combination"]["hook_types"].keys()),
    "best_hooks": distill["how"]["hook_combination"]["最强配对"],
    "title_rules": distill["how"]["title_constraints"],
    "thumbnail_guidelines": distill["how"]["thumbnail_guidelines"],
    "cover_title_synergy": distill["how"]["cover_title_synergy"],
    "emoji_strategy": distill["how"]["emoji_strategy"],
}, ensure_ascii=False, indent=2)

print(f"📊 开始分析 Apocalyptic Films，共 {len(videos)} 条视频")
print(f"   频道: {channel_stats['subscribers']} 订阅, {channel_stats['total_views']} 总播放")
print()

# ── 2. 逐视频分析 ──
video_scores = []

for i, v in enumerate(videos):
    vid = v["video_id"]
    title = v["title"]
    views = v["views"]
    likes = v["likes"]
    comments = v["comments"]
    duration = v.get("duration", "PT0S")
    description = v.get("description", "")[:200]
    tags = v.get("description_tags", [])

    # 封面分析
    cover = covers_map.get(vid, {})
    cover_info = ""
    if cover and "overall_score" in cover:
        cover_info = f"""
封面分析（已有）:
- 整体评分: {cover.get('overall_score', 'N/A')}/10
- 人物: {cover.get('person_detail', 'N/A')[:150]}
- 情绪: {cover.get('emotion_detail', 'N/A')[:150]}
- 文字: {cover.get('text_detail', 'N/A')[:150]}
- 封面×标题协同: {json.dumps(cover.get('封面×标题协同', {}), ensure_ascii=False)[:200]}
"""
    else:
        cover_info = "封面分析: 无已有数据，请基于标题和题材推断封面特征。"

    # 计算like_rate
    like_rate = round(likes / max(views, 1) * 100, 2)

    prompt = f"""你是YouTube短剧频道标题优化专家。请分析以下视频并输出JSON。

## 蒸馏知识（英文短剧市场规律）
{distill_summary}

## 频道背景
- 频道名: Apocalyptic Films
- 题材: 末世/重生/异能短剧（英文配音）
- 目标受众: 英文市场，女性18-34岁为主（占47.8%）
- 流量来源: 相关视频46.3%, 订阅23.5%, 搜索8.4%

## 当前视频信息
- 标题: {title}
- 播放: {views}, 点赞: {likes}, 评论: {comments}
- 点赞率: {like_rate}%
- 时长: {duration}
- 描述: {description}
- 描述标签: {', '.join(tags[:8])}

{cover_info}

## 请输出以下JSON格式（不要其他文字）:
{{
  "video_id": "{vid}",
  "original_title": "{title}",
  "title_skeleton": "识别的标题骨架类型（从蒸馏知识中选）",
  "title_analysis": "标题结构分析（50字内）",
  "hooks": {{
    "emotion": "情绪钩子分析",
    "identity": "身份钩子分析",
    "relationship": "关系钩子分析",
    "reversal": "反转钩子分析",
    "compensation": "补偿钩子分析",
    "time": "时间钩子分析"
  }},
  "cover_synergy": {{
    "score": 1-10,
    "pattern": "协同模式",
    "analysis": "封面与标题协同分析（80字内）"
  }},
  "score": {{
    "title_score": 1-10,
    "hook_score": 1-10,
    "cover_score": 1-10,
    "seo_score": 1-10,
    "overall": 1-10
  }},
  "optimized_title": "优化后的标题（50字符内，英文）",
  "optimized_reason": "优化理由（50字内）",
  "top_issues": ["问题1", "问题2"],
  "quick_fixes": ["修复建议1", "修复建议2"]
}}"""

    print(f"[{i+1}/{len(videos)}] 分析: {title[:50]}...")
    result = call_for_task("title_optimize", prompt, max_tokens=8192, temperature=0.5)

    if result.get("error"):
        print(f"  ❌ API错误: {result['error']}")
        parsed = {"error": result["error"], "video_id": vid, "original_title": title}
    else:
        parsed = parse_json_response(result)
        if "error" in parsed:
            print(f"  ⚠️ JSON解析失败: {parsed.get('raw', '')[:100]}")
            parsed["video_id"] = vid
            parsed["original_title"] = title
        else:
            score = parsed.get("score", {}).get("overall", "?")
            print(f"  ✅ 评分: {score}/10")

    # 附加基础数据
    parsed["_views"] = views
    parsed["_likes"] = likes
    parsed["_comments"] = comments
    parsed["_like_rate"] = like_rate
    video_scores.append(parsed)

    # rate limit
    if i < len(videos) - 1:
        print(f"  ⏳ 等待16秒（rate limit）...")
        time.sleep(16)

# ── 3. 聚合统计 ──
print("\n📈 聚合统计...")
valid_scores = [v for v in video_scores if "score" in v and isinstance(v["score"], dict)]
if valid_scores:
    avg_title = sum(v["score"].get("title_score", 0) for v in valid_scores) / len(valid_scores)
    avg_hook = sum(v["score"].get("hook_score", 0) for v in valid_scores) / len(valid_scores)
    avg_cover = sum(v["score"].get("cover_score", 0) for v in valid_scores) / len(valid_scores)
    avg_seo = sum(v["score"].get("seo_score", 0) for v in valid_scores) / len(valid_scores)
    avg_overall = sum(v["score"].get("overall", 0) for v in valid_scores) / len(valid_scores)
else:
    avg_title = avg_hook = avg_cover = avg_seo = avg_overall = 0

all_issues = []
all_fixes = []
for v in valid_scores:
    all_issues.extend(v.get("top_issues", []))
    all_fixes.extend(v.get("quick_fixes", []))

summary = {
    "total_videos_analyzed": len(video_scores),
    "valid_analyses": len(valid_scores),
    "avg_scores": {
        "title": round(avg_title, 1),
        "hook": round(avg_hook, 1),
        "cover": round(avg_cover, 1),
        "seo": round(avg_seo, 1),
        "overall": round(avg_overall, 1),
    },
    "top_issues": list(set(all_issues))[:8],
    "top_fixes": list(set(all_fixes))[:8],
    "views_stats": {
        "total": sum(v["_views"] for v in video_scores),
        "avg": round(sum(v["_views"] for v in video_scores) / max(len(video_scores), 1)),
        "max": max(v["_views"] for v in video_scores),
        "min": min(v["_views"] for v in video_scores),
    },
    "engagement_stats": {
        "avg_like_rate": round(sum(v["_like_rate"] for v in video_scores) / max(len(video_scores), 1), 2),
    }
}

# ── 4. 频道级战略分析 ──
print("\n🎯 频道级战略分析...")
channel_prompt = f"""你是YouTube短剧频道增长战略专家。请对以下频道进行深度战略分析。

## 频道数据
- 频道名: Apocalyptic Films
- 订阅: {channel_stats['subscribers']}, 总播放: {channel_stats['total_views']}, 视频数: {channel_stats['total_videos']}
- 30天数据: 播放{analytics.get('views',0)}, 获赞{analytics.get('likes',0)}, 新增订阅{analytics.get('subscribersGained',0)}, 流失{analytics.get('subscribersLost',0)}
- 平均观看时长: {analytics.get('averageViewDuration',0)}秒, 完播率: {analytics.get('averageViewPercentage',0)}%
- 流量来源: 相关视频{snapshot.get('traffic_ratios',{}).get('RELATED_VIDEO','46.3')}%, 订阅{snapshot.get('traffic_ratios',{}).get('SUBSCRIBER','23.5')}%, 搜索{snapshot.get('traffic_ratios',{}).get('YT_SEARCH','8.4')}%
- 地理: US 23.3%, PH 18.4%, IN 8.3%, NG 5.7%
- 受众: 女性62.3%, 男性25.1%, 18-34岁占50.8%
- 播放分布: 前3条占77%, 头部54.3%, 尾部15.5%
- 内容一致性: 末世题材62%, 重生4次, 平均标题88字符

## 最近8条视频表现
""" + "\n".join([f"- {v['original_title'][:60]}: 播放{v['_views']}, 点赞率{v['_like_rate']}%" for v in video_scores]) + f"""

## 视频评分汇总
- 平均标题分: {avg_title}/10
- 平均钩子分: {avg_hook}/10
- 平均封面分: {avg_cover}/10
- 平均SEO分: {avg_seo}/10
- 平均总分: {avg_overall}/10

## 蒸馏知识
{distill_summary}

## 请输出JSON（不要其他文字）:
{{
  "channel_positioning": "频道定位分析（80字内）",
  "content_strategy": "内容策略评估（80字内）",
  "audience_fit": "受众匹配度分析（80字内）",
  "growth_barriers": ["障碍1", "障碍2", "障碍3"],
  "opportunities": ["机会1", "机会2", "机会3"],
  "title_strategy": "标题策略建议（80字内）",
  "thumbnail_strategy": "封面策略建议（80字内）",
  "seo_strategy": "SEO策略建议（80字内）",
  "content_calendar": "内容排期建议（80字内）",
  "competitive_advantage": "竞争优势（60字内）",
  "30_day_plan": ["第1周行动", "第2周行动", "第3周行动", "第4周行动"],
  "kpi_targets": {{
    "30d_views_target": "目标播放",
    "30d_subs_target": "目标订阅",
    "avg_ctr_target": "目标点击率",
    "avg_retention_target": "目标完播率"
  }},
  "priority_actions": ["最高优先级1", "最高优先级2", "最高优先级3"],
  "risk_factors": ["风险1", "风险2"]
}}"""

print("  调用 channel_analysis...")
time.sleep(16)  # rate limit
ch_result = call_for_task("channel_analysis", channel_prompt, max_tokens=8192, temperature=0.5)

if ch_result.get("error"):
    print(f"  ❌ 频道分析API错误: {ch_result['error']}")
    channel_llm = {"error": ch_result["error"]}
else:
    channel_llm = parse_json_response(ch_result)
    if "error" in channel_llm:
        print(f"  ⚠️ JSON解析失败")
    else:
        print(f"  ✅ 频道分析完成")

# ── 5. 保存结果 ──
output = {
    "channel_name": "Apocalyptic Films",
    "language": "en",
    "diagnosed_at": datetime.now(timezone.utc).isoformat(),
    "channel": {
        "channel_id": channel_stats["channel_id"],
        "name": channel_stats["name"],
        "subscribers": channel_stats["subscribers"],
        "total_views": channel_stats["total_views"],
        "total_videos": channel_stats["total_videos"],
        "country": channel_stats["country"],
        "published_at": channel_stats["published_at"],
    },
    "analytics_30d": {
        "views": analytics.get("views", 0),
        "likes": analytics.get("likes", 0),
        "comments": analytics.get("comments", 0),
        "shares": analytics.get("shares", 0),
        "subscribersGained": analytics.get("subscribersGained", 0),
        "subscribersLost": analytics.get("subscribersLost", 0),
        "averageViewDuration": analytics.get("averageViewDuration", 0),
        "averageViewPercentage": analytics.get("averageViewPercentage", 0),
        "estimatedMinutesWatched": analytics.get("estimatedMinutesWatched", 0),
        "traffic_ratios": snapshot.get("traffic_ratios", {}),
        "geo_top5": dict(list(snapshot.get("analytics", {}).get("geo", {}).items())[:5]),
        "demographics": snapshot.get("analytics", {}).get("demographics", []),
    },
    "channel_llm": channel_llm,
    "video_scores": [],
    "summary": summary,
    "retention_data": None,
    "growth": snapshot.get("growth", {}),
    "weekly_growth": snapshot.get("weekly_growth", {}),
    "view_distribution": snapshot.get("view_distribution", {}),
    "engagement_funnel": snapshot.get("engagement_funnel", {}),
    "diagnostics": snapshot.get("diagnostics", []),
}

# 清理video_scores中的临时字段
for v in video_scores:
    clean = {k: v2 for k, v2 in v.items() if not k.startswith("_")}
    output["video_scores"].append(clean)

out_path = "data/own/channel_diagnosis/Apocalyptic_Films_latest.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 诊断完成，保存到 {out_path}")
print(f"   分析视频: {len(video_scores)} 条")
print(f"   有效评分: {len(valid_scores)} 条")
print(f"   平均总分: {avg_overall}/10")
