#!/usr/bin/env python3
"""
distill_operations_director.py — 将结构化素材蒸馏为运营总监脑

输入：data/materials_structured/*.json （多剧素材）
输出：
  distill/outputs/operations-director_v0.md    人类可读运营手册
  distill/outputs/operations-director/rules.json   机器规则
  distill/outputs/operations-director/evidence.json 证据/高频词统计
  references/operations-director/SKILL.md     技能调用说明
  references/operations-director/META.md      元信息
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE / "scripts"))
from nuwa_api import nuwa_chat

def load_all_materials() -> list[dict]:
    mat_dir = BASE / "data" / "materials_structured"
    files = list(mat_dir.glob("*.json"))
    all_mats = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        all_mats.append(data)
    return all_mats

def extract_patterns(materials: list[dict]) -> dict:
    """统计高频元素（用于 evidence.json）"""
    # 标题公式模式（正则）
    title_formulas = []
    for m in materials:
        for t in m.get("domestic_title", []):
            # 提取模式：如 "重生+地点+事件+结果"
            pass

    # 道具/场景词频
    all_props = []
    all_scenes = []
    all_conflicts = []
    all_emotions = []
    for m in materials:
        all_props.extend([p["name"] for p in m.get("key_props", [])])
        all_scenes.extend([s["name"] for s in m.get("key_scenes", [])])
        all_conflicts.extend([c["type"] for c in m.get("main_conflict", [])])
        all_emotions.append(m.get("emotion", ""))

    evidence = {
        "top_props": Counter(all_props).most_common(20),
        "top_scenes": Counter(all_scenes).most_common(20),
        "top_conflicts": Counter(all_conflicts).most_common(20),
        "emotion_distribution": Counter(all_emotions),
        "genre_distribution": Counter(m.get("target_audience", "") for m in materials),
    }
    return evidence

def distill_into_operational_director(materials: list[dict], evidence: dict) -> dict:
    """用 Nuwa 将多剧素材蒸馏为运营总监脑（rules + 知识）"""

    # 构造统计摘要
    summary_lines = []
    summary_lines.append(f"素材剧集数量: {len(materials)}")
    summary_lines.append(f"题材分布: {dict(evidence['genre_distribution'])}")
    summary_lines.append(f"高频冲突: {evidence['top_conflicts'][:8]}")
    summary_lines.append(f"高频道具: {evidence['top_props'][:8]}")
    summary_lines.append(f"高频场景: {evidence['top_scenes'][:8]}")
    summary_lines.append(f"情绪分布: {dict(evidence['emotion_distribution'])}")

    # 抽几条代表性的标题、冲突、反转
    sample_titles = []
    sample_conflicts = []
    sample_reversals = []
    for m in materials[:3]:  # 取前3剧为代表
        sample_titles.extend(m["domestic_title"][:2])
        sample_conflicts.extend([c["type"] for c in m["main_conflict"][:3]])
        sample_reversals.extend(m["reversal_point"][:2])

    summary_lines.append("\n【代表性投放标题】")
    for t in sample_titles[:6]:
        summary_lines.append(f"- {t}")
    summary_lines.append("\n【核心冲突类型】")
    for c in sample_conflicts[:8]:
        summary_lines.append(f"- {c}")
    summary_lines.append("\n【高频反转点】")
    for r in sample_reversals[:6]:
        summary_lines.append(f"- {r}")

    summary_text = "\n".join(summary_lines)

    prompt = f"""你是一位资深短剧出海运营总监。请基于以下国内投放素材统计摘要，输出一套完整的 operations-director 规则体系。

【素材统计摘要】
{summary_text}

【任务】输出两份内容：
1. human-readable 运营手册（Markdown）
2. machine-readable 规则集（JSON Schema）

要求如下：

---
### 1. 标题公式（3-5条）
每条包含：
- formula_name: 公式名（如"重生+身份反转+地点+事件"）
- pattern: 正则模板或占位符（如"重生第{{age}}天，我{{action}}，才发现{{twist}}"）
- example: 真实标题案例
-适用题材: 总裁/甜宠/古装等
- 长度范围: 中文字数

### 2. 封面元素清单
- mandatory_elements: 必须出现的元素（人物特写/服装反差/关键道具）
- optional_elements: 可选的（场景/背景光斑）
- forbidden_elements: 禁止的（红圈/箭头/黄底黑字/文档特写）
- character_templates: 人物模板（女频：女主面部60%+，服装颜色+材质）
- prop_priority: 道具优先级（服装 > 道具 > 场景）

### 3. 冲突点映射表
映射题材 → 核心冲突 → 视觉元素 → 构图建议
例如：总裁 → 身份反转 → DNA报告/婚戒 → 左右分割

### 4. 反转点模式
提取3-5个高频反转句式模板（如"重生第X天，我{{action}}，才发现{{truth}}"）

