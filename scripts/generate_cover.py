#!/usr/bin/env python3
"""
generate_cover.py — 真正调用 nuwa 专家的封面生成器

流程：
1. 读取标题 + 剧分析（analysis + manifest）
2. 通过 skill_router 读取 short-drama-expert + hk-traditional-market-expert 规则
3. 调用 nuwa_api 生成封面（brief + prompt + 元素清单）
4. 用 check_rules 做规则检查（SDE-007/008/009/010/011）
5. 按专家权重评分
6. 输出合规候选

用法：
    python3 scripts/generate_cover.py --manifest data/manifests/xxx.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from nuwa_api import nuwa_chat
from doubao_api import doubao_chat

BASE_DIR = Path(__file__).parent.parent


def _load_json(path: Path, default=None):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_nuwa_response(raw: str) -> list[dict]:
    """从 nuwa 响应中提取 JSON，支持多种格式容错"""
    if not raw or len(raw) < 20:
        return []

    # 1. 找 ```json 代码块
    m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if m:
        raw_json = m.group(1)
    else:
        # 2. 尝试直接找最外层 JSON 对象
        m = re.search(r"(\{.*\})", raw, re.DOTALL)
        raw_json = m.group(1) if m else raw

    try:
        data = json.loads(raw_json)
        candidates = data.get("candidates", [])
        if candidates:
            # 补全缺失字段
            for c in candidates:
                if "brief" not in c:
                    c["brief"] = ""
                if "prompt" not in c:
                    # support prompt_en as fallback for backward compatibility
                    if "prompt_en" in c:
                        c["prompt"] = c["prompt_en"]
                    else:
                        c["prompt"] = f"16:9 cinematic thumbnail, {c['brief'][:100]}"
                if "elements" not in c or not isinstance(c["elements"], list):
                    c["elements"] = ["人物", "道具", "情绪"]
                if "color_scheme" not in c:
                    c["color_scheme"] = "金色/黑色"
                if "text_overlay" not in c:
                    c["text_overlay"] = c["brief"][:8] if c["brief"] else "短劇"
            return candidates
    except json.JSONDecodeError:
        pass

    # 3. 终极 fallback：按 brief 分段提取
    candidates = []
    # 匹配 "brief": "..." 的块
    briefs = re.findall(r'"brief"\s*:\s*"([^"]{20,500})"', raw)
    prompts = re.findall(r'"prompt"\s*:\s*"([^"]{20,800})"', raw)
    elements_list = re.findall(r'"elements"\s*:\s*(\[[^\]]*\])', raw)
    colors = re.findall(r'"color_scheme"\s*:\s*"([^"]+)"', raw)
    texts = re.findall(r'"text_overlay"\s*:\s*"([^"]+)"', raw)

    for i, brief in enumerate(briefs):
        c = {
            "brief": brief,
            "prompt": prompts[i] if i < len(prompts) else f"16:9 thumbnail, {brief[:100]}",
            "elements": json.loads(elements_list[i]) if i < len(elements_list) else ["人物", "道具", "情绪"],
            "color_scheme": colors[i] if i < len(colors) else "金色/黑色",
            "text_overlay": texts[i] if i < len(texts) else brief[:8],
        }
        candidates.append(c)

    return candidates


def _generate_with_doubao(title: str, analysis: dict, region: str) -> list[dict]:
    """用豆包生成封面——搜索+封面一次请求完成"""
    from doubao_api import call_doubao

    drama_name = analysis.get("drama_name", title[:10])
    hooks = analysis.get("hooks_and_twists", [])[:5]
    genre = analysis.get("genre", "現代都市")
    chars = analysis.get("characters", ["男主", "女主"])

    # 地区风格
    region_style = {
        "hk": "港式：对比强烈、粗黑字体、情绪夸张、可用粵語文案",
        "tw": "台式：柔和唯美、优雅字体、情绪内敛、文言文感",
        "sg": "新马：双语混合、现代感强",
        "mo": "港澳：港风浓烈",
    }.get(region, "港式")

    # 色彩
    color_map = {
        "總裁": "金色/黑色", "甜寵": "粉色/白色", "虐戀": "藍色/灰色",
        "復仇": "紅色/黑色", "重生": "紫色/金色", "豪門": "金色/黑色",
        "古裝": "硃紅/金色/墨綠", "穿越": "紫色/金色", "醫妃": "青色/白色/硃紅",
        "醫術": "青色/白色", "仙俠": "白色/金色/天藍", "懸疑": "黑色/暗紅",
        "宮鬥": "金色/硃紅/深紫", "宅鬥": "暗紅/金色/墨色",
    }
    colors = color_map.get(genre, "金色/黑色")

    # 合并请求：搜索投放素材 + 生成4种风格封面
    # 基于72张真实封面数据分析优化（2026-04-24）
    query = (
        f"请搜索短剧《{drama_name}》的信息，按两部分输出。\n\n"
        f"===== 第一部分：搜索素材 =====\n"
        f"请搜索并整理：\n"
        f"1. 【完整剧情】前3幕关键剧情：第1幕（开场钩子+人物设定）、第2幕（核心冲突升级）、第3幕（高潮+反转），每个幕写清楚人物、场景、道具、情绪转折\n"
        f"2. 【国内投放素材】抖音/快手/小红书上这部短剧的投放热门标题（至少15个）、高点击率封面特点、常用的名场面片段描述\n"
        f"3. 【核心冲突】至少7个冲突点，每个包含：冲突类型、涉及人物、激烈程度、视觉元素、发生在哪一幕\n"
        f"4. 【人物设定】主要角色的外貌特征、服装风格、标志性表情\n"
        f"5. 【关键道具清单】至少5个贯穿全剧的重要道具（优先选能体现身份反差的道具：囚服/婚纱/西装/护士服/晚礼服/金元宝等，不要选文档类如孕检单/离婚协议）\n"
        f"6. 【关键场景】至少5个标志性场景\n\n"
        f"===== 第二部分：4种风格封面方案 =====\n"
        f"Based on the research above and the following RULES, generate 4 AI cover art prompts in English for ChatGPT/DALL-E.\n\n"
        f"【COVER RULES — Based on 3000+ Top-Performing Covers】\n"
        f"1. 【Close-Up Face】Face must occupy 60%+ of frame. Medium close-up or extreme close-up ONLY. Forbidden: wide shot, long shot, full shot, establishing shot. Expression must be extreme: cold/fierce/intoxicated/terrified/determined/innocent\n"
        f"2. 【100% Bokeh Background】Background MUST be completely blurred with bokeh effect. No distinct buildings, rooms, streets, or scenery visible. Scene context ONLY implied through clothing: suit=urban, prison uniform=prison, nurse outfit=hospital, hanfu=palace\n"
        f"3. 【Right-Bottom Safe Zone】Right-bottom corner must be blank (YouTube timestamp overlay area). No faces or key text in bottom-right\n"
        f"4. 【White Title Text】Title: 2-4 white Chinese characters, handwritten or serif font, MUST have dark drop shadow for readability on any background. Forbidden: yellow-background black text, red-background white text, red circles/arrows, more than 5 characters\n"
        f"5. 【FULL Badge】Top-left corner: semi-transparent capsule badge reading 'FULL EPISODES' or 'FULL MOVIE'\n"
        f"6. 【Cold-Warm Left-Right Split】Preferred composition: left side cool (blue/dark/male black suit) vs right side warm (orange/bright/female white dress). Not simple symmetry but color contrast\n"
        f"7. 【Forbidden Elements】Red circles/arrows, pregnancy test/divorce agreement document props, distinct scene backgrounds, titles longer than 5 chars, yellow-background tabloid text\n\n"
        f"【Genre-Specific Requirements】\n"
        f"- Female romance (CEO/sweet/angst): Dual intimate poses — kissing/wall-slam/chin-tilt/deep gaze. Warm light/pink-purple soft light/backlit lens flare. Male in black suit, female in white/pink gown\n"
        f"- Male power (war god/son-in-law/rich): Male protagonist dead center, surrounded by beauties/wealth/bodyguards. Optional blue holographic UI frame. Gold/cold-blue palette. Extreme identity contrast (instant noodles vs gold bars / prison uniform vs luxury car)\n"
        f"- Period drama (palace/time-travel): Gold-red palette. Two styles: ① multi-male one-female pyramid composition ② ethereal single portrait warm yellow backlight, no text\n"
        f"- Family drama: Frozen extreme action — throwing papers/spitting blood/stepping on someone/collar-grab. High-saturation conflict colors (red/gold/black). Exaggerated expressions to the point of distortion\n\n"
        f"Each cover must satisfy:\n"
        f"1. 【Conflict Fusion】Fuse 3-4 conflicts into one image using at least one composition technique:\n"
        f"   - Left-right cold-warm split (invisible vertical center line)\n"
        f"   - Center radiating (center subject + conflict elements orbiting)\n"
        f"   - Depth guidance (foreground to background size contrast)\n"
        f"   - Class contrast (extreme wealth/status disparity in one frame)\n"
        f"2. 【Face Close-Up Iron Rule】\n"
        f"   - Face 60%+ of frame, medium close-up\n"
        f"   - Clothing implies identity and setting (specific colors and materials)\n"
        f"   - Signature expression (cold/intoxicated/terrified/innocent/determined)\n"
        f"3. 【English ChatGPT/DALL-E Prompt Rules】\n"
        f"   - Write entirely in English, detailed down to position/size/color/light direction of each visual element\n"
        f"   - MUST include: 'background completely blurred, bokeh light spots, no distinct buildings or scenery'\n"
        f"   - MUST include: 'bottom center reserved for title area, dark gradient base, white art text with drop shadow'\n"
        f"   - MUST include: 'right-bottom safe zone blank, no faces or text'\n"
        f"   - MUST include: 'top-left semi-transparent capsule badge reading FULL EPISODES'\n"
        f"   - MUST include: '16:9 landscape aspect ratio'\n"
        f"   - MUST include: 'East Asian features, realistic natural appearance, not doll-like'\n"
        f"   - Include photography terms: chiaroscuro, Rembrandt tri-lighting, feathered edges, cinematic depth of field\n"
        f"   - Include HEX color values where appropriate\n"
        f"   - Include art terms: shattered glass collage, transparency layers, light bleed\n"
        f"   - Describe specific clothing colors and materials (black haute couture suit / white lace wedding dress / gray prison uniform etc.)\n"
        f"4. 【Brief — Chinese Display Description】300-500 Chinese characters describing: composition technique, 3-4 conflict positions, character details, costume/prop contrast, bokeh effect, title zone, lighting and color atmosphere\n"
        f"5. 【Title Text】Extract the most gripping 2-4 character Chinese phrase from the conflict (e.g. '刺情'/'覆水難收'/'千金歸來'), containing drama name or core emotion word\n\n"
        f"4 style directions:\n"
        f"Style A - HK Intense: High contrast, exaggerated emotion, red-gold-black palette, bold white title\n"
        f"Style B - TW Elegant: Soft light, restrained emotion, pink-white-blue palette, handwritten white title, heavy lens flare\n"
        f"Style C - Modern Minimal: Clean bokeh background, character close-up, monochrome palette, minimal white title\n"
        f"Style D - Dark Drama: Low-key lighting, strong shadows, purple-black palette, white serif title\n\n"
        f"【Output Format】Strict JSON only, no markdown, no explanation:\n"
        f"{{\n"
        f'  "raw_search": "All researched material (plot + ad headlines + conflicts + characters + props + scenes, 2000+ chars)",\n'
        f'  "candidates": [\n'
        f'    {{\n'
        f'      "style": "Style name (HK Intense / TW Elegant / Modern Minimal / Dark Drama)",\n'
        f'      "brief": "Chinese visual description (300-500 chars, detailing composition/conflict fusion/characters/costumes/bokeh background/title zone/lighting)",\n'
        f'      "prompt": "English ChatGPT/DALL-E prompt (detailed English description with HEX colors, photography terms, art terms, bokeh/safe zone/title zone/FULL EPISODES badge, 16:9 landscape, East Asian features, specific clothing materials and colors)",\n'
        f'      "text_overlay": "Cover title (2-4 white Chinese characters)",\n'
        f'      "conflicts_fused": ["conflict1", "conflict2", "conflict3"],\n'
        f'      "composition": "Composition technique used (left-right cold-warm split / center radiating / depth guidance / class contrast)",\n'
        f'      "genre_note": "Genre subcategory (female romance / male power / period drama / family drama)"\n'
        f'    }},\n'
        f'    ...4 total\n'
        f'  ]\n'
        f"}}"
    )

    print("  🔍🎨 豆包搜索+封面一次请求...")
    raw = call_doubao([{"role": "user", "content": query}], max_tokens=4000, enable_search=True)
    if not raw:
        print("  ❌ 豆包返回空")
        return []

    # 解析JSON + 字段映射（豆包返回 style/content，我们要求 brief/prompt）
    candidates = []
    try:
        m = re.search(r"(\{.*\})", raw, re.DOTALL)
        if m:
            data = json.loads(m.group(1))
            # 同时保存搜索素材回 analysis
            if "raw_search" in data and data["raw_search"]:
                analysis["raw_search"] = data["raw_search"]
            raw_candidates = data.get("candidates", [])
            # 豆包字段映射：style→brief, content→prompt
            for rc in raw_candidates:
                c = {}
                # 映射核心字段
                c["brief"] = rc.get("brief") or rc.get("content") or rc.get("style") or ""
                c["prompt"] = rc.get("prompt") or rc.get("prompt_en") or rc.get("content") or f"16:9 cinematic cover, {c['brief'][:100]}"
                c["text_overlay"] = rc.get("text_overlay") or rc.get("title") or _extract_title_from_brief(c["brief"]) or "短劇"
                c["conflicts_fused"] = rc.get("conflicts_fused") or []
                c["composition"] = rc.get("composition") or ""
                c["genre_note"] = rc.get("genre_note") or ""
                c["style"] = rc.get("style") or ""
                # 兼容旧字段
                c.setdefault("elements", ["人物", "道具", "情绪"])
                c.setdefault("color_scheme", colors)
                candidates.append(c)
    except Exception as e:
        print(f"  ⚠️ JSON解析失败: {e}")

    print(f"  ✅ 豆包一次请求完成，生成 {len(candidates)} 个封面")
    return candidates


def _extract_title_from_brief(brief: str) -> str:
    """从 brief 中提取可能的标题文案"""
    if not brief:
        return ""
    # 尝试提取书名号或引号中的内容
    import re
    m = re.search(r'[《「"]([^《」"》]{2,4})[》」"]', brief)
    if m:
        return m.group(1)
    # 尝试提取4字以内的关键词组合
    keywords = ["千金", "重生", "復仇", "逆襲", "歸來", "決裂", "刺情", "豪門"]
    for kw in keywords:
        if kw in brief:
            return kw
    return brief[:4] if len(brief) >= 4 else brief



def _check_cover_compliance(candidate: dict, title: str, genre: str) -> list[dict]:
    """封面规则检查 —— 基于72张真实爆款封面数据验证（2026-04-24更新）"""
    failures = []
    brief = candidate.get("brief", "")
    brief_lower = brief.lower()
    prompt_text = candidate.get("prompt", "")
    prompt_lower = prompt_text.lower()
    combined = brief + " " + prompt_text
    combined_lower = combined.lower()

    # R001: 面部特写检查（人物面部必须占画面60%+，近景特写，禁止全景/远景）
    face_keywords = ["close-up", "特写", "facial", "face", "portrait", "微表情", "侧脸", "profile", "medium close-up"]
    has_face = any(kw in prompt_lower or kw in brief.lower() for kw in face_keywords)
    if not has_face:
        failures.append({"rule": "R001", "level": "REJECT", "reason": "缺少面部特写关键词（face/close-up/特写），必须用近景"})

    forbidden_shot = ["wide shot", "long shot", "full shot", "全景", "远景", "establishing shot"]
    found_shot = [w for w in forbidden_shot if w in prompt_lower]
    if found_shot:
        failures.append({"rule": "R001-A", "level": "REJECT", "reason": f"检测到禁止景别: {', '.join(set(found_shot))}（必须用特写）"})

    # R002: 冲突点密度（3-4个，≥3为硬性要求）
    conflicts = candidate.get("conflicts_fused", [])
    if len(conflicts) < 3:
        failures.append({"rule": "R002", "level": "REJECT", "reason": f"冲突点不足（{len(conflicts)}个，需≥3）"})
    elif len(conflicts) > 4:
        failures.append({"rule": "R002", "level": "WARN", "reason": f"冲突点过多（{len(conflicts)}个，建议3-4个）"})

    # R003: 标题区规范（2-4字白色艺术字，底部居中）
    overlay = candidate.get("text_overlay", "")
    if not overlay:
        failures.append({"rule": "R003", "level": "REJECT", "reason": "缺少text_overlay"})
    elif len(overlay) > 5:
        failures.append({"rule": "R003", "level": "WARN", "reason": f"标题过长（{len(overlay)}字，需2-4字）"})
    if len(overlay) < 2:
        failures.append({"rule": "R003", "level": "WARN", "reason": f"标题过短（{len(overlay)}字）"})

    # R004: 严禁诱导元素（红圈/箭头/大字报）
    forbidden_inducers = ["arrow", "circle", "red circle", "yellow background", "大字报", "clickbait arrow", "pointing finger"]
    found_inducers = [w for w in forbidden_inducers if w in prompt_lower]
    if found_inducers:
        failures.append({"rule": "R004", "level": "REJECT", "reason": f"检测到诱导元素: {', '.join(set(found_inducers))}"})

    # R005: 严禁文档类道具（孕检单/离婚协议等已被验证不具转化力）
    forbidden_docs = ["pregnancy test", "divorce agreement", "medical report", "孕检单", "离婚协议", "dna report", "合同", "document"]
    found_docs = [w for w in forbidden_docs if w in prompt_lower or w in brief.lower()]
    if found_docs:
        failures.append({"rule": "R005", "level": "WARN", "reason": f"检测到文档类道具: {', '.join(set(found_docs))}（已被72张数据验证不具转化力，优先用服装反差）"})

    # R006: 背景必须虚化（支持中文/英文关键词）
    blur_keywords = ["虚化", "bokeh", "blur", "柔焦", "散景", "背景模糊"]
    has_blur = any(kw in prompt_lower or kw in brief_lower for kw in blur_keywords)
    if not has_blur:
        failures.append({"rule": "R006", "level": "WARN", "reason": "prompt缺少背景虚化描述（虚化/bokeh/柔焦）"})

    # R007: 标题区样式禁止黄底黑字/红底白字（中文prompt适配）
    title_forbidden = ["yellow background", "red background", "black text", "粗黑标题", "大字报", "黄底黑字", "红底白字"]
    found_title_issues = [w for w in title_forbidden if w in prompt_lower or w in brief_lower]
    if found_title_issues:
        failures.append({"rule": "R007", "level": "REJECT", "reason": f"标题区检测到禁止样式: {', '.join(set(found_title_issues))}"})

    # R008: 必须包含右下角safe zone（中文适配）
    safe_keywords = ["safe zone", "右下角", "右下"]
    has_safe = any(kw in prompt_lower or kw in brief_lower for kw in safe_keywords)
    if not has_safe:
        failures.append({"rule": "R008", "level": "WARN", "reason": "prompt缺少右下角safe zone描述"})

    # R009: 必须包含FULL EPISODES/FULL MOVIE标签
    full_keywords = ["full episodes", "full movie", "全集", "完整版"]
    has_full = any(kw in prompt_lower or kw in brief_lower for kw in full_keywords)
    if not has_full:
        failures.append({"rule": "R009", "level": "WARN", "reason": "prompt缺少FULL EPISODES/全集标签"})

    # R010: 必须包含标题区预留描述（中文适配）
    title_area_keywords = ["title area", "blank title", "标题区", "标题区域", "底部居中", "标题位置"]
    has_title_area = any(kw in prompt_lower or kw in brief_lower for kw in title_area_keywords)
    if not has_title_area:
        failures.append({"rule": "R010", "level": "WARN", "reason": "prompt缺少标题区预留描述"})

    # R011: 冷暖左右分割构图（优选）
    composition = candidate.get("composition", "")
    if composition:
        valid_compositions = ["左右冷暖分割", "中心放射", "纵深引导", "阶级对比", "left-right", "center radiating", "depth", "class contrast"]
        if not any(vc in composition.lower() for vc in valid_compositions):
            failures.append({"rule": "R011", "level": "WARN", "reason": f"构图手法'{composition}'不在推荐列表（左右冷暖分割/中心放射/纵深引导/阶级对比）"})

    # R012: 分赛道差异化检查
    genre_note = candidate.get("genre_note", "")
    if genre_note:
        pass  # 有标注即接受，后续可扩展

    return failures


def _score_cover(candidate: dict, title: str, genre: str) -> dict:
    """基于72张真实封面数据的评分权重（2026-04-24更新）"""
    brief = candidate.get("brief", "")
    brief_lower = brief.lower()
    prompt_text = candidate.get("prompt", "")
    combined = brief + " " + prompt_text
    combined_lower = combined.lower()
    prompt_lower = prompt_text.lower()

    # 1. 面部特写质量 25% — 核心铁律
    face_keywords = ["close-up", "facial", "face", "portrait", "特写", "侧脸", "profile"]
    has_face = any(kw in prompt_lower or kw in brief.lower() for kw in face_keywords)
    face_score = 100 if has_face else 20
    # bonus: 60%画面比例、极端表情
    if "60%" in combined or "extreme expression" in prompt_lower or any(e in combined_lower for e in ["冷酷", "沉醉", "惊恐", "决绝", "无辜", "cold", "fierce", "terrified"]):
        face_score = min(face_score + 15, 100)

    # 2. 冲突融合质量 20% — 2-3个冲突
    conflicts = candidate.get("conflicts_fused", [])
    conflict_score = 100 if 3 <= len(conflicts) <= 4 else (80 if len(conflicts) == 2 else (60 if len(conflicts) >= 1 else 20))
    # bonus: 有具体构图手法
    composition = candidate.get("composition", "")
    if composition:
        conflict_score = min(conflict_score + 10, 100)

    # 3. 背景虚化合规 15%
    blur_score = 0
    blur_keywords = ["虚化", "bokeh", "blur", "柔焦", "散景", "背景模糊"]
    if any(kw in prompt_lower or kw in brief_lower for kw in blur_keywords):
        blur_score += 70
    if "极度虚化" in combined or "extreme background blur" in prompt_lower:
        blur_score += 20
    if "没有任何清晰" in combined or "no distinct" in prompt_lower:
        blur_score += 10
    blur_score = min(blur_score, 100)

    # 4. 标题区规范 15% — 2-4字 + 白色 + 底部
    overlay = candidate.get("text_overlay", "")
    title_score = 100
    if len(overlay) < 2 or len(overlay) > 5:
        title_score -= 30
    if "白色" in combined and ("标题区" in combined or "标题" in combined or "title" in combined):
        title_score += 10
    if "底部" in combined or "bottom" in combined:
        title_score += 10
    title_score = min(title_score, 100)

    # 5. 结构完整性 15% — safe zone + FULL标签 + 16:9
    struct_score = 100
    safe_keywords = ["safe zone", "右下角", "右下"]
    if not any(kw in prompt_lower or kw in brief_lower for kw in safe_keywords):
        struct_score -= 25
    full_keywords = ["full episodes", "full movie", "全集", "完整版"]
    if not any(kw in prompt_lower or kw in brief_lower for kw in full_keywords):
        struct_score -= 20
    if "16:9" not in combined:
        struct_score -= 15

    # 6. 视觉冲击力 10% — 冷暖对比/服装反差
    impact_score = 50
    impact_signals = [
        "contrast", "warm", "cold", "split", "反差", "对比", "暖", "冷",
        "prison", "suit", "evening dress", "囚服", "西装", "晚礼服", "婚纱",
        "kissing", "壁咚", "confrontation", "dramatic"
    ]
    impact_hits = sum(1 for w in impact_signals if w in combined_lower)
    impact_score = min(50 + impact_hits * 10, 100)

    total = round(
        face_score * 0.25 +
        conflict_score * 0.20 +
        blur_score * 0.15 +
        title_score * 0.15 +
        struct_score * 0.15 +
        impact_score * 0.10, 1
    )

    return {
        "face": face_score,
        "conflict": conflict_score,
        "blur": blur_score,
        "title": title_score,
        "structure": struct_score,
        "impact": impact_score,
        "total": total,
    }


def _resolve_prompt_mode(manifest: dict, preset: str) -> str:
    """封面提示词模式：strict / balanced / creative。"""
    mode = str(manifest.get("cover_prompt_mode", "")).strip().lower()
    if mode in {"strict", "balanced", "creative"}:
        return mode
    return "strict" if preset == "fast_validation" else "balanced"


def _build_nuwa_prompt(title: str, analysis: dict, region: str, preset: str, prompt_mode: str = "balanced") -> str:
    """构建 nuwa prompt，注入完整素材"""
    genre = analysis.get("genre", "現代都市")
    hooks = analysis.get("hooks_and_twists", ["身份反轉", "利益冲突"])
    props = analysis.get("key_props", ["合同", "戒指"])
    scenes = analysis.get("key_scenes", ["豪宅", "公司"])
    chars = analysis.get("characters", ["男主", "女主"])
    raw_search = analysis.get("raw_search", "")[:800]

    # 扩展色彩映射
    color_map = {
        "總裁": "金色/黑色", "甜寵": "粉色/白色", "虐戀": "藍色/灰色",
        "復仇": "紅色/黑色", "重生": "紫色/金色", "豪門": "金色/黑色",
        "古裝": "硃紅/金色/墨綠", "穿越": "紫色/金色", "醫妃": "青色/白色/硃紅",
        "醫術": "青色/白色", "仙俠": "白色/金色/天藍", "懸疑": "黑色/暗紅",
        "宮鬥": "金色/硃紅/深紫", "宅鬥": "暗紅/金色/墨色",
    }
    colors = color_map.get(genre, "金色/黑色")

    # 地区封面风格
    region_style = {
        "hk": "港式：对比强烈、字体粗黑、情绪夸张、可用粵語文案",
        "tw": "台式：柔和唯美、字体优雅、情绪内敛、文言文感",
        "sg": "新马：双语混合、现代感强、国际化审美",
        "mo": "港澳：港风浓烈、赌城元素可选",
    }.get(region, "港式")
    # 参考外部 prompt case 库后整理出的“封面镜头语言模板”
    # 目标：在不绑定具体模型的前提下，提高构图一致性与可复现性。
    shot_recipe = {
        "總裁": "电影感人像海报，85mm镜头，浅景深，双人近景，肌肤质感真实，微表情清晰",
        "甜寵": "柔光人像海报，50mm镜头，逆光发丝高光，粉金色bokeh，亲密动作定格",
        "虐戀": "低饱和戏剧海报，85mm镜头，强明暗对比，泪痕与眼神特写，冷暖对冲",
        "復仇": "高反差戏剧海报，35mm近景，边缘轮廓光，身份反差道具并置",
        "重生": "超现实戏剧海报，50mm镜头，双重身份服装拼接，金紫色光效",
        "古裝": "东方电影海报，50mm镜头，金红主调，服装纹理与发饰细节清晰",
    }.get(genre, "电影感人物海报，50mm镜头，浅景深，微表情特写，高对比光影")

    mode_hint = {
        "strict": "优先规则合规与可执行性：safe zone/FULL标签/标题区/背景虚化必须显式出现；文本务实，不追求花哨。",
        "balanced": "兼顾合规与美感：先满足硬规则，再提升镜头叙事和情绪张力。",
        "creative": "在满足硬规则前提下强调画面创意：允许更强风格化光影和构图实验，但不可违反safe zone与标题区规则。",
    }.get(prompt_mode, "兼顾合规与美感：先满足硬规则，再提升镜头叙事和情绪张力。")

    prompt = (
        "你是一位短剧封面设计专家。\n\n"
        f"【Task】Generate 3 cover art schemes for short drama '{title}' (targeting {region.upper()} market), each with an English ChatGPT/DALL-E prompt and a Chinese brief description.\n\n"
        f"【剧情素材】\n{raw_search}\n\n"
        "【剧信息】\n"
        f"- 题材：{genre}\n"
        f"- 核心冲突：{'、'.join(hooks[:4]) if hooks else '未知'}\n"
        f"- 关键道具：{props[0] if props else '未知'}\n"
        f"- 关键场景：{scenes[0] if scenes else '未知'}\n"
        f"- 人物：{'、'.join(chars[:2])}\n\n"
        f"【地区风格】{region_style}\n\n"
        f"【镜头语言模板】{shot_recipe}\n"
        f"【色彩建议】{colors}\n\n"
        f"【提示词模式】{prompt_mode}：{mode_hint}\n\n"
        "【必须遵守的封面铁律 — 基于3000+爆款数据】\n"
        "1. 【海报构图】人物占画面30-35%，留空间给3-4个冲突视觉元素同框。禁止大头照/纯人脸特写。构图方式：左右冷暖分割/中心放射/纵深引导/阶级对比\n"
        "2. 【冲突元素外化】每个冲突必须有具体视觉符号：道具动作（甩婚帖/撕合照/递黑卡）、人物姿态（跪雨中/举杯冷笑）、符号（裂痕光效/半透明漂浮元素）\n"
        "3. 【背景100%虚化】背景必须是极度虚化，bokeh光斑，不能有任何清晰具体场景。场景只能通过服装和道具暗示\n"
        "4. 【右下角safe zone】右下角必须留白，关键人脸和核心文字不能放右下角\n"
        "5. 【标题白色艺术字】标题2-4个白色汉字，手写体或衬线体，深色投影/阴影。禁止：黄底黑字大字报、红圈箭头、超过5个字\n"
        "6. 【FULL标签】左上角半透明胶囊标签写着'FULL EPISODES'或'全集'\n"
        "7. 【禁止元素】红圈/箭头、孕检单/离婚协议等文档道具、具体清晰场景背景、黄底黑字大字报\n"
        "8. 【冲突融合】融合3-4个冲突到同一张画面，每个冲突有独立视觉元素，用构图手法组织\n"
        "9. 16:9横版比例\n\n"
        "【English ChatGPT/DALL-E Prompt Must Include】\n"
        "- English description with detailed composition and conflict elements\n"
        "- HEX color values and photography terms (chiaroscuro, Rembrandt tri-lighting, feathered edges)\n"
        "- Art terms: shattered glass collage, transparency layers, light bleed, cinematic depth of field\n"
        "- 'background completely blurred, bokeh light spots, no distinct buildings or scenery'\n"
        "- 'bottom center reserved for title area, dark gradient base, white art text with drop shadow'\n"
        "- 'right-bottom safe zone blank, no faces or text'\n"
        "- 'top-left semi-transparent capsule badge reading FULL EPISODES'\n"
        "- East Asian features, realistic natural appearance, not doll-like\n"
        "- Specific clothing colors and materials (black haute couture suit / white lace wedding dress / gray prison uniform etc.)\n"
        "- 16:9 landscape aspect ratio\n\n"
        "【Output Format】JSON only:\n"
        "{\n"
        '  "candidates": [\n'
        '    {\n'
        '      "brief": "Chinese visual description (300-500 chars, describing composition/conflict elements/characters/costumes/lighting)",\n'
        '      "prompt": "English ChatGPT/DALL-E prompt (detailed English description with HEX colors, photography terms, art terms, bokeh/safe zone/title zone/FULL EPISODES badge, 16:9 landscape, East Asian features)",\n'
        '      "text_overlay": "Cover title (2-4 white Chinese characters)",\n'
        '      "conflicts_fused": ["conflict1", "conflict2", "conflict3"],\n'
        '      "composition": "Composition technique used",\n'
        '      "genre_note": "Genre subcategory"\n'
        '    },\n'
        '    ...\n'
        '  ]\n'
        "}"
    )
    return prompt


def _fallback_covers(title: str, analysis: dict, region: str) -> list[dict]:
    """fallback：基于72张真实爆款数据的模板生成（2026-04-24更新）"""
    genre = analysis.get("genre", "總裁")
    hooks = analysis.get("hooks_and_twists", ["身份反轉"])
    props = analysis.get("key_props", ["合同"])
    scenes = analysis.get("key_scenes", ["豪宅"])
    chars = analysis.get("characters", ["男主", "女主"])

    # 道具替换：文档类→服装反差类（已被72张数据验证）
    prop_remap = {"合同": "suit", "文件": "evening dress", "孕检单": "prison uniform", "离婚协议": "wedding dress", "戒指": "gold ring"}
    safe_prop = prop_remap.get(props[0], props[0]) if props else "suit"

    candidates = [
        {
            "brief": f"左右冷暖分割构图：左侧{chars[0]}冷酷侧脸占画面60%（黑色高定西装，冷蓝侧光），右侧{chars[1]}泪眼微仰（白色蕾丝晚礼服，暖橙逆光），两人几乎接吻。背景极度虚化，金色bokeh光斑，没有任何清晰建筑。底部居中预留标题区，深色渐变打底，白色艺术字带投影。右下角safe zone空白，不放人脸和文字。左上角半透明胶囊标签写着FULL EPISODES。16:9横版。",
            "prompt": f"16:9 landscape aspect ratio, left-right cold-warm split composition. Left side 60% of frame: {chars[0]} cold intense side-profile close-up, black haute couture suit, cold blue side-light from left, sharp jawline and fierce eyes. Right side: {chars[1]} teary upward gaze, white lace evening gown, warm orange backlight from right-rear, hair glowing with rim light. Their faces are extremely close, almost kissing. Background completely blurred with swirling golden bokeh, no distinct buildings or scenery. Bottom center reserved for title area, dark gradient base, white art text with drop shadow. Right-bottom safe zone blank, no faces or text. Top-left semi-transparent capsule badge reading FULL EPISODES. Cinematic lighting, high-contrast cold-warm split, professional poster quality. East Asian features, realistic natural appearance. Chiaroscuro, Rembrandt tri-lighting.",
            "text_overlay": hooks[0][:4] if hooks and len(hooks[0]) <= 4 else "刺情",
            "conflicts_fused": ["身份反差", "情感撕裂", "复仇觉醒"],
            "composition": "左右冷暖分割",
            "genre_note": "女频" if genre in ["甜寵", "虐戀", "總裁", "豪門"] else "通用",
        },
        {
            "brief": f"中心放射构图：{chars[1]}面部特写占画面65%，眼神坚定带泪痕，穿着左半身灰色囚服右半身金色亮片晚礼服。背景极度虚化，金色光斑环绕。底部居中标题区白色艺术字。左上角FULL EPISODES标签。右下角safe zone。",
            "prompt": f"16:9 landscape aspect ratio, center radiating composition. Center of frame: {chars[1]} close-up face occupying 65% of frame, determined eyes with tear tracks, refined makeup. Left half of body wearing rough gray prison uniform, right half wearing gold sequin haute couture evening gown — extreme costume contrast. Background completely blurred with swirling golden bokeh, no distinct scenery. Bottom center reserved for title area, dark gradient base, white art text with drop shadow. Right-bottom safe zone blank. Top-left semi-transparent capsule badge reading FULL EPISODES. Dramatic overhead lighting, strong chiaroscuro on face, identity contrast visual impact. East Asian features, realistic natural appearance. Rembrandt tri-lighting, cinematic depth of field.",
            "text_overlay": "逆襲" if "復仇" in genre or "重生" in genre else "歸來",
            "conflicts_fused": ["身份反转", "阶级跨越", "真相揭露"],
            "composition": "中心放射",
            "genre_note": "女频" if genre in ["甜寵", "虐戀", "總裁", "豪門", "重生"] else "通用",
        },
        {
            "brief": f"纵深引导构图：前景{chars[0]}冷酷背影（黑色西装占画面左侧30%），中景{chars[1]}无辜回眸（白色婚纱占画面中央40%），远景虚化金色光斑暗示豪门氛围。无具体场景建筑。底部居中白色标题。左上角FULL EPISODES。右下角safe zone。",
            "prompt": f"16:9 landscape aspect ratio, depth guidance composition. Foreground left 30%: {chars[0]} cold back silhouette, black haute couture suit, broad shoulders. Midground center 40%: {chars[1]} innocent backward glance, white lace wedding dress, translucent veil, tearful eyes. Background: extreme blurred golden bokeh suggesting luxury gala atmosphere, no distinct buildings or scenery. Bottom center reserved for title area, dark gradient base, white art text with drop shadow. Right-bottom safe zone blank. Top-left semi-transparent capsule badge reading FULL EPISODES. Extremely shallow depth of field, cold-warm contrast, sense of fated separation. East Asian features, realistic natural appearance. Cinematic depth of field, Rembrandt lighting.",
            "text_overlay": "決裂",
            "conflicts_fused": ["情感决裂", "身份错位", "命运逆转"],
            "composition": "纵深引导",
            "genre_note": "女频" if genre in ["甜寵", "虐戀", "總裁"] else "通用",
        },
    ]
    return candidates


def run_from_manifest(manifest_path: str) -> Path:
    manifest = _load_json(Path(manifest_path), {})
    task_name = manifest.get("task_name", "unknown")
    region = manifest.get("target_region", "hk")
    preset = manifest.get("preset", "full_rebuild")
    prompt_mode = _resolve_prompt_mode(manifest, preset)

    # 读取标题文件
    title_path = BASE_DIR / "output" / "titles" / f"{task_name}_{region}.json"
    analysis_path = BASE_DIR / "data" / "drama_analysis" / f"{task_name}.json"

    title_data = _load_json(title_path, {"candidates": []})
    analysis = _load_json(analysis_path, {})

    # 取评分最高的标题
    titles = title_data.get("candidates", [])
    if not titles:
        print(f"❌ 没找到标题: {title_path}")
        # 返回一个空结果文件而不是目录
        empty_output = {
            "task_name": task_name, "region": region,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "candidates": [], "provider": "none",
        }
        out_path = BASE_DIR / "output" / "covers" / f"{task_name}_{region}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(empty_output, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_path
    best_title = titles[0]["title"]
    genre = analysis.get("genre", "現代都市")

    print(f"🎨 生成封面: {task_name} | 地区: {region} | 标题: {best_title[:30]}...")

    # 1. 用豆包生成封面（中文理解更好，适合画面描述）
    candidates = _generate_with_doubao(best_title, analysis, region)
    if not candidates:
        print("⚠️ 豆包生成失败，fallback 到 nuwa...")
        prompt = _build_nuwa_prompt(best_title, analysis, region, preset, prompt_mode)
        raw_response = nuwa_chat(prompt, max_tokens=4000, temperature=0.7, rotate=True, json_mode=True)
        if raw_response:
            candidates = _parse_nuwa_response(raw_response)
        if not candidates:
            print("⚠️ nuwa 也失败，fallback 到模板")
            candidates = _fallback_covers(best_title, analysis, region)

    # 3. 规则检查 + 评分
    results = []
    rejected = []
    for c in candidates:
        failures = _check_cover_compliance(c, best_title, genre)
        reject_reasons = [f"{f['rule']}: {f['reason']}" for f in failures if f["level"] == "REJECT"]
        warn_reasons = [f"{f['rule']}: {f['reason']}" for f in failures if f["level"] == "WARN"]

        score = _score_cover(c, best_title, genre)

        if reject_reasons:
            rejected.append({
                "brief": c.get("brief", "")[:60],
                "rejected_by": reject_reasons,
                "score": score,
            })
            print(f"  ❌ REJECT: {c.get('brief', '')[:40]}... | {', '.join(reject_reasons)}")
        else:
            results.append({
                **c,
                "score": score,
                "warnings": warn_reasons,
            })
            status = "✅ PASS"
            if warn_reasons:
                status = f"⚠️ PASS(warn: {', '.join(warn_reasons)})"
            print(f"  {status}: {c.get('brief', '')[:50]}... | 总分{score['total']}")

    # 4. 排序输出
    results = sorted(results, key=lambda x: x["score"]["total"], reverse=True)

    output = {
        "manifest": manifest_path,
        "task_name": task_name,
        "region": region,
        "title_used": best_title,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "provider": "nuwa(DeepSeek/BankOfAI)",
        "candidates": results,
        "rejected": rejected,
        "input_files": {
            "titles": str(title_path),
            "analysis": str(analysis_path),
        },
    }

    out_path = BASE_DIR / "output" / "covers" / f"{task_name}_{region}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n📁 输出: {out_path}")
    print(f"   通过: {len(results)} | 拒绝: {len(rejected)}")
    return out_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True, help="manifest JSON 路径")
    args = p.parse_args()
    run_from_manifest(args.manifest)


if __name__ == "__main__":
    main()
