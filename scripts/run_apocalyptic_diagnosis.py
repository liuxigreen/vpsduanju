#!/usr/bin/env python3
"""Apocalyptic Films 频道完整诊断分析 - 子agent执行"""
import sys, json, time, os
from datetime import datetime, timezone

sys.path.insert(0, os.path.expanduser("~/duanju/scripts"))
from edgefn_models import call_for_task, parse_json_response

# ── Load Data ──────────────────────────────────────────────────
base = os.path.expanduser("~/duanju")
with open(f"{base}/data/own/channel_snapshots/Apocalyptic_Films_latest.json") as f:
    snapshot = json.load(f)
with open(f"{base}/data/own/channel_diagnosis/Apocalyptic_Films_covers.json") as f:
    covers_data = json.load(f)
with open(f"{base}/knowledge/en/distill.json") as f:
    distill = json.load(f)
with open(f"{base}/data/yt_analytics/en_global.json") as f:
    analytics = json.load(f)

videos = snapshot["videos"]
covers_index = {}
for c in covers_data.get("details", []):
    covers_index[c["video_id"]] = c

# Build retention lookup from analytics
retention_data = analytics.get("retention", {})

print(f"=== Apocalyptic Films Diagnosis: {len(videos)} videos ===")
print(f"Retention data available: {retention_data.get('has_data', False)}")

# ── Per-Video Analysis ────────────────────────────────────────
def build_video_prompt(video, cover_info):
    vid = video["video_id"]
    title = video["title"]
    views = video["views"]
    likes = video["likes"]
    like_rate = round(likes / views * 100, 2) if views > 0 else 0
    
    # Cover synergy from covers.json
    synergy = cover_info.get("封面×标题协同", {})
    synergy_text = ""
    if synergy:
        synergy_text = f"""
### 封面×标题协同（已有分析，直接采用）
- 协同分: {synergy.get('score', 'N/A')}/10
- 协同模式: {synergy.get('synergy_pattern', 'N/A')}
- 反模式: {synergy.get('anti_pattern', 'N/A')}
- 评估: {synergy.get('assessment', '')[:200]}
- 改进建议: {synergy.get('improvement', '')[:150]}"""

    # Cover visual details
    cover_text = ""
    if cover_info and "person_score" in cover_info:
        cover_text = f"""
### 封面视觉分析（MiMo已有）
- 人物: {cover_info.get('person_score',0)}/10 — {cover_info.get('person_detail','')[:150]}
- 情绪: {cover_info.get('emotion_score',0)}/10 — {cover_info.get('emotion_detail','')[:150]}
- 道具: {cover_info.get('prop_score',0)}/10 — {cover_info.get('prop_detail','')[:150]}
- 文字: {cover_info.get('text_score',0)}/10 — {cover_info.get('text_detail','')[:150]}
- 构图: {cover_info.get('composition_score',0)}/10
- 色彩: {cover_info.get('color_score',0)}/10
- 总分: {cover_info.get('overall_score',0)}/10
{synergy_text}"""
    elif synergy_text:
        cover_text = synergy_text

    return f"""你是短剧YouTube频道运营诊断专家。分析以下单个视频。

## 频道信息
- 频道: Apocalyptic Films (末世/灾难/重生短剧, 英文)
- 订阅: {snapshot['channel_stats']['subscribers']}, 总播放: {snapshot['channel_stats']['total_views']}
- 赞率基准: 整体{snapshot['engagement_funnel']['overall_like_rate']}%

## 视频数据
- video_id: {vid}
- 标题: {title}
- 播放: {views}, 点赞: {likes}, 赞率: {like_rate}%
- 时长: {video.get('duration','N/A')}
- 标签: {video.get('description_tags', [])}
{cover_text}

## 诊断框架
### 钩子×骨架×创新
- 钩子分类（6+类）: emotion(情绪), identity(身份), reversal(反转), time(时间), conflict(冲突), relationship(关系), other(自由发现)
- 骨架: 先抑后扬 / 低位闯高位 / 隐藏身份 / 第一人称极端遭遇 / 契约交易
- 评分标准: 9-10=三重钩子+具体场景+悬念, 7-8=两钩子+场景+点击欲, 5-6=一钩子可更强, 3-4=概述型/泛冲突, 1-2=无钩子

### 英文末世题材蒸馏
- 高频钩子词: CEO, reborn, betrayed, revenge, apocalypse, zombie, safe house, spatial power, system
- 最佳标题长度: ~84字符(±15%)
- 骨架: "身份+伤害+反转", "低位+逆袭+打脸", "重生+改命"
- 情绪触发词: mocked, abandoned, betrayed, fuming, begging, exposed

### 封面×标题协同参考（通用框架，以上面已有分析为准）
协同模式: 标题给反差封面给证据 / 封面定格冲突标题补因果 / 情绪反转视觉化 / 互补优于重复
反模式: 题材错位 / 只美不钩 / 标题有爆点封面无证据 / 信息过散

## 输出JSON格式（严格遵循）
{{
  "video_id": "{vid}",
  "title": "{title}",
  "views": {views},
  "likes": {likes},
  "like_rate": {like_rate},
  "score": 7.5,
  "title_analysis": {{
    "skeleton": "识别到的骨架类型",
    "hooks": {{"emotion": true/false, "identity": true/false, "reversal": true/false, "time": true/false, "conflict": true/false, "relationship": true/false, "other": ["自由发现的钩子"]}},
    "hook_types_found": ["emotion", "time", ...],
    "packaging": "句式/标点/长度评估",
    "missing": ["缺失的钩子或骨架元素"]
  }},
  "cover_synergy": {{
    "score": 8,
    "synergy_pattern": "协同模式",
    "anti_pattern": "反模式或无",
    "assessment": "评估",
    "improvement": "改进建议"
  }},
  "issues": ["问题1", "问题2"],
  "optimized": [
    {{"title": "优化标题1", "reason": "优化理由"}},
    {{"title": "优化标题2", "reason": "优化理由"}}
  ]
}}

注意:
1. score必须是单个数字(如7.5)，不是object
2. 如果有封面×标题协同已有分析，直接采用其协同分和评估，补充改进建议
3. 标题优化要参考蒸馏骨架和钩子模式
4. 输出纯JSON，不要markdown代码块"""


