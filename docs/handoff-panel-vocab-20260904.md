# 交接文档：面板改造 × 词表治理 × 字幕v2（2026-09-04）

> 接手 agent 必读。本文档 = 2026-09-03/04 两日 ZCode 施工的全量记录 + 踩坑清单 + 双 agent 协作约定。
> 前置阅读：`docs/handoff-subtitle-trace-20260902.md`（字幕资产与系统现状）、`docs/drama-trace-v3-design.md`（溯源v3）、`docs/overseas-intel-product-design.md`（情报三产品）。

---

## 一、这轮改了什么（commit 索引，全部已推 GitHub）

| commit | 内容 | 关键文件 |
|---|---|---|
| `14c3cc9` | agent WIP 交接检查点（脏值守卫/频道封禁三道拦截/图谱L2亚型/合辑阈值1h→2h） | collect_video_daily, daily_pipeline, graph_v2, aggregate_v1/v2, panel_v3 |
| `ed30f73` | **首载半透明+行点击不稳定根治**：fade 从 keyframes 动画改状态驱动 transition | panel/frontend/src/style.css |
| `21698e4` | 图谱页钩子效果区块（含出现时点 P25/中位/P75）；**修共享缓存被 pop 原地删 nodes 的 bug**；效率榜→动量榜 | graph_v2, panel_v3, KnowledgeGraph.vue |
| `61074f2` | 内容库 SubtitleAtlas：列表索引+详情库+过滤分页 API + 详情卡（反转时间轴/证据高亮） | build_subtitle_library.py, panel_v3, SubtitleAtlas.vue, router.js |
| `dbbf542` | 题材×钩子交叉分布进弹层；剧情模式链上墙；格子点击深链内容库；预警卡实证 chips+sparkline | graph_v2, panel_v3, KnowledgeGraph.vue, CompetitorAlerts.vue |
| `ddff2ca` | 预警 vs 热榜区分说明 + 🚨重叠标记（300条中94条重叠）；预警卡折叠"内容实证"；内容库移出导航 | panel_v3, CompetitorAlerts.vue, router.js |
| `6ddcb32` | **词表统一**：聚合层归一化从 genre_vocab.yaml 切到 genre_vocab_map.json（534→261 标签，覆盖98.3%）；词表治理报告；姊妹簇聚类 v0 | subtitle_aggregate_v2, vocab_governance.py, sister_clusters.py, KnowledgeGraph.vue |
| `81a6922` | 蓝海雷达并入图谱页顶部；blue_ocean schema 白名单放宽 2.x；**恢复被误删的 /blue-ocean 路由** | blue_ocean.py, router.js, KnowledgeGraph.vue |
| `a7062d3` | 矩阵合一：热力/四象限双模式切换（格子按象限着色、数字切中位播放） | KnowledgeGraph.vue |
| `138ba7a` | **字幕分析提示词 v2**（extract_v2，analyze_subs 自动优先）+ 增量批选片器 | prompts.md, analyze_subs.py, select_alert_batch.py |
| `4168b72` | v2.1：Gemini 对抗评审修订（三门禁防幻觉 + antagonist 反派画像 + 台词双数组同长校验） | prompts.md, analyze_subs.py |

## 二、新增机制（agent 接手后要会用的）

### 1. 聚合重跑联动链（顺序固定）
```
subtitle_aggregate_v2.py → build_subtitle_library.py → vocab_governance.py
→ competitor_knowledge_graph_v2.py → sister_clusters.py
```
任何字幕数据/词表变更后按此链全量重跑。产物：`library_index/details.json`（内容库API数据源）、`vocab_governance.json`（词表健康卡）、`knowledge_graph.json`（schema 2.2）、`drama_trace_v3/sister_clusters.json`（316簇/122中文锚点）。

### 2. 增量批跑字幕（新口径：只跑预警/热榜）
```
python3 scripts/select_alert_batch.py            # 生成 data/alert_sub_batch/manifest_{date}.json
# 池=爆款预警∪24h热榜Top100−已在库，按增量降序，默认日批30（--limit 可调）
# 实测首日: 池99，已在库31，待跑68
```
跑批用 `analyze_subs.py`，会**自动优先加载 prompts.md 的 prompt:extract_v2**（v1 自动回退）。
v2 新维度：hit_signals(爆因)/episode_structure(合辑判定去时长依赖)/cliffhanger_loop(卡点循环)/
emotion_tags/audience/title_match(标题通胀)/cn_title_guess(溯源直连)/antagonist(反派画像)/
characters[].cn_name + distinctive_lines_cn(中文还原与直译)。**v1 字段全保留，下游零改动。**

### 3. 词表治理
- 单一来源 = `data/subtitle_analysis/genre_vocab_map.json`（l1_rules contains + tag2l1 + t2s + drop）。
  旧 `scripts/l1_calibration/genre_vocab.yaml` 已降级为聚合层兼容层（alias/non_genre 仍生效）。
- `vocab_governance.py` 产出待评审标签（出现≥3次未覆盖）；图谱页"题材命名一致性"卡展示。
- 当前待评审 4 个：萌宠×4 / 赌神×3 / 误会×3 / 扮猪吃虎×3——用户拍板后往 vocab_map l1_rules 加规则，重跑联动链。

