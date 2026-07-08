#!/usr/bin/env python3
"""Apocalyptic Films频道完整YouTube诊断分析"""
import sys
import json
import time
from datetime import datetime, timezone

sys.path.insert(0, 'scripts')
from edgefn_models import call_for_task, parse_json_response

# ============================================================
# 1. 读取数据文件
# ============================================================
with open('data/own/channel_snapshots/Apocalyptic_Films_latest.json') as f:
    snapshot = json.load(f)

with open('data/own/channel_diagnosis/Apocalyptic_Films_covers.json') as f:
    covers = json.load(f)

with open('knowledge/en/distill.json') as f:
    distill = json.load(f)

with open('data/yt_analytics/en_global.json') as f:
    analytics = json.load(f)

videos = snapshot['videos']
channel_stats = snapshot['channel_stats']
cover_details = {c['video_id']: c for c in covers.get('details', []) if 'error' not in c}

print(f"=== Apocalyptic Films 诊断分析 ===")
print(f"频道: {channel_stats['name']}, 订阅: {channel_stats['subscribers']}, 总播放: {channel_stats['total_views']}, 视频数: {channel_stats['total_videos']}")
print(f"待分析视频: {len(videos)}条")
print()

# ============================================================
# 2. 逐视频分析
# ============================================================
video_scores = []

for i, v in enumerate(videos):
    vid = v['video_id']
    title = v['title']
    views = v['views']
    likes = v['likes']
    comments = v['comments']
    duration = v.get('duration', '')
    desc = v.get('description', '')[:200]
    tags = v.get('description_tags', [])

    # 获取封面分析
    cover = cover_details.get(vid, None)
    cover_info = ""
    if cover:
        cover_info = f"""
封面分析（已有）:
- 人物得分: {cover.get('person_score','N/A')}/10 — {cover.get('person_detail','')[:150]}
- 情绪得分: {cover.get('emotion_score','N/A')}/10 — {cover.get('emotion_detail','')[:150]}
- 道具得分: {cover.get('prop_score','N/A')}/10
- 色彩得分: {cover.get('color_score','N/A')}/10
- 文字得分: {cover.get('text_score','N/A')}/10
- 构图得分: {cover.get('composition_score','N/A')}/10
- 整体得分: {cover.get('overall_score','N/A')}/10
- 封面×标题协同: {cover.get('封面×标题协同',{}).get('score','N/A')}/10
- 协同模式: {cover.get('封面×标题协同',{}).get('synergy_pattern','')}
- 建议: {'; '.join(cover.get('suggestions',[]))}
"""
    else:
        cover_info = "\n封面分析: 无已有数据，请基于标题推测封面可能情况并给出建议。\n"

    # 蒸馏知识摘要
    distill_summary = json.dumps({
        "title_skeletons": [s['name'] for s in distill['how']['title_skeletons']],
        "hook_types": list(distill['how']['hook_combination']['hook_types'].keys()),
        "best_hooks": distill['how']['hook_combination']['最强配对'],
        "key_patterns": [p['name'] for p in distill['how']['rhetorical_patterns']['sentence_structures']],
        "thumbnail_rules": distill['why']['thumbnail'][:3],
        "title_rules": distill['why']['title'][:3],
    }, ensure_ascii=False)

    prompt = f"""你是一位YouTube短剧频道诊断专家。请对以下视频进行全面分析，并以JSON格式输出结果。

## 视频信息
- 标题: {title}
- 播放量: {views}
- 点赞: {likes}
- 评论: {comments}
- 时长: {duration}
- 描述摘要: {desc}
- 标签: {', '.join(tags[:8])}

## 封面分析
{cover_info}

## 蒸馏知识（英文短剧市场规律）
{distill_summary}

## 频道背景
- 频道名: Apocalyptic Films
- 题材: 末世/重生/丧尸/灾难短剧（英文配音）
- 核心受众: 18-34岁女性为主（占53%），美国、菲律宾、印度为主
- 平均播放: ~800（排除爆款后）

## 请输出以下JSON格式（不要输出其他内容）：
```json
{{
  "video_id": "{vid}",
  "title": "{title}",
  "views": {views},
  "likes": {likes},
  "comments": {comments},
  "title_skeleton": {{
    "type": "骨架类型名称（如：重生改命型/身份落差型/关系背叛补偿型/系统开挂型/情绪爆点型/外部干预型）",
    "narrative_pattern": "标题的叙事结构描述",
    "psychological_hook": "触发观众点击的心理机制"
  }},
  "hook_analysis": {{
    "primary_hook": "主要钩子类型（emotion/identity/relationship/reversal/compensation/time）",
    "secondary_hook": "次要钩子类型",
    "hook_strength": "钩子强度1-10分",
    "hook_detail": "钩子分析详情"
  }},
  "cover_synergy": {{
    "score": "封面×标题协同得分1-10",
    "pattern": "协同模式",
    "assessment": "协同评估",
    "improvement": "改进建议"
  }},
  "scores": {{
    "title_clarity": "标题清晰度1-10",
    "hook_power": "钩子力度1-10",
    "emotion_trigger": "情绪触发1-10",
    "identity_gap": "身份落差1-10",
    "cover_title_synergy": "封面标题协同1-10",
    "seo_potential": "SEO潜力1-10",
    "overall": "综合评分1-10"
  }},
  "optimized_title": {{
    "new_title": "优化后的标题（英文，50-65字符内）",
    "rationale": "优化理由"
  }},
  "key_issues": ["问题1", "问题2"],
  "quick_wins": ["快速改进1", "快速改进2"]
}}
```"""

    print(f"[{i+1}/8] 分析: {title[:60]}...")
    result = call_for_task("title_optimize", prompt, max_tokens=8192, temperature=0.5)
    parsed = parse_json_response(result)

    if 'error' in parsed and parsed.get('error'):
        print(f"  ⚠️ 错误: {parsed['error']}")
        # 保存原始响应用于调试
        parsed = {
            "video_id": vid,
            "title": title,
            "views": views,
            "error": parsed.get('error', ''),
            "raw": parsed.get('raw', result.get('content', '')[:500])
        }
    else:
        print(f"  ✅ 完成 - 综合评分: {parsed.get('scores', {}).get('overall', 'N/A')}")

    video_scores.append(parsed)

    # Rate limit: 每次调用间隔16秒
    if i < len(videos) - 1:
        print(f"  ⏳ 等待16秒（rate limit）...")
        time.sleep(16)