# ── Step 3: Per-Video LLM Analysis ─────────────────────────────
video_scores = []
for i, video in enumerate(videos):
    vid = video["video_id"]
    cover = covers_index.get(vid, {})
    prompt = build_video_prompt(video, cover)
    
    print(f"\n[{i+1}/8] Analyzing: {video['title'][:60]}...")
    if i > 0:
        print("  ⏳ Waiting 3s...")
        time.sleep(3)
    
    result = call_for_task("title_optimize", prompt, max_tokens=8192, temperature=0.5)
    
    if result.get("error"):
        print(f"  ❌ Error: {result['error']}")
        # Create fallback
        video_scores.append({
            "video_id": vid,
            "title": video["title"],
            "views": video["views"],
            "likes": video["likes"],
            "like_rate": round(video["likes"]/video["views"]*100,2) if video["views"]>0 else 0,
            "analyses": [{"n": 1, "score": 5.0, "title_analysis": {}, "cover_synergy": {},
                          "issues": [f"LLM error: {result['error']}"], "optimized": [],
                          "video_id": vid, "title": video["title"],
                          "views": video["views"], "likes": video["likes"],
                          "like_rate": round(video["likes"]/video["views"]*100,2) if video["views"]>0 else 0}]
        })
        continue
    
    parsed = parse_json_response(result)
    if "error" in parsed and "raw" in parsed:
        print(f"  ⚠️ JSON parse failed, attempting raw extraction...")
        raw = parsed.get("raw", "")
        # Try to find JSON in content
        content = result.get("content", "")
        try:
            # Find the JSON object
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed = json.loads(content[start:end])
        except:
            print(f"  ❌ Could not parse. Using fallback.")
            parsed = {"score": 5.0, "title_analysis": {}, "cover_synergy": {},
                      "issues": ["JSON parse failed"], "optimized": []}
    
    # Ensure required fields
    score = parsed.get("score", 5.0)
    if isinstance(score, dict):
        score = score.get("overall", score.get("title_score", 5.0))
    
    analysis = {
        "n": 1,
        "score": float(score) if isinstance(score, (int, float)) else 5.0,
        "title_analysis": parsed.get("title_analysis", {}),
        "cover_synergy": parsed.get("cover_synergy", cover.get("封面×标题协同", {})),
        "issues": parsed.get("issues", []),
        "optimized": parsed.get("optimized", []),
        "video_id": vid,
        "title": video["title"],
        "views": video["views"],
        "likes": video["likes"],
        "like_rate": round(video["likes"]/video["views"]*100, 2) if video["views"] > 0 else 0
    }
    
    video_scores.append({
        "video_id": vid,
        "analyses": [analysis]
    })
    
    print(f"  ✅ Score: {analysis['score']}, Hooks: {analysis['title_analysis'].get('hook_types_found', [])}")

