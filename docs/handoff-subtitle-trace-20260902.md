# 交接文档：字幕数据 × 搬运溯源（2026-09-02）

> 接手人必读。本文档 = 系统现状 + 数据资产 + 踩坑记录 + 搬运溯源重设计提案。
> 配套阅读：`docs/drama-trace-v2-design.md`（v2 原设计）、`docs/overseas-intel-product-design.md`（情报三产品）、`docs/vps-duanju-infra.md`（基础设施）。
> 仓库规则见 `AGENTS.md`：模型走 `scripts/model_router.py`，不硬编码；输出落 `data/` 且 schema 确定。

---

## 一、系统总览

```
本地机器（用户侧）                    VPS 43.134.81.206 (ubuntu, 1C/1.9G/50G)
┌──────────────────┐   字幕回传文件   ┌─────────────────────────────────────┐
│ fetch_subs.py     │ ──────────────▶ │ ingest_subs.py → subs_norm.jsonl     │
│ (yt-dlp 拉字幕)   │                 │ analyze_subs.py → results_p*.jsonl   │
└──────────────────┘                 │   (bai/qwen3.8-flash 分析)           │
                                     │ aggregate_v1 → p0_normalized.jsonl   │
                                     │ trace_v2.py → data/drama_trace_v2/   │
                                     └─────────────────────────────────────┘
VPS 常驻服务：
  panel_v3.py :8009  运营面板（Caddy 反代 https://duanju.opspilot.me，keep_alive.sh 60s 守护）
  Hermes gateway :8642  (systemd hermes-gateway-duanju.service，Telegram/飞书 bot)
  Caddy 反代
```

**Cron 任务（hermes cron list 可查，全部 active 且 09-02 跑成功）**：

| job | 时间 | 作用 |
|---|---|---|
| duanju-video-daily-alerts | 08:30 | 爆款预警 → `data/alerts_latest.json` |
| duanju-daily-intel-report | 08:45 | 出海情报日报（no-agent 脚本模式，`~/.hermes/scripts/daily_report.py`，直投 TG） |
| duanju-daily-channel-discovery | 09:00 | 新频道发现 |
| yt-analytics-daily | 09:30 | 自有频道分析 |
| duanju-daily-bitable-sync | 09:15 | 飞书多维表格同步 |
| duanju-yt-accounts-cache | 09:35 | 账号缓存 |
| daily-diagnosis | 10:00 | 频道诊断 |
| duanju-competitor-velocity-refresh | 周一/四 11:00 | 竞品动量 |
| duanju-competitor-weekly-snapshot | 周一 10:00 | 竞品快照 |
| duanju-market-insights-biweekly | 1/15 日 08:00 | 市场洞察（跑 `scripts/run_insights_current_model.py`） |

**面板页面**（Vue，`panel/frontend/src/views/`）：Briefing 今日简报 / CompetitorAlerts 爆款预警+24h热榜 / CompetitorChannels / ChannelAnalysis / KnowledgeGraph / Review / Upload 上架助手 / YouTube / Distill（已隐藏）。改前端：build 后 `cp dist/* web/` 再 restart 面板。

---

## 二、数据资产（字幕相关，接手核心）

| 路径 | 内容 | 状态 |
|---|---|---|
| `data/l1_manifest.json` | 458 条入选（A235/B223），生成 08-30 | 冻结 |
| `data/subtitle_analysis/p0_normalized.jsonl` | **188 条** P0 字幕分析定稿（schema 见下） | ✅ 可用 |
| `data/subtitle_analysis/p0_report.json` | P0 质检报告 | ✅ |
| `data/subtitle_analysis/subtitle_graph_trial.json` | 题材图谱试跑 | 参考 |
| `data/drama_trace_v2/*.json` | 84 条溯源输出（**旧代码产出，层4缺失，部分结论已证伪**） | ⚠️ 需重跑 |
| `data/alerts_latest.json` | 爆款预警（每日 08:30 刷新） | ✅ |
| `data/competitor_tiers.json` + `data/video_views_history/` | 竞品池 + 播放历史（动量池=L0 数据源，`common.load_momentum_videos()`） | ✅ |
| `data/subtitle_analysis/incoming/` | **不存在/空** —— 4318 条 Phase2 回传的落点 | ⏳ 等回传 |

### p0_normalized.jsonl 每行 schema

```json
{ "video_id", "title", "channel", "language", "lang_code", "views",
  "duration_sec", "is_compilation",
  "analysis": {
    "genre_l1": [], "genre_l2": [], "payoffs": [],
    "opening_hook": {"type","event","appears_at_sec"},
    "key_reveals": [{"event","at_sec"}],
    "ending_cliffhanger": {"present","pattern","quote"},
    "reversal_density", "confidence",
    "origin_signals": {"feels_translated","reason"}
}}
```

⚠️ **注意**：`prompts.md` 里定义的 v1 prompt 含 `synopsis`/`characters`/`distinctive_lines` 字段，但 **P0 实际产出没有这些字段**（回传数据缺、聚合层也没造出来）。这是已知缺陷，重设计里要补。

