#!/usr/bin/env python3
"""
第二层蒸馏 v2：从7个 distill.json 提炼统一 SKILL.md
流式输出 + 分3次调用 + 强制覆盖7语言

用法：
  python3 scripts/distill_skill_v2.py
  python3 scripts/distill_skill_v2.py --test   # 只蒸馏英文测试
  python3 scripts/distill_skill_v2.py --step 1 # 只跑第1步
"""

import json
import os
import sys
import time
import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "distill" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# API 配置
API_BASE = os.environ.get("DISTILL_API_BASE", "https://api.zyloo.io/v1")
API_KEY = os.environ.get("ZYLOO_API_KEY", "")
MODEL = "zyloo/gpt-5.4"

LANGS = ["en", "es", "id", "jp", "pt", "tr", "繁中"]
LANG_NAMES = {
    "en": "英文", "es": "西语", "id": "印尼", "jp": "日语",
    "pt": "葡萄牙", "tr": "土耳其", "繁中": "繁中"
}


def load_all_distill(test_mode=False) -> dict:
    """加载所有语言的 distill.json"""
    data = {}
    langs = ["en"] if test_mode else LANGS
    for lang in langs:
        path = ROOT / "knowledge" / lang / "distill.json"
        if path.exists():
            d = json.loads(path.read_text())
            data[lang] = d
            print(f"  ✅ {LANG_NAMES[lang]}: {len(json.dumps(d)):,} chars")
        else:
            print(f"  ⚠️ {lang}: 文件不存在")
    return data


def call_gpt54_stream(prompt: str, max_tokens: int = 0, label: str = "") -> str:
    """流式调用 GPT-5.4 API（max_tokens=0 表示不限制）"""
    import urllib.request
    import json as json_mod

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": MODEL,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
    }
    if max_tokens > 0:
        payload["max_tokens"] = max_tokens
    data = json_mod.dumps(payload).encode()

    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=data,
        headers=headers,
        method="POST",
    )

    for attempt in range(3):
        try:
            full_content = ""
            token_count = 0
            start = time.time()

            with urllib.request.urlopen(req, timeout=600) as resp:
                for line in resp:
                    decoded = line.decode("utf-8").strip()
                    if not decoded.startswith("data: ") or decoded == "data: [DONE]":
                        continue
                    try:
                        chunk = json_mod.loads(decoded[6:])
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {}).get("content") or ""
                            if delta:
                                full_content += delta
                                token_count += 1
                                # 每50个chunk打印进度
                                if token_count % 50 == 0:
                                    elapsed = time.time() - start
                                    print(f"  ⏳ {label} {elapsed:.0f}s | {len(full_content):,} chars", flush=True)
                    except (json_mod.JSONDecodeError, IndexError):
                        pass

            elapsed = time.time() - start
            print(f"  ✅ {label} 完成 | {elapsed:.0f}s | {len(full_content):,} chars | ~{token_count} tokens")
            return full_content

        except Exception as e:
            print(f"  ⚠️ 尝试 {attempt+1}/3 失败: {e}")
            if attempt < 2:
                time.sleep(10 * (attempt + 1))
                # 重建 request
                req = urllib.request.Request(
                    f"{API_BASE}/chat/completions",
                    data=data,
                    headers=headers,
                    method="POST",
                )
            else:
                raise RuntimeError(f"GPT-5.4 API 调用失败: {e}")


def extract_json_from_response(text: str) -> dict:
    """从响应中提取 JSON，支持多种格式"""
    text = text.strip()

    # 1. 尝试直接解析
    try:
        return json.loads(text)
    except:
        pass

    # 2. 去掉 code block
    patterns = [
        r'```json\s*(.*?)\s*```',
        r'```\s*(.*?)\s*```',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1).strip())
            except:
                pass

    # 3. 找第一个 { 和最后一个 }
    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        try:
            return json.loads(text[first:last+1])
        except:
            pass

    # 4. 尝试修复常见 JSON 错误
    if first >= 0 and last > first:
        candidate = text[first:last+1]
        # 去掉尾部逗号
        candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
        # 修复单引号
        candidate = candidate.replace("'", '"')
        try:
            return json.loads(candidate)
        except:
            pass

    raise ValueError(f"无法从响应中提取 JSON（{len(text)} chars）")


