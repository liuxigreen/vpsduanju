#!/usr/bin/env python3
"""
diagnosis_engine.py — 频道深度诊断引擎

分析维度：
- 播放分布（头部集中度/长尾/断崖）
- 标题模式（长度/emoji/钩子词/公式）
- 点赞漏斗（播放→点赞→评论转化）
- 内容一致性（是否偏离定位）
- SEO分析（标签/描述）
- 发布节奏（频率/时间/间隔稳定性）
- 视频时长与表现
- 周增长趋势
- 竞品对标（同量级频道对比）

输出：结构化诊断报告，每条建议含具体数据+可执行步骤
"""
from __future__ import annotations

import re
import os
import json
import requests
from collections import Counter
from datetime import datetime, timezone
from typing import Optional


def classify_genre_deepseek(videos: list, lang: str = "es") -> dict:
    """用LLM分析视频题材，基于标题+description_tags（自动路由：flash）"""
    if not videos:
        return {"genre_tags": [], "confidence": "low", "reasoning": "无视频数据"}

    from edgefn_models import call_for_task, parse_json_response

    sorted_videos = sorted(videos, key=lambda v: v.get("views", 0), reverse=True)[:5]
    video_texts = []
    for v in sorted_videos:
        title = v.get("title", "")
        tags = v.get("description_tags", [])
        tags_str = ", ".join(tags[:5]) if tags else "无"
        video_texts.append(f"标题: {title}\n标签: {tags_str}")
    sample_text = "\n---\n".join(video_texts)

    prompt = f"""你是短剧题材分类专家。根据以下{len(sorted_videos)}个视频的标题和标签，判断该频道的整体题材（1-3个标签）。

可选标签：大女主、逆袭、复仇、甜宠、虐恋、豪门、重生、穿越、战神、赘婿、都市、悬疑、古装、校园、职场、家庭伦理、霸总、闪婚、萌宝、医神、末世、系统流

视频数据：
{sample_text}

严格返回JSON：{{"genre_tags": ["标签"], "confidence": "high/medium/low", "reasoning": "一句话"}}"""

    result = call_for_task("genre_classify", prompt)
    if result["error"]:
        return {"genre_tags": [], "confidence": "low", "reasoning": result["error"]}

    parsed = parse_json_response(result)
    if "error" in parsed:
        return {"genre_tags": [], "confidence": "low", "reasoning": parsed["error"]}

    return {
        "genre_tags": parsed.get("genre_tags", []),
        "confidence": parsed.get("confidence", "medium"),
        "reasoning": parsed.get("reasoning", ""),
        "method": "llm"
    }