### 4. 面板新 API
- `/api/subtitle-library?lang=&genre=&hook=&tier=&trans=&min_views=&q=&page=`（服务端过滤分页）
- `/api/subtitle-detail?id=video_id`
- `/api/vocab-governance`
- `/api/knowledge-graph`：**已剥 nodes**，顶层新增 `hooks`（含 sec_p25/median/p75）；genre_rank 新增 `hooks[]`（题材×钩子交叉）、`subtypes[]`（L2 剧情模式链）
- `/api/competitor-alerts`：alerts 附 `subtitle`(chips) + `content`(折叠详情: synopsis/l2/hook_event/reveals/conf) + `spark`(近14天，null=缺日)；ranking 附 `alerted`
- 内容库路由 `/library` 已隐藏（导航不显示，深链可用）——定位=AI语料层+图谱下钻落地页

### 5. GitHub 备份通道（已打通）
VPS `~/.ssh/duanju_push_ed25519`（可写 deploy key，用户已在 GitHub 配置）。
remote push URL = `git@github-push-duanju:liuxigreen/vpsduanju.git`。**每次施工后必须 push。**

## 三、踩坑清单（血泪，勿重蹈）

1. **cached_json_read 返回共享缓存对象，禁止原地修改**。`data.pop("nodes")` 会把缓存里的 nodes 永久删掉
   （症状：接口首个请求正常、之后全空）。要改就先 `data = dict(raw)` 浅拷贝。已修两处，新代码注意。
2. **不要用本地旧副本 scp 覆盖 VPS 新文件**。router.js 蓝海路由曾被本地旧副本覆盖（61074f2 事故，81a6922 恢复）。
   改文件前先 `scp vps:文件 本地` 同步，或直接在 VPS 上改。
3. **前端页面/接口改完浏览器看不到 → HTTP 缓存**。index 与 /api/* 都有 Cache-Control；
   验证时 `fetch('/', {cache:'reload'})` + reload，或 curl 127.0.0.1 直查。
4. **页面首载发暗 = 后台标签页渲染节流**，非 bug（fade 已改 transition 加固）。前台浏览正常。
5. **schema 白名单要跟着升**：blue_ocean.py 曾硬编码 2.0/2.1，图谱升 2.2 后四象限接口静默报错。
   已放宽 `startswith("2.")`；以后升 schema 记得全局 grep 白名单。
6. **蓝海散点与矩阵的关系已定**：四象限编码进热力矩阵（双模式切换），散点组件与独立入口已移除。
   `/blue-ocean` 路由 = 重定向图谱页。不要再把散点加回来。
7. Playwright 点 `position:sticky` 的 td 会 actionability 超时——用 `evaluate(() => td.click())` 验证逻辑。

## 四、待办与待用户决策

| 项 | 状态 | 等谁 |
|---|---|---|
| /sub.txt 公开订阅路径迁移（`duanju.opspilot.me/sub.txt` 无鉴权可下载，代理节点凭据暴露风险） | 方案已给（改随机路径），等用户确认（涉及代理客户端换订阅链接） | 用户 |
| trace_v3 上层：L2 番茄小说反查（web可搜性>剧名搜索）+ 人工确认队列（复用Review流）+ 搬运雷达页 | L1 数据已就绪：`sister_clusters.json` 122 簇含中文锚点（中文名可直接提取）；设计见 drama-trace-v3-design.md + Gemini 评审纠偏 | 用户看完锚点质量后拍板 |
| 词表 4 个待评审词的归并决策 | 已在面板"题材命名一致性"卡展示 | 用户 |
| L1 是否收敛 ~20 大盘（先婚后爱/替嫁等细分降 L2） | 建议观察治理机制跑一个月的新词流量再定 | 用户+数据 |
| distinctive_lines 双数组 → `lines:[{orig,cn}]` 对象数组 | 更优雅但破坏现有消费端，记大版本 | 择机 |
| 字幕维度再扩展（钩子后留存/强度细分等） | 攒到下一批增量跑批一起加，勿单独重跑 4481 条 | 数据积累 |

## 五、双 agent 协作约定

- **分工默认**：服务器 agent = 日常 cron、跑批（select_alert_batch → analyze_subs）、词表评审执行、数据管线；
  ZCode = 面板/前端改造、代码审查、提示词设计、结构性重构。
- **同步机制**：以 GitHub 为准（现在可写）。任何一方施工前先 `git pull`（或确认远端无新提交），
  完工必须 commit + push；跨 agent 的大改动在 `docs/handoff-*.md` 追加日期文档。
- **禁区**：`~/.hermes/`（密钥）、cookies*.txt、`config/settings.yaml`（含开关）、对方正在改的文件（问用户）。
- **验证纪律**：前端改动 = build + `cp dist/* ../web/` + 重启面板 + Playwright/浏览器实测；
  后端改动 = `ast.parse` 语法检查 + curl 接口实测；两者都过才 commit。

—— ZCode，2026-09-04
