# 封面分析提示词 v2.0

> **单一母本**，两个场景各用一段。改提示词只改此文件，代码是投影。

## 两套prompt的分工

| 场景 | 用哪段 | 用途 |
|------|--------|------|
| 竞品蒸馏 | `## 蒸馏prompt` | 从竞品封面提取结构化数据+描述，喂给统计分析 |
| 自有诊断 | `## 诊断prompt` | 给自己封面打分找问题 |

**共用核心**：结构化枚举字段（scene_type/composition/color_type等），机器可读、可统计。

**已删除**：
- hook_type — 标题分析已覆盖，封面不重复
- 复现prompt — 太长LLM不遵循，精简为"symbols"字段提取关键视觉符号
- 诊断评分 — 只在自有诊断场景用，蒸馏不需要

## 变更纪律

1. 改 prompt 只改此文件
2. 代码从 `references/cover-analysis-prompt.md` 读取
3. 旧数据不删不覆盖

---

## 蒸馏prompt

```
分析这张YouTube短剧封面图片。

标题：{title}
播放量：{views}

返回严格JSON，两个部分。

## 第一部分：结构化字段

"结构化": {
  "person_count": <整数>,
  "scene_type": "<豪宅/办公室/街道/室内温馨/法庭宴会厅/废墟末世/古装宫廷/校园/纯人物无场景/其他>",
  "composition": "<center/contrast/rule_of_thirds/collage/symmetry>",
  "shot_scale": "<close_up/half_body/full_body/wide>",
  "color_type": "<warm/cold/high_contrast/mixed/low_saturation>",
  "emotion": "<romance/tension/anger/surprise/mystery/power/cute/other>",
  "has_text": <true或false>,
  "text_content": "<封面文字原文，无则空>",
  "text_position": "<top_left/top_right/bottom/center/none>",
  "identity_visible": <true或false>,
  "symbols": ["<≤4字视觉符号，最多5个>"]
}

## 第二部分：中文描述

"人物": "数量、表情、服装、肢体语言、关系暗示",
"道具": "关键道具及象征意义",
"色彩": "主色调、辅助色、光影、情绪氛围",
"构图": "布局、景别、视角、视线引导",
"文字": "文字内容、位置、风格、是否增强悬念",
"视觉层级": "第一眼/第二眼/第三眼看什么",
"题材元素": "该题材独有的视觉符号",
"封面标题配合": "封面与标题是否围绕同一钩子分工",
"地区适配": "最适合哪个市场及原因",
"整体风格": "风格+情绪基调+目标受众"

每个字段2-3句话，总输出控制在500字以内。
```

---

## 诊断prompt

```
分析这张YouTube短剧封面图片，给出诊断评分。

标题：{title}
播放量：{views}

返回严格JSON。

## 结构化字段

"结构化": {
  "person_count": <整数>,
  "scene_type": "<豪宅/办公室/街道/室内温馨/法庭宴会厅/废墟末世/古装宫廷/校园/纯人物无场景/其他>",
  "composition": "<center/contrast/rule_of_thirds/collage/symmetry>",
  "shot_scale": "<close_up/half_body/full_body/wide>",
  "color_type": "<warm/cold/high_contrast/mixed/low_saturation>",
  "emotion": "<romance/tension/anger/surprise/mystery/power/cute/other>",
  "has_text": <true或false>,
  "text_content": "<封面文字原文，无则空>",
  "text_position": "<top_left/top_right/bottom/center/none>",
  "identity_visible": <true或false>,
  "symbols": ["<≤4字视觉符号，最多5个>"]
}

## 7维评分

"构图": {"score": <0-10>, "analysis": "2-3句"},
"人物": {"score": <0-10>, "analysis": "2-3句"},
"色彩": {"score": <0-10>, "analysis": "2-3句"},
"情绪": {"score": <0-10>, "analysis": "2-3句"},
"视觉符号": {"score": <0-10>, "analysis": "2-3句"},
"文字": {"score": <0-10>, "analysis": "2-3句"},
"封面×标题协同": {"score": <0-10>, "analysis": "2-3句"},
"总分": <0-10均值>,
"总评": "一句话",
"改进建议": ["建议1", "建议2"]
```
