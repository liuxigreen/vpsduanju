#!/usr/bin/env python3
"""追劇姐妹频道完整YouTube诊断分析"""
import sys, os, json, time, re
sys.path.insert(0, '/Users/liuxi/duanju/scripts')
from edgefn_models import call_for_task, parse_json_response

# ── 加载数据 ──────────────────────────────────────────────
BASE = "/Users/liuxi/duanju"

with open(f"{BASE}/data/own/channel_snapshots/追劇姐妹_latest.json") as f:
    snapshot = json.load(f)

with open(f"{BASE}/data/own/channel_diagnosis/追劇姐妹_covers.json") as f:
    covers = json.load(f)

with open(f"{BASE}/knowledge/繁中/distill.json") as f:
    distill = json.load(f)

with open(f"{BASE}/data/yt_analytics/hk.json") as f:
    oauth = json.load(f)

# 建立cover索引
cover_map = {}
for d in covers.get("details", []):
    cover_map[d["video_id"]] = d

# 提取蒸馏知识摘要
distill_summary = distill.get("why", {}).get("title", [])
distill_templates = distill.get("what", [])
distill_market = distill.get("why", {}).get("market_insights", {})

# ── 构建逐视频分析prompt ──────────────────────────────────
def build_video_prompt(v, cover_data, idx, total):
    vid = v["video_id"]
    title = v["title"]
    views = v.get("views", 0)
    likes = v.get("likes", 0)
    like_rate = round(likes / max(views, 1) * 100, 2)
    duration = v.get("duration", "")

    # 封面数据
    cover_section = ""
    if cover_data:
        c = cover_data
        cover_section = f"""
【封面MiMo分析 - 已有数据，直接使用】
- 人物评分: {c.get('person_score')}/10 — {c.get('person_detail','')}
- 情绪评分: {c.get('emotion_score')}/10 — {c.get('emotion_detail','')}
- 道具评分: {c.get('prop_score')}/10 — {c.get('prop_detail','')}
- 色彩评分: {c.get('color_score')}/10 — {c.get('color_detail','')}
- 文字评分: {c.get('text_score')}/10 — {c.get('text_detail','')}
- 构图评分: {c.get('composition_score')}/10 — {c.get('composition_detail','')}
- 综合评分: {c.get('overall_score')}/10
- 封面×标题协同: {json.dumps(c.get('封面×标题协同',{}), ensure_ascii=False)}
"""

    prompt = f"""你是短剧YouTube频道标题优化专家。分析以下视频标题，给出评分和优化建议。

## 视频 #{idx}/{total}
- 视频ID: {vid}
- 标题: {title}
- 播放: {views} | 点赞: {likes} | 赞率: {like_rate}%
- 时长: {duration}
{cover_section}

## 分析框架
### 钩子×骨架×包装
**钩子类型（6+类）**：情绪类(spoiled/obsessed/heartbroken/furious/terrifying)、身份类(billionaire/CEO/heiress/secret agent)、反转类(but actually/turns out/reborn/exposed)、时间类(10 years later/after divorce/from tomorrow's me)、冲突类(betrayed/abandoned/forced/revenge)、关系类(stepbrother/ex-husband/arranged marriage)

**5种标题骨架**：
1. 先抑后扬：「被[伤害]后，我[反转]」
2. 低位闯高位：「[低位身份]闯入[高位场景]」
3. 隐藏身份：「所有人都不知道我是[真实身份]」
4. 第一人称极端遭遇：「我[极端遭遇]，然后[反转]」
5. 契约/交易：「为了[目的]，我[妥协]」

**评分公式**：
- 9-10分：三重钩子 + 具体场景 + 悬念
- 7-8分：两个钩子 + 具体场景 + 点击欲望
- 5-6分：一个钩子但表述可以更有力
- 3-4分：概述型/泛冲突/缺少悬念
- 1-2分：无钩子/纯描述/完全无点击欲望

### 封面协同评分
- 有MiMo数据时，基于MiMo的封面×标题协同analysis评分
- 无MiMo数据时，基于标题推测封面应有的协同模式

## 输出JSON（严格格式）
```json
{{
  "n": {idx},
  "score": 7.5,
  "title_analysis": {{
    "skeleton": "先抑后扬",
    "hooks": {{"情绪类": "愤怒/心疼", "身份类": "女强人/首富"}},
    "hook_types_found": ["情绪类", "身份类", "反转类"],
    "packaging": "疑问句式+省略号悬念",
    "missing": ["缺少时间钩子"]
  }},
  "cover_synergy": {{
    "score": 7,
    "synergy_pattern": "封面定格高潮标题补前因",
    "anti_pattern": "无",
    "assessment": "封面与标题协同良好...",
    "improvement": "可在封面添加..."
  }},
  "issues": ["标题过长，核心钩子被稀释"],
  "optimized": [
    {{"title": "优化后标题1", "reason": "加入了情绪钩子和反转钩子"}},
    {{"title": "优化后标题2", "reason": "缩短了长度，强化了身份钩子"}}
  ],
  "video_id": "{vid}",
  "title": {json.dumps(title, ensure_ascii=False)},
  "views": {views},
  "likes": {likes},
  "like_rate": {like_rate}
}}
```

注意：
- score必须是number（如7.5），不能是object
- 钩子类型用中文名称
- 优化标题保持中文
- 封面协同：已有MiMo数据的直接用其分析，anti_pattern有才写没有就不写
- 评分时要对比播放量和赞率，高播放低赞率说明标题好但内容差，低播放高赞率说明标题差但内容好"""
    return prompt


