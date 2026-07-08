#!/usr/bin/env python3
"""
第二层蒸馏：从7个 distill.json 提炼统一 SKILL.md

输入：knowledge/{lang}/distill.json × 7
输出：distill/outputs/skill_consolidated.json → 写入 SKILL.md

用法：
  python3 scripts/distill_skill.py
  python3 scripts/distill_skill.py --test   # 只蒸馏1个语言测试
"""

import json
import sys
import time
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "distill" / "outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# API 配置
API_BASE = "https://api.zyloo.io/v1"
API_KEY = "sk-zy-afcffd57c5e32f06fc5ca62a4d03d02757e61396b76f3ade"
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
            print(f"  ✅ {LANG_NAMES[lang]}: {len(json.dumps(d))} chars")
        else:
            print(f"  ⚠️ {lang}: 文件不存在")
    return data


def compress_for_prompt(data: dict) -> dict:
    """压缩数据，保留关键信息，控制 prompt 长度"""
    compressed = {}
    for lang, d in data.items():
        c = {
            "lang": LANG_NAMES.get(lang, lang),
            "why": d.get("why", {}),
            "what": d.get("what", []),
            "how": {
                "title_skeletons": d.get("how", {}).get("title_skeletons", []),
                "hook_combination": {
                    "核心发现": d.get("how", {}).get("hook_combination", {}).get("核心发现", ""),
                    "最强配对": d.get("how", {}).get("hook_combination", {}).get("最强配对", []),
                    "低效组合": d.get("how", {}).get("hook_combination", {}).get("低效组合", []),
                    "规则": d.get("how", {}).get("hook_combination", {}).get("规则", []),
                    "hook_types": {
                        k: {"definition": v.get("definition", "")}
                        for k, v in d.get("how", {}).get("hook_combination", {}).get("hook_types", {}).items()
                    },
                    "emergent_hooks": d.get("how", {}).get("hook_combination", {}).get("emergent_hooks", []),
                    "hook_stats": d.get("how", {}).get("hook_combination", {}).get("hook_stats", {}),
                },
                "title_constraints": d.get("how", {}).get("title_constraints", {}),
                "emoji_strategy": d.get("how", {}).get("emoji_strategy", {}),
                "hashtag_strategy": {
                    "title_tags": d.get("how", {}).get("hashtag_strategy", {}).get("title_tags", []),
                    "description_tags": d.get("how", {}).get("hashtag_strategy", {}).get("description_tags", []),
                    "combination_pattern": d.get("how", {}).get("hashtag_strategy", {}).get("combination_pattern", ""),
                    "rules": d.get("how", {}).get("hashtag_strategy", {}).get("rules", []),
                },
                "description_template": d.get("how", {}).get("description_template", {}),
                "thumbnail_guidelines": d.get("how", {}).get("thumbnail_guidelines", {}),
                "cover_title_synergy": {
                    "rule": d.get("how", {}).get("cover_title_synergy", {}).get("rule", ""),
                    "hook_cover_mapping": d.get("how", {}).get("cover_title_synergy", {}).get("hook_cover_mapping", []),
                    "patterns": d.get("how", {}).get("cover_title_synergy", {}).get("patterns", []),
                    "anti_patterns": d.get("how", {}).get("cover_title_synergy", {}).get("anti_patterns", []),
                    "female_freq": d.get("how", {}).get("cover_title_synergy", {}).get("female_freq", ""),
                    "male_freq": d.get("how", {}).get("cover_title_synergy", {}).get("male_freq", ""),
                },
                "publish_time": d.get("how", {}).get("publish_time", {}),
                "growth_strategy": d.get("how", {}).get("growth_strategy", []),
                "rhetorical_patterns": d.get("how", {}).get("rhetorical_patterns", {}),
            },
            "boundaries": d.get("boundaries", {}),
            "stats": d.get("stats", {}),
        }
        compressed[lang] = c
    return compressed


