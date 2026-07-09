---
name: operations-director
component: distillation-pipeline
version: 0.1.0
status: experimental
created: 2026-04-26
maintainer: duanju-system
dependencies:
  - scripts/material_structurer.py
  - scripts/distill_operations_director.py
  - scripts/generate_cover_structured.py
  - scripts/nuwa_api.py (DeepSeek-V3.2)
  - data/materials_structured/*.json
outputs:
  - distill/outputs/operations-director_v0.md
  - distill/outputs/operations-director/rules.json
  - distill/outputs/operations-director/evidence.json
  - output/covers_structured/{drama}_{region}.json
---

# Operations-Director META

## 版本历史

| 版本 | 日期 | 变更 | 原因 |
|------|------|------|------|
| v0 | 2026-04-26 | 初始版本，基于1部剧（以千金之名）蒸馏 | MVP验证 |
| v0.1 | - | 待定 | - |

## 设计初衷

将短剧国内投放素材转化为可执行的运营规则，替代过去"凭感觉调 prompt"的黑盒方式。

核心洞察：  
**Nuwa 不是数据源，是蒸馏器**。它把分散的素材压缩成可复用的 pattern（标题公式、封面构图、冲突映射）。

## 数据流

```
豆包搜索 (raw_search)
    ↓
material_structurer.py  →  data/materials_structured/剧名.json  (12字段结构化)
    ↓
distill_operations_director.py  →  rules.json + evidence.json (运营脑)
    ↓
generate_cover_structured.py  →  output/covers_structured/剧名_region.json (10要素封面指令)
    ↓
即梦/可灵 → 封面图
```

## 关键指标

- **素材覆盖率**：`materials_structured/*.json` 剧集数（当前 1）
- **规则置信度**：evidence 高频词是否稳定（当前 4 道具/4 场景/7 冲突）
- **生成成功率**：`covers_structured` JSON 解析成功率 / 女娲调用成功率
- **封面合规率**：规则检查 PASS 率（目标 ≥80%）

## 已知问题

1. **target_audience 误判**：`material_structurer` 中用 `genre` 繁体匹配失败（"总裁" != "總裁"），导致《以千金之名》被判男频
2. **道具/场景统计稀疏**：单剧证据弱，待多剧数据
3. **prompt 超时**：1562字 prompt + 5000 token 输出，女娲需 80-120 秒，需 timeout=240

## 与 Skill 系统的关系

- **short-drama-expert**：提供基础规则（长度/题材词/合规）
- **operations-director**：提供**从同类素材归纳的 pattern**（此剧的冲突→构图映射）
- **生成脚本选择**：
  - 有运营脑 → 用 `generate_cover_structured.py`（稳定、可解释）
  - 无运营脑/新题材 → fallback 到 `generate_cover.py`（豆包一次请求）

## 更新策略

每积累 **5-10 部** 同题材结构化素材，运行一次蒸馏：
```bash
python3 scripts/distill_operations_director.py
git add distill/outputs/operations-director_*
git commit -m "ops-dir: update rules with 8 new dramas"
```

当 `evidence.json` 中 `top_conflicts` 达到 5 个以上高频词且覆盖率达 80%+，可视为运营脑成熟，冻结为 v1.0。

## 链路验证

- [x] material_structurer.py：以千金之名 → 结构化 JSON
- [x] distill_operations_director.py：单剧蒸馏 → rules.json + evidence.json
- [x] generate_cover_structured.py：以千金之名 → 3方案，10要素完整
- [ ] panel_v3 集成：一键生成
- [ ] 多剧蒸馏（需批量采集数据）

---

**维护提示**：操作总监脑的 value 在于**领域覆盖度**。题材越聚焦（如只做豪门总裁），规则越准；题材发散（加古装/甜宠）需重新积累证据。
