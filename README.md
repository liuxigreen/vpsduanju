# duanju：短剧出海 YouTube 运营系统

一句话定位：
**从7个语言、322个频道、3000+视频中蒸馏出跨语言运营规则，通过诊断引擎+面板+定时任务实现自动化频道管理。**

## 核心模块

| 模块 | 功能 | 状态 |
|------|------|------|
| **诊断引擎** | 频道健康评分、视频打分、LLM深度分析、战略建议 | ✅ 最稳 |
| **采集链路** | YT Analytics 8维度+留存、CTR 28天、周快照、竞品采集 | ✅ 稳定 |
| **面板** | Vue3 前端 + Python 后端，展示诊断结果和频道数据 | ✅ 可用 |
| **上架助手** | 输入剧名 → 标题/封面/标签/描述方案 | ⚠️ 能跑但脆 |
| **规则库** | 6个专家参考文档 + 2531条蒸馏规则 | ✅ 资产价值高 |
| **模型路由** | 统一管理多模型调用 | ✅ |

## 目录结构

```
duanju/
├── scripts/                    # 核心脚本
│   ├── panel_v3.py             # 面板后端（端口8009）
│   ├── diagnose_channel.py     # 频道诊断引擎（182KB）
│   ├── diagnosis_engine.py     # 诊断分析逻辑（35KB）
│   ├── collect_yt_analytics.py # YT Analytics 采集
│   ├── collect_ctr.py          # CTR 数据采集
│   ├── channel_weekly_snapshot.py  # 周快照
│   ├── skill_router.py         # 规则路由
│   ├── model_router.py         # 模型路由
│   ├── pre_upload_pipeline.py  # 上架流水线
│   ├── competitor/             # 竞品采集+打分
│   ├── competitor_analysis/    # 竞品深度分析（与competitor有重叠）
│   ├── core/                   # 配置、API客户端、LLM客户端
│   ├── own_channel/            # 自有频道诊断
│   └── archived/               # 已归档脚本
├── references/                 # 专家参考文档
│   ├── short-drama-expert/     # 短剧内容策略
│   ├── distribution-expert/    # 分发运营
│   ├── hk-traditional-market-expert/  # 繁体市场
│   ├── operations-director/    # 运营总监
│   ├── overseas-drama-director/ # 海外短剧导演
│   └── short-drama-youtube/    # YouTube短剧专家
├── distill/                    # 蒸馏数据
│   ├── outputs/                # 蒸馏规则输出
│   ├── evidence/               # 证据
│   ├── themes/                 # 主题分类
│   └── {语言}/                 # 按语种组织的蒸馏数据
├── data/                       # 运行数据
│   ├── own/                    # 自有频道数据
│   ├── competitor_data/        # 竞品数据
│   ├── yt_analytics/           # Analytics 数据
│   └── channel_diagnosis/      # 诊断结果
├── panel/                      # 面板
│   ├── frontend/               # Vue3 前端
│   └── channel_setup/          # 频道配置
├── config/                     # 配置文件
├── docs/                       # 文档
└── requirements.txt            # Python 依赖
```

## 数据流

```
YT API ──→ collect_yt_analytics.py ──→ data/own/yt_analytics/*.json
         ──→ collect_ctr.py ──→ data/own/ctr_reports/*.json
         ──→ channel_weekly_snapshot.py ──→ data/own/snapshots/*.json
                                                          │
                                                          ▼
                                       diagnose_channel.py ← references/ (规则)
                                                          │
                                                          ▼
                                       data/own/channel_diagnosis/*_latest.json
                                                          │
                                                          ▼
                                            panel_v3.py (API: /api/channel-analysis)
                                                          │
                                                          ▼
                                            Vue3 前端展示 (duanju.opspilot.me)
```

## 运行方式

```bash
# 面板
python3 scripts/panel_v3.py &

# 频道诊断
python3 scripts/diagnose_channel.py --channel 追劇姐妹
python3 scripts/diagnose_channel.py --all

# CTR 采集
python3 scripts/collect_ctr.py

# 周快照
python3 scripts/channel_weekly_snapshot.py
```

## 依赖

- Python 3.12+
- Google API (YouTube Analytics + Reporting)
- yt-dlp（竞品采集）
- Vue3 + Vite（面板前端）

## 已知问题

1. **`~/.hermes/` 依赖**：API key、knowledge 目录等从 `~/.hermes/` 读取，限制了可移植性
2. **竞品双包重叠**：`competitor/` 和 `competitor_analysis/` 功能有重叠
3. **diagnose_channel.py 过大**：182KB，需要拆分
4. **上架助手不稳定**：LLM 输出依赖四层正则兜底
5. **requirements.txt 不完整**：缺少 yt-dlp 等实际依赖声明