def analyze_view_distribution(videos: list) -> dict:
    """播放分布分析：头部集中度、长尾比例、是否有断崖"""
    if not videos:
        return {}

    views = sorted([v["views"] for v in videos], reverse=True)
    total = sum(views)
    if total == 0:
        return {"concentration": 0, "head_ratio": 0, "cliff": False}

    # Top 3 占比
    top3_ratio = sum(views[:3]) / total * 100 if len(views) >= 3 else 100

    # 头部（top 20%）占比
    head_count = max(1, len(views) // 5)
    head_ratio = sum(views[:head_count]) / total * 100

    # 长尾（bottom 50%）占比
    tail_count = len(views) // 2
    tail_ratio = sum(views[-tail_count:]) / total * 100 if tail_count > 0 else 0

    # 断崖检测：最近5条 vs 前5条
    cliff = False
    cliff_ratio = 0
    if len(views) >= 10:
        recent_5 = sorted([v["views"] for v in videos[:5]], reverse=True)
        # Get older videos (by published_at)
        sorted_by_date = sorted(videos, key=lambda x: x.get("published_at", ""), reverse=True)
        recent_5 = [v["views"] for v in sorted_by_date[:5]]
        older_5 = [v["views"] for v in sorted_by_date[5:10]]
        if older_5 and sum(older_5) > 0:
            cliff_ratio = sum(recent_5) / (sum(older_5) / len(older_5) * len(recent_5))
            if cliff_ratio < 0.3:  # 最近播放不到之前的30%
                cliff = True

    # 均匀度（0-1，1=完全均匀）
    if len(views) > 1:
        avg = total / len(views)
        variance = sum((v - avg) ** 2 for v in views) / len(views)
        cv = (variance ** 0.5) / avg if avg > 0 else 0  # 变异系数
        uniformity = max(0, 1 - cv / 3)  # 归一化
    else:
        uniformity = 1

    return {
        "top3_ratio": round(top3_ratio, 1),
        "head_ratio": round(head_ratio, 1),
        "tail_ratio": round(tail_ratio, 1),
        "cliff": cliff,
        "cliff_ratio": round(cliff_ratio, 2),
        "uniformity": round(uniformity, 2),
        "total_views": total,
        "avg_views": round(total / len(views)) if views else 0,
    }


def analyze_title_patterns(videos: list) -> dict:
    """标题模式深度分析"""
    if not videos:
        return {}

    lengths = [len(v["title"]) for v in videos]

    # Emoji 分析
    emoji_pattern = re.compile(r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\u2764\uFE0F⭐🌟❤️🔥💀👁️‍🗨️]')
    emoji_videos = [v for v in videos if emoji_pattern.search(v["title"])]

    # 重复 emoji 模式（如 ❤️⭐️🌟 每个标题都有）
    emoji_seqs = []
    for v in videos:
        found = emoji_pattern.findall(v["title"])
        emoji_seqs.append("".join(found))
    seq_counter = Counter(emoji_seqs)
    repeated_emoji = any(count > len(videos) * 0.5 for count in seq_counter.values())

    # 钩子词检测
    hook_words = ["真相", "秘密", "震惊", "没想到", "竟然", "居然", "突然", "发现",
                  "最后", "结局", "反转", "逆袭", "复仇", "打脸", "觉醒",
                  "secret", "truth", "reveal", "shocking", "twist", "ending", "revenge",
                  "爆火", "全集", "完整版", "FULL", "合集"]
    hook_counts = {}
    for word in hook_words:
        count = sum(1 for v in videos if word.lower() in v["title"].lower())
        if count > 0:
            hook_counts[word] = count

    # 标题重复度
    title_starts = [v["title"][:10] for v in videos]
    start_counter = Counter(title_starts)
    repeated_starts = {k: v for k, v in start_counter.items() if v > 2}

    # 长度 vs 表现
    def avg_lr(vids):
        if not vids:
            return 0
        rates = [v["likes"]/v["views"]*100 if v["views"] > 0 else 0 for v in vids]
        return sum(rates)/len(rates)

    short = [v for v in videos if len(v["title"]) <= 40]
    medium = [v for v in videos if 40 < len(v["title"]) <= 60]
    long = [v for v in videos if 60 < len(v["title"]) <= 80]
    xlong = [v for v in videos if len(v["title"]) > 80]

    # 最佳长度区间
    buckets = {"≤40": short, "41-60": medium, "61-80": long, ">80": xlong}
    best_bucket = max(buckets.items(), key=lambda x: avg_lr(x[1]) if x[1] else -1)

    return {
        "avg_length": round(sum(lengths)/len(lengths), 0),
        "min_length": min(lengths),
        "max_length": max(lengths),
        "emoji_ratio": round(len(emoji_videos)/len(videos), 2),
        "repeated_emoji": repeated_emoji,
        "hook_words": hook_counts,
        "repeated_starts": repeated_starts,
        "length_performance": {
            "≤40": {"count": len(short), "avg_like_rate": round(avg_lr(short), 2)},
            "41-60": {"count": len(medium), "avg_like_rate": round(avg_lr(medium), 2)},
            "61-80": {"count": len(long), "avg_like_rate": round(avg_lr(long), 2)},
            ">80": {"count": len(xlong), "avg_like_rate": round(avg_lr(xlong), 2)},
        },
        "best_length_bucket": best_bucket[0],
        "best_length_lr": round(avg_lr(best_bucket[1]), 2) if best_bucket[1] else 0,
    }


def analyze_engagement_funnel(videos: list) -> dict:
    """点赞漏斗分析：播放→点赞→评论"""
    if not videos:
        return {}

    total_views = sum(v["views"] for v in videos)
    total_likes = sum(v["likes"] for v in videos)
    total_comments = sum(v.get("comments", 0) for v in videos)

    # 零互动视频
    zero_like_videos = [v for v in videos if v.get("likes", 0) == 0 and v.get("views", 0) > 0]
    zero_comment_videos = [v for v in videos if v.get("comments", 0) == 0 and v.get("views", 0) > 0]

    # 高互动视频（点赞率 > 2%）
    high_eng = [v for v in videos if v["views"] > 0 and v["likes"]/v["views"]*100 > 2.0]

    # 评论/点赞比（反映内容深度）
    comment_like_ratio = total_comments / total_likes * 100 if total_likes > 0 else 0

    return {
        "total_views": total_views,
        "total_likes": total_likes,
        "total_comments": total_comments,
        "overall_like_rate": round(total_likes / total_views * 100, 2) if total_views > 0 else 0,
        "overall_comment_rate": round(total_comments / total_views * 100, 3) if total_views > 0 else 0,
        "comment_like_ratio": round(comment_like_ratio, 1),
        "zero_like_count": len(zero_like_videos),
        "zero_like_ratio": round(len(zero_like_videos) / len(videos), 2),
        "high_engagement_count": len(high_eng),
        "high_engagement_ratio": round(len(high_eng) / len(videos), 2),
    }


def analyze_content_consistency(videos: list, channel_niche: str = "", distill: dict = None) -> dict:
    """内容一致性分析：是否偏离定位"""
    if not videos:
        return {}

    # 提取所有标签
    all_tags = []
    for v in videos:
        all_tags.extend(v.get("tags", []))
    tag_counter = Counter(all_tags)

    # 提取标题关键词
    title_words = []
    for v in videos:
        # 中文分词（简单按字符）
        title_words.extend(re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', v["title"]))
    word_counter = Counter(title_words)

    # 内容类型检测（中文关键词 + 蒸馏数据的多语种题材标签）
    content_types = {
        "霸总": ["总裁", "CEO", "boss", "霸总", "豪门", "董事长"],
        "甜宠": ["甜宠", "甜蜜", "恋爱", "爱情", "情人", "男友", "女友", "sweet", "love", "romance", "romantic"],
        "虐恋": ["虐", "心碎", "分手", "背叛", "错爱", "伤", "betrayal", "heartbreak", "pain"],
        "复仇": ["复仇", "逆袭", "打脸", "报复", "反击", "revenge", "venganza", "vingança"],
        "古装": ["古代", "宫廷", "王爷", "王妃", "皇帝", "皇后", "穿越"],
        "家庭": ["家庭", "妈妈", "爸爸", "儿子", "女儿", "亲情", "萌宝", "family", "familia", "mãe", "pai"],
        "末世": ["末世", "末日", "丧尸", "生存", "apocalypse", "zombie", "survival"],
        "系统": ["系统", "升级", "level", "system", "game"],
        "ceo": ["ceo", "billionaire", "boss", "empresário", "CEO"],
        "重生": ["重生", "reborn", "renacer", "renascer", "reborn"],
        "豪门": ["豪门", "rich", "wealthy", "rico", "riquísimo", "herdeiro"],
        "contract": ["contract", "contrato", "casamento", "marriage", "married", "married"],
    }

    # 从蒸馏数据加载多语种题材标签
    if distill:
        genre_tags = distill.get("meta", {}).get("genre_tags", [])
        for tag in genre_tags:
            tag_lower = tag.lower()
            # 检查是否已经在content_types中
            found = False
            for ctype, keywords in content_types.items():
                if tag_lower in [k.lower() for k in keywords]:
                    found = True
                    break
            if not found:
                # 为新标签创建一个类型
                content_types[tag_lower] = [tag_lower]

    detected_types = {}
    for ctype, keywords in content_types.items():
        count = sum(1 for v in videos if any(kw.lower() in v["title"].lower() for kw in keywords))
        if count > 0:
            detected_types[ctype] = count

    # 主要类型
    primary_type = max(detected_types.items(), key=lambda x: x[1])[0] if detected_types else "未知"
    primary_ratio = detected_types.get(primary_type, 0) / len(videos) if videos else 0

    # 一致性评分（主要类型占比越高越一致）
    consistency = primary_ratio

    return {
        "top_tags": dict(tag_counter.most_common(10)),
        "top_title_words": dict(word_counter.most_common(15)),
        "detected_types": detected_types,
        "primary_type": primary_type,
        "primary_ratio": round(primary_ratio, 2),
        "consistency_score": round(consistency, 2),
    }


def analyze_seo(videos: list) -> dict:
    """SEO分析：标签使用、描述优化"""
    if not videos:
        return {}

    # 标签统计
    total_tags = sum(len(v.get("tags", [])) for v in videos)
    avg_tags = total_tags / len(videos) if videos else 0
    videos_with_tags = sum(1 for v in videos if v.get("tags"))

    # 热门标签
    all_tags = []
    for v in videos:
        all_tags.extend(v.get("tags", []))
    tag_counter = Counter(all_tags)

    return {
        "avg_tags_per_video": round(avg_tags, 1),
        "videos_with_tags": videos_with_tags,
        "videos_without_tags": len(videos) - videos_with_tags,
        "top_tags": dict(tag_counter.most_common(15)),
    }


def generate_diagnostics(channel_data: dict) -> list:
    """生成具体的诊断建议
    
    基于6个agent核心理论：
    1. Video Optimization Specialist — CTR 8%目标、前30秒hook理论、Session优化思维
    2. Trend Researcher — 弱信号检测、趋势生命周期、竞争情报分层
    3. Content Creator — 内容再利用矩阵、跨平台适配
    4. Short-Video Editing Coach — 节奏控制、音频-14 LUFS标准、调色工作流
    5. Multi-Platform Publisher — Draft-First、频率控制、图片去重
    6. Cross-Border E-Commerce — 本地化>机器翻译、市场进入策略
    """
    videos = channel_data.get("videos", [])
    stats = channel_data.get("channel_stats", {})
    growth = channel_data.get("growth", {})
    view_dist = channel_data.get("view_distribution", {})
    title_pat = channel_data.get("title_patterns", {})
    engagement = channel_data.get("engagement_funnel", {})
    content = channel_data.get("content_consistency", {})
    seo = channel_data.get("seo_analysis", {})
    posting = channel_data.get("posting_pattern", {})
    duration = channel_data.get("duration_impact", {})

    issues = []
    name = stats.get("name", "")
    
    # 频道阶段判断
    subs = stats.get("subscribers", 0)
    days = stats.get("days_alive", 0) if "days_alive" in stats else 0
    if not days:
        created = stats.get("published_at", "")
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                days = (datetime.now(timezone.utc) - created_dt).days
            except (ValueError, KeyError):
                days = 0
    
    is_cold_start = subs < 1000 or days < 30
    daily_publish_target = 2 if is_cold_start else 1

    # === 播放分布问题 ===
    if view_dist.get("top3_ratio", 0) > 60:
        top3 = view_dist["top3_ratio"]
        issues.append({
            "severity": "critical",
            "category": "播放分布",
            "issue": f"头部严重集中：前3条视频占总播放{top3:.0f}%",
            "detail": f"除爆款外，其余视频平均播放仅{view_dist.get('avg_views', 0):,}。内容质量不均或算法推荐不稳定。",
            "action": "① 分析爆款视频的标题/封面/时长特征，复制到后续视频\n② 确保每条视频都有独立的钩子，不要依赖系列流量\n③ 检查非爆款视频是否在发布后24小时内获得初始流量",
        })

    if view_dist.get("cliff"):
        ratio = view_dist.get("cliff_ratio", 0)
        issues.append({
            "severity": "critical",
            "category": "播放分布",
            "issue": f"近期流量断崖：最近视频播放仅为之前的{ratio:.0%}",
            "detail": "最近5条视频播放量大幅下降，可能被算法降权或内容质量下滑。",
            "action": "① 检查最近3条视频是否有违规标签或敏感词\n② 对比断崖前后的标题长度/封面风格变化\n③ 暂停发布2-3天，然后用爆款风格的标题+封面重新发布\n④ 检查频道是否有 Community Guidelines 警告",
        })

    # === 点赞率问题 ===
    overall_lr = engagement.get("overall_like_rate", 0)
    if overall_lr < 0.5:
        issues.append({
            "severity": "critical",
            "category": "互动率",
            "issue": f"点赞率极低 {overall_lr:.2f}%（行业基准1.5-2%）",
            "detail": f"零互动视频{engagement.get('zero_like_count', 0)}条（占{engagement.get('zero_like_ratio', 0):.0%}），高互动视频仅{engagement.get('high_engagement_count', 0)}条。",
            "action": "① 标题前10字必须有冲突钩子（如'被开除当天，我成了CEO'）\n② 封面必须有情绪化面部特写（占画面60%+）\n③ 视频前5秒加入'如果觉得好看请点赞'的口播引导\n④ 参考本频道点赞率最高的视频风格",
        })
    elif overall_lr < 1.0:
        issues.append({
            "severity": "major",
            "category": "互动率",
            "issue": f"点赞率偏低 {overall_lr:.2f}%",
            "detail": f"低于行业基准1.5%，说明内容能被看到但无法引发互动。",
            "action": "① 优化标题钩子：用冲突+悬念替代平铺直叙\n② 封面增加情绪张力（惊讶/愤怒/甜蜜表情）\n③ 在视频结尾加'你觉得女主做得对吗？'等互动提问",
        })

    # === 标题问题 ===
    avg_len = title_pat.get("avg_length", 0)
    if avg_len > 80:
        issues.append({
            "severity": "major",
            "category": "标题",
            "issue": f"标题过长（平均{avg_len:.0f}字符，最佳40-60）",
            "detail": f"YouTube标题超过60字符会被截断，关键信息丢失。标题长度范围：{title_pat.get('min_length', 0)}-{title_pat.get('max_length', 0)}字符。",
            "action": "① 标题公式：[冲突钩子] + [身份反差] + [情绪词]，控制在50字符内\n② 删掉'爆火短劇全集'等无意义后缀\n③ 删掉开头重复emoji（如❤️⭐️🌟），用1个有区分度的emoji\n④ 参考本频道最佳长度区间（{best}字符，点赞率{lr}%）".format(
                best=title_pat.get("best_length_bucket", "40-60"),
                lr=title_pat.get("best_length_lr", 0)
            ),
        })

    if title_pat.get("repeated_emoji"):
        issues.append({
            "severity": "major",
            "category": "标题",
            "issue": "所有视频用相同emoji前缀，无区分度",
            "detail": "重复的emoji序列会让观众产生视觉疲劳，降低点击率。",
            "action": "① 每个视频只用1-2个emoji，且与内容相关（如复仇用🔥，甜蜜用💕）\n② emoji放在标题末尾而非开头\n③ 完全去掉emoji也行，纯文字标题点赞率反而更高（2.478% vs 1.195%）",
        })

    if title_pat.get("repeated_starts"):
        starts = title_pat["repeated_starts"]
        worst = max(starts.items(), key=lambda x: x[1])
        issues.append({
            "severity": "major",
            "category": "标题",
            "issue": f"标题开头重复：'{worst[0]}...'出现{worst[1]}次",
            "detail": "开头相同的标题会让观众认为内容重复，降低点击意愿。",
            "action": "① 每条视频标题开头必须不同\n② 用不同的冲突场景开头（如'被开除''被退婚''被赶出家门'）\n③ 参考爆款视频的开头方式",
        })

    # === 内容一致性 ===
    if content.get("consistency_score", 1) < 0.5:
        primary = content.get("primary_type", "未知")
        detected = content.get("detected_types", {})
        types_str = "、".join([f"{k}({v}条)" for k, v in list(detected.items())[:4]])
        issues.append({
            "severity": "major",
            "category": "内容定位",
            "issue": f"内容混杂：{types_str}",
            "detail": f"主要类型'{primary}'仅占{content.get('primary_ratio', 0):.0%}。YouTube算法需要一致的内容标签才能精准推荐。",
            "action": "① 确定1个核心赛道（如'家庭伦理'或'霸总甜宠'），连续发布同类型内容\n② 用系列标题强化定位（如'豪门恩怨系列'）\n③ 删除或隐藏与定位严重不符的旧视频",
        })

    # === 订阅转化 ===
    days = stats.get("days_alive", 0) if "days_alive" in stats else 0
    if not days:
        created = stats.get("published_at", "")
        if created:
            try:
                created_dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
                days = (datetime.now(timezone.utc) - created_dt).days
            except (ValueError, KeyError):
                days = 0

    subs = stats.get("subscribers", 0)
    total_views = engagement.get("total_views", 0)
    view_sub = total_views / max(subs, 1)

    if view_sub > 100 and subs < 500:
        issues.append({
            "severity": "major",
            "category": "订阅转化",
            "issue": f"播放/订阅比 {view_sub:.0f}:1（正常应<50:1）",
            "detail": f"总播放{total_views:,}但仅{subs}订阅，说明观众看完不订阅。",
            "action": "① 每条视频开头3秒加'订阅频道看更多精彩短剧'口播\n② 视频描述第一行加订阅链接\n③ 用YouTube End Screen在最后20秒加订阅按钮\n④ 在视频中提到'下集更精彩'制造连续期待",
        })

    if subs < 100 and days > 30:
        issues.append({
            "severity": "critical",
            "category": "订阅转化",
            "issue": f"{days}天仅{subs}订阅，增长极慢",
            "detail": f"日均订阅{subs/max(days,1):.2f}，按此速度需要{max(0,1000-subs)/max(subs/max(days,1),0.01):.0f}天才能达到1000订阅（YouTube变现门槛）。",
            "action": "① 重新审视频道定位，参考同赛道标杆频道的标题+封面策略\n② 增加发布频率（建议每天1-2条）\n③ 优化SEO：标题含搜索关键词，标签覆盖题材+地区+语言\n④ 考虑在其他平台（TikTok/Instagram）引流到YouTube",
        })

    # === 发布节奏 ===
    if posting:
        weekday_data = posting.get("by_weekday", {})
        if weekday_data:
            total_videos = sum(weekday_data.values())
            if total_videos > 5:
                # 检查是否有集中发布
                max_day = max(weekday_data.items(), key=lambda x: x[1])
                if max_day[1] / total_videos > 0.4:
                    issues.append({
                        "severity": "info",
                        "category": "发布节奏",
                        "issue": f"发布集中在{max_day[0]}（占{max_day[1]/total_videos:.0%}）",
                        "detail": "发布日过于集中，不利于算法持续推荐。",
                        "action": "① 均匀分布在周一到周五发布\n② 参考目标市场的活跃时段（美西：PST 12-15点；东南亚：ICT 19-21点）",
                    })

    # === 时长问题 ===
    # 短剧频道：时长基本固定（70-110分钟），时长诊断意义不大
    # 改为分析短视频（预告片/片段）的表现，给出更实用的建议
    if duration:
        # 检查是否有短视频（预告片/片段）
        short_labels = ["<5min", "5-30min"]
        short_videos = {k: v for k, v in duration.items() if k in short_labels}
        long_videos = {k: v for k, v in duration.items() if k not in short_labels}
        
        if short_videos and long_videos:
            # 有短视频和长视频，对比表现
            short_count = sum(v.get("count", 0) for v in short_videos.values())
            long_count = sum(v.get("count", 0) for v in long_videos.values())

            if short_count > 0 and long_count > 0:
                short_avg_rate = sum(v.get("avg_like_rate", 0) * v.get("count", 0)
                                   for v in short_videos.values()) / short_count
                long_avg_rate = sum(v.get("avg_like_rate", 0) * v.get("count", 0)
                                  for v in long_videos.values()) / long_count

                if short_avg_rate > long_avg_rate * 1.5:  # 短视频点赞率比长视频高50%以上
                    issues.append({
                        "severity": "info",
                        "category": "内容策略",
                        "issue": "预告片/片段点赞率高于完整短剧",
                        "detail": f"短视频（<30min）平均点赞率{short_avg_rate:.2f}%，长视频（>60min）平均点赞率{long_avg_rate:.2f}%。预告片/片段可能更吸引观众互动。",
                        "action": "① 考虑为每部短剧制作1-2分钟的预告片\n② 预告片可单独发布，提升频道互动率\n③ 预告片标题可加预告标签，避免与完整短剧混淆",
                    })
        # 时长桶单一（只有长视频或只有短视频）：无对比意义，不加 issue，继续走后面的周增长/评论等诊断

    # === 周增长 ===
    if growth.get("has_prev"):
        sub_ch = growth.get("subscribers_change", 0)
        view_ch = growth.get("views_change", 0)
        if sub_ch > 0:
            issues.append({
                "severity": "info",
                "category": "增长趋势",
                "issue": f"周增{sub_ch}订阅（日均{growth.get('daily_sub_growth', 0):+.1f}）",
                "detail": f"播放变化{view_ch:+,}。保持当前增速，预计{max(0, 1000-subs)/max(sub_ch, 1):.0f}周后达到1000订阅。",
                "action": "① 维持当前发布频率和内容质量\n② 尝试增加发布频率加速增长",
            })
        elif sub_ch < 0:
            issues.append({
                "severity": "critical",
                "category": "增长趋势",
                "issue": f"周减{abs(sub_ch)}订阅",
                "detail": "订阅负增长，可能是内容质量下降或受众不匹配。",
                "action": "① 检查是否有大量取消订阅的视频（YouTube Studio → 分析 → 受众）\n② 回顾最近发布的内容是否偏离了原有定位\n③ 暂停发布，重新审视内容策略",
            })

    # === 评论互动 ===
    if engagement.get("comment_like_ratio", 0) < 5 and engagement.get("total_likes", 0) > 10:
        issues.append({
            "severity": "info",
            "category": "互动深度",
            "issue": f"评论/点赞比仅{engagement.get('comment_like_ratio', 0)}%",
            "detail": "观众点赞但不评论，说明内容能看但缺乏讨论点。",
            "action": "① 在视频中设置争议性问题（如'你觉得她该原谅吗？'）\n② 在描述中提问引导评论\n③ 置顶一条引导评论的评论",
        })

    # === 封面诊断 ===
    # 封面数据来自batch_cover_analysis.py的分析结果
    cover_analysis = channel_data.get("cover_analysis", {})
    if cover_analysis and cover_analysis.get("analyzed_count", 0) > 0:
        avg_scores = cover_analysis.get("avg_scores", {})
        
        # 人物特写评分
        person_score = avg_scores.get("avg_person_score", 0)
        if person_score < 6:
            issues.append({
                "severity": "major",
                "category": "封面",
                "issue": f"人物特写不足（平均{person_score}分）",
                "detail": "面部不清晰或占比<60%，影响观众识别",
                "action": "① 封面人物面部必须清晰，占画面60%以上\n② 使用情绪化面部特写（惊讶/愤怒/甜蜜表情）\n③ 参考爆款视频的封面构图"
            })
        
        # 情绪表达评分
        emotion_score = avg_scores.get("avg_emotion_score", 0)
        if emotion_score < 6:
            issues.append({
                "severity": "major",
                "category": "封面",
                "issue": f"情绪表达不足（平均{emotion_score}分）",
                "detail": "封面缺乏情绪张力，无法吸引点击",
                "action": "① 封面必须有情绪化表情（惊讶/愤怒/甜蜜/坚定）\n② 使用冷暖对比光强化情绪\n③ 参考短剧专家SDE-011：CEO/豪门首选双人对峙型封面"
            })
        
        # 关键道具评分
        prop_score = avg_scores.get("avg_prop_score", 0)
        if prop_score < 5:
            issues.append({
                "severity": "info",
                "category": "封面",
                "issue": f"关键道具缺失（平均{prop_score}分）",
                "detail": "封面缺乏与冲突相关的道具元素",
                "action": "① 添加关键道具（DNA报告、婚戒、股权转让书）\n② 道具置于视觉焦点附近\n③ 参考运营总监封面规范：服装反差 > 关键道具 > 场景暗示"
            })
        
        # 文字标签评分
        text_score = avg_scores.get("avg_text_score", 0)
        if text_score < 5:
            issues.append({
                "severity": "info",
                "category": "封面",
                "issue": f"文字标签缺失（平均{text_score}分）",
                "detail": "封面缺乏题材词标签，不利于算法识别",
                "action": "① 添加简洁的题材词标签（如'重生'、'逆袭'、'豪门'）\n② 字体需小且不喧宾夺主\n③ 参考运营总监封面规范：文字标签为可选元素"
            })
        
        # 整体评分
        overall_score = avg_scores.get("avg_overall_score", 0)
        if overall_score < 6:
            issues.append({
                "severity": "major",
                "category": "封面",
                "issue": f"封面整体质量偏低（平均{overall_score}分）",
                "detail": "封面设计需要优化，影响CTR",
                "action": "① 参考运营总监封面规范\n② 分析爆款视频的封面特征\n③ 使用AI工具生成封面草稿，再人工优化"
            })

    # ═══ OAuth Analytics 诊断（已授权频道）═══
    analytics = channel_data.get("analytics", {})
    if analytics:
        # --- 留存率（按视频时长分档）---
        avg_pct = analytics.get("averageViewPercentage", 0)
        avg_dur = analytics.get("averageViewDuration", 0)  # 秒
        if avg_pct > 0 and avg_dur > 0:
            # 根据平均观看时长推断视频总时长，选择对应基准
            # avg_dur 是实际观看秒数，视频总时长 ≈ avg_dur / (avg_pct/100)
            est_video_dur = avg_dur / (avg_pct / 100) if avg_pct > 0 else 0
            if est_video_dur > 1200:  # >20分钟
                bench_low, bench_ok = 15, 25
            elif est_video_dur > 300:  # 5-20分钟
                bench_low, bench_ok = 25, 35
            else:  # <5分钟
                bench_low, bench_ok = 40, 60
            if avg_pct < bench_low:
                issues.append({
                    "severity": "critical",
                    "category": "留存",
                    "issue": f"留存率 {avg_pct}% 低于同长度基准 {bench_low}%",
                    "detail": f"平均观看 {avg_dur//60}分{avg_dur%60}秒，视频预估 {est_video_dur//60} 分钟。平均观看占比 {avg_pct}%，中段流失严重（AVD占比是整体指标，不代表开头hook问题）。",
                    "action": "① 每3-5分钟设置一次re-engagement hook\n② 检查中段是否有拖沓段落\n③ 如需判断开头hook，请查看1分钟留存数据"
                })
            elif avg_pct < bench_ok:
                issues.append({
                    "severity": "major",
                    "category": "留存",
                    "issue": f"留存率 {avg_pct}% 偏低（同长度健康线 {bench_ok}%）",
                    "detail": f"平均观看 {avg_dur//60}分{avg_dur%60}秒，有提升空间。",
                    "action": "① 每3-5分钟设置一个re-engagement hook\n② 检查中段是否有拖沓段落"
                })

        # --- 订阅健康度 ---
        gained = analytics.get("subscribersGained", 0)
        lost = analytics.get("subscribersLost", 0)
        if gained > 0 and lost > 0:
            churn_rate = lost / gained * 100
            if lost > gained:
                issues.append({
                    "severity": "critical",
                    "category": "订阅",
                    "issue": f"订阅净流失：+{gained}/-{lost}（净增 {gained-lost}）",
                    "detail": "流失超过新增，频道在萎缩。可能是内容偏离观众预期或更新频率下降。",
                    "action": "① 检查最近内容是否偏离定位\n② 分析流失发生在哪些视频后\n③ 增加发布频率，稳定算法推荐"
                })
            elif churn_rate > 20:
                issues.append({
                    "severity": "major",
                    "category": "订阅",
                    "issue": f"订阅流失率偏高 {churn_rate:.0f}%（+{gained}/-{lost}）",
                    "detail": "新增订阅中有较多取消订阅，可能内容质量不稳定。",
                    "action": "① 保持内容风格一致，避免题材跳跃\n② 在视频结尾引导订阅"
                })

        # --- 流量来源健康度 ---
        ratios = analytics.get("traffic_ratios", {})
        if ratios:
            browse = ratios.get("RELATED_VIDEO", 0)  # 推荐流量
            sub = ratios.get("SUBSCRIBER", 0)         # 订阅流量
            search = ratios.get("YT_SEARCH", 0)       # 搜索流量

            if sub > 50:
                issues.append({
                    "severity": "major",
                    "category": "流量",
                    "issue": f"过度依赖订阅流量 {sub}%（推荐仅 {browse}%）",
                    "detail": "算法信任度低，新观众获取受限。需要提升推荐流量占比。",
                    "action": "① 优化标题+封面提升CTR\n② 增加发布频率触发推荐\n③ 分析推荐流量高的视频特征并复制"
                })
            elif browse < 30:
                issues.append({
                    "severity": "major",
                    "category": "流量",
                    "issue": f"推荐流量偏低 {browse}%",
                    "detail": "算法推荐不足，可能是CTR或留存低于同类频道。",
                    "action": "① 优化标题钩子（至少命中2个钩子）\n② 封面增加情绪张力\n③ 检查中段节奏（AVD占比反映整体，非前30秒）"
                })

            if search < 5:
                issues.append({
                    "severity": "info",
                    "category": "SEO",
                    "issue": f"搜索流量仅 {search}%",
                    "detail": "搜索优化不足，错失长尾流量。",
                    "action": "① 标题包含搜索关键词\n② 描述区前2行包含核心关键词\n③ 每视频至少5个标签"
                })

    return issues


def build_comprehensive_report(report: dict, distill: dict = None) -> dict:
    """构建完整诊断报告"""
    videos = report.get("videos", [])
    stats = report.get("channel_stats", {})

    # 运行所有分析
    report["view_distribution"] = analyze_view_distribution(videos)
    report["engagement_funnel"] = analyze_engagement_funnel(videos)
    report["content_consistency"] = analyze_content_consistency(videos, distill=distill)
    report["seo_analysis"] = analyze_seo(videos)

    # 重新计算标题分析（使用增强版）
    report["title_patterns"] = analyze_title_patterns(videos)

    # 生成诊断建议
    report["diagnostics"] = generate_diagnostics(report)

    return report
