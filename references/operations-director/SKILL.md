---
name: operations-director
description: 短剧运营总监脑 — 将国内投放素材蒸馏为标题公式/封面规则/冲突映射
version: 0.1.0
---

# Operations-Director Skill

## 概述

**Operations-Director** 是短剧出海系统的**运营知识蒸馏层**。它的输入是豆包联网搜索得到的国内投放素材（`data/materials_structured/*.json`），输出是结构化的运营规则库，用于指导：

1. **标题生成**：5套标题公式 + 题材适配
2. **封面指令生成**：10要素封面方案（主体/冲突/道具/场景/构图/色彩/标题区/必须保留/可牺牲/禁止）
3. **质量门控**：禁止误用点清单

## 文件位置

```
distill/outputs/operations-director/
├── operations-director_v0.md      # 人类可读运营手册
├── rules.json                     # 机器规则集
└── evidence.json                  # 高频统计证据

references/operations-director/
├── SKILL.md                       # 本文档
└── META.md                        # 元信息（版本/依赖/更新）
```

## 核心产出

### rules.json 结构

```json
{
  "version": "v0",
  "generated_at": "2026-04-26T...",
  "title_formulas": [
    {
      "formula_name": "重生复仇+时间锚点",
      "pattern": "重生第{time}天，我{action}，才发现{truth}",
      "example": "重生回15岁那天，我直接挖了假死养父母的坟！",
      "genres": ["男频","总裁","重生"],
      "length_range": [30, 50]
    }
  ],
  "cover_elements": {
    "mandatory": ["人物特写(面部≥60%)", "服装反差", "关键道具", "FULL EPISODES标签"],
    "optional": ["场景暗示(虚化)", "光影对比", "极简文字"],
    "forbidden": ["红圈/箭头", "文档特写", "背景清晰", "多人平铺"],
    "character_templates": {
      "女频": "女主面部≥60%，服装颜色反差（素色→亮色），材质棉麻→丝绸/镶钻",
      "男频": "男主/男配主导，西装/腕表体现权力，表情冷峻/腹黑"
    },
    "prop_priority": ["服装反差", "身份道具", "场景氛围道具"]
  },
  "conflict_mapping": [
    {
      "genre": "总裁/豪门",
      "conflict": "真假千金身份反转",
      "visual": "DNA鉴定报告、婚戒、两把钥匙",
      "composition": "左右冷暖分割构图"
    }
  ],
  "reversal_patterns": ["重生第X天，我直接{action}，才发现{truth}."],
  "prop_scene_mapping": {
    "总裁/豪门/重生": {
      "props": ["婚戒/家徽", "DNA报告/股权文件", "奢华礼服/定制西装", "日记本/旧照片", "酒杯/钢笔"],
      "scenes": ["宴会厅/豪宅大厅", "总裁办公室/会议室", "医院/亲子鉴定中心"]
    }
  },
  "forbidden_misuse": [
    "纯英文标题", "标题<30字或>60字", "无核心题材关键词",
    "封面面部<60%", "背景清晰不虚化", "使用红圈/箭头等禁止元素"
  ]
}
```

### evidence.json 结构

高频统计，用于追溯规则来源：

```json
{
  "_meta": {"note": "高频统计，用于佐证规则来源"},
  "top_props": [{"name":"DNA鉴定报告","count":1}, ...],
  "top_scenes": [{"name":"豪门别墅","count":1}, ...],
  "top_conflicts": [{"type":"真假千金身份反转","count":1}, ...],
  "genre_dist": [{"genre":"女频","count":?}],
  "emotion_dist": [{"emotion":"爽感","count":?}]
}
```

## 使用方式

### 1. 生成结构化素材（前置）

```bash
python3 scripts/material_structurer.py --drama "以千金之名"
# 输出: data/materials_structured/以千金之名.json
```

### 2. 蒸馏运营脑（只在新增剧种时需重蒸馏）

```bash
python3 scripts/distill_operations_director.py
# 或单剧: python3 scripts/distill_operations_director.py --drama "以千金之名"
# 输出: distill/outputs/operations-director_v0.md
#       distill/outputs/operations-director/rules.json
#       distill/outputs/operations-director/evidence.json
```

### 3. 生成封面指令（每部剧）