def call_gpt54(prompt: str, max_tokens: int = 16384) -> str:
    """调用 GPT-5.4 API"""
    import urllib.request
    import urllib.error

    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }
    data = json.dumps({
        "model": MODEL,
        "max_tokens": max_tokens,
        "stream": False,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()

    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=data,
        headers=headers,
        method="POST",
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                result = json.loads(resp.read())
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                print(f"  📊 tokens: {usage.get('prompt_tokens', '?')} in / {usage.get('completion_tokens', '?')} out")
                return content
        except Exception as e:
            print(f"  ⚠️ 尝试 {attempt+1}/3 失败: {e}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise RuntimeError(f"GPT-5.4 API 调用失败: {e}")


def build_prompt(compressed_data: dict) -> str:
    """构建蒸馏 prompt"""
    data_json = json.dumps(compressed_data, ensure_ascii=False, indent=1)

    return f"""你是短剧YouTube运营专家。以下是从7个语言市场（英文/西语/印尼/日语/葡萄牙/土耳其/繁中）蒸馏的完整数据。

你的任务：将7个语言的数据合并成一个统一的 SKILL.md，遵循女娲Skill的结构。

## 核心原则

1. **成语思维**：每个规则都是压缩的智慧——既有明确的结构，又保留开放性让AI发挥
2. **跨语言验证**：只收录在至少2个语言中出现的规则（三重验证：跨域复现+有生成力+有排他性）
3. **给渔不给鱼**：教思维方式和工具，不是堆数据
4. **骨架可复用，血肉必须创新**：规则是骨架，具体标题是血肉

## 输出结构（12个模块）

直接输出一个 JSON 对象，包含以下字段：

```json
{{
  "skill_header": {{
    "name": "short-drama-youtube",
    "description": "Skill描述（含触发词）",
    "version": "3.0.0"
  }},

  "module_1_skeletons": {{
    "title": "骨架公式",
    "description": "跨语言验证的标题叙事原型",
    "skeletons": [
      {{
        "name": "骨架名称",
        "narrative_pattern": "叙事结构描述",
        "psychological_hook": "心理机制",
        "sub_genre": "适用题材",
        "avg_views_range": "跨语言平均播放范围",
        "languages_found": ["出现在哪些语言"],
        "examples": ["跨语言示例1", "示例2"],
        "rules": ["改编规则", "反例"],
        "verification": "三重验证说明"
      }}
    ]
  }},

  "module_2_hooks": {{
    "title": "钩子体系",
    "description": "钩子大类+子类型+组合规则",
    "hook_types": {{
      "大类名": {{
        "definition": "定义",
        "subtypes": [
          {{"name": "子类型名", "definition": "定义", "examples": ["示例"]}}
        ]
      }}
    }},
    "emergent_hooks": [
      {{"name": "名称", "definition": "定义", "languages": ["出现语言"]}}
    ],
    "combination_rules": {{
      "strongest_pairs": ["配对1", "配对2"],
      "ineffective": ["低效组合"],
      "rules": ["规则"]
    }}
  }},

  "module_3_packaging": {{
    "title": "包装模式",
    "description": "句式/标点/emoji/递进/长度约束",
    "sentence_structures": [
      {{
        "name": "句式名",
        "pattern": "模板",
        "when_to_use": "适用场景",
        "avg_views": "跨语言平均播放",
        "languages": ["出现语言"]
      }}
    ],
    "punctuation_strategy": {{
      "universal": "通用标点规则",
      "language_specific": {{
        "语言": "特殊标点规则"
      }}
    }},
    "emoji_strategy": {{
      "best_position": "最佳位置",
      "rules": ["规则"]
    }},
    "progression_techniques": [
      {{"name": "递进手法", "pattern": "模板", "example": "示例"}}
    ],
    "constraints": {{
      "avg_length_by_lang": {{"en": 97, "es": 87}},
      "key_words_by_lang": {{"en": ["CEO", "Billionaire"]}},
      "top_emojis_by_lang": {{"en": ["🔥", "💕"]}}
    }}
  }},

  "module_4_cover_synergy": {{
    "title": "封面×标题协同规则",
    "rule": "核心原则",
    "hook_cover_mapping": [
      {{
        "hook_type": "钩子类型",
        "title_pattern": "标题模式",
        "cover_pattern": "封面模式",
        "example": "示例"
      }}
    ],
    "patterns": [{{"name": "模式名", "description": "描述"}}],
    "anti_patterns": [{{"name": "反模式", "description": "描述"}}],
    "female_vs_male": {{
      "female": "女频策略",
      "male": "男频策略"
    }}
  }},

  "module_5_cover_guide": {{
    "title": "封面指南",
    "composition": "构图建议",
    "figures": "人物建议",
    "colors": "配色建议",
    "emotion": "情绪基调",
    "visual_symbols": "视觉符号",
    "text": "文字建议"
  }},

  "module_6_tags": {{
    "title": "标签策略",
    "universal_rules": ["通用规则"],
    "title_tags": ["标题标签"],
    "description_tags": ["描述标签"],
    "combination_pattern": "组合规律",
    "language_specific": {{
      "语言": ["特殊标签"]
    }}
  }},

  "module_7_publish_time": {{
    "title": "发布时间策略",
    "best_hours_utc": [10, 12, 15, 16],
    "best_weekdays": ["Thursday", "Friday"],
    "rules": ["规则"]
  }},

  "module_8_description": {{
    "title": "描述模板",
    "structure": "描述结构规律",
    "template_types": [
      {{"name": "模板名", "pattern": "模式", "when_to_use": "适用场景"}}
    ],
    "rules": ["规则"]
  }},

  "module_9_growth": {{
    "title": "增长策略",
    "strategies": ["策略1", "策略2"]
  }},

  "module_10_market": {{
    "title": "市场洞察",
    "by_language": {{
      "语言": {{
        "gender_bias": "性别偏好",
        "emerging_trends": "新兴趋势",
        "content_quality_signals": "质量信号"
      }}
    }}
  }},

  "module_11_antipatterns": {{
    "title": "反模式黑名单",
    "title_antipatterns": ["标题反模式"],
    "cover_antipatterns": ["封面反模式"],
    "tag_antipatterns": ["标签反模式"]
  }},

  "module_12_boundaries": {{
    "title": "诚实边界",
    "data_sources": "数据来源说明",
    "limitations": ["局限"],
    "sample_sizes": {{"语言": "样本量"}}
  }}
}}
```

## 7语言蒸馏数据

{data_json}

## 要求

1. 骨架公式：从7语言的 title_skeletons 合并同类项，保留跨语言通用的+语言独有的（标注）
2. 钩子体系：合并 hook_types，细分 subtypes（如 emotion→愤怒/心疼/甜蜜/震惊），用跨语言数据验证
3. 包装模式：从 rhetorical_patterns 合并，保留通用句式+语言专属句式
4. 封面协同：从 cover_title_synergy 合并，保留通用模式+语言特殊模式
5. 标签/描述/发布时间/增长策略：合并7语言，标注通用vs专属
6. 市场洞察：按语言分别保留
7. 反模式：合并所有 anti_patterns
8. 诚实边界：汇总 boundaries

直接输出 JSON，不要有任何前言、总结、客套话，不要包裹在 code block 中。"""


def extract_json(text: str) -> dict:
    """从响应中提取 JSON"""
    # 尝试直接解析
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def format_skill_md(data: dict) -> str:
    """将蒸馏结果格式化为 SKILL.md"""
    header = data.get("skill_header", {})
    lines = [
        "---",
        f"name: {header.get('name', 'short-drama-youtube')}",
        f"version: {header.get('version', '3.0.0')}",
        f"description: {header.get('description', '')}",
        "---",
        "",
        f"# {header.get('name', 'short-drama-youtube')} v{header.get('version', '3.0.0')}",
        "",
    ]

    # 模块1：骨架公式
    m1 = data.get("module_1_skeletons", {})
    lines.append(f"## {m1.get('title', '骨架公式')}")
    lines.append(f"\n{m1.get('description', '')}\n")
    for i, s in enumerate(m1.get("skeletons", []), 1):
        lines.append(f"### {i}. {s.get('name', '')}")
        lines.append(f"\n**叙事结构**：{s.get('narrative_pattern', '')}")
        lines.append(f"**心理机制**：{s.get('psychological_hook', '')}")
        lines.append(f"**适用题材**：{s.get('sub_genre', '')}")
        langs = s.get("languages_found", [])
        lines.append(f"**跨语言验证**：{', '.join(langs)}（{len(langs)}个语言）")
        lines.append(f"\n**示例**：")
        for ex in s.get("examples", []):
            lines.append(f"- {ex}")
        lines.append(f"\n**规则**：")
        for r in s.get("rules", []):
            lines.append(f"- {r}")
        lines.append("")

    # 模块2：钩子体系
    m2 = data.get("module_2_hooks", {})
    lines.append(f"\n## {m2.get('title', '钩子体系')}")
    lines.append(f"\n{m2.get('description', '')}\n")
    for hook_name, hook_data in m2.get("hook_types", {}).items():
        lines.append(f"### {hook_name}")
        lines.append(f"\n{hook_data.get('definition', '')}\n")
        for st in hook_data.get("subtypes", []):
            lines.append(f"- **{st.get('name', '')}**：{st.get('definition', '')}")
            for ex in st.get("examples", []):
                lines.append(f"  - {ex}")
    if m2.get("emergent_hooks"):
        lines.append("\n### 新发现钩子")
        for eh in m2["emergent_hooks"]:
            lines.append(f"- **{eh.get('name', '')}**：{eh.get('definition', '')}（{', '.join(eh.get('languages', []))}）")
    cr = m2.get("combination_rules", {})
    if cr:
        lines.append("\n### 钩子组合规则")
        lines.append(f"\n**最强配对**：{', '.join(cr.get('strongest_pairs', []))}")
        lines.append(f"**低效组合**：{', '.join(cr.get('ineffective', []))}")
        lines.append("\n**规则**：")
        for r in cr.get("rules", []):
            lines.append(f"- {r}")
    lines.append("")

    # 模块3-12（简化输出）
    modules = [
        ("module_3_packaging", "包装模式"),
        ("module_4_cover_synergy", "封面×标题协同规则"),
        ("module_5_cover_guide", "封面指南"),
        ("module_6_tags", "标签策略"),
        ("module_7_publish_time", "发布时间策略"),
        ("module_8_description", "描述模板"),
        ("module_9_growth", "增长策略"),
        ("module_10_market", "市场洞察"),
        ("module_11_antipatterns", "反模式黑名单"),
        ("module_12_boundaries", "诚实边界"),
    ]
    for key, default_title in modules:
        mod = data.get(key, {})
        title = mod.get("title", default_title)
        lines.append(f"\n## {title}")
        # 把整个模块内容格式化为 markdown
        content = json.dumps(mod, ensure_ascii=False, indent=2)
        # 简单格式化：把 key-value 转成 markdown
        for k, v in mod.items():
            if k == "title":
                continue
            if isinstance(v, str):
                lines.append(f"\n**{k}**：{v}")
            elif isinstance(v, list):
                lines.append(f"\n**{k}**：")
                for item in v:
                    if isinstance(item, dict):
                        lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
                    else:
                        lines.append(f"- {item}")
            elif isinstance(v, dict):
                lines.append(f"\n**{k}**：")
                for dk, dv in v.items():
                    if isinstance(dv, str):
                        lines.append(f"  - {dk}: {dv}")
                    elif isinstance(dv, list):
                        lines.append(f"  - {dk}: {', '.join(str(x) for x in dv[:5])}")
                    else:
                        lines.append(f"  - {dk}: {dv}")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="第二层蒸馏：distill.json → SKILL.md")
    parser.add_argument("--test", action="store_true", help="测试模式（只蒸馏英文）")
    parser.add_argument("--max-tokens", type=int, default=16384, help="最大输出token")
    args = parser.parse_args()

    print("=" * 60)
    print("🔬 第二层蒸馏：distill.json → SKILL.md")
    print("=" * 60)

    # 1. 加载数据
    print("\n📂 加载蒸馏数据...")
    data = load_all_distill(test_mode=args.test)
    if not data:
        print("❌ 无数据可蒸馏")
        return

    # 2. 压缩数据
    print("\n📦 压缩数据...")
    compressed = compress_for_prompt(data)
    prompt = build_prompt(compressed)
    prompt_size = len(prompt)
    print(f"  📊 Prompt 长度: {prompt_size:,} chars ({prompt_size // 4:,} tokens approx)")

    # 3. 调用 GPT-5.4
    print(f"\n🧠 调用 {MODEL}...")
    start = time.time()
    result = call_gpt54(prompt, max_tokens=args.max_tokens)
    elapsed = time.time() - start
    print(f"  ⏱️ 耗时: {elapsed:.0f}秒")

    # 4. 保存原始响应
    raw_file = OUTPUT_DIR / "skill_raw_response.txt"
    raw_file.write_text(result)
    print(f"  💾 原始响应 → {raw_file}")

    # 5. 解析 JSON
    print("\n📝 解析结果...")
    try:
        skill_data = extract_json(result)
        json_file = OUTPUT_DIR / "skill_consolidated.json"
        json_file.write_text(json.dumps(skill_data, ensure_ascii=False, indent=2))
        print(f"  💾 JSON → {json_file}")
    except json.JSONDecodeError as e:
        print(f"  ❌ JSON 解析失败: {e}")
        print(f"  💾 原始响应已保存到 {raw_file}，请手动检查")
        return

    # 6. 生成 SKILL.md
    print("\n📄 生成 SKILL.md...")
    skill_md = format_skill_md(skill_data)
    md_file = OUTPUT_DIR / "SKILL_v3.md"
    md_file.write_text(skill_md)
    print(f"  💾 SKILL.md → {md_file}")
    print(f"  📊 {len(skill_md):,} chars, {len(skill_md.splitlines())} lines")

    print("\n✅ 蒸馏完成！")


if __name__ == "__main__":
    main()
