#!/usr/bin/env python3
"""
generate_title.py — 真正调用 nuwa 专家的标题生成器

流程：
1. 读取剧的信息（analysis + ad_materials + manifest）
2. 通过 skill_router 读取 short-drama-expert + hk-traditional-market-expert 规则
3. 调用 nuwa_api 生成标题（DeepSeek / Bank of AI 轮询）
4. 用 check_rules 做规则检查（REJECT/WARN）
5. 输出合规候选 + 评分

用法：
    python3 scripts/generate_title.py --manifest data/manifests/xxx.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

# 把 scripts 加入路径
sys.path.insert(0, str(Path(__file__).parent))

from nuwa_api import nuwa_chat
from skill_router import build_prompt_with_skill, check_rules, get_skill_context

BASE_DIR = Path(__file__).parent.parent
DISTILL_DIR = BASE_DIR / "distill"


def _load_distill_data(region: str, model: str = 'mimo') -> dict:
    """加载蒸馏规则（JSON 为唯一真相源）
    model: 'mimo' 或 'gpt'，决定读哪个蒸馏版本
    """
    region_map = {
        "hk": "繁中", "tw": "繁中", "sg": "繁中", "mo": "繁中",
        "en": "英文", "us": "英文", "gb": "英文",
        "id": "印尼", "pt": "葡萄牙", "br": "葡萄牙",
        "es": "西语", "mx": "西语",
        "zh-CN": "zh-CN", "zh": "zh-CN",
    }
    lang = region_map.get(region, region)

    if model == 'gpt':
        json_file = DISTILL_DIR / "outputs" / f"distilled-rules-{lang}-gpt55-v5.json"
    else:
        json_file = DISTILL_DIR / "outputs" / f"distilled-rules-{lang}.json"
    if json_file.exists():
        data = json.loads(json_file.read_text(encoding="utf-8"))
        # 序列化为字符串，和MD一样以文本形式传入prompt
        return {"lang": lang, "distill": json.dumps(data, ensure_ascii=False, indent=2)}

    # fallback: 读 MD（兼容旧数据）
    md_file = DISTILL_DIR / "outputs" / f"distill-{lang}.md"
    if md_file.exists():
        return {"lang": lang, "distill": md_file.read_text()[:3000]}

    return {"lang": lang, "rules": None}


def _load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_conflict_points(title: str, analysis: dict | None = None) -> int:
    """计算冲突点数量：优先用素材中的真实冲突词，fallback到通用词表"""
    if analysis:
        hooks = analysis.get("hooks_and_twists", [])
        # 用素材里的真实冲突词匹配标题
        real_hits = sum(1 for h in hooks if h in title)
        if real_hits >= 2:
            return real_hits
    # fallback 通用钩子词表
    generic_hooks = ["重生", "逆襲", "復仇", "背叛", "陷害", "離婚", "替嫁", "反轉", "揭穿",
                     "寵上天", "團寵", "陰謀", "真相", "曝光", "竟然", "點知", "沒想到", "不料",
                     "打臉", "虐心", "吃醋", "追妻", "火葬場", "決裂", "聯手", "化解", "逼宮"]
    return sum(1 for h in generic_hooks if h in title)


def _refine_best_title(best_title: str, analysis: dict, region: str) -> str:
    """二次精炼：让nuwa对最高分标题进行最终优化"""
    genre = analysis.get("genre", "")
    hooks = analysis.get("hooks_and_twists", [])
    raw = analysis.get("raw_search", "")[:500]

    prompt = (
        f"你是一位短剧标题优化师。请对以下标题进行最终精修，要求：\n"
        f"1. 保留所有核心冲突点和钩子\n"
        f"2. 确保30-60字\n"
        f"3. 确保含\"短劇\"或\"Drama\"\n"
        f"4. 面向{region}市场，用语自然\n"
        f"5. 只输出优化后的标题文字，不要解释\n\n"
        f"原标题：{best_title}\n"
        f"题材：{genre}\n"
        f"真实冲突：{', '.join(hooks[:3])}\n"
        f"剧情参考：{raw[:200]}"
    )
    refined = nuwa_chat(prompt, max_tokens=200, temperature=0.5, rotate=False)
    if refined and 20 <= len(refined) <= 80 and ("短劇" in refined or "Drama" in refined):
        return refined.strip().strip('"').strip("'")
    return best_title


def _check_title_compliance(title: str, region: str) -> list[dict]:
    """用规则检查标题合规性 —— 对应 short-drama-expert 规则卡"""
    check_data = {
        "title": title,
        "length": len(title),
        "has_drama": "短劇" in title or "drama" in title.lower(),
        "has_collection": any(w in title for w in ["全集", "完整版", "一口氣看完"]),
        "conflict_points": _extract_conflict_points(title),
        "has_genre": any(w in title for w in ["總裁", "甜寵", "重生", "逆襲", "穿越", "復仇", "豪門", "千金", "古裝", "醫妃", "醫術", "先婚"]),
        "pure_english": not any("\u4e00" <= c <= "\u9fff" for c in title),
    }

    # 繁体长度检查
    failures = []

    # SDE-017: 必须含"短劇"或"Drama"
    if not check_data["has_drama"]:
        failures.append({"rule": "SDE-017", "level": "REJECT", "reason": "标题不含'短劇'或'Drama'"})

    # SDE-001: 必须≥3个冲突点
    if check_data["conflict_points"] < 3:
        failures.append({"rule": "SDE-001", "level": "REJECT", "reason": f"冲突点仅{check_data['conflict_points']}个，需≥3个"})

    # HKT-004 / SDE-004: 长度 30-60 字
    if not (30 <= check_data["length"] <= 60):
        failures.append({"rule": "HKT-004", "level": "WARN", "reason": f"长度{check_data['length']}字，建议30-60字"})

    # HKT-005: 禁止纯英文
    if check_data["pure_english"]:
        failures.append({"rule": "HKT-005", "level": "REJECT", "reason": "标题纯英文，繁体市场CTR低35%"})

    # SDE-020: 必须有题材标识
    if not check_data["has_genre"]:
        failures.append({"rule": "SDE-020", "level": "REJECT", "reason": "标题无题材标识（總裁/甜寵/重生等）"})

    # HUM-001: emoji堆叠（>2个装饰性emoji）
    # 覆盖所有常见emoji范围：杂项符号(2600-26FF)、装饰(2700-27BF)、
    # 几何(25A0-25FF)、杂项符号和象形文字(1F300-1F9FF)、补充(1FA00-1FAFF)
    emoji_ranges = [
        (0x2600, 0x27BF),   # ☀️☁️❤️✏️ etc
        (0x2B50, 0x2B55),   # ⭐⭕
        (0x1F300, 0x1F9FF), # 🌟🔥💀🎭 etc
        (0x1FA00, 0x1FAFF), # 🫠🫡 etc
        (0x200D, 0x200D),   # ZWJ (joiner in emoji sequences)
        (0xFE0F, 0xFE0F),   # Variation selector
    ]
    def is_emoji(c):
        cp = ord(c)
        return any(lo <= cp <= hi for lo, hi in emoji_ranges)
    emoji_count = len([c for c in title if is_emoji(c)])
    if emoji_count > 2:
        failures.append({"rule": "HUM-001", "level": "WARN", "reason": f"emoji过多({emoji_count}个)，竞品数据显示0-1个emoji点赞率更高"})

    # HUM-002: AI高频填充词（简繁都检查）
    ai_filler_words = [
        "爆火短剧", "爆火短劇", "热播短剧", "热播短劇",
        "必看短剧", "必看短劇", "全网最火", "火爆全网",
        "超火短剧", "超火短劇", "热门短剧", "热门短劇",
        "爆火", "超火",
    ]
    found_fillers = [w for w in ai_filler_words if w in title]
    # 去重：如果短词是长词的子串，只保留长词
    found_fillers = sorted(set(found_fillers), key=len, reverse=True)
    deduped = []
    for w in found_fillers:
        if not any(w in longer for longer in deduped):
            deduped.append(w)
    found_fillers = deduped
    if found_fillers:
        failures.append({"rule": "HUM-002", "level": "WARN", "reason": f"含AI高频词{'、'.join(found_fillers)}，竞品标题中未见，建议用具体冲突替代"})

    return failures


def _score_title(title: str, analysis: dict) -> dict:
    """基于规则的评分 —— 素材感知的动态权重"""
    # 冲突点权重 30%（优先用素材真实冲突）
    cp = _extract_conflict_points(title, analysis)
    conflict = min(cp * 30, 100)

    # 题材匹配权重 25%（从素材提取的真实题材词）
    genre = analysis.get("genre", "")
    raw_search = analysis.get("raw_search", "")
    # 动态提取题材词：从素材高频词 + 固定词表
    dynamic_genre_words = ["總裁", "甜寵", "重生", "逆襲", "穿越", "復仇", "豪門", "千金", "古裝", "醫妃", "醫術", "先婚"]
    if genre and genre not in dynamic_genre_words:
        dynamic_genre_words.append(genre)
    # 从raw_search中提取额外关键词
    extra_keywords = re.findall(r'(打臉|追妻|火葬場|虐戀|宮鬥|宅鬥|權謀|懸疑|仙俠)', raw_search[:500])
    dynamic_genre_words.extend(extra_keywords)
    genre_hits = sum(1 for w in set(dynamic_genre_words) if w in title)
    genre_score = min(40 + genre_hits * 20, 100)

    # 搜索关键词权重 20%
    seo_words = ["短劇", "全集", "完整版", "一口氣看完"]
    seo_hits = sum(1 for w in seo_words if w in title)
    seo = min(seo_hits * 25, 100)

    # 钩子密度权重 15%
    hook_words = ["點知", "竟然", "沒想到", "曝光", "反轉", "真相", "即刻", "直接"]
    hook_hits = sum(1 for w in hook_words if w in title)
    hook = min(30 + hook_hits * 15, 100)

    # 长度适配权重 10%
    length_ok = 30 <= len(title) <= 60
    length = 100 if length_ok else 50

    total = round(conflict * 0.30 + genre_score * 0.25 + seo * 0.20 + hook * 0.15 + length * 0.10, 1)

    return {
        "conflict": conflict,
        "genre": genre_score,
        "seo": seo,
        "hook": hook,
        "length": length,
        "total": total,
    }


def _build_nuwa_prompt(manifest: dict, analysis: dict, ad: dict, direction: str = "", distill_model: str = "mimo") -> str:
    """构建 nuwa prompt，注入三层蒸馏数据 + 完整素材"""
    drama = manifest.get("task_name", "未知剧名")
    region = manifest.get("target_region", "hk")

    # 读取投放素材标题
    ad_titles = [x.get("title", "") for x in ad.get("title_candidates", []) if x.get("title")]
    ad_titles_str = "\n".join([f"- {t}" for t in ad_titles[:5]]) if ad_titles else "（无投放素材）"

    # 读取剧分析（优先用完整搜索素材）
    raw_search = analysis.get("raw_search", "")
    plot = raw_search[:1500] if len(raw_search) > 200 else analysis.get("plot_summary", "")
    hooks = analysis.get("hooks_and_twists", ["身份反轉", "利益冲突"])
    props = analysis.get("key_props", ["合同", "戒指"])
    scenes = analysis.get("key_scenes", ["豪宅", "公司"])
    chars = analysis.get("characters", ["男主", "女主"])
    genre = analysis.get("genre", "現代都市")

    # 地区口语词映射
    region_words = {
        "hk": {"surprise": "點知/即刻/竟然", "style": "港式口语，可用粵語詞如佢/嘅/係"},
        "tw": {"surprise": "沒想到/竟然/直接", "style": "台式书面，保留文言文感"},
        "sg": {"surprise": "竟然/没想到", "style": "新马双语，可混英文关键词"},
        "mo": {"surprise": "點知/竟然", "style": "港澳风格"},
        "en": {"surprise": "Suddenly/Plot twist/Wait what", "style": "English, dramatic hook style, short punchy"},
        "us": {"surprise": "Suddenly/Plot twist/Wait what", "style": "English, dramatic hook style, short punchy"},
        "gb": {"surprise": "Suddenly/Plot twist/Wait what", "style": "English, dramatic hook style, short punchy"},
        "id": {"surprise": "Ternyata/Tak disangka", "style": "Bahasa Indonesia, gaya dramatis"},
        "pt": {"surprise": "De repente/Quando ela", "style": "Português, estilo dramático"},
        "br": {"surprise": "De repente/Quando ela", "style": "Português brasileiro, estilo dramático"},
        "es": {"surprise": "De repente/Cuando ella", "style": "Español, estilo dramático"},
        "mx": {"surprise": "De repente/Cuando ella", "style": "Español mexicano, estilo dramático"},
    }
    rw = region_words.get(region, region_words["hk"])

    hooks_str = ", ".join(hooks[:5])
    props_str = ", ".join(props[:5])
    scenes_str = ", ".join(scenes[:5])
    chars_str = ", ".join(chars[:6])

    # 题材方向：手动指定 > 自动检测
    direction_section = ""
    if direction:
        direction_section = (
            f"\n【用户指定题材方向】\n"
            f"标题和标签必须重点体现以下方向：{direction}\n"
            f"在标题的情绪钩子、冲突类型、标签选择上都要往这个方向靠拢。\n\n"
        )

    # 加载三层蒸馏数据（根据选择的模型方案）
    distill = _load_distill_data(region, model=distill_model)
    distill_section = ""
    if distill["distill"]:
        distill_section = (
            f"\n【三层蒸馏数据（{distill['lang']}市场，方案: {distill_model}）】\n"
            f"以下是从竞品爆款数据中提炼的三层架构，请参考但不要直接复制：\n\n"
            f"{distill['distill']}\n\n"
        )

    prompt = (
        f"你是一位精通短剧市场的运营专家。\n\n"
        f"{distill_section}"
        f"{direction_section}"
        f"【任务】为短剧《{drama}》生成5个面向{region.upper()}市场的YouTube标题 + 5个标签 + 3个AI封面指令。\n\n"
        "【完整剧情素材】（来自真实搜索）\n" + plot + "\n\n"
        "【提取的关键信息】\n"
        f"- 题材：{genre}\n"
        f"- 核心冲突：{hooks_str}\n"
        f"- 关键道具/元素：{props_str}\n"
        f"- 关键场景：{scenes_str}\n"
        f"- 主要人物：{chars_str}\n\n"
        f"【地区风格要求：{rw['style']}】\n"
        f"- 意外/转折用词偏好：{rw['surprise']}\n\n"
    )

    # 根据地区生成不同的规则
    is_cjk = region in ("hk", "tw", "sg", "mo")
    if is_cjk:
        prompt += (
            "【生成规则】\n"
            "1. 骨架可以复用，血肉必须创新——不要直接抄蒸馏示例\n"
            "2. 每个标题必须体现至少2个原则（从蒸馏数据中选择）\n"
            "3. 黄金组合：情绪钩子 + 身份钩子 + 反转钩子\n"
            "4. 标题前半句放冲突/弱势，后半句放反转/强势\n\n"
            "【规则】\n"
            "1. 标题必须含\"短劇\"或\"Drama\"\n"
            "2. 标题必须含≥3个冲突点/钩子/反转（从素材中提取真实冲突，不要编造）\n"
            "3. 中文标题30-60字\n"
            "4. 必须含题材关键词：總裁/甜寵/重生/逆襲/穿越/復仇/豪門/千金/古裝/醫妃（根据真实素材选）\n"
            f"5. 面向该市场用\"{rw['surprise']}\"等本地转折词\n"
            "6. 长视频合集可含\"全集/完整版/一口氣看完\"\n"
            "7. 禁止纯英文标题（新加坡除外可双语）\n"
            "8. 标签用英文#Hashtag格式，如 #ShortDrama #穿越 #古裝劇\n"
            "9. 【最重要】标题必须基于上方【完整剧情素材】中的真实情节，禁止编造素材中没有的内容\n\n"
            "【AI封面指令规则】\n"
            "生成3个AI图片生成指令（中文描述），用于生成YouTube视频封面缩略图。\n"
            "要求：\n"
            "1. 每个封面指令描述一个具体的画面场景（人物+表情+场景+氛围）\n"
            "2. 写成完整的画面描述，可直接用于AI图片生成\n"
            "3. 画面要有戏剧冲突感，能吸引点击\n"
            "4. 3个封面分别对应不同风格：情绪冲突型、身份反转型、悬念型\n"
            "5. 【必须】封面尺寸为1280x720（16:9横屏），在指令中明确写'16:9横屏构图'\n"
            "6. 【必须】左上角留出'FULL EPISODES'胶囊徽章位置\n"
            "7. 【必须】底部15%预留标题文字区域\n\n"
            "【输出格式】只输出JSON：\n"
            "{\n"
            '  "candidates": [\n'
            '    {"title": "", "style": "港式|台式|新马", "conflict_points": ["冲突1", "冲突2", "冲突3"], "principles_used": ["原则1", "原则2"]},\n'
            '    {"title": "", "style": "港式|台式|新马", "conflict_points": ["冲突1", "冲突2", "冲突3"], "principles_used": ["原则1", "原则2"]},\n'
            '    {"title": "", "style": "港式|台式|新马", "conflict_points": ["冲突1", "冲突2", "冲突3"], "principles_used": ["原则1", "原则2"]},\n'
            '    {"title": "", "style": "港式|台式|新马", "conflict_points": ["冲突1", "冲突2", "冲突3"], "principles_used": ["原则1", "原则2"]},\n'
            '    {"title": "", "style": "港式|台式|新马", "conflict_points": ["冲突1", "冲突2", "冲突3"], "principles_used": ["原则1", "原则2"]}\n'
            '  ],\n'
            '  "title_hashtags": ["#短劇", "#flickreels", "#DramaBox"],\n'
            '  "description_tags": ["#标签1", "#标签2", "#标签3", "#标签4", "#标签5", "#标签6", "#标签7", "#标签8", "#标签9", "#标签10"],\n'
            '  "description_template": "🔥 {title}\\n\\n{synopsis}\\n\\n▶ 全集完整版，一口氣看完！\\n\\n#短劇 #flickreels #DramaBox {extra_tags}\\n\\n📌 訂閱頻道，不錯過任何精彩短劇！",\n'
            '  "cover_instructions": [\n'
            '    {"style": "情绪冲突型", "instruction": "16:9横屏构图，中文画面描述..."},\n'
            '    {"style": "身份反转型", "instruction": "16:9横屏构图，中文画面描述..."},\n'
            '    {"style": "悬念型", "instruction": "16:9横屏构图，中文画面描述..."}\n'
            '  ]\n'
            "}"
        )
    else:
        prompt += (
            "【生成规则】\n"
            "1. 骨架可以复用，血肉必须创新——不要直接抄蒸馏示例\n"
            "2. 每个标题必须体现至少2个原则（从蒸馏数据中选择）\n"
            "3. 黄金组合：情绪钩子 + 身份钩子 + 反转钩子\n"
            "4. 标题前半句放冲突/弱势，后半句放反转/强势\n\n"
            "【规则】\n"
            "1. 标题用当地语言（英文/葡文/西文/印尼文），不要用中文\n"
            "2. 标题必须含≥3个冲突点/钩子/反转（从素材中提取真实冲突，不要编造）\n"
            "3. 标题长度40-80个字符（英文/葡文/西文/印尼文）\n"
            f"4. 面向该市场用\"{rw['surprise']}\"等本地表达\n"
            "5. 长视频合集可含\"Full Episodes/Episódios Completos\"\n"
            "6. 标签用英文#Hashtag格式 + 当地语言标签，如 #ShortDrama #Revenge\n"
            "7. 【最重要】标题必须基于上方【完整剧情素材】中的真实情节，禁止编造素材中没有的内容\n\n"
            "【AI封面指令规则】\n"
            "生成3个AI图片生成指令（中文描述），用于生成YouTube视频封面缩略图。\n"
            "要求：\n"
            "1. 每个封面指令描述一个具体的画面场景（人物+表情+场景+氛围）\n"
            "2. 写成完整的画面描述，可直接用于AI图片生成\n"
            "3. 画面要有戏剧冲突感，能吸引点击\n"
            "4. 3个封面分别对应不同风格：情绪冲突型、身份反转型、悬念型\n"
            "5. 【必须】封面尺寸为1280x720（16:9横屏），在指令中明确写'16:9横屏构图'\n"
            "6. 【必须】左上角留出'FULL EPISODES'胶囊徽章位置\n"
            "7. 【必须】底部15%预留标题文字区域\n\n"
            "【输出格式】只输出JSON：\n"
            "{\n"
            '  "candidates": [\n'
            '    {"title": "", "style": "EN|PT|ES|ID", "conflict_points": ["conflict1", "conflict2", "conflict3"], "principles_used": ["principle1", "principle2"]},\n'
            '    {"title": "", "style": "EN|PT|ES|ID", "conflict_points": ["conflict1", "conflict2", "conflict3"], "principles_used": ["principle1", "principle2"]},\n'
            '    {"title": "", "style": "EN|PT|ES|ID", "conflict_points": ["conflict1", "conflict2", "conflict3"], "principles_used": ["principle1", "principle2"]},\n'
            '    {"title": "", "style": "EN|PT|ES|ID", "conflict_points": ["conflict1", "conflict2", "conflict3"], "principles_used": ["principle1", "principle2"]},\n'
            '    {"title": "", "style": "EN|PT|ES|ID", "conflict_points": ["conflict1", "conflict2", "conflict3"], "principles_used": ["principle1", "principle2"]}\n'
            '  ],\n'
            '  "title_hashtags": ["#ShortDrama", "#flickreels", "#DramaBox"],\n'
            '  "description_tags": ["#tag1", "#tag2", "#tag3", "#tag4", "#tag5", "#tag6", "#tag7", "#tag8", "#tag9", "#tag10"],\n'
            '  "description_template": "🔥 {title}\\n\\n{synopsis}\\n\\n▶ Watch Full Episodes!\\n\\n#ShortDrama #flickreels #DramaBox {extra_tags}\\n\\n📌 Subscribe for more!",\n'
            '  "cover_instructions": [\n'
            '    {"style": "情绪冲突型", "instruction": "16:9横屏构图，中文画面描述..."},\n'
            '    {"style": "身份反转型", "instruction": "16:9横屏构图，中文画面描述..."},\n'
            '    {"style": "悬念型", "instruction": "16:9横屏构图，中文画面描述..."}\n'
            '  ]\n'
            "}"
        )
    return prompt


def _parse_nuwa_response(raw: str) -> tuple[list[dict], list[str], list[dict], list[str], str]:
    """从 nuwa 响应中提取 JSON，返回 (candidates, title_hashtags, cover_instructions, description_tags, description_template)"""
    # 先找 ```json ... ```
    m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if m:
        raw_json = m.group(1)
    else:
        # 找最外层 {...}
        m = re.search(r"(\{.*\})", raw, re.DOTALL)
        raw_json = m.group(1) if m else raw

    try:
        data = json.loads(raw_json)
        # 兼容新旧格式：新格式用title_hashtags，旧格式用tags
        title_hashtags = data.get("title_hashtags", data.get("tags", []))
        description_tags = data.get("description_tags", [])
        description_template = data.get("description_template", "")
        return (data.get("candidates", []), title_hashtags,
                data.get("cover_instructions", []), description_tags, description_template)
    except json.JSONDecodeError:
        # fallback：按行解析
        titles = []
        for line in raw.splitlines():
            line = line.strip()
            if line and ("title" in line or len(line) > 20):
                # 简单提取引号内的内容
                qm = re.findall(r'"([^"]+)"', line)
                for q in qm:
                    if len(q) > 10 and ("短劇" in q or "Drama" in q or "drama" in q):
                        titles.append({"title": q, "style": "fallback", "conflict_points": []})
                        break
        return titles[:5], [], [], [], ""


def run_from_manifest(manifest_path: str) -> Path:
    manifest = _load_json(Path(manifest_path), {})
    task_name = manifest.get("task_name", "unknown")
    region = manifest.get("target_region", "hk")

    # 读取分析文件
    analysis_path = BASE_DIR / "data" / "drama_analysis" / f"{task_name}.json"
    ad_path = BASE_DIR / "data" / "ad_materials" / task_name / "search_raw.json"
    analysis = _load_json(analysis_path, {})
    ad = _load_json(ad_path, {})

    # 如果分析为空，自动豆包搜索
    if not analysis or not analysis.get("genre"):
        print(f"🔍 未找到《{task_name}》剧情分析，自动搜索...")
        try:
            from doubao_api import doubao_search
            search_query = f"""请搜索短剧《{task_name}》的完整信息，按以下格式分条输出，内容越详细越好：