# ── Step 4: Aggregate Statistics ───────────────────────────────
print("\n=== Aggregating Statistics ===")

scores = []
like_rates = []
hook_dist = {"emotion":0,"identity":0,"reversal":0,"time":0,"conflict":0,"relationship":0,"other":0}
skeleton_dist = {}
top_issues = []

for vs in video_scores:
    a = vs["analyses"][0]
    s = a["score"]
    scores.append(s)
    like_rates.append(a.get("like_rate", 0))
    
    # Hook distribution from LLM
    hooks = a.get("title_analysis", {}).get("hooks", {})
    for k in ["emotion","identity","reversal","time","conflict","relationship"]:
        if hooks.get(k):
            hook_dist[k] += 1
    other_hooks = hooks.get("other", [])
    if isinstance(other_hooks, list) and other_hooks:
        hook_dist["other"] += len(other_hooks)
    
    # Skeleton distribution
    sk = a.get("title_analysis", {}).get("skeleton", "unknown")
    skeleton_dist[sk] = skeleton_dist.get(sk, 0) + 1
    
    # Issues
    for issue in a.get("issues", []):
        top_issues.append(issue)

avg_score = round(sum(scores) / len(scores), 1) if scores else 0
needs_opt = sum(1 for s in scores if s < 7)
avg_lr = round(sum(like_rates) / len(like_rates), 2) if like_rates else 0

# Count hook levels
hook_levels = {"triple":0, "double":0, "single":0, "none":0}
for vs in video_scores:
    hooks = vs["analyses"][0].get("title_analysis", {}).get("hooks", {})
    active = sum(1 for k in ["emotion","identity","reversal","time","conflict","relationship"] if hooks.get(k))
    other_len = len(hooks.get("other", [])) if isinstance(hooks.get("other"), list) else 0
    total = active + (1 if other_len > 0 else 0)
    if total >= 3: hook_levels["triple"] += 1
    elif total == 2: hook_levels["double"] += 1
    elif total == 1: hook_levels["single"] += 1
    else: hook_levels["none"] += 1

print(f"  Avg score: {avg_score}, Needs optimization: {needs_opt}/{len(scores)}")
print(f"  Hook levels: {hook_levels}")
print(f"  Hook distribution: {hook_dist}")
print(f"  Skeleton distribution: {skeleton_dist}")

# ── Step 5: Channel-Level Strategic Analysis ───────────────────
print("\n=== Channel-Level Strategic Analysis ===")

# Prepare findings for channel LLM
ch = snapshot["channel_stats"]
analytics_summary = snapshot.get("analytics", {})
engagement = snapshot.get("engagement_funnel", {})
view_dist = snapshot.get("view_distribution", {})
growth = snapshot.get("growth", {})
weekly = snapshot.get("weekly_growth", {})

# Build cover summary
cover_avg = covers_data.get("avg_scores", {})
cover_synergy_scores = []
for c in covers_data.get("details", []):
    syn = c.get("封面×标题协同", {})
    if syn.get("score"):
        cover_synergy_scores.append(syn["score"])
avg_cover_synergy = round(sum(cover_synergy_scores)/len(cover_synergy_scores), 1) if cover_synergy_scores else 0

# Retention summary
ret_summary = ""
if retention_data.get("has_data"):
    ret_summary = f"""
### 留存数据（OAuth实测, {retention_data.get('video_count',0)}个视频）
- 1%处平均留存: {retention_data.get('avg_retention_1pct',0)*100:.1f}% (>80%=hook强)
- 3分钟处平均留存: {retention_data.get('avg_retention_3min',0)*100:.1f}% (>30%=好)
- 5分钟处平均留存: {retention_data.get('avg_retention_5min',0)*100:.1f}% (>25%=好)
- Hook质量: {"强" if retention_data.get("avg_retention_1pct",0)>0.8 else "一般" if retention_data.get("avg_retention_1pct",0)>0.6 else "差"}
"""

# Video scores summary for channel prompt
vs_summary = "\n".join([
    f"  - {vs['analyses'][0]['title'][:50]}... | Score:{vs['analyses'][0]['score']} | Views:{vs['analyses'][0]['views']} | LikeRate:{vs['analyses'][0]['like_rate']}%"
    for vs in video_scores
])