```bash
python3 scripts/generate_cover_structured.py --drama "以千金之名" --region hk
# 输出: output/covers_structured/以千金之名_hk.json
```

### 4. 面板调用（待接入）

`panel_v3.py` 可扩展 `/api/cover_structured` 端点，读取 `rules.json` + 当前剧 `material`，自动生成 10 要素方案。

## 更新运营脑

- 当新增题材（如"古装仙侠"）或发现新的违规模式时，需重新运行 `distill_operations_director.py`
- `evidence.json` 会随 `materials_structured/*.json` 增加自动丰富高频词
- `rules.json` 中的公式/映射应由 Nuwa 基于证据自动归纳（避免人工维护）

## 与现有流程的集成点

| 现有脚本 | 替代/增强 |
|---------|---------|
| `generate_cover.py`（豆包一次请求） | 可降级为兜底；优先走 `generate_cover_structured.py`（更稳定） |
| `generate_title.py` | 可读取 `rules.json` 的 `title_formulas` 作为约束，而非硬编码规则 |
| `panel_v3.py` | 增加“基于运营脑生成封面”按钮 |

## 字段定义：10 要素封面指令

每个 `candidate` 包含：

| 字段 | 说明 | 示例 |
|------|------|------|
| `subject` | **主体**：谁+姿态+面部占比 | "女主角特写，面部占比>60%，侧脸回眸" |
| `conflict` | **冲突**：融合哪2-3个核心冲突 | "真假千金身份反转 + 重生复仇" |
| `props` | **道具**：名称+象征意义+画面位置 | "DNA报告（真相象征），握于手中，一角捏皱" |
| `scene` | **场景**：背景虚化描述 | "冷色调光斑暗示夜晚走廊，暖光晕暗示宴会厅" |
| `composition` | **构图**：具体手法 | "左右冷暖分割构图" |
| `color_scheme` | **色彩**：主色调+对比色+光影方向 | "深蓝黑主调，右侧金色暖光，左冷右暖" |
| `title_zone` | **标题区**：位置+样式 | "底部居中预留，深色渐变打底，白色艺术字+投影" |
| `must_keep` | **必须保留**：不可省略的元素 | ["面部特写>60%", "服装反差", "DNA报告清晰"] |
| `can_sacrifice` | **可牺牲**：次要元素可简化 | ["股权书完整度", "会议室细节"] |
| `forbidden` | **禁止**：明确禁止出现的元素 | ["红圈箭头", "黄底黑字", "背景清晰"] |
| `brief` | **画面整体描述**：200-300字中文 | "画面以暗黑戏剧风格呈现..." |
| `prompt` | **AI绘图指令**：中文，400-600字，含所有10要素 | "主体：一位25岁亚洲女性... 必须包含：背景极度虚化..." |
| `text_overlay` | **封面文案**：2-4字 | "真千金归来" |
| `genre_note` | **赛道标签** | "女频/豪门" |

## 设计原则

1. **素材驱动**：所有公式/映射必须来自真实国内投放标题和剧情素材
2. **可解释**：`evidence.json` 提供高频词统计，规则可追溯
3. **可迭代**：每新增 5-10 部剧，重新蒸馏一次 `operations-director`
4. **机器可读**：`rules.json` 可直接导入自动化脚本做 rule-based 校验
5. **人类可读**：`_v0.md` 用表格/列表呈现，运营可手动查阅

## 限制与假设

- **素材质量依赖豆包搜索**：若国内素材搜索不全，蒸馏出的公式会偏窄
- **单剧局限性**：当前仅 1 部剧结构化，evidence 统计未收敛
- **题材覆盖不全**：仅覆盖"总裁/豪门/重生"，待扩展"古装/仙侠/甜宠"
- **男频误判**：`target_audience` 判定逻辑需修复（繁体关键词匹配）

## 下一步

- [ ] `panel_v3` 集成："一键生成运营脑" + "基于运营脑出封面"
- [ ] 扩展 materials_structured 支持 5 个新区域（en_global/id/th/br/es_latam）
- [ ] 在 `generate_title.py` 注入 `rules.json` 的 title_formulas 作为硬约束
- [ ] 建立 distill pipeline cron job：当 `materials_structured` 新增 ≥3 剧时自动重蒸馏
