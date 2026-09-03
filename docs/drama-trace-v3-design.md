# 搬运溯源 v3 设计（drama_trace_v3）

> **唯一目的：给定一条海外搬运视频，找到国内原剧的《剧名》+ 一条能直接点开的链接。**
> 剧名是中间产物，链接才是终点。点开看不到这部剧 = 溯源失败。
> 取代 trace_v2（猜剧名→验证）。基于 4497 条全量回传数据（`data/subtitle_analysis/full_normalized.jsonl`）。
> 用户流程：设计 → git push → 评审确认 → 小样本测试 → 放量。

---

## 一、数据现状（设计的前提）

| 事实 | 数字 | 意义 |
|---|---|---|
| 全量回传完成，新 schema 齐 | 4497 条，synopsis/characters/distinctive_lines/evidence 全有 | 指纹提取可直接开工 |
| 翻译剧占比 | 3908/4497 = 87% | 溯源是主战场 |
| 繁中池 | 430 条，标题/角色名全中文 | **库内现成中文锚点**，之前两版设计都没利用 |
| 角色名前缀重合≥3次 | 377 个 | 跨语种姊妹聚类可行 |
| ⚠️ is_compilation=True | 4088/4497=91%，但时长大头 30m–2h | **标志失真**（多集连剪全被误标），选材不能依赖 |

## 二、核心思想

```
v2:  字幕 → LLM猜剧名 → 验证存在性        ← 猜是黑箱，且猜中了也没给链接
v3:  向内聚(库内指纹聚类,零成本) → 三路指纹搜索 → 剧名候选 → 【链接解析】→ 剧名+可点开链接
```

1. **向内优先**：一部剧被搬到 id/en/tr，多语种版本的角色名音译、台词直译互相印证。簇里含繁中/中文条目 → 剧名几乎白送；纯外语簇 → 才花搜索配额。
2. **指纹而非猜测**：台词**直译**还原（不是意译）+ 角色名音译还原 + 非套路细节，三路指纹各自搜索互相打分。
3. **链接是硬交付**：拿到剧名后必须解析出稳定可点开的链接（见 L5），按可打开性排序交付。

## 三、六层流水线

```
L0 触发
   ├─ 增量：爆款预警+24h热榜 中 feels_translated=true（日10–20条，搜狗红线内）
   └─ 存量：4497条一次性批量（只跑L1库内聚类，零网络；L2–L5只对预警级爆款跑）
        │
L1 库内指纹聚类（零成本，先跑）
   ├─ 角色名音译规范化前缀 + genre_l1 + synopsis关键词 → 姊妹簇
   ├─ 簇内含繁中/中文标题条目 → 中文剧名候选直接提取（最强路径）
   └─ 纯外语簇 → 多语种指纹互相印证，生成更干净的还原输入
        │
L2 中文指纹提取（bai，走 model_router）
   ├─ a) 台词直译还原：distinctive_lines 逐句直译回中文 → 2–3个中文短句
   │      （"¿Cómo te atreves a pegarme? Soy tu prometido"→"你敢打我？我是你未婚夫"）
   ├─ b) 角色名还原：cn_surname.yaml 音译表 + bai → 中文人名候选
   └─ c) 独特细节：key_reveals/synopsis 挑非套路词（霸总/复仇/打脸=套路词，搜了没用）
        │
L3 候选池搜索（强指纹→弱指纹逐级降级）
   ├─ 1) 本地片单索引 cn_drama_index.jsonl（零请求，命中即强候选）
   ├─ 2) 搜狗微信 type=2（≥8s，只取标题+摘要文本，链接丢弃）
   ├─ 3) 百度（新建Session+≥8s+utf-8强制）/ DDG兜底（≥3s）
   └─ query：人名+题材 / 直译台词加引号 / 独特道具词；禁用搬运号标题（教训1）
        │
L4 剧名确认
   ├─ 候选剧 × 三路指纹 → 匹配度分；证据链：字幕原句↔中文还原↔搜索摘要
   └─ 铁律不变：LLM猜的剧名必须过存在性验证（cn_verify 三态沿用）
        │
L5 链接解析（新增，交付终点）
   ├─ 目标：给确认剧名找【用户设备上能直接点开、点开就是这部剧】的链接
   ├─ 优先级：
   │   1) 抖音合集页 https://www.douyin.com/collection/<id>（一集入坑全集）
   │   2) 抖音账号页 https://www.douyin.com/user/<id>（版权方/首发号）
   │   3) B站搜索结果页 https://search.bilibili.com/all?keyword=<剧名>
   │   4) 兜底搜索页：https://www.douyin.com/search/<剧名> + 百度 <剧名> 短剧
   ├─ 解析方式：搜 "<剧名> 合集 site:douyin.com"（搜狗/百度），从结果URL提取
   │   collection/user id；白名单校验域名，防止给到搬运号/盗版站
   ├─ 验证：服务器侧 HEAD/GET 返回200且页面含剧名（抖音反爬时降级为格式校验+标注）
   └─ 每条候选输出链接带 confidence：direct(合集页)/channel(账号页)/search(搜索页)
```

