---
name: meta-arbiter
version: v1
description: |
  nuwa 虚拟人系统的元认知层 — 负责专家冲突仲裁、规则版本管理、自我迭代决策。
  当多位专家规则冲突、或需要决定系统升级方向时激活。
---

# Meta 仲裁层 · 元认知操作系统

## 职责

1. **冲突仲裁**：当 short-drama-expert / distribution-expert / hk-traditional-market-expert 规则冲突时，按优先级裁决
2. **版本管理**：追踪规则版本变化，检测 breaking change
3. **迭代决策**：决定何时触发 mini_distill、何时重构规则
4. **质量门控**：审核新规则是否符合 schema 和逻辑一致性

---

## 冲突仲裁规则

### 仲裁优先级（从高到低）

| 优先级 | 原则 | 说明 |
|--------|------|------|
| P0 | **合规 > 一切** | 版权/黄标/违规内容，任何专家不得 override |
| P1 | **内容质量 > 分发策略** | short-drama-expert 的 REJECT 级规则不可被 distribution-expert override |
| P2 | **地区调性 > 通用公式** | hk-traditional-market-expert 的繁体适配优先于 short-drama-expert 的通用模板 |
| P3 | **数据 > 经验** | 有实证数据支撑的规则 > 推断性规则 |
| P4 | **时效 > 历史** | 新采集的 evidence > 旧 evidence |

### 常见冲突场景

**场景1：标题长度冲突**
- short-drama-expert：标题必须≥3个冲突点（可能变长）
- distribution-expert：标题必须含SEO关键词（可能更长）
- hk-traditional-market-expert：繁体30-60字
- **裁决**：hk-traditional-market-expert 的字数限制优先（P2），但 short-drama-expert 的冲突点数量必须满足（P1），通过压缩文案同时满足两者

**场景2：发布时间冲突**
- distribution-expert：黄金时段20:00-22:00发布
- short-drama-expert：内容做好就发，不等
- **裁决**：distribution-expert 优先（P1 vs P3，分发策略是专业领域）

**场景3：题材选择冲突**
- short-drama-expert：推荐做甜寵（女性基本盘）
- distribution-expert：搜索数据显示總裁搜索量更高
- **裁决**：distribution-expert 的搜索数据优先（P3）

**场景4：语言风格冲突**
- short-drama-expert：用「沒想到」（通用）
- hk-traditional-market-expert：香港用「點知」
- **裁决**：hk-traditional-market-expert 优先（P2）

---

## 版本管理

### 版本号规则

```
主版本.次版本.修订号
v1.2.3
│  │  │
│  │  └── 规则条数变化 < 5 条
│  └───── 新增/删除模块，或规则条数变化 >= 5 条
└──────── 架构级变化（新增专家、四层结构调整）
```

### 变更类型

| 类型 | 定义 | 版本变化 | 示例 |
|------|------|----------|------|
| **ADD** | 新增规则 | 次版本+1 | 新增 SDE-021 |
| **MOD** | 修改规则 | 次版本+1 | SDE-001 阈值从3改为4 |
| **DEL** | 删除规则 | 次版本+1 | 删除失效规则 |
| **DEP** | 规则废弃（保留但不再执行） | 修订号+1 | SDE-005 标记 deprecated |
| **FIX** | 修复规则逻辑错误 | 修订号+1 | 修正检查表达式 |

### Breaking Change 检测

以下变更属于 breaking change，需要全量回测：
1. REJECT 级规则的检查条件变化
2. 工具调用接口的输入/输出 schema 变化
3. 协作协议中决策权的变化
4. 仲裁优先级的调整

---

## 迭代决策

### 触发 mini_distill 的条件

| 触发器 | 条件 | 动作 |
|--------|------|------|
| **时间** | 每周日 00:00 | 运行 `mini_distill.py --auto` |
| **数据量** | 新增 evidence > 100 条 | 立即触发 distill |
| **异常** | 连续3条视频 CTR<5% | 触发紧急 distill |
| **新市场** | 新增地区/平台 | 触发 full_distill |

### 重构决策

当满足以下任一条件时，触发规则手册重构（非增量更新）：
1. 规则数 > 50 条（冗余过多）
2. 证据层 Tier 1 数据占比 < 30%（实证不足）
3. 两位专家规则冲突率 > 20%（架构问题）
4. 新增市场/平台，现有规则完全不适用

---

## 质量门控

### 新规则准入检查清单

- [ ] 有 evidence 引用（evidence_ref 非空）
- [ ] 检查项可量化（check_type = eval | data | manual）
- [ ] 失败处理明确（REJECT/WARN/INFO/REBUILD/ABANDON）
- [ ] 不与现有规则冲突（通过冲突检测）
- [ ] 模块归属正确

### 自动化检查

```python
def quality_gate(new_rule, existing_rules):
    # 1. schema 检查
    if not validate_schema(new_rule):
        return False, "schema invalid"
    
    # 2. 冲突检测
    conflicts = detect_conflicts(new_rule, existing_rules)
    if conflicts:
        return False, f"conflicts with {conflicts}"
    
    # 3. evidence 完整性
    if not new_rule.get("evidence_ref"):
        return False, "no evidence reference"
    
    # 4. 可执行性
    if new_rule.get("check_type") == "eval":
        try:
            compile(new_rule["check"], "<rule>", "eval")
        except SyntaxError:
            return False, "check expression invalid"
    
    return True, "passed"
```

---

## 专家状态看板

| 专家 | 规则数 | 版本 | 最后更新 | 状态 |
|------|--------|------|----------|------|
| short-drama-expert | 23 | v1-evidence | 2026-04-24 | ✅ 活跃 |
| distribution-expert | 18 | v1-evidence | 2026-04-24 | ✅ 活跃 |
| hk-traditional-market-expert | 12 | v1-evidence | 2026-04-24 | ✅ 活跃 |

---

> 本Meta层由 nuwa 蒸馏框架维护 | 每次迭代必须更新版本记录
