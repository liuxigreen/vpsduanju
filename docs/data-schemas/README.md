# 数据文件 Schema 说明

`data/` 目录下的文件均为脱敏样本，保留完整结构。真实数据在 VPS 上的 `~/duanju/data/`。

## 关键文件

### `data/own/channel_analysis_latest.json`
**用途**：面板 `/api/channel-analysis` 直接读取，ChannelAnalysis.vue 展示。
**产出脚本**：`scripts/collect_yt_analytics.py`
**顶层字段**：
- `report_date`: 采集日期
- `channels[]`: 频道概览列表（订阅/播放/异常状态）
- `channel_details{}`: 每频道详情（recent_videos 列表 + oauth 深度数据）

### `data/own/channel_diagnosis/{name}_latest.json`
**用途**：面板每个频道展开时读，`ChannelAnalysis.vue` 展示诊断详情。
**产出脚本**：`scripts/diagnose_channel.py`
**顶层字段**：
- `channel`: 频道基础信息
- `channel_llm`: LLM 战略诊断输出（17 字段）
  - `health_score`, `health_grade`, `summary`, `ctr_status`
  - `bottleneck`, `secondary_bottleneck`
  - `strengths[]`, `problems[]`
  - `quadrant_summary`: 爆款基因/标题超卖/门面拖累/选题失败/数据异常/样本不足
  - `sub_conversion_analysis`, `growth_diagnosis`, `channel_weight`
  - `monetization_readiness`, `traffic_geo`, `upload_series`
  - `actions[]`, `ai_discoveries[]`
  - `conflicts`: 跨层一致性检查
- `distill_benchmark`: 对标蒸馏规则
- `video_scores[]`: 逐视频评分
- `retention_data`: 留存曲线原始数据

### `data/own/our_channels.json`
**用途**：频道注册表，token 已 mask。
**结构**：`{channels: [{slug, name, channel_id, oauth: {access_token, refresh_token}}]}`

## 未包含的数据文件（真实内容太敏感）

- `data/own/channel_snapshots/` — 每周快照
- `data/own/channel_analytics/{slug}.json` — YT Analytics 原始数据
- `data/competitors_channels_all.json` — 竞品动态数据
- `data/proposal_history/` — 上架历史
- `distill/evidence/` — 真实蒸馏证据

审阅时可参照 `scripts/panel_v3.py` 的 `DATA_PATHS` 字典（L48-L76）看完整数据路径。