## 四、质量门禁

| 门禁 | 做法 |
|---|---|
| 合集标志失真 | 重定义双信号：duration>7200s 或 标题正则（`EP\.?\s*\d+.*EP` / `Full Movie`）；旧flag仅弱参考 |
| 合集喂料 | 合集条目 L2 只取前30分钟字段（教训2：超长压缩+被动语态→主客体反转） |
| evidence 强制 | 还原结论必须引用字幕原句，无原句=丢弃 |
| 链接白名单 | 只交付 douyin.com/collection|user|search、bilibili.com/search、百度搜索结果页；**绝不交付** mp.weixin 会话绑定链接（教训3） |
| 放量纪律 | L1全量跑 → 抽30条人工目视验收（剧名+链接都点开核对）→ 达标才开日增量 |

## 五、产出物

```
data/cn_drama_index.jsonl             # 片单索引（每周搜狗微信采集，剧名+集数）
data/drama_trace_v3/clusters.jsonl    # L1 姊妹簇全量
data/drama_trace_v3/{video_id}.json   # 单条溯源，交付格式：
  { video_id, cn_title: "《一见你就笑》", score: 0.86,
    link: { url: "https://www.douyin.com/collection/7xxxxxxxx", type: "direct", verified: true },
    fallback_links: ["https://www.douyin.com/search/一见你就笑", "https://www.baidu.com/s?wd=一见你就笑+短剧"],
    evidence: [{sub_quote, cn_restore, search_snippet}],
    siblings: [video_id...], status: confirmed|top3|no_match }
```

日报/面板展示：每条爆款预警 → 《剧名》🔗合集页（点开即看）。Top3 未确认时并列三条候选各带证据和搜索页链接，人点哪个查哪个。

副产品（不展开设计）：溯源结果攒够后聚合"母本×语种×播放"矩阵，反哺蓝海雷达。

## 六、实现顺序

1. **P0** L1 库内聚类（纯本地当天可验证）→ clusters.jsonl + 人工抽查
2. **P0** 合集标志重定义（影响所有选材）
3. **P1** L2 指纹提取 + L3 搜索编排（复用 trace_v2 的 _baidu/_ddg/cn_verify，搜狗微信新写）
4. **P1** **L5 链接解析**（抖音 collection/user id 提取 + 白名单 + 验证）——和 L3 同优先级，因为没有 L5 前面全白做
5. **P2** 片单采集器 cn_drama_index.jsonl（提升 L3 命中率）
6. **P2** 日报内嵌溯源小节（✅剧名🔗链接 / ⚪Top3待确认）；旧 drama_trace_v2/ 84条归档删除

## 七、明确不做

- ❌ 用搬运号标题生成 query（教训1）
- ❌ 交付微信临时链接/盗版站链接（教训3 + L5白名单）
- ❌ 只给剧名不给链接（本次评审纠偏：剧名是中间产物）
- ❌ 服务器拉 YouTube（IP拉黑）/ Firecrawl 批量（配额红线）
- ❌ 机器自动下"就是这部剧"结论（Top3+证据+链接，人确认）