# ═══════════════════════════════════════════════
#  第1步：why + what（原理 + 故事模板）
# ═══════════════════════════════════════════════

def build_step1_prompt(data: dict) -> str:
    """构建第1步 prompt：why + what（开放性）"""
    sections = []
    for lang, d in data.items():
        lang_name = LANG_NAMES.get(lang, lang)
        why = d.get("why", {})
        what = d.get("what", [])
        section = f"""
### {lang_name}（{lang}）

#### why.title（标题原则）
{json.dumps(why.get("title", []), ensure_ascii=False, indent=2)}

#### why.thumbnail（封面原则）
{json.dumps(why.get("thumbnail", []), ensure_ascii=False, indent=2)}

#### why.tags_and_distribution（标签原则）
{json.dumps(why.get("tags_and_distribution", []), ensure_ascii=False, indent=2)}

#### why.market_insights（市场洞察）
{json.dumps(why.get("market_insights", {}), ensure_ascii=False, indent=2)}

#### what（故事模板）
{json.dumps(what, ensure_ascii=False, indent=2)}
"""
        sections.append(section)

    all_sections = "\n".join(sections)

    return f"""你是一个短剧YouTube数据分析专家。你手里有7个语言市场的竞品蒸馏数据。

## 任务

从这7个语言的数据中，提炼出「为什么观众会点击」的深层原理和「什么故事模板最有效」。

## 思考方式

1. 先逐个语言扫描数据，标记每个语言的核心规律
2. 跨语言对比：哪些规律是普遍存在的？哪些是某语言独有的？
3. 深挖心理机制：不要停留在"身份反转有效"这种表面结论，要解释**为什么**人的心理会被这种模式捕获
4. 每个原则必须附带具体可执行的操作指南

## 输出要求

直接输出 JSON，不要有前言、总结、客套话，不要包裹在 code block 中。

关键要求：
- title_principles 至少 8 条，每条必须有 psychology（心理机制）和 application（具体怎么写标题）
- thumbnail_principles 至少 5 条
- tag_principles 至少 4 条
- market_insights.by_language 必须覆盖全部7个语言（en, es, id, jp, pt, tr, 繁中），每个语言至少写 3 个维度
- what 故事模板至少 6 种，每种必须有 2 个以上跨语言示例

JSON 结构：
{{
  "why": {{
    "title_principles": [{{"principle": "...", "psychology": "深层心理机制", "application": "具体操作指南", "languages_found": ["lang"], "source_count": N}}],
    "thumbnail_principles": [{{"principle": "...", "psychology": "...", "application": "...", "languages_found": ["lang"]}}],
    "tag_principles": [{{"principle": "...", "psychology": "...", "application": "...", "languages_found": ["lang"]}}],
    "market_insights": {{"universal": "...", "by_language": {{"语言": {{"gender_bias": "...", "emerging_trends": "...", "content_quality_signals": "..."}}}}}}
  }},
  "what": [{{"name": "...", "template": "...", "why_it_works": "...", "sub_genre": "...", "languages_found": ["lang"], "examples": [{{"lang": "...", "title": "..."}}]}}]
}}

## 7语言蒸馏数据

{all_sections}
"""


# ═══════════════════════════════════════════════
#  第2步：骨架 + 钩子 + 包装模式（核心规则）
# ═══════════════════════════════════════════════