print("\n=== 逐视频分析完成 ===\n")

# ============================================================
# 3. 聚合统计
# ============================================================
valid_scores = [v for v in video_scores if 'scores' in v and not v.get('error')]

if valid_scores:
    avg_scores = {}
    score_keys = ['title_clarity', 'hook_power', 'emotion_trigger', 'identity_gap',
                  'cover_title_synergy', 'seo_potential', 'overall']
    for key in score_keys:
        vals = [v['scores'][key] for v in valid_scores if isinstance(v.get('scores', {}).get(key), (int, float))]
        avg_scores[f"avg_{key}"] = round(sum(vals) / len(vals), 1) if vals else 0

    # 钩子分布
    hook_dist = {}
    for v in valid_scores:
        h = v.get('hook_analysis', {}).get('primary_hook', 'unknown')
        hook_dist[h] = hook_dist.get(h, 0) + 1

    # 骨架分布
    skeleton_dist = {}
    for v in valid_scores:
        s = v.get('title_skeleton', {}).get('type', 'unknown')
        skeleton_dist[s] = skeleton_dist.get(s, 0) + 1

    # 播放分层
    top3 = sorted(valid_scores, key=lambda x: x.get('views', 0), reverse=True)[:3]
    bottom3 = sorted(valid_scores, key=lambda x: x.get('views', 0))[:3]

    summary = {
        "total_videos": len(videos),
        "analyzed_videos": len(valid_scores),
        "avg_scores": avg_scores,
        "hook_distribution": hook_dist,
        "skeleton_distribution": skeleton_dist,
        "top3_avg_views": round(sum(v.get('views', 0) for v in top3) / 3) if top3 else 0,
        "bottom3_avg_views": round(sum(v.get('views', 0) for v in bottom3) / 3) if bottom3 else 0,
        "top3_avg_overall": round(sum(v['scores']['overall'] for v in top3) / 3, 1) if top3 else 0,
        "bottom3_avg_overall": round(sum(v['scores']['overall'] for v in bottom3) / 3, 1) if bottom3 else 0,
    }