# Demographics
demographics = analytics.get("demographics", [])
female_pct = sum(d["pct"] for d in demographics if d["gender"]=="female")
male_pct = sum(d["pct"] for d in demographics if d["gender"]=="male")
top_age = max(demographics, key=lambda d: d["pct"]) if demographics else {}

channel_prompt = f"""你是短剧YouTube频道运营诊断专家。对Apocalyptic Films频道进行战略诊断。

## 频道基础数据
- 频道: Apocalyptic Films, 英文末世/灾难/重生短剧
- 订阅: {ch['subscribers']}, 总播放: {ch['total_views']}, 总视频: {ch['total_videos']}
- 创建: {ch['published_at'][:10]}, 国家: {ch['country']}

## 30天OAuth数据
- 观看: {analytics_summary.get('views',0):,}, 点赞: {analytics_summary.get('likes',0):,}, 评论: {analytics_summary.get('comments',0):,}
- 赞率: {round(analytics_summary.get('likes',0)/analytics_summary.get('views',1)*100,2)}%
- 平均观看时长: {analytics_summary.get('averageViewDuration',0)}秒, 平均观看比例: {analytics_summary.get('averageViewPercentage',0)}%
- 总观看分钟: {analytics_summary.get('estimatedMinutesWatched',0):,}
- 新增订阅: {analytics_summary.get('subscribersGained',0)}, 流失: {analytics_summary.get('subscribersLost',0)}
- 分享: {analytics_summary.get('shares',0)}

## 流量来源
- 推荐: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('RELATED_VIDEO',0)}%
- 订阅: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('SUBSCRIBER',0)}%
- 搜索: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('YT_SEARCH',0)}%
- 其他页面: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('YT_OTHER_PAGE',0)}%
- 频道页: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('YT_CHANNEL',0)}%
- 播放列表: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('PLAYLIST',0)}%
- 外部: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('EXT_URL',0)}%
- 通知: {snapshot.get('analytics',{}).get('traffic_ratios',{}).get('NOTIFICATION',0)}%

## 地域分布（30天）
{json.dumps({r[0]:r[1] for r in analytics.get("geo",{}).get("rows",[])}, indent=2)}

## 受众分布
- 女性: {female_pct}%, 男性: {male_pct}%
- 最大年龄组: {top_age.get('age','N/A')} {top_age.get('gender','N/A')} {top_age.get('pct',0)}%
- 完整分布: {json.dumps(demographics, indent=2)}

## 设备分布
{json.dumps({d["type"]:d["views"] for d in analytics.get("device",[])}, indent=2)}

## 近8条视频分析结果
{vs_summary}

## 聚合统计
- 平均诊断分: {avg_score}/10
- 需优化视频: {needs_opt}/{len(scores)}
- 钩子层级: 三重{hook_levels['triple']}条, 双重{hook_levels['double']}条, 单一{hook_levels['single']}条, 无{hook_levels['none']}条
- 钩子分布: {json.dumps(hook_dist)}
- 骨架分布: {json.dumps(skeleton_dist)}
- 平均赞率: {avg_lr}%
- 封面平均总分: {cover_avg.get('avg_overall_score',0)}/10
- 封面×标题平均协同分: {avg_cover_synergy}/10

## 播放分布
- 头部3条占比: {view_dist.get('top3_ratio',0)}%
- 头部1条占比: {view_dist.get('head_ratio',0)}%
- 尾部占比: {view_dist.get('tail_ratio',0)}%
- 均匀度: {view_dist.get('uniformity',0)}

## 增长趋势
- 日增订阅: {growth.get('daily_sub_growth',0)}, 日增播放: {growth.get('daily_view_growth',0)}
- 周增订阅: {weekly.get('subscribers_change',0)} ({weekly.get('subscribers_change_pct',0)}%)
- 赞率变化: {growth.get('like_rate_prev',0)}% → {growth.get('like_rate_curr',0)}%

{ret_summary}

## 蒸馏知识（英文末世/重生短剧）
- 高频钩子词: reborn, betrayed, apocalypse, zombie, safe house, spatial power, system, ex, revenge
- 标题骨架: "身份+伤害+反转", "低位+逆袭+打脸", "重生+改命"
- 最强配对: emotion+identity, relationship+reversal, identity+reversal
- 发布最佳: Thu/Fri/Wed, UTC 10-16时
- 末世题材是英文短剧蓝海，无专门竞品

## 诊断标准
- 赞率: >3%标杆, 1.5-3%健康, <1%转化差
- 播放分布: 头部>50%=爆款依赖
- 留存: 1%处>80%=hook强
- 流量: 推荐>40%=CTR健康, 订阅>25%=粉丝粘性强
- YPP: 短剧频道25-30天可达标

## 输出JSON格式（严格15字段）
{{
  "market_comparison": {{"vs_benchmark": "与末世/短剧赛道对比", "opportunity": "机会分析"}},
  "actions": [
    {{"priority": 1, "action": "具体行动", "effort": "低/中/高", "expected_impact": "预期效果"}},
    {{"priority": 2, "action": "...", "effort": "...", "expected_impact": "..."}},
    {{"priority": 3, "action": "...", "effort": "...", "expected_impact": "..."}}
  ],
  "ai_discoveries": [
    {{"pattern": "发现的模式", "insight": "洞察"}},
    {{"pattern": "...", "insight": "..."}}
  ],
  "retention_diagnosis": {{"status": "好/一般/差", "evidence": "证据", "hook_quality": "hook质量评估"}},
  "audience_insight": {{"actual_profile": "实际受众画像", "age_gender_breakdown": "年龄性别分布洞察", "match_with_content": "与内容的匹配度"}}
}}

注意: 字段名必须严格是 market_comparison / actions / ai_discoveries / retention_diagnosis / audience_insight。输出纯JSON。"""