def build_step2_prompt(data: dict) -> str:
    """构建第2步 prompt：骨架 + 钩子 + 包装模式（开放性）"""
    sections = []
    for lang, d in data.items():
        lang_name = LANG_NAMES.get(lang, lang)
        how = d.get("how", {})
        section = f"""
### {lang_name}（{lang}）

#### title_skeletons（标题骨架）
{json.dumps(how.get("title_skeletons", []), ensure_ascii=False, indent=2)}

#### hook_combination（钩子组合）
{json.dumps(how.get("hook_combination", {}), ensure_ascii=False, indent=2)}

#### title_constraints（标题约束）
{json.dumps(how.get("title_constraints", {}), ensure_ascii=False, indent=2)}

#### emoji_strategy（emoji策略）
{json.dumps(how.get("emoji_strategy", {}), ensure_ascii=False, indent=2)}

#### rhetorical_patterns（修辞模式）
{json.dumps(how.get("rhetorical_patterns", {}), ensure_ascii=False, indent=2)}
"""
        sections.append(section)

    all_sections = "\n".join(sections)

    return f"""你是一个短剧YouTube数据分析专家。你手里有7个语言市场的标题骨架、钩子组合、约束条件、修辞模式原始数据。

## 任务

从7个语言的数据中，提炼出短剧标题的「骨架公式」「钩子体系」「包装模式」。

## 思考方式

1. **骨架**：扫描所有语言的 title_skeletons，找出叙事结构相似的合并。每个骨架的核心是**叙事弧线**（不是句式模板）。比如"低位受辱→身份曝光→打脸"是一个骨架，不管用什么语言表达。
2. **钩子**：从 hook_combination 和 rhetorical_patterns 中，自己发现钩子类别。不要预设分类，从数据中归纳。每个钩子子类型必须有 2-3 个不同语言的真实标题示例。
3. **包装**：句式、标点、emoji、递进手法——每个维度都要标注「通用规则」和「语言专属规则」。

## 输出要求

直接输出 JSON，不要有前言、总结、客套话，不要包裹在 code block 中。

关键要求：
- skeletons 至少 10 种，每种必须有 3 个以上跨语言示例、rules（改编规则+反例）
- hooks.types 至少 5 个大类，每个大类至少 2 个子类型，每个子类型必须有 examples（真实标题）和 languages_found
- hooks.emergent_hooks 记录你在数据中发现的新兴钩子模式
- packaging.sentence_structures 至少 5 种句式，每种标注 avg_views 和 languages_found
- packaging.constraints 覆盖全部 7 语言的 avg_length、key_words、top_emojis

JSON 结构：
{{
  "skeletons": [
    {{
      "name": "骨架名称",
      "narrative_pattern": "叙事弧线描述",
      "psychological_hook": "为什么这个叙事弧线有效",
      "sub_genre": "适用题材",
      "avg_views_range": "播放范围",
      "languages_found": ["lang"],
      "examples": [{{"lang": "...", "title": "..."}}],
      "rules": ["改编规则", "反例"]
    }}
  ],
  "hooks": {{
    "types": {{
      "大类名": {{
        "definition": "定义",
        "subtypes": [
          {{
            "name": "子类型名",
            "definition": "定义",
            "examples": ["真实标题示例1", "真实标题示例2"],
            "languages_found": ["lang"]
          }}
        ]
      }}
    }},
    "emergent_hooks": [{{"name": "...", "definition": "...", "languages_found": ["lang"], "examples": ["..."]}}],
    "combination_rules": {{"strongest_pairs": ["..."], "ineffective": ["..."], "rules": ["..."]}},
    "hook_stats_by_language": {{"lang": {{"hook_type": "数量"}}}}
  }},
  "packaging": {{
    "sentence_structures": [{{"name": "...", "pattern": "...", "when_to_use": "...", "avg_views": "...", "languages_found": ["lang"]}}],
    "punctuation_strategy": {{"universal": "...", "by_language": {{"lang": "..."}}}},
    "emoji_strategy": {{"best_position": "...", "rules": ["..."]}},
    "progression_techniques": [{{"name": "...", "pattern": "...", "example": "..."}}],
    "constraints": {{"avg_length_by_lang": {{"lang": N}}, "key_words_by_lang": {{"lang": ["..."]}}, "top_emojis_by_lang": {{"lang": ["..."]}}}}
  }}
}}

## 7语言蒸馏数据

{all_sections}
"""


# ═══════════════════════════════════════════════
#  第3步：封面协同 + 标签 + 描述 + 发布 + 增长 + 反模式
# ═══════════════════════════════════════════════