# ── 逐视频分析 ────────────────────────────────────────────
videos = snapshot.get("videos", [])
total = len(videos)
print(f"共{total}条视频，开始逐条分析...")

video_scores = []
for i, v in enumerate(videos):
    vid = v["video_id"]
    print(f"\n[{i+1}/{total}] 分析 {vid}...")
    cover_data = cover_map.get(vid)
    has_cover = "有MiMo" if cover_data else "无MiMo"
    print(f"  封面数据: {has_cover}")

    prompt = build_video_prompt(v, cover_data, i+1, total)
    result = call_for_task("title_optimize", prompt, max_tokens=8192, temperature=0.5)

    if result.get("error"):
        print(f"  ❌ 调用失败: {result['error']}")
        parsed = {"error": result["error"], "video_id": vid, "n": i+1}
    else:
        parsed = parse_json_response(result)
        if "error" in parsed:
            print(f"  ⚠️ JSON解析问题: {parsed['error']}")
        else:
            print(f"  ✅ 评分: {parsed.get('score', '?')}")

    video_scores.append(parsed)
    if i < total - 1:
        time.sleep(3)  # 间隔3秒

print(f"\n逐视频分析完成，共{len(video_scores)}条")

# ── 频道级战略分析 ────────────────────────────────────────
# 聚合数据
scores_list = []
total_likes = 0
total_views_sum = 0
for vs in video_scores:
    if "score" in vs and isinstance(vs["score"], (int, float)):
        scores_list.append(vs["score"])
    total_likes += vs.get("likes", 0)
    total_views_sum += vs.get("views", 0)

avg_score = round(sum(scores_list) / len(scores_list), 1) if scores_list else 0
avg_like_rate = round(total_likes / max(total_views_sum, 1) * 100, 2)

# 构建频道级prompt
video_summaries = []
for vs in video_scores:
    summary = {
        "video_id": vs.get("video_id", ""),
        "title": vs.get("title", ""),
        "score": vs.get("score"),
        "views": vs.get("views", 0),
        "likes": vs.get("likes", 0),
        "like_rate": vs.get("like_rate", 0),
        "skeleton": vs.get("title_analysis", {}).get("skeleton", ""),
        "hooks": vs.get("title_analysis", {}).get("hook_types_found", []),
        "issues": vs.get("issues", [])[:2],
        "cover_synergy_score": vs.get("cover_synergy", {}).get("score", 0),
    }
    video_summaries.append(summary)