print("  Calling Pro for channel analysis...")
time.sleep(3)
channel_result = call_for_task("channel_analysis", channel_prompt, max_tokens=8192, temperature=0.5)

channel_llm = {}
if channel_result.get("error"):
    print(f"  ❌ Channel LLM error: {channel_result['error']}")
    channel_llm = {
        "market_comparison": {"vs_benchmark": "LLM error", "opportunity": "N/A"},
        "actions": [],
        "ai_discoveries": [],
        "retention_diagnosis": {"status": "N/A", "evidence": "", "hook_quality": ""},
        "audience_insight": {"actual_profile": "", "age_gender_breakdown": "", "match_with_content": ""}
    }
else:
    parsed_channel = parse_json_response(channel_result)
    if "error" in parsed_channel and "raw" in parsed_channel:
        content = channel_result.get("content", "")
        try:
            start = content.find("{")
            end = content.rfind("}") + 1
            if start >= 0 and end > start:
                parsed_channel = json.loads(content[start:end])
        except:
            parsed_channel = {}
    
    # Extract the 5 required fields
    channel_llm = {
        "market_comparison": parsed_channel.get("market_comparison", {}),
        "actions": parsed_channel.get("actions", []),
        "ai_discoveries": parsed_channel.get("ai_discoveries", []),
        "retention_diagnosis": parsed_channel.get("retention_diagnosis", {}),
        "audience_insight": parsed_channel.get("audience_insight", {})
    }
    print(f"  ✅ Channel analysis complete. Actions: {len(channel_llm['actions'])}")

# ── Step 6: Build & Save Final JSON ────────────────────────────
print("\n=== Building Final JSON ===")

# Channel stats from snapshot
channel_stats = snapshot["channel_stats"]

final = {
    "channel_name": "Apocalyptic Films",
    "language": "en",
    "diagnosed_at": datetime.now(timezone.utc).isoformat(),
    "channel": {
        "subscribers": channel_stats["subscribers"],
        "total_views": channel_stats["total_views"],
        "total_videos": channel_stats["total_videos"],
        "published_at": channel_stats["published_at"],
        "country": channel_stats.get("country", "US"),
        "avg_views": round(channel_stats["total_views"] / max(channel_stats["total_videos"], 1)),
    },
    "channel_llm": channel_llm,
    "video_scores": video_scores,
    "summary": {
        "avg_score": avg_score,
        "needs_optimization": needs_opt,
        "top_issues": list(set(top_issues))[:10],
        "total_videos": len(videos),
        "avg_like_rate": avg_lr
    },
    "retention_data": retention_data if retention_data.get("has_data") else None
}

output_path = f"{base}/data/own/channel_diagnosis/Apocalyptic_Films_latest.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=2)

print(f"\n✅ Saved to: {output_path}")
print(f"   Videos analyzed: {len(video_scores)}")
print(f"   Avg score: {avg_score}")
print(f"   Needs optimization: {needs_opt}/{len(scores)}")
print(f"   Channel LLM fields: {list(channel_llm.keys())}")
print(f"   Retention data: {'included' if final['retention_data'] else 'none'}")