def build_step3_prompt(data: dict) -> str:
    """构建第3步 prompt：封面协同 + 其他模块（开放性）"""
    sections = []
    for lang, d in data.items():
        lang_name = LANG_NAMES.get(lang, lang)
        how = d.get("how", {})
        section = f"""
### {lang_name}（{lang}）

#### cover_title_synergy（封面×标题协同）
{json.dumps(how.get("cover_title_synergy", {}), ensure_ascii=False, indent=2)}

#### thumbnail_guidelines（封面指南）
{json.dumps(how.get("thumbnail_guidelines", {}), ensure_ascii=False, indent=2)}

#### hashtag_strategy（标签策略）
{json.dumps(how.get("hashtag_strategy", {}), ensure_ascii=False, indent=2)}

#### description_template（描述模板）
{json.dumps(how.get("description_template", {}), ensure_ascii=False, indent=2)}

#### publish_time（发布时间）
{json.dumps(how.get("publish_time", {}), ensure_ascii=False, indent=2)}

#### growth_strategy（增长策略）
{json.dumps(how.get("growth_strategy", []), ensure_ascii=False, indent=2)}
"""
        sections.append(section)

    all_sections = "\n".join(sections)

    return f"""你是一个短剧YouTube数据分析专家。你手里有7个语言市场的封面协同、标签策略、描述模板、发布时间、增长策略原始数据。

## 任务

从7个语言的数据中，提炼出「封面×标题协同」「标签策略」「发布时间」「增长策略」的核心规则，以及「反模式」和「诚实边界」。

## 思考方式

1. **封面协同**：核心问题是「标题说了A，封面应该展示什么？」。从数据中归纳出 hook_type → cover_pattern 的映射关系，每种映射给 1 个具体例子。by_language 要写每个语言的特殊封面习惯。
2. **标签**：不是堆关键词，而是「什么标签组合能带来曝光」。分通用标签和语言专属标签。
3. **反模式**：从数据中找到「什么做法会降低播放」，按标题/封面/标签分类。
4. **诚实边界**：哪些结论有数据支撑，哪些是推测，哪些语言数据不足。

## 输出要求

直接输出 JSON，不要有前言、总结、客套话，不要包裹在 code block 中。

关键要求：
- cover_synergy.hook_cover_mapping 至少 7 种钩子类型的映射，每种必须有 title_pattern + cover_pattern + example
- cover_synergy.by_language 覆盖全部 7 语言，每种写 3+ 条 special_patterns 和 2+ 条 special_antipatterns（不要截断）
- cover_guide 6 个维度（composition/figures/colors/emotion/visual_symbols/text）都要有实质内容
- tags.by_language 覆盖全部 7 语言
- antipatterns 按 title/cover/tags 分类，每类至少 4 条
- boundaries 诚实列出每个语言的样本量和局限

JSON 结构：
{{
  "cover_synergy": {{
    "rule": "核心原则（2-3句话）",
    "hook_cover_mapping": [
      {{"hook_type": "...", "title_pattern": "...", "cover_pattern": "...", "example": "..."}}
    ],
    "patterns": [{{"name": "...", "description": "...", "example": "..."}}],
    "anti_patterns": [{{"name": "...", "description": "..."}}],
    "female_vs_male": {{"female": "...", "male": "..."}},
    "by_language": {{"lang": {{"special_patterns": ["..."], "special_antipatterns": ["..."]}}}}
  }},
  "cover_guide": {{"composition": "...", "figures": "...", "colors": "...", "emotion": "...", "visual_symbols": "...", "text": "..."}},
  "tags": {{"universal_rules": ["..."], "title_tags": ["..."], "description_tags": ["..."], "combination_pattern": "...", "by_language": {{"lang": {{"title_tags": ["..."], "description_tags": ["..."]}}}}}},
  "description": {{"structure": "...", "template_types": [{{"name": "...", "pattern": "...", "when_to_use": "..."}}], "rules": ["..."]}},
  "publish_time": {{"best_hours_utc": [...], "best_weekdays": ["..."], "rules": ["..."], "by_language": {{"lang": {{"best_hours": [...], "best_weekdays": ["..."]}}}}}},
  "growth_strategies": {{"universal": ["..."], "by_language": {{"lang": ["..."]}}}},
  "antipatterns": {{"title": ["..."], "cover": ["..."], "tags": ["..."]}},
  "boundaries": {{"data_sources": "...", "sample_sizes": {{"lang": "..."}}, "limitations": ["..."]}}
}}

## 7语言蒸馏数据

{all_sections}
"""