### 5. 道具场景映射
题材 → 必备道具（3-5个）+ 必备场景（2-3个）

### 6. 禁止误用点
基于常见违规：纯英文标题、标题过长/过短、无题材词、封面面部<60%、背景清晰等

---
### 输出格式 — 先输出 Markdown，再输出 JSON（不要markdown围栏）

## operations-director_v0.md
（此处写markdown，分章节，用表格/列表清晰呈现）

---JSON SEPARATOR---

{{
  "version": "v0",
  "generated_at": "2026-04-26T...",
  "title_formulas": [
    {{"formula_name":"...", "pattern":"...", "example":"...", "genres":["..."], "length_range":[30,60]}}
  ],
  "cover_elements": {{
    "mandatory": [...],
    "optional": [...],
    "forbidden": [...],
    "character_templates": {{"女频": "...", "男频": "..."}},
    "prop_priority": ["服装反差", "身份道具", "场景"]
  }},
  "conflict_mapping": [
    {{"genre":"总裁", "conflict":"身份反转", "visual":"婚戒/DNA报告", "composition":"左右冷暖分割"}}
  ],
  "reversal_patterns": ["..."],
  "prop_scene_mapping": {{"总裁": {{"props":["西装","合同","婚戒"], "scenes":["宴会厅","办公室"]}}}},
  "forbidden_misuse": ["纯英文标题", "标题<30字或>60字", "封面面部<60%", "背景清晰不虚化"]
}}
"""

    resp = nuwa_chat(prompt, max_tokens=5000, rotate=False, json_mode=False)
    return resp

def parse_and_save(resp: str, materials_count: int, materials: list):
    """分离 Markdown 和 JSON，分别保存"""
    import re

    # 初始化
    md_part = resp
    json_part = "{}"

    # 找分隔符或最后一个 JSON block
    sep = "---JSON SEPARATOR---"
    if sep in resp:
        md_part, json_part = resp.split(sep, 1)
    else:
        m = re.search(r'(\{.*\})\s*$', resp, re.DOTALL)
        if m:
            json_part = m.group(1)
            md_part = resp[:m.start()].strip()

    # 清理 JSON：去掉 markdown 围栏
    json_part = json_part.strip()
    json_part = re.sub(r'^```json\s*', '', json_part, flags=re.IGNORECASE)
    json_part = re.sub(r'\s*```$', '', json_part)

    out_base = BASE / "distill" / "outputs" / "operations-director"
    out_base.mkdir(parents=True, exist_ok=True)

    # 1. 保存 Markdown
    md_path = BASE / "distill" / "outputs" / "operations-director_v0.md"
    md_path.write_text(md_part.strip(), encoding="utf-8")
    print(f"✅ Markdown 已保存: {md_path}")

    # 2. 解析并保存 JSON
    try:
        data = json.loads(json_part)
        data["_meta"] = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "source_materials_count": materials_count,
        }
        rules_path = out_base / "rules.json"
        rules_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ rules.json 已保存: {rules_path}")

        # 3. 生成 evidence.json（基于传入的 materials）
        from collections import Counter
        evidence = {
            "_meta": {"note": "高频统计，用于佐证规则来源"},
            "top_props": [{"name":k,"count":v} for k,v in Counter([p['name'] for m in materials for p in m.get('key_props',[])]).most_common(30)],
            "top_scenes": [{"name":k,"count":v} for k,v in Counter([s['name'] for m in materials for s in m.get('key_scenes',[])]).most_common(30)],
            "top_conflicts": [{"type":k,"count":v} for k,v in Counter([c['type'] for m in materials for c in m.get('main_conflict',[])]).most_common(30)],
            "genre_dist": [{"genre":k,"count":v} for k,v in Counter([m.get('target_audience','') for m in materials]).most_common(10)],
            "emotion_dist": [{"emotion":k,"count":v} for k,v in Counter([m.get('emotion','') for m in materials]).most_common(10)],
        }
        evidence_path = out_base / "evidence.json"
        evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"✅ evidence.json 已保存: {evidence_path}")

    except Exception as e:
        print(f"⚠️ JSON解析失败: {e}")
        print(f"JSON部分前300字: {json_part[:300]}")
        (out_base / "rules_raw.txt").write_text(json_part, encoding="utf-8")
        print(f"⚠️ 原始JSON已保存: {out_base/'rules_raw.txt'}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--drama", help="仅蒸馏单个剧（可选，默认所有剧）")
    args = parser.parse_args()

    materials = load_all_materials()
    if args.drama:
        materials = [m for m in materials if m.get("drama_name") == args.drama]
    if not materials:
        print("❌ 未找到素材")
        return

    evidence = extract_patterns(materials)
    resp = distill_into_operational_director(materials, evidence)
    parse_and_save(resp, len(materials), materials)

if __name__ == "__main__":
    main()