else:
    summary = {"error": "无有效视频分析结果"}

print(f"聚合统计: {json.dumps(summary, ensure_ascii=False, indent=2)}\n")

# ============================================================
# 4. 频道级战略分析
# ============================================================
print("=== 频道级战略分析 ===")

# 准备分析数据摘要
analytics_summary = analytics.get('summary', {}).get('rows', [[]])[0] if analytics.get('summary', {}).get('rows') else []
analytics_headers = analytics.get('summary', {}).get('headers', [])
analytics_dict = dict(zip(analytics_headers, analytics_summary)) if analytics_summary else {}

traffic = snapshot.get('analytics', {}).get('traffic_ratios', {})
geo = snapshot.get('analytics', {}).get('geo', {})
demographics = snapshot.get('analytics', {}).get('demographics', [])
diagnostics = snapshot.get('diagnostics', [])
view_dist = snapshot.get('view_distribution', {})
engagement = snapshot.get('engagement_funnel', {})
growth = snapshot.get('growth', {})

video_summary_for_llm = []
for v in video_scores:
    if 'error' not in v or not v.get('error'):
        video_summary_for_llm.append({
            "title": v.get('title', ''),
            "views": v.get('views', 0),
            "overall_score": v.get('scores', {}).get('overall', 'N/A'),
            "primary_hook": v.get('hook_analysis', {}).get('primary_hook', 'N/A'),
            "optimized_title": v.get('optimized_title', {}).get('new_title', 'N/A'),
            "key_issues": v.get('key_issues', [])
        })

channel_prompt = f"""你是一位YouTube频道战略顾问。请基于以下数据，为"Apocalyptic Films"频道提供全面的战略分析。

## 频道基础数据
- 频道名: Apocalyptic Films
- 订阅: {channel_stats['subscribers']}
- 总播放: {channel_stats['total_views']}
- 总视频: {channel_stats['total_videos']}
- 创建时间: {channel_stats['published_at']}
- 国家: {channel_stats['country']}

## 30天分析数据
- 总播放: {analytics_dict.get('views', 'N/A')}
- 总点赞: {analytics_dict.get('likes', 'N/A')}
- 总评论: {analytics_dict.get('comments', 'N/A')}
- 平均观看时长: {analytics_dict.get('averageViewDuration', 'N/A')}秒
- 平均观看比例: {analytics_dict.get('averageViewPercentage', 'N/A')}%
- 新增订阅: {analytics_dict.get('subscribersGained', 'N/A')}
- 流失订阅: {analytics_dict.get('subscribersLost', 'N/A')}

## 流量来源
{json.dumps(traffic, ensure_ascii=False)}

## 地区分布（前10）
{json.dumps(geo, ensure_ascii=False)}

## 人口统计
{json.dumps(demographics, ensure_ascii=False)}

## 播放分布
{json.dumps(view_dist, ensure_ascii=False)}

## 互动漏斗
{json.dumps(engagement, ensure_ascii=False)}

## 增长数据
{json.dumps(growth, ensure_ascii=False)}

## 逐视频分析摘要
{json.dumps(video_summary_for_llm, ensure_ascii=False, indent=2)}

## 已有诊断问题
{json.dumps(diagnostics, ensure_ascii=False, indent=2)}

## 蒸馏知识 - 市场趋势
- 女频CEO/闪婚/背叛/重生复仇是主流高播放题材
- 男频系统/异能降临正在崛起
- 标题最佳长度40-60字符
- 封面需要强文字钩子（5-7词）
- 最强钩子配对: emotion+identity, relationship+reversal, identity+reversal

## 请输出以下JSON格式（不要输出其他内容）：
```json
{{
  "channel_positioning": "频道定位评估（一句话）",
  "content_mix_analysis": "当前内容组合分析",
  "audience_insight": "受众洞察",
  "top_performing_pattern": "爆款模式总结",
  "underperforming_pattern": "低效模式总结",
  "title_strategy": {{
    "current_issues": ["当前标题问题1", "问题2"],
    "recommended_formula": "推荐的标题公式",
    "optimal_length": "推荐标题长度",
    "emoji_strategy": "emoji使用建议"
  }},
  "thumbnail_strategy": {{
    "current_issues": ["当前封面问题1"],
    "recommended_style": "推荐封面风格",
    "text_overlay": "封面文字建议"
  }},
  "content_strategy": {{
    "primary_genre": "主攻题材",
    "secondary_genre": "测试题材",
    "genre_ratio": "建议比例",
    "publishing_frequency": "发布频率建议",
    "best_publish_time": "最佳发布时间"
  }},
  "seo_recommendations": ["SEO建议1", "建议2"],
  "growth_roadmap": {{
    "30_day": ["30天目标1", "目标2"],
    "90_day": ["90天目标1", "目标2"],
    "key_metrics_to_track": ["关键指标1", "指标2"]
  }},
  "competitive_advantage": "频道竞争优势",
  "biggest_risk": "最大风险",
  "priority_actions": [
    {{"action": "行动1", "impact": "high/medium/low", "effort": "low/medium/high"}},
    {{"action": "行动2", "impact": "high/medium/low", "effort": "low/medium/high"}},
    {{"action": "行动3", "impact": "high/medium/low", "effort": "low/medium/high"}}
  ]
}}
```"""