# ═══════════════════════════════════════════════
#  合并 + 生成 SKILL.md
# ═══════════════════════════════════════════════

def merge_results(step1: dict, step2: dict, step3: dict) -> dict:
    """合并3步结果"""
    return {
        "skill_header": {
            "name": "short-drama-youtube",
            "version": "3.0.0",
            "description": "短剧YouTube运营专家 — 从7个语言、322个频道、3000+视频蒸馏的跨语言通用规则。触发词：生成标题/封面/标签/上架方案/诊断/优化"
        },
        "module_1_skeletons": step2.get("skeletons", []),
        "module_2_hooks": step2.get("hooks", {}),
        "module_3_packaging": step2.get("packaging", {}),
        "module_4_cover_synergy": step3.get("cover_synergy", {}),
        "module_5_cover_guide": step3.get("cover_guide", {}),
        "module_6_tags": step3.get("tags", {}),
        "module_7_publish_time": step3.get("publish_time", {}),
        "module_8_description": step3.get("description", {}),
        "module_9_growth": step3.get("growth_strategies", {}),
        "module_10_antipatterns": step3.get("antipatterns", {}),
        "module_11_boundaries": step3.get("boundaries", {}),
        "why": step1.get("why", {}),
        "what": step1.get("what", []),
    }


def format_skill_md(data: dict) -> str:
    """将合并结果格式化为 SKILL.md"""
    header = data.get("skill_header", {})
    lines = [
        "---",
        f"name: {header.get('name', 'short-drama-youtube')}",
        f"version: {header.get('version', '3.0.0')}",
        f"description: |",
        f"  {header.get('description', '')}",
        "---",
        "",
        f"# {header.get('name', 'short-drama-youtube')} v{header.get('version', '3.0.0')}",
        "",
        "> 从7个语言、322个频道、3000+视频中蒸馏的跨语言通用规则",
        "",
    ]

    # 模块1：骨架公式
    skeletons = data.get("module_1_skeletons", [])
    lines.append("## 模块1: 骨架公式\n")
    lines.append(f"跨语言验证的标题叙事原型（{len(skeletons)}种）\n")
    for i, s in enumerate(skeletons, 1):
        if isinstance(s, dict):
            lines.append(f"### {i}. {s.get('name', '')}\n")
            lines.append(f"**叙事结构**：{s.get('narrative_pattern', '')}")
            lines.append(f"**心理机制**：{s.get('psychological_hook', '')}")
            lines.append(f"**适用题材**：{s.get('sub_genre', '')}")
            langs = s.get("languages_found", [])
            lines.append(f"**跨语言验证**：{', '.join(langs)}（{len(langs)}个语言）")
            lines.append(f"**播放范围**：{s.get('avg_views_range', '')}")
            examples = s.get("examples", [])
            if examples:
                lines.append("\n**示例**：")
                for ex in examples[:3]:
                    if isinstance(ex, dict):
                        lines.append(f"- [{ex.get('lang', '')}] {ex.get('title', '')}")
                    else:
                        lines.append(f"- {ex}")
            rules = s.get("rules", [])
            if rules:
                lines.append("\n**规则**：")
                for r in rules:
                    lines.append(f"- {r}")
            lines.append("")

    # 模块2：钩子体系
    hooks = data.get("module_2_hooks", {})
    lines.append("\n## 模块2: 钩子体系\n")
    lines.append(f"{hooks.get('description', '跨语言验证的钩子类型体系')}\n")
    for hook_name, hook_data in hooks.get("types", {}).items():
        if isinstance(hook_data, dict):
            lines.append(f"### {hook_name}")
            lines.append(f"\n{hook_data.get('definition', '')}\n")
            for st in hook_data.get("subtypes", []):
                if isinstance(st, dict):
                    lines.append(f"- **{st.get('name', '')}**：{st.get('definition', '')}")
                    for ex in st.get("examples", []):
                        lines.append(f"  - {ex}")
    emergent = hooks.get("emergent_hooks", [])
    if emergent:
        lines.append("\n### 新发现钩子\n")
        for eh in emergent:
            if isinstance(eh, dict):
                lines.append(f"- **{eh.get('name', '')}**：{eh.get('definition', '')}（{', '.join(eh.get('languages_found', []))}）")
    cr = hooks.get("combination_rules", {})
    if cr:
        lines.append("\n### 钩子组合规则\n")
        lines.append(f"**最强配对**：{', '.join(cr.get('strongest_pairs', []))}")
        lines.append(f"**低效组合**：{', '.join(cr.get('ineffective', []))}")
        lines.append("\n**规则**：")
        for r in cr.get("rules", []):
            lines.append(f"- {r}")
    lines.append("")

    # 模块3：包装模式
    pkg = data.get("module_3_packaging", {})
    lines.append("\n## 模块3: 包装模式\n")
    ss = pkg.get("sentence_structures", [])
    if ss:
        lines.append("### 句式模板\n")
        for s in ss:
            if isinstance(s, dict):
                lines.append(f"- **{s.get('name', '')}**：`{s.get('pattern', '')}`")
                lines.append(f"  场景：{s.get('when_to_use', '')} | 播放：{s.get('avg_views', '')} | {', '.join(s.get('languages_found', []))}")
    ps = pkg.get("punctuation_strategy", {})
    if ps:
        lines.append("\n### 标点策略\n")
        lines.append(f"**通用**：{ps.get('universal', '')}")
        for lang, rule in ps.get("by_language", {}).items():
            lines.append(f"**{lang}**：{rule}")
    es = pkg.get("emoji_strategy", {})
    if es:
        lines.append("\n### Emoji策略\n")
        lines.append(f"**最佳位置**：{es.get('best_position', '')}")
        for r in es.get("rules", []):
            lines.append(f"- {r}")
    pt_list = pkg.get("progression_techniques", [])
    if pt_list:
        lines.append("\n### 叙事递进\n")
        for pt in pt_list:
            if isinstance(pt, dict):
                lines.append(f"- **{pt.get('name', '')}**：{pt.get('pattern', '')}")
    constraints = pkg.get("constraints", {})
    if constraints:
        lines.append("\n### 约束条件\n")
        avg_len = constraints.get("avg_length_by_lang", {})
        if avg_len:
            lines.append(f"**标题平均长度**：{json.dumps(avg_len, ensure_ascii=False)}")
        kw = constraints.get("key_words_by_lang", {})
        if kw:
            lines.append("\n**高频关键词**：")
            for lang, words in kw.items():
                lines.append(f"- {lang}: {', '.join(words[:8])}")
    lines.append("")

    # 模块4-11（简化格式化）
    simple_modules = [
        ("module_4_cover_synergy", "封面×标题协同规则"),
        ("module_5_cover_guide", "封面指南"),
        ("module_6_tags", "标签策略"),
        ("module_7_publish_time", "发布时间策略"),
        ("module_8_description", "描述模板"),
        ("module_9_growth", "增长策略"),
        ("module_10_antipatterns", "反模式黑名单"),
        ("module_11_boundaries", "诚实边界"),
    ]
    for key, default_title in simple_modules:
        mod = data.get(key, {})
        if not mod:
            continue
        title = mod.get("title", default_title) if isinstance(mod.get("title"), str) else default_title
        lines.append(f"\n## {title}\n")
        for k, v in mod.items():
            if k == "title":
                continue
            if isinstance(v, str):
                lines.append(f"**{k}**：{v}\n")
            elif isinstance(v, list):
                lines.append(f"**{k}**：")
                for item in v:
                    if isinstance(item, dict):
                        name = item.get("name", item.get("hook_type", ""))
                        desc = item.get("description", item.get("pattern", item.get("title_pattern", "")))
                        if name and desc:
                            lines.append(f"- **{name}**：{desc}")
                            # 输出额外字段
                            for extra_key in ["cover_pattern", "example", "definition"]:
                                extra_val = item.get(extra_key, "")
                                if extra_val:
                                    lines.append(f"  {extra_key}：{extra_val}")
                        elif name:
                            lines.append(f"- **{name}**")
                            for ik, iv in item.items():
                                if ik not in ("name", "hook_type") and iv:
                                    lines.append(f"  {ik}：{iv}")
                        else:
                            lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
                    else:
                        lines.append(f"- {item}")
                lines.append("")
            elif isinstance(v, dict):
                lines.append(f"**{k}**：")
                for dk, dv in v.items():
                    if isinstance(dv, str):
                        lines.append(f"- {dk}: {dv}")
                    elif isinstance(dv, list):
                        lines.append(f"- {dk}: {', '.join(str(x) for x in dv[:8])}")
                    elif isinstance(dv, dict):
                        lines.append(f"- {dk}: {json.dumps(dv, ensure_ascii=False)[:200]}")
                lines.append("")

    # why（原理）
    why = data.get("why", {})
    if why:
        lines.append("\n## 原理（Why）\n")
        for principle_type in ["title_principles", "thumbnail_principles", "tag_principles"]:
            principles = why.get(principle_type, [])
            if principles:
                lines.append(f"### {principle_type.replace('_principles', '')}\n")
                for p in principles:
                    if isinstance(p, dict):
                        lines.append(f"- **{p.get('principle', '')}**")
                        lines.append(f"  心理：{p.get('psychology', '')}")
                        lines.append(f"  应用：{p.get('application', '')}")
                        langs = p.get("languages_found", [])
                        if langs:
                            lines.append(f"  验证：{', '.join(langs)}")
        lines.append("")

    # what（故事模板）
    what = data.get("what", [])
    if what:
        lines.append("\n## 故事模板（What）\n")
        for w in what:
            if isinstance(w, dict):
                lines.append(f"### {w.get('name', '')}\n")
                lines.append(f"**模板**：{w.get('template', '')}")
                lines.append(f"**为什么有效**：{w.get('why_it_works', '')}")
                lines.append(f"**适用题材**：{w.get('sub_genre', '')}")
                langs = w.get("languages_found", [])
                if langs:
                    lines.append(f"**验证**：{', '.join(langs)}")
                examples = w.get("examples", [])
                if examples:
                    lines.append("\n**示例**：")
                    for ex in examples[:3]:
                        if isinstance(ex, dict):
                            lines.append(f"- [{ex.get('lang', '')}] {ex.get('title', '')}")
                        else:
                            lines.append(f"- {ex}")
                lines.append("")

    return "\n".join(lines)


