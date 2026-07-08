#!/usr/bin/env python3
"""
material_structurer.py — 将豆包 raw_search 文本解析为结构化素材

输入：data/drama_analysis/{剧名}.json 中的 raw_search（2000+字）
输出：data/materials_structured/{剧名}.json

字段定义（12个）：
- drama_name
- source (doubao_web_search)
- source_url (暂空)
- domestic_title (国内投放标题Top3)
- cover_description (封面特点描述)
- opening_hook (爆款开场钩子×3)
- main_conflict (核心冲突×7，每项含类型/人物/激烈度/视觉元素/幕次)
- character_setup (人物设定×N)
- key_props (关键道具×5+)
- key_scenes (关键场景×5+)
- reversal_point (反转点×3+)
- emotion (情绪基调：虐心/爽感/悬疑)
- target_audience (目标受众：女频/男频/古装/家庭)
- usable_for_title (bool: 是否可用于标题生成)
- usable_for_cover (bool: 是否可用于封面)
- notes (备注：如“道具服装反差强，适合封面”)
"""

import argparse
import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent.parent

def _load_analysis(drama_name: str) -> dict:
    p = BASE / "data" / "drama_analysis" / f"{drama_name}.json"
    if not p.exists():
        raise FileNotFoundError(f"Analysis not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))

def _extract_section(text: str, header: str) -> str:
    """从 raw_search 提取指定章节内容"""
    # 支持 【剧情概述】 或 1. 【剧情概述】 等形式
    pattern = rf'(?:第[一二三四五六七八九十]幕|{re.escape(header)}|【{header}】)\s*(?:\n|：|:\\s*)'
    # 简化：找下一个章节起始
    start = text.find(header)
    if start == -1:
        return ""
    # 找下一章
    next_section = re.search(r'\n\s*【[^】]+】', text[start+len(header):])
    if next_section:
        end = start + len(header) + next_section.start()
        return text[start:end].strip()
    return text[start:].strip()

def structure_material(drama_name: str) -> dict:
    analysis = _load_analysis(drama_name)
    raw = analysis.get("raw_search", "")
    genre = analysis.get("genre", "")
    hooks = analysis.get("hooks_and_twists", [])
    props = analysis.get("key_props", [])
    scenes = analysis.get("key_scenes", [])
    chars = analysis.get("characters", [])

    # 1. 提取投放标题（从 "国内投放素材" 或 "热门标题" 段落）
    domestic_titles = []
    # 尝试匹配列表项 "- 标题" 或数字列表
    title_match = re.findall(r'[-•●]\s*([^\n]{10,60}?（[0-9]+）?)', raw)  # 简化
    if not title_match:
        # 从 "热门标题" 段落直接取行
        in_title_section = False
        for line in raw.splitlines():
            if any(kw in line for kw in ["热门标题", "投放标题", "爆款标题"]):
                in_title_section = True
                continue
            if in_title_section and line.strip() and not line.startswith("【") and len(line) < 80:
                domestic_titles.append(line.strip())
            if in_title_section and line.startswith("【"):
                in_title_section = False
        domestic_titles = domestic_titles[:15]
    else:
        domestic_titles = [t.strip() for t in title_match[:15]]

    # 2. 封面特点（从 "高点击率封面特点" 段落）
    cover_desc = ""
    if "封面特点" in raw or "高点击率" in raw:
        idx = raw.find("封面特点")
        if idx == -1: idx = raw.find("高点击率")
        if idx != -1:
            # 取到下一段
            end = raw.find("【", idx+1)
            cover_desc = raw[idx:end].strip() if end != -1 else raw[idx:].strip()[:500]

    # 3. 核心冲突（至少7个，含类型/人物/激烈度/视觉/幕次）
    main_conflicts = []
    # 期望格式：冲突类型、涉及人物、激烈程度(1-5)、视觉元素、幕次
    conflict_pattern = re.compile(
        r'冲突类型[：:]\s*(?P<type>[^，,]+)[，,\s]*'
        r'涉及人物[：:]\s*(?P<char>[^，,]+)[，,\s]*'
        r'激烈程度[：:]\s*(?P<intensity>[1-5])[，,\s]*'
        r'视觉元素[：:]\s*(?P<visual>[^，,]+)[，,\s]*'
        r'发生在[第幕]*(?P<act>[0-9一二三四五六七八九十]+)幕',
        re.IGNORECASE
    )
    for m in conflict_pattern.finditer(raw):
        main_conflicts.append({
            "type": m.group("type").strip(),
            "characters": m.group("char").strip(),
            "intensity": int(m.group("intensity")),
            "visual_elements": m.group("visual").strip(),
            "act": m.group("act").strip(),
        })
    # 如果正则没抓到，fallback 从 hooks_and_twists 列表映射
    if len(main_conflicts) < 7:
        intensity_map = {"身份反转": 5, "复仇": 5, "背叛": 4, "真相揭露": 5, "打脸": 4, "重生": 5}
        for h in hooks[:7]:
            main_conflicts.append({
                "type": h,
                "characters": "主角相关",
                "intensity": intensity_map.get(h, 4),
                "visual_elements": props[0] if props else "情绪特写",
                "act": "1-3",
            })

    # 4. 开场钩子（提取爆款开场钩子×3）
    opening_hooks = []
    hook_section = re.search(r'爆款开场钩子.*?：\s*(.*?)(?=\n\s*【|\Z)', raw, re.DOTALL)
    if hook_section:
        lines = hook_section.group(1).splitlines()
        for line in lines:
            line = line.strip().strip("-•●")
            if 10 < len(line) < 200:
                opening_hooks.append(line)
    if not opening_hooks and hooks:
        opening_hooks = [f"{h}剧情引爆" for h in hooks[:3]]

    # 5. 人物设定（提取角色外貌/服装/表情）
    character_setup = []
    for c in chars:
        # 简单从 raw 中搜索该角色的描述段落
        # 这里先简化：使用 analysis 中的 characters 列表 + 通用标签
        character_setup.append({
            "name": c,
            "description": f"{c}（需从素材中提取外貌/服装/表情）",
            "source": "analysis.characters",
        })

    # 6. 道具/场景（已有列表）
    key_props = [{"name": p, "usage": "服装反差/身份象征"} for p in props[:10]]
    key_scenes = [{"name": s, "act": "1-3"} for s in scenes[:10]]

    # 7. 反转点（提取×3+）
    reversals = []
    rev_section = re.search(r'(反转点|名场面|高潮).*?：\s*(.*?)(?=\n\s*【|\Z)', raw, re.DOTALL)
    if rev_section:
        for line in rev_section.group(2).splitlines():
            line = line.strip().strip("-•●")
            if line and 5 < len(line) < 150:
                reversals.append(line)
    if not reversals:
        reversals = [f"第{i}幕关键反转" for i in range(1,4)]

    # 8. 封面可用性判断（简单规则）
    usable_for_cover = bool(props and scenes and any(w in genre for w in ["总裁","甜宠","虐恋","古装","豪门","總裁","豪門"]))
    usable_for_title = bool(hooks and domestic_titles)

    # 目标受众：直接用 genre 映射（避免繁体匹配失败）
    genre_lower = genre.lower()
    if any(w in genre_lower for w in ["总裁", "總裁", "豪门", "豪門", "甜宠", "虐恋", "千金", "古装", "穿越", "重生"]):
        target_audience = "女频"
    elif any(w in genre_lower for w in ["战神", "赘婿", "神豪", "高手"]):
        target_audience = "男频"
    else:
        target_audience = "女频"  # 默认

    # 增强角色设定：从 raw_search 中提取外貌/服装/表情描述
    character_setup_enhanced = []
    for c in chars:
        cname = c.split("(")[0].strip()
        # 从 raw_search 提取角色描述（如“女主：外貌+服装+表情”）
        pat = rf'{re.escape(cname)}[：:（）(](.*?)(?:
\s*[【[]|$)'
        matches = re.findall(pat, raw, re.DOTALL)
        desc = matches[0].strip()[:80] if matches else f"{c}（需人工补全外貌/服装/表情）"
        character_setup_enhanced.append({
            "name": c,
            "description": desc,
            "source": "raw_search_extracted",
        })
）]'
        matches = re.findall(pattern, raw, re.DOTALL)
        desc = matches[0].strip()[:100] if matches else f"{c}（需人工补全外貌/服装/表情）"
        character_setup_enhanced.append({
            "name": c,
            "description": desc,
            "source": "raw_search_extracted",
        })

    structured = {
        "drama_name": drama_name,
        "source": "doubao_web_search",
        "source_url": "",  # TODO: 从 search 结果补全
        "domestic_title": domestic_titles,
        "cover_description": cover_desc[:500] if cover_desc else "",
        "opening_hook": opening_hooks[:3],
        "main_conflict": main_conflicts,
        "character_setup": character_setup_enhanced,
        "key_props": key_props,
        "key_scenes": key_scenes,
        "reversal_point": reversals[:5],
        "emotion": "虐心" if "虐" in genre else "爽感" if any(w in genre for w in ["逆袭","复仇","打脸"]) else "悬疑",
        "target_audience": target_audience,
        "usable_for_title": usable_for_title,
        "usable_for_cover": usable_for_cover,
        "notes": "道具服装反差强，适合封面视觉张力",
    }
    return structured

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drama", required=True, help="剧名")
    args = parser.parse_args()

    out_dir = BASE / "data" / "materials_structured"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{args.drama}.json"

    structured = structure_material(args.drama)
    out_path.write_text(json.dumps(structured, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ 结构化素材已保存: {out_path}")
    print(f"   标题可用: {structured['usable_for_title']} | 封面可用: {structured['usable_for_cover']}")
    print(f"   冲突数: {len(structured['main_conflict'])} | 道具数: {len(structured['key_props'])}")

if __name__ == "__main__":
    main()