result = call_for_task("channel_analysis", channel_prompt, max_tokens=8192, temperature=0.5)
channel_llm = parse_json_response(result)

if 'error' in channel_llm and channel_llm.get('error'):
    print(f"⚠️ 频道分析错误: {channel_llm['error']}")
    channel_llm = {"error": channel_llm.get('error', ''), "raw": channel_llm.get('raw', result.get('content', '')[:1000])}
else:
    print(f"✅ 频道分析完成")
    print(f"  定位: {channel_llm.get('channel_positioning', 'N/A')[:80]}")

# ============================================================
# 5. 保存结果
# ============================================================
output = {
    "channel_name": "Apocalyptic Films",
    "language": "en",
    "diagnosed_at": datetime.now(timezone.utc).isoformat(),
    "channel": {
        "channel_id": channel_stats['channel_id'],
        "name": channel_stats['name'],
        "subscribers": channel_stats['subscribers'],
        "total_views": channel_stats['total_views'],
        "total_videos": channel_stats['total_videos'],
        "country": channel_stats['country'],
        "published_at": channel_stats['published_at'],
        "analytics_30d": {
            "views": analytics_dict.get('views', 0),
            "likes": analytics_dict.get('likes', 0),
            "comments": analytics_dict.get('comments', 0),
            "shares": analytics_dict.get('shares', 0),
            "avg_view_duration": analytics_dict.get('averageViewDuration', 0),
            "avg_view_pct": analytics_dict.get('averageViewPercentage', 0),
            "subscribers_gained": analytics_dict.get('subscribersGained', 0),
            "subscribers_lost": analytics_dict.get('subscribersLost', 0),
            "traffic_ratios": traffic,
            "geo_top5": dict(list(geo.items())[:5]),
            "demographics": demographics,
        },
        "view_distribution": view_dist,
        "engagement_funnel": engagement,
        "growth": growth,
        "diagnostics": diagnostics,
    },
    "channel_llm": channel_llm,
    "video_scores": video_scores,
    "summary": summary,
    "retention_data": None,
}

output_path = 'data/own/channel_diagnosis/Apocalyptic_Films_latest.json'
with open(output_path, 'w', encoding='utf-8') as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n=== 诊断完成 ===")
print(f"结果已保存到: {output_path}")
print(f"分析视频: {len(video_scores)}条")
print(f"有效分析: {len(valid_scores)}条")
if valid_scores:
    print(f"平均综合评分: {avg_scores.get('avg_overall', 'N/A')}/10")