# OAuth摘要
oauth_summary = {
    "period": "30d",
    "total_views": oauth["summary"]["rows"][0][0],
    "total_likes": oauth["summary"]["rows"][0][1],
    "avg_view_duration": oauth["summary"]["rows"][0][7],
    "avg_view_pct": oauth["summary"]["rows"][0][8],
    "subscribers_gained": oauth["summary"]["rows"][0][4],
    "subscribers_lost": oauth["summary"]["rows"][0][5],
    "traffic": {r[0]: r[1] for r in oauth["traffic"]["rows"]},
    "geo_top5": {r[0]: r[1] for r in oauth["geo"]["rows"][:5]},
    "demographics": oauth["demographics"],
    "device": oauth["device"],
}

channel_prompt = f"""你是短剧YouTube频道运营诊断专家。基于以下数据，给出频道级战略分析。

## 频道基础信息
- 频道名: 追劇姐妹
- 订阅: 81 | 总播放: 18270 | 总视频: 24
- 国家: TW | 语言: 繁中
- 创建: 2026-05-07 (约47天)

## 视频分析聚合
- 总分析视频: {total}条
- 平均评分: {avg_score}/10
- 平均赞率: {avg_like_rate}%
- 各视频摘要:
{json.dumps(video_summaries, ensure_ascii=False, indent=2)}

## OAuth 30天数据
{json.dumps(oauth_summary, ensure_ascii=False, indent=2)}

## 快照诊断数据
- 播放分布: 头部3条占66%，近期断崖（最近视频仅17%）
- 互动率: 赞率0.59%（低于1.5%基准）
- 增长: 47天仅81订阅，日均1.72
- 播放/订阅比: 198:1（正常<50:1）
- 内容定位: 混杂（甜宠/虐恋/重生），主要类型占比仅21%
- SEO: 0标签，搜索流量仅0.8%
- 流量来源: 推荐57.2% + 订阅35.2%
- 最佳时长: 1-2hr（均播1336 vs 2hr+均播440）

## 繁中短剧蒸馏知识
- 身份反转是核心：「身份本身不稀缺，身份反轉才稀缺」
- 反转词是关键：「豈料、怎料、殊不知、原來」
- 极端不公配极端补偿
- 女频看关系反转，男频看战力反转
- 封面定格最大张力一秒
- 对比构图比中心美照更有点击力

## 输出JSON（严格格式）
```json
{{
  "channel_llm": {{
    "market_comparison": {{
      "vs_benchmark": "与繁中短剧标杆对比...",
      "opportunity": "该频道的机会在于..."
    }},
    "actions": [
      {{"priority": 1, "action": "具体行动", "effort": "高/中/低", "expected_impact": "预期效果"}}
    ],
    "ai_discoveries": [
      {{"pattern": "数据中发现的模式", "insight": "基于该模式的洞察"}}
    ],
    "retention_diagnosis": {{
      "status": "该频道暂无留存数据",
      "evidence": "OAuth数据中无retention字段"
    }},
    "audience_insight": {{
      "actual_profile": "基于demographics的实际受众画像",
      "match_with_content": "受众与内容的匹配度分析"
    }}
  }}
}}
```

注意：
- channel_llm字段名必须是market_comparison/actions/ai_discoveries/retention_diagnosis/audience_insight
- 所有分析文字用中文输出
- yt_analytics数据已在上述注入，请充分利用
- 没有retention数据，retention_diagnosis写"该频道暂无留存数据"
- actions至少3条，按优先级排序
- ai_discoveries至少2条"""

print("\n开始频道级战略分析...")
channel_result = call_for_task("channel_analysis", channel_prompt, max_tokens=8192, temperature=0.5)