1. 【剧情概述】完整剧情介绍（包含起承转合、主要转折点、结局，尽量详细）
2. 【核心冲突】至少7个主要冲突点，每个包含：冲突类型、涉及人物、激烈程度(1-5)、视觉元素
3. 【热门标题】国内抖音/快手/小红书投放的热门标题和关键词（至少15个）
4. 【人物关系】主要角色及关系、性格特征、身份背景
5. 【经典台词/钩子】爆款开场钩子、经典台词、催泪/爽点台词（至少10句）
6. 【投放素材】国内常用的剪辑方向、高点击率片段描述、名场面时间戳

请尽量详细，1000-2000字都没问题。"""
            search_result = doubao_search(search_query, max_tokens=4000)
            if search_result and len(search_result) > 200:
                import re
                # 提取题材类型
                genre_match = re.search(r'(古装|现代|都市|总裁|甜宠|虐恋|重生|穿越|复仇|悬疑|奇幻|仙侠|武侠)', search_result)
                genre = genre_match.group(1) if genre_match else "未知"
                
                # 提取冲突点（更宽松的匹配）
                hooks = re.findall(r'[\u4e00-\u9fff]{2,}(?:反转|冲突|误会|陷害|背叛|复仇|逆袭|揭露|真相|打脸|虐心|甜宠|互撩)[\u4e00-\u9fff]{0,4}', search_result)
                hooks = list(dict.fromkeys(hooks))[:10]  # 去重，最多10个
                
                # 提取道具
                props = re.findall(r'(?:戒指|合同|药|玉佩|剑|医术|秘籍|令牌|银针|丹药|毒|酒|信物)[\u4e00-\u9fff]{0,2}', search_result)
                props = list(dict.fromkeys(props))[:5]
                
                # 提取场景
                scenes = re.findall(r'(?:王府|皇宫|医院|公司|豪宅|战场|江湖|山谷|宫廷|医馆|侯府|丞相府|客栈|大街)[\u4e00-\u9fff]{0,2}', search_result)
                scenes = list(dict.fromkeys(scenes))[:5]
                
                # 提取人物
                chars = re.findall(r'([^，。\s]{2,4})(?:饰演|饰|扮演|主角|女主|男主|由|是)', search_result)
                chars = list(dict.fromkeys(chars))[:6]
                
                analysis = {
                    "genre": genre,
                    "plot_summary": search_result[:300],
                    "hooks_and_twists": hooks if hooks else ["身份反转", "利益冲突"],
                    "key_props": props if props else ["信物"],
                    "key_scenes": scenes if scenes else ["王府"],
                    "characters": chars if chars else ["男主", "女主"],
                    "raw_search": search_result[:2000],  # 保存原始搜索供nuwa读取
                    "source": "doubao_auto_search",
                }
                analysis_path.parent.mkdir(parents=True, exist_ok=True)
                analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  ✅ 搜索完成，返回 {len(search_result)} 字，已保存")
            else:
                print(f"  ⚠️ 搜索结果太短({len(search_result) if search_result else 0}字)，使用默认分析")
        except Exception as e:
            print(f"  ⚠️ 搜索失败: {e}")

    print(f"🎬 生成标题: {task_name} | 地区: {region}")

    # 1. 构建 prompt
    direction = manifest.get("direction", "")
    distill_model = manifest.get("distill_model", "mimo")
    prompt = _build_nuwa_prompt(manifest, analysis, ad, direction=direction, distill_model=distill_model)
    print(f"🤖 调用 nuwa 专家生成 (蒸馏方案: {distill_model})...")

    # 2. 调用 nuwa API
    raw_response = nuwa_chat(prompt, max_tokens=4000, temperature=0.7, rotate=True)
    tags = []
    cover_instructions = []
    title_hashtags = []
    description_tags = []
    description_template = ""
    if not raw_response:
        print("❌ nuwa API 返回空，fallback 到模板生成")
        candidates = _fallback_templates(task_name, analysis, region)
    else:
        candidates, title_hashtags, cover_instructions, description_tags, description_template = _parse_nuwa_response(raw_response)

    if not candidates:
        print("⚠️ nuwa 未返回有效标题，fallback 到模板")
        candidates = _fallback_templates(task_name, analysis, region)

    # 2.5 后处理：非CJK标题过滤中文字符
    is_cjk = region in ("hk", "tw", "sg", "mo", "zh-CN", "zh")
    if not is_cjk:
        for c in candidates:
            original = c.get("title", "")
            cleaned = _strip_cjk_for_non_cjk(original, region)
            if cleaned != original:
                c["title"] = cleaned
                print(f"  🧹 过滤中文: {original[:40]}... → {cleaned[:40]}...")

    # 3. 评分排序（不reject，AI按prompt生成即可）
    results = []
    for c in candidates:
        title = c.get("title", "")
        if not title:
            continue
        score = _score_title(title, analysis)
        results.append({
            "title": title,
            "style": c.get("style", "unknown"),
            "conflict_points": c.get("conflict_points", []),
            "score": score,
        })
        print(f"  ✅: {title[:50]}... | 总分{score['total']}")

    # 4. 排序输出（取前5）
    results = sorted(results, key=lambda x: x["score"]["total"], reverse=True)[:5]

    # 5. 二次精炼最高分标题
    if results:
        best = results[0]
        print(f"🔧 二次精炼最高分标题...")
        refined = _refine_best_title(best["title"], analysis, region)
        if refined != best["title"]:
            best["title"] = refined
            best["score"] = _score_title(refined, analysis)
            best["refined"] = True
            print(f"  ✨ 精炼后: {refined[:50]}...")

    # 按地区设置 fallback tags 和 description_template
    region_defaults = {
        "hk": {"hashtags": ["#短劇", "#flickreels", "#DramaBox", "#港劇", "#粵語短劇"],
               "desc_tags": ["#短劇推薦", "#港劇推薦", "#追劇", "#短視頻", "#粵語", "#香港", "#DramaBox", "#短劇", "#追劇日常", "#必看短劇"],
               "desc_tpl": "🔥 {title}\n\n{synopsis}\n\n▶ 全集完整版，一口氣看完！\n\n#短劇 #flickreels #DramaBox {extra_tags}\n\n📌 訂閱頻道，不錯過任何精彩短劇！"},
        "tw": {"hashtags": ["#短劇", "#flickreels", "#DramaBox", "#台劇", "#台灣短劇"],
               "desc_tags": ["#短劇推薦", "#台劇推薦", "#追劇", "#短視頻", "#台灣", "#DramaBox", "#短劇", "#追劇日常", "#必看短劇", "#陸劇"],
               "desc_tpl": "🔥 {title}\n\n{synopsis}\n\n▶ 全集完整版，一口氣看完！\n\n#短劇 #flickreels #DramaBox {extra_tags}\n\n📌 訂閱頻道，不錯過任何精彩短劇！"},
        "en": {"hashtags": ["#ShortDrama", "#flickreels", "#DramaBox", "#DramaShorts"],
               "desc_tags": ["#ShortDrama", "#DramaBox", "#DramaShorts", "#Revenge", "#PlotTwist", "#FullEpisode", "#MustWatch", "#ShortFilm", "#Drama", "#BingeWatch"],
               "desc_tpl": "🔥 {title}\n\n{synopsis}\n\n▶ Watch Full Episodes!\n\n#ShortDrama #flickreels #DramaBox {extra_tags}\n\n📌 Subscribe for more!"},
        "us": {"hashtags": ["#ShortDrama", "#flickreels", "#DramaBox", "#DramaShorts"],
               "desc_tags": ["#ShortDrama", "#DramaBox", "#DramaShorts", "#Revenge", "#PlotTwist", "#FullEpisode", "#MustWatch", "#ShortFilm", "#Drama", "#BingeWatch"],
               "desc_tpl": "🔥 {title}\n\n{synopsis}\n\n▶ Watch Full Episodes!\n\n#ShortDrama #flickreels #DramaBox {extra_tags}\n\n📌 Subscribe for more!"},
        "br": {"hashtags": ["#DramaCurto", "#flickreels", "#DramaBox", "#DramaBrasileiro"],
               "desc_tags": ["#DramaCurto", "#DramaBox", "#Vingança", "#PlotTwist", "#EpisódioCompleto", "#AssistaAgora", "#Drama", "#Maratona", "#Novela", "#CurtaDuração"],
               "desc_tpl": "🔥 {title}\n\n{synopsis}\n\n▶ Assista o Episódio Completo!\n\n#DramaCurto #flickreels #DramaBox {extra_tags}\n\n📌 Inscreva-se para mais!"},
        "mx": {"hashtags": ["#DramaCorto", "#flickreels", "#DramaBox", "#DramaLatino"],
               "desc_tags": ["#DramaCorto", "#DramaBox", "#Venganza", "#PlotTwist", "#EpisodioCompleto", "#MíraloAhora", "#Drama", "#Maratón", "#Novela", "#CurtaDuración"],
               "desc_tpl": "🔥 {title}\n\n{synopsis}\n\n▶ ¡Mira el Episodio Completo!\n\n#DramaCorto #flickreels #DramaBox {extra_tags}\n\n📌 ¡Suscríbete para más!"},
        "id": {"hashtags": ["#DramaPendek", "#flickreels", "#DramaBox", "#DramaIndonesia"],
               "desc_tags": ["#DramaPendek", "#DramaBox", "#BalasDendam", "#PlotTwist", "#EpisodeLengkap", "#TontonSekarang", "#Drama", "#Maraton", "#Sinetron", "#DurasiPendek"],
               "desc_tpl": "🔥 {title}\n\n{synopsis}\n\n▶ Tonton Episode Lengkap!\n\n#DramaPendek #flickreels #DramaBox {extra_tags}\n\n📌 Subscribe untuk lebih banyak!"},
    }
    # 兼容映射
    region_key_map = {"gb": "en", "sg": "hk", "mo": "hk", "es": "mx", "latam": "mx", "pt": "br", "zh-CN": "tw", "zh": "tw"}
    rk = region_key_map.get(region, region)
    defaults = region_defaults.get(rk, region_defaults["en"])

    fallback_hashtags = defaults["hashtags"]
    fallback_desc_tags = defaults["desc_tags"]
    fallback_desc_tpl = defaults["desc_tpl"]

    output = {
        "manifest": manifest_path,
        "task_name": task_name,
        "region": region,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "provider": "agent-plan",
        "distill_model": manifest.get("distill_model", "mimo"),
        "candidates": results,
        "tags": title_hashtags if title_hashtags else fallback_hashtags,
        "title_hashtags": title_hashtags if title_hashtags else fallback_hashtags,
        "description_tags": description_tags if description_tags else fallback_desc_tags,
        "description_template": description_template if description_template else fallback_desc_tpl,
        "cover_instructions": cover_instructions if cover_instructions else [
            {"style": "情绪冲突型", "instruction": f"一位年轻女性在豪华办公室中，表情震惊地看着手中的文件，背后是落地窗城市夜景。短剧《{task_name}》风格。"},
            {"style": "身份反转型", "instruction": f"一位穿着朴素的女性站在豪宅门口，眼神坚定，身后是奢华的派对场景。短剧《{task_name}》风格。"},
            {"style": "悬念型", "instruction": f"一位西装男性背对镜头站在雨中，手中握着一枚戒指，面前是一扇半开的门。短剧《{task_name}》风格。"},
        ],
        "input_files": {
            "analysis": str(analysis_path),
            "ad_materials": str(ad_path),
        },
    }

    out_path = BASE_DIR / "output" / "titles" / f"{task_name}_{region}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n📁 输出: {out_path}")
    print(f"   通过: {len(results)}")
    return out_path


def _strip_cjk_for_non_cjk(title: str, region: str) -> str:
    """非CJK地区标题：移除混入的中文字符，保留当地语言"""
    if region in ("hk", "tw", "sg", "mo", "zh-CN", "zh"):
        return title
    # 移除CJK统一汉字
    cleaned = re.sub(r'[\u4e00-\u9fff]+', ' ', title)
    # 移除CJK标点
    cleaned = re.sub(r'[，。！？；：""''【】（）、]+', ' ', cleaned)
    # 合并空格
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    # 清理首尾标点
    cleaned = cleaned.strip('|·—- ')
    return cleaned if len(cleaned) > 10 else title  # 太短则保留原文


def _fallback_templates(task_name: str, analysis: dict, region: str) -> list[dict]:
    """fallback：模板生成，确保列表非空。按地区语言生成。"""
    hooks = analysis.get("hooks_and_twists", []) or []
    props = analysis.get("key_props", []) or []
    scenes = analysis.get("key_scenes", []) or []
    genre = analysis.get("genre", "")

    # 中文 fallback（hk/tw/mo/sg）
    if region in ("hk", "tw", "mo", "sg"):
        h = hooks[0] if hooks else ("穿越反轉" if genre == "古装" else "身份反轉")
        p = props[0] if props else ("玉佩" if genre == "古装" else "合同")
        s = scenes[0] if scenes else ("王府" if genre == "古装" else "豪宅")
        surprise = "點知" if region in ("hk", "mo") else "沒想到" if region == "tw" else "竟然"
        templates = [
            f"【短劇】{task_name}：{h}！{p}一出全場反轉，{surprise}真相即刻曝光",
            f"【短劇】{task_name}：{s}對峙，{surprise}{h}，全集完整版一口氣看完",
            f"【短劇】{task_name}：被背叛後她在{s}反擊，{p}揭開終局真相",
            f"【短劇】{task_name}：{surprise}她的真實身份曝光，{h}讓所有人震驚",
            f"【短劇】{task_name}：{p}暗藏玄機，{s}裡{h}逆襲翻盤",
        ]
        return [{"title": t, "style": f"{region}_fallback", "conflict_points": [h]} for t in templates]

    # 英文 fallback（us/uk/global）
    h = hooks[0] if hooks else "Identity Reversal"
    templates_en = [
        f"Short Drama | {task_name}: {h}! The Truth That Changes Everything",
        f"Short Drama | {task_name}: Betrayal, Revenge, and a Secret That Will Shock You",
        f"Short Drama | {task_name}: Full Episode — She Fought Back When No One Expected",
        f"Short Drama | {task_name}: The Hidden Identity That Turned the Tables",
        f"Short Drama | {task_name}: A Contract, A Lie, and the Ultimate Revenge",
    ]

    # 葡文 fallback（br）
    templates_pt = [
        f"Drama Curto | {task_name}: A Grande Revelação Que Mudou Tudo",
        f"Drama Curto | {task_name}: Traição, Vingança e Um Segredo Chocante",
        f"Drama Curto | {task_name}: Episódio Completo — Ela Revidou Quando Ninguém Esperava",
        f"Drama Curto | {task_name}: A Identidade Oculta Que Inverteu o Jogo",
        f"Drama Curto | {task_name}: Um Contrato, Uma Mentira e a Vingança Final",
    ]

    # 西文 fallback（mx/latam）
    templates_es = [
        f"Drama Corto | {task_name}: La Gran Revelación Que Lo Cambió Todo",
        f"Drama Corto | {task_name}: Traición, Venganza y Un Secreto Impactante",
        f"Drama Corto | {task_name}: Episodio Completo — Ella Contraatacó Cuando Nadie lo Esperaba",
        f"Drama Corto | {task_name}: La Identidad Oculta Que Invertió la Situación",
        f"Drama Corto | {task_name}: Un Contrato, Una Mentira y la Venganza Final",
    ]

    # 印尼文 fallback（id）
    templates_id = [
        f"Drama Pendek | {task_name}: Pengungkapan Besar yang Mengubah Segalanya",
        f"Drama Pendek | {task_name}: Pengkhianatan, Balas Dendam, dan Rahasia Mengejutkan",
        f"Drama Pendek | {task_name}: Episode Lengkap — Dia Melawan Ketika Tidak Ada yang Menyangka",
        f"Drama Pendek | {task_name}: Identitas Tersembunyi yang Membalik Keadaan",
        f"Drama Pendek | {task_name}: Sebuah Kontrak, Sebuah Kebohongan, dan Balasan Terakhir",
    ]

    lang_map = {"en": templates_en, "us": templates_en, "uk": templates_en, "global": templates_en,
                "br": templates_pt, "pt": templates_pt,
                "mx": templates_es, "es": templates_es, "latam": templates_es,
                "id": templates_id}
    templates = lang_map.get(region, templates_en)
    return [{"title": t, "style": f"{region}_fallback", "conflict_points": [h]} for t in templates]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True, help="manifest JSON 路径")
    args = p.parse_args()
    run_from_manifest(args.manifest)


if __name__ == "__main__":
    main()