### 关键统计（P0 188 条）

- **169 条 (89%) feels_translated=true** —— 翻译剧是绝对主体
- 72 条含华裔姓氏音译角色名（Zong→宗、Chan→陈 等，词表 `scripts/l1_calibration/cn_surname.yaml`）
- 指纹聚类：189 条 → 10 组跨语种姊妹版（同剧被搬到多语种）
- `is_compilation: true` 的条目（如 2.7 小时缝合怪）**hook/key_reveals 不可信**（见 §四教训2）

### Phase 2（4318 条）

本地 agent 正在跑字幕分析，**即将全量回传**。回传后流程：文件放 `~/incoming/` → `venv/bin/python3 scripts/l1_calibration/ingest_subs.py <files>` → `analyze_subs.py` → aggregate。接手人第一优先级就是接这批数据（但先读 §五，schema 可能要先改再放量）。

---

## 三、LLM / 搜索通道现状

| 通道 | 状态 | 用法 |
|---|---|---|
| **bai**（主模型） | ✅ 可用 | `~/.hermes/config.yaml` provider `bai`，默认模型 `qwen3.8-flash`。**⚠️ 模型漂移史**：默认曾被换成 glm-5.3-flash 导致思考失控(36K think/473s)，已改回。跑长任务前确认 `cfg["model"]["default"]` |
| doubao/ARK | ❌ key 失效(401) | `scripts/doubao_search.py` 勿用 |
| Firecrawl MCP | ✅ 但配额有限 | 用户明确：只做兜底深挖，一天个位数次，禁止批量 |
| YouTube (yt-dlp/transcript-api) | ❌ **服务器 IP 被拉黑**（429/bot 检测，cookies.txt 也救不了） | 服务器侧不要试图拉 YouTube 字幕/元数据；字幕一律走本地 agent 回传 |
| 搜狗微信 weixin.sogou.com | ✅ **可用**（type=2 文章搜索，零反爬） | 见 §五配方 |
| 百度 | ⚠️ 服务器 IP 时好时坏（len<50000=被拦壳页） | 本机可用；服务器侧失败率高 |
| DDG html | ✅ 可用 | 202=反爬，需 3s 退避 |
| 搜狗主站/Bing | ❌ | 纯反爬/召回差，弃用 |

**频率纪律（用户红线）**：搜狗微信间隔 ≥8s，百度 ≥8s 且每次新建 Session（复用 cookie 会被降级壳页），DDG ≥3s。溯源范围**只做爆款预警+增量热榜**（日 10-20 条），不全量搜。

---

## 四、搬运溯源：已做 + 失败教训（重设计的依据）

### 已落地（git 11a661f）

`scripts/l1_calibration/trace_v2.py`：
- 层1 翻译判定 → 层2 姓氏/剧名还原（bai）→ 层3 跨语种指纹聚类 → 层4 `cn_verify()` 中文引擎存在性验证（百度主/DDG兜底，三态 true/false/None）
- 实测：幻觉剧名《总裁的999个保姆》(bai 0.74 conf) 被正确拦截；真剧《一见你就笑》4 hits 验证通过
- **LLM 猜的剧名必须过层4，这是铁律**

### 四条实锤教训（用户目视验证）

1. **搬运号标题是二创噱头，不是剧情**。按标题生成 query 搜回来的全是同套路无关剧（"乞丐报恩"搜出陕癫侠段子号）。
2. **合集视频的 hook 会主客体反转**。`oqvm2thQcK0`（2.7h 合集）字幕分析写"穷小伙没钱女总裁买单"，用户看视频实际是"女总裁没钱穷小伙付钱"——方向反了，query 全废。根因：超长字幕压缩+印尼语被动语态歧义+套路先验压过原文。
3. **搜狗微信文章链接是会话绑定的临时签名，谁都打不开**。微信搜索的价值只在**标题+摘要文本**（当证据用），输出给人看的应该是**抖音/百度搜索页 URL**（稳定 GET 链接）。
4. **3 条爆款实测只有 1 条强匹配**（《相亲走错桌》），准确率瓶颈不在搜索引擎，在 query 质量 → 上游 hook 质量。同套路剧几百部，区分靠独特细节，而现有 schema 恰恰没提取（synopsis/characters/distinctive_lines 缺失）。

**结论：v2 设计（猜剧名→验证）方向要调整。用户已拍板重新设计，见下。**

---

## 五、搬运溯源 v3 重设计提案（待接手人实现+用户确认）

### 核心思想转变

```
v2: 字幕分析 → LLM猜中文剧名 → 搜索引擎验证     ← 猜不准，验证只是过滤噪声
v3: 字幕分析 → 还原"中文指纹" → 指纹搜索 → 候选池 → 匹配度打分 → 人工确认
```

不再指望一步猜中剧名（爆款切片改名率极高），改为**多信号指纹搜索 + 证据链输出**，允许"Top3 候选+证据"而不是"1 个答案"。

### 指纹优先级（强→弱）