# ═══════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="第二层蒸馏 v2：distill.json → SKILL.md")
    parser.add_argument("--test", action="store_true", help="测试模式（只蒸馏英文）")
    parser.add_argument("--step", type=int, choices=[1, 2, 3], help="只运行指定步骤")
    parser.add_argument("--max-tokens", type=int, default=0, help="每步最大输出token（0=不限制）")
    parser.add_argument("--model", type=str, default="", help="覆盖模型名（如 zyloo/gpt-5.4 或 mimo）")
    parser.add_argument("--api-base", type=str, default="", help="覆盖 API base URL")
    parser.add_argument("--api-key", type=str, default="", help="覆盖 API key")
    parser.add_argument("--output-tag", type=str, default="", help="输出目录后缀（如 gpt54/mimo）")
    args = parser.parse_args()

    global MODEL, API_BASE, API_KEY, OUTPUT_DIR
    if args.model:
        MODEL = args.model
    if args.api_base:
        API_BASE = args.api_base
    if args.api_key:
        API_KEY = args.api_key
    if args.output_tag:
        OUTPUT_DIR = ROOT / "distill" / f"outputs_{args.output_tag}"
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("🔬 第二层蒸馏 v2：distill.json → SKILL.md（流式 + 分步）")
    print("=" * 60)

    # 1. 加载数据
    print("\n📂 加载蒸馏数据...")
    data = load_all_distill(test_mode=args.test)
    if not data:
        print("❌ 无数据可蒸馏")
        return

    results = {}

    # Step 1: why + what
    if not args.step or args.step == 1:
        print("\n" + "=" * 60)
        print("📝 Step 1/3: why（原理）+ what（故事模板）")
        print("=" * 60)
        prompt1 = build_step1_prompt(data)
        print(f"  📊 Prompt: {len(prompt1):,} chars (~{len(prompt1)//4:,} tokens)")
        raw1 = call_gpt54_stream(prompt1, max_tokens=args.max_tokens, label="Step1")
        (OUTPUT_DIR / "step1_raw.txt").write_text(raw1)
        try:
            results["step1"] = extract_json_from_response(raw1)
            (OUTPUT_DIR / "step1.json").write_text(json.dumps(results["step1"], ensure_ascii=False, indent=2))
            print(f"  ✅ Step1 JSON 解析成功")
        except ValueError as e:
            print(f"  ❌ Step1 JSON 解析失败: {e}")
            results["step1"] = {"why": {}, "what": []}

    # Step 2: 骨架 + 钩子 + 包装
    if not args.step or args.step == 2:
        print("\n" + "=" * 60)
        print("📝 Step 2/3: 骨架 + 钩子 + 包装模式")
        print("=" * 60)
        prompt2 = build_step2_prompt(data)
        print(f"  📊 Prompt: {len(prompt2):,} chars (~{len(prompt2)//4:,} tokens)")
        raw2 = call_gpt54_stream(prompt2, max_tokens=args.max_tokens, label="Step2")
        (OUTPUT_DIR / "step2_raw.txt").write_text(raw2)
        try:
            results["step2"] = extract_json_from_response(raw2)
            (OUTPUT_DIR / "step2.json").write_text(json.dumps(results["step2"], ensure_ascii=False, indent=2))
            print(f"  ✅ Step2 JSON 解析成功")
        except ValueError as e:
            print(f"  ❌ Step2 JSON 解析失败: {e}")
            results["step2"] = {"skeletons": [], "hooks": {}, "packaging": {}}

    # Step 3: 封面 + 标签 + 描述 + 发布 + 增长 + 反模式
    if not args.step or args.step == 3:
        print("\n" + "=" * 60)
        print("📝 Step 3/3: 封面协同 + 标签 + 描述 + 发布 + 增长 + 反模式")
        print("=" * 60)
        prompt3 = build_step3_prompt(data)
        print(f"  📊 Prompt: {len(prompt3):,} chars (~{len(prompt3)//4:,} tokens)")
        raw3 = call_gpt54_stream(prompt3, max_tokens=args.max_tokens, label="Step3")
        (OUTPUT_DIR / "step3_raw.txt").write_text(raw3)
        try:
            results["step3"] = extract_json_from_response(raw3)
            (OUTPUT_DIR / "step3.json").write_text(json.dumps(results["step3"], ensure_ascii=False, indent=2))
            print(f"  ✅ Step3 JSON 解析成功")
        except ValueError as e:
            print(f"  ❌ Step3 JSON 解析失败: {e}")
            results["step3"] = {}

    # 合并结果
    if len(results) == 3:
        print("\n" + "=" * 60)
        print("📄 合并结果 + 生成 SKILL.md")
        print("=" * 60)
        merged = merge_results(
            results.get("step1", {}),
            results.get("step2", {}),
            results.get("step3", {}),
        )
        (OUTPUT_DIR / "skill_consolidated_v2.json").write_text(
            json.dumps(merged, ensure_ascii=False, indent=2)
        )

        skill_md = format_skill_md(merged)
        md_file = OUTPUT_DIR / "SKILL_v3.md"
        md_file.write_text(skill_md)
        print(f"  💾 SKILL.md → {md_file}")
        print(f"  📊 {len(skill_md):,} chars, {len(skill_md.splitlines())} lines")

    print("\n✅ 蒸馏完成！")


if __name__ == "__main__":
    main()