if channel_result.get("error"):
    print(f"❌ 频道分析失败: {channel_result['error']}")
    channel_llm = {
        "market_comparison": {"vs_benchmark": "分析失败", "opportunity": "分析失败"},
        "actions": [{"priority": 1, "action": "API调用失败，请重试", "effort": "中", "expected_impact": "未知"}],
        "ai_discoveries": [],
        "retention_diagnosis": {"status": "该频道暂无留存数据", "evidence": "OAuth数据中无retention字段"},
        "audience_insight": {"actual_profile": "分析失败", "match_with_content": "分析失败"}
    }
else:
    channel_llm_parsed = parse_json_response(channel_result)
    if "error" in channel_llm_parsed:
        print(f"⚠️ 频道分析JSON解析问题: {channel_llm_parsed.get('error')}")
        channel_llm = {
            "market_comparison": {"vs_benchmark": "JSON解析失败", "opportunity": "JSON解析失败"},
            "actions": [{"priority": 1, "action": "JSON解析失败，请重试", "effort": "中", "expected_impact": "未知"}],
            "ai_discoveries": [],
            "retention_diagnosis": {"status": "该频道暂无留存数据", "evidence": "OAuth数据中无retention字段"},
            "audience_insight": {"actual_profile": "JSON解析失败", "match_with_content": "JSON解析失败"}
        }
    else:
        channel_llm = channel_llm_parsed.get("channel_llm", channel_llm_parsed)
        print("✅ 频道级分析完成")

# ── 组装最终结果 ──────────────────────────────────────────
# 确保每个video_scores项格式正确
final_video_scores = []
for vs in video_scores:
    vid = vs.get("video_id", "")
    # 确保score是number
    score = vs.get("score")
    if isinstance(score, dict):
        score = score.get("score", score.get("overall", 5.0))
    if not isinstance(score, (int, float)):
        try:
            score = float(score)
        except:
            score = 5.0

    item = {
        "video_id": vid,
        "analyses": [{
            "n": vs.get("n", 0),
            "score": score,
            "title_analysis": vs.get("title_analysis", {}),
            "cover_synergy": vs.get("cover_synergy", {}),
            "issues": vs.get("issues", []),
            "optimized": vs.get("optimized", []),
            "video_id": vid,
            "title": vs.get("title", ""),
            "views": vs.get("views", 0),
            "likes": vs.get("likes", 0),
            "like_rate": vs.get("like_rate", 0),
        }]
    }
    final_video_scores.append(item)

# 计算summary
all_scores = [item["analyses"][0]["score"] for item in final_video_scores]
all_like_rates = [item["analyses"][0]["like_rate"] for item in final_video_scores]
needs_opt = sum(1 for s in all_scores if s < 6)

# 收集top issues
all_issues = []
for item in final_video_scores:
    all_issues.extend(item["analyses"][0].get("issues", []))
issue_counts = {}
for issue in all_issues:
    issue_counts[issue] = issue_counts.get(issue, 0) + 1
top_issues = sorted(issue_counts.items(), key=lambda x: -x[1])[:5]

output = {
    "channel_name": "追劇姐妹",
    "language": "zh",
    "diagnosed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "channel": snapshot.get("channel_stats", {}),
    "channel_llm": channel_llm,
    "video_scores": final_video_scores,
    "summary": {
        "avg_score": round(sum(all_scores) / len(all_scores), 1) if all_scores else 0,
        "needs_optimization": needs_opt,
        "top_issues": [f"{issue} ({count}次)" for issue, count in top_issues],
        "total_videos": total,
        "avg_like_rate": round(sum(all_like_rates) / len(all_like_rates), 2) if all_like_rates else 0,
    }
}

# ── 保存 ──────────────────────────────────────────────────
out_path = f"{BASE}/data/own/channel_diagnosis/追劇姐妹_latest.json"
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(output, f, ensure_ascii=False, indent=2)

print(f"\n✅ 诊断完成，保存到: {out_path}")
print(f"   频道评分: {output['summary']['avg_score']}")
print(f"   需优化: {output['summary']['needs_optimization']}/{total}条")
print(f"   平均赞率: {output['summary']['avg_like_rate']}%")