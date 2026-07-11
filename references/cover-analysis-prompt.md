# 封面分析统一提示词 v1.0

> **单一母本**：cover_analysis_own.py（诊断）和 daily_pipeline.py（蒸馏）共用此文件。
> 改提示词只改此文件，代码是投影。版本号见文件头。

## 替代关系

- 替代 `cover_analysis_own.py` 中硬编码的 7 维打分 prompt
- 替代 `daily_pipeline.py` L1399 中硬编码的 11 字段 + 结构化 prompt
- 替代 `batch_cover_analysis.py` 中硬编码的 11 字段 prompt

## 变更纪律

1. 改 prompt 只改此文件
2. 代码从 `references/cover-analysis-prompt.md` 读取（`__file__` 相对路径）
3. 新 prompt 先跑 10 张验证（5 爆款 + 5 差封面），验证通过后代码自动生效
4. 旧数据不删不覆盖，新旧字段聚合时分开处理

## 附：验证记录

（待首次验证后填写）

---

## Prompt 正文

```
分析这张YouTube短剧封面图片。

标题：{title}
播放量：{views}

返回严格JSON，包含三大部分。

## 第一部分：结构化字段（枚举值，机器可读）

"结构化": {
  "person_count": <整数，画面中可辨认的人物数量>,
  "scene_type": "<枚举：豪宅/办公室/街道/室内温馨/法庭宴会厅医院/废墟末世/古装宫廷/校园/纯人物无场景/其他>",
  "composition": "<枚举：center/contrast/rule_of_thirds/collage/symmetry>",
  "shot_scale": "<枚举：close_up_close/half_body/full_body_with_scene/wide_narrative>",
  "color_type": "<枚举：warm/cold/high_contrast/mixed/low_saturation>",
  "emotion": "<枚举：romance/tension/anger/surprise/mystery/power/cute/other>",
  "has_text": <true或false>,
  "text_content": "<封面文字原文，无文字则空字符串>",
  "text_position": "<枚举：top_left/top_right/bottom/center/none>",
  "identity_visible": <true或false，是否可见身份阶级符号>,
  "symbols": ["<视觉符号1>", "<最多5个，按显著度排序，≤4字>"]
}

## 第二部分：复现prompt（用于生成相似封面）

"复现prompt": "<80-120词英文text-to-image prompt，按四层结构写：1)前景道具 2)主体人物(数量/表情/服装/姿态) 3)背景场景(环境/色调/光影) 4)右上留文字区。要求照此prompt生图能复现原封面的构图与氛围。不要写'大脸特写'，封面是场景叙事而非面部特写。>"

## 第三部分：中文描述字段

"人物": "数量、表情、服装差异、肢体语言、关系暗示（2-3句）",
"道具": "关键道具及其象征意义（2-3句）",
"色彩": "主色调、辅助色、饱和度、光影效果、情绪氛围（2-3句）",
"构图": "布局类型、景别、视角高低、视线引导路径（2-3句）",
"文字": "文字数量、内容、位置、字体风格、颜色、是否增强悬念（2-3句）",
"视觉层级": "第一眼看什么、第二眼看什么、第三眼看什么（2-3句）",
"题材元素": "该题材独有的视觉符号（2-3句）",
"封面标题配合": "封面情绪与标题钩子是否一致、互补、增强悬念（2-3句）",
"地区适配": "最适合哪个地区市场及原因（2-3句）",
"整体风格": "风格+情绪基调+目标受众（2-3句）"

## 第四部分：诊断评分

"构图评分": {"score": <0-10>, "analysis": "2-3句"},
"人物评分": {"score": <0-10>, "analysis": "2-3句"},
"色彩评分": {"score": <0-10>, "analysis": "2-3句"},
"情绪评分": {"score": <0-10>, "analysis": "2-3句"},
"视觉符号评分": {"score": <0-10>, "analysis": "2-3句"},
"文字评分": {"score": <0-10>, "analysis": "2-3句"},
"封面标题协同评分": {"score": <0-10>, "analysis": "2-3句"},
"总分": <0-10的均值>,
"总评": "一句话总评",
"改进建议": ["建议1", "建议2"]

## 第五部分：钩子归类

"hook_type": "<枚举：identity/emotion/relationship/reversal/compensation/time/system/other，与7张模板卡对齐>"
```