1. **台词直译还原**（最强）：译制字幕是中文剧本直译过去的，把西语/印尼语关键台词**直译回中文**（不是意译！"¿Cómo te atreves a pegarme? Soy tu prometido"→"你敢打我？我是你未婚夫"）就是原剧台词句式。用 `distinctive_lines`（需补提取）逐句还原成 2-3 个中文短句去搜。
2. **角色名音译还原**：`cn_surname.yaml` 已有 72 条命中，Zong→宗、YeMing→叶明，人名+题材组合搜索。
3. **独特道具/场景/职业细节**：麻辣烫、狙击枪不死、99道测试——从 key_reveals 里挑**非套路词**（套路词=霸总/复仇/打脸，这些搜了没用）。
4. 剧情梗概（最弱，只用于兜底和打分）。

### 候选池扩充：片单文章索引（新武器）

实测发现微信里大量"短剧片单/资源"文章（一篇几百部剧名+集数），等于免费红果镜像。设计：
- 常驻采集器：每周抓 N 篇片单文章（搜狗微信搜"短剧 片单/合集/资源 全集"），解析出《剧名》+集数 → `data/cn_drama_index.jsonl`
- 溯源时先查本地索引（零请求），命中即强候选；未命中再走在线搜索
- 搜狗微信配方：`GET https://weixin.sogou.com/weixin?type=2&query=<词>`，浏览器 UA + Accept-Language zh-CN，结果在 `<h3>` 标题 + `class="txt-info"` 摘要，间隔 ≥8s。**只取文本，链接丢弃**。

### 质量门禁（上游，先于溯源）

- **hook 只喂前 5 分钟字幕**（现在 opening_0_3min 字段 ingest 已切好，analyze 时限制喂料范围）
- **evidence 强制引用字幕原句**（prompts.md 已设计，P0 实际没执行——重跑时必须开）
- **补 synopsis + characters + distinctive_lines 三字段**（prompt 已有定义，改 analyze_subs.py 落盘映射即可）
- `is_compilation: true` 条目单独标记 `needs_reanalysis`，溯源只取第一段（前 30 分钟）

### 输出物（给人看的）

每条溯源输出：`{候选剧名, 匹配度分, 证据链[字幕原句↔中文还原↔搜索摘要], 抖音搜索URL, 百度搜索URL}`。人点开对比确认，机器不越权下结论。

### 范围

只处理：爆款预警 Top5 + 24h 增量热榜里 `feels_translated=true` 的新条目（日 10-20 条）。存量 188 条不重跑（等 4318 新 schema 一起处理）。

---

## 六、待办优先级

- [ ] **P0**：接 4318 回传 → 但**先**改 analyze prompt（补 synopsis/characters/distinctive_lines + evidence 强制 + 合集限前5分钟），避免旧病重演（用户原则：放量前先冻结 schema，返工成本要算）
- [ ] **P0**：搬运溯源 v3 设计评审 → 用户确认后再动工（用户流程：设计→技术文档→git push→评审→测试→放量）
- [ ] **P1**：片单文章采集器 + `cn_drama_index.jsonl` 本地索引
- [ ] **P1**：台词直译还原模块（西/印尼/日/土/葡 → 中，bai 跑，输出 2-3 个中文短句）
- [ ] **P2**：日报内嵌溯源小节（预警/热榜段，验证结果标 ✅/❌/⚪）
- [ ] **P2**：`data/drama_trace_v2/` 84 条旧输出清理重跑（旧代码无层4，结论不可信）
- [ ] **P3**：蓝海雷达面板页（`blue_ocean.py` 已有，前端页未建）

## 七、坑清单（别重复踩）

1. 服务器 IP 拉不了 YouTube（429/bot），字幕只走回传
2. 百度响应无 charset → 必须 `r.encoding="utf-8"`，否则验证码页乱码漏检（假阴性）
3. 百度复用 Session 会被静默降级壳页 → 每次新建 Session + ≥8s
4. DDG 连续快请求 HTTP 202 → 3s 退避
5. 搜狗微信 `/link` 解析出的 mp.weixin 链接会话绑定，**永远打不开，别交付给人**
6. bai 默认模型漂移过（glm-5.3-flash 思考失控），跑批前查 `cfg["model"]["default"]`
7. P0 数据没有 synopsis/characters 字段（prompt 有定义但产出缺），trace_v2 里已有兼容拼接（opening_hook+key_reveals+reason），但质量受限
8. 面板前端 build 后要 `cp dist/* web/` 再 restart，否则改动不生效
9. 凭据走文件传输，不进对话/git（cookies_fresh.txt 已 gitignore）
10. 用户验收方式：**亲自目视视频/点开链接**，会话绑定或临时签名链接=无效交付；LLM 产出必须标注实际模型名

## 八、关键 git 记录

```
11a661f trace_v2 层4 cn_verify + P0 schema适配 + 反爬退避
75db695 出海情报三产品实装（日报/标题真相引擎/蓝海雷达）
2a6b490 溯源v2设计 + 情报产品设计
4f0f586 字幕链路放量前修复集（多源合并/合辑双信号/坏行容错/去重）
772ff25 L1 字幕校准工具链（ingest/analyze/confusion_matrix/trace + genre_vocab）
```
