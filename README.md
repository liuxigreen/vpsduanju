# vpsduanju — 短剧出海内容操作系统（脱敏审阅版）

> **本仓库用途**：供外部 AI/审阅者阅读代码、诊断逻辑、面板前后端、蒸馏规则，给出优化意见。
>
> ⚠️ **数据说明**：真实运营数据（`data/`, `.env`, cookies）已脱敏或移除。所有 API key 改为 `os.getenv()`。数据文件保留结构与字段说明，视频 ID/标题打码，播放量级保留（真实 152340 → 假 150000）。

## 系统概述

一体化的 YouTube 短剧频道运营系统：
- **数据采集**：yt-dlp + YouTube Data API v3 + Analytics/Reporting API
- **AI 诊断**：LLM（MiMo / DeepSeek / Doubao / GPT-5.5）分析频道健康度，输出 17 字段战略诊断 JSON
- **面板**：Vue 3.5 + Vite 8 前端 + Python `http.server` 后端（`scripts/panel_v3.py`）
- **蒸馏系统**：7 语种（en / es / id / jp / pt / tr / 繁中）骨架-钩子-包装规律库

线上面板：https://duanju.opspilot.me/

## 目录结构

```
├── main.py                              CLI 入口
├── AGENTS.md                            操作规矩（YouTube API纪律 / 批量任务骨架 / 数据文件纪律）
├── scripts/                             70+ py，采集/诊断/面板/上传/蒸馏
│   ├── diagnose_channel.py              ⭐ 核心诊断（含完整 LLM prompt）
│   ├── collect_yt_analytics.py          YT Analytics/Reporting 采集
│   ├── panel_v3.py                      面板后端 API（端口 8009）
│   ├── channel_weekly_snapshot.py       每周快照
│   ├── distill_skill.py / distill_skill_v2.py  蒸馏规则生成
│   ├── model_router.py / skill_router.py       路由层
│   ├── nuwa_api.py                      Bank of AI 调用层
│   ├── competitor/                      竞品分析
│   └── ...
├── panel/frontend/                      Vue 3 面板源码
│   ├── src/App.vue, router.js, api/index.js, stores/store.js
│   └── src/views/                       6 个页面
├── references/                          6 个专家 skill 定义
├── prompts/                             独立提示词 txt
├── distill/outputs/                     7 语种蒸馏规则
├── knowledge/{en,es,id,jp,pt,tr,繁中}/  面板实际读取的 distill.json
├── data/                                ⚠️ 脱敏样本
│   └── own/
│       ├── channel_analysis_latest.json      面板主数据（脱敏）
│       ├── channel_diagnosis/EXAMPLE_*.json  一份完整诊断样本（脱敏）
│       └── our_channels.json                 频道注册表（token 已mask）
├── docs/
├── config/                              只有 *.example.*
├── tests/
└── requirements.txt
```

## 关键诊断链路（重点审阅点）

```
scripts/collect_yt_analytics.py  →  data/own/channel_analytics/{slug}.json
scripts/diagnose_channel.py      →  data/own/channel_diagnosis/{name}_latest.json
                                      ↑ 17 字段 JSON
scripts/panel_v3.py (:8009)      →  Vue 前端展示
```

**诊断 prompt** 见 `scripts/diagnose_channel.py` 中 `llm_strategic_diagnosis` 函数：
- 输入：26 板块数据（基础指标 / CTR / 留存曲线 / 视频评分 / 蒸馏对标）
- 输出：17 字段 JSON（health / bottleneck / quadrant / sub_conversion / growth / actions / conflicts）
- 模型：MiMo v2.5（8k tokens, temp 0.4）

## YouTube API 硬约束

- CTR/展示量**只在 Reporting API**（`channel_reach_basic_a1` 报表 CSV），Analytics API v2 无
- 留存曲线（`audienceWatchRatio`）**只能逐视频拉**，单次约 60s
- 报表数据 48h 延迟，空列表标 pending 不重试

## 面板技术栈

- Vue 3.5.34 + vue-router 4.6.4 + Vite 8.0.12
- 后端 `http.server` 手写，路由见 `panel_v3.py`
- 前端 API 层 `src/api/index.js`：去重 + TTL 缓存

## 审阅建议方向

1. **诊断 prompt 质量**（`scripts/diagnose_channel.py`）：17 字段设计、CTR×留存公式
2. **数据流纪律**（`AGENTS.md`）：latest 快照的原子写入、断点续传、pending 处理
3. **面板 UX**（`panel/frontend/src/views/ChannelAnalysis.vue`）：展示密度、交互流畅度
4. **蒸馏规则应用**（`distill/outputs/`）：骨架/钩子/包装的覆盖度
5. **专家 skill 定义**（`references/`）：6 个专家的分工

## 快速启动（本地开发）

```bash
# 后端
pip install -r requirements.txt
cp .env.example .env  # 填 API keys
python scripts/panel_v3.py --port 8009

# 前端
cd panel/frontend
npm install
npm run dev  # 或 npm run build
```
