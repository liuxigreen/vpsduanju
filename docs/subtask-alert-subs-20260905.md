# 增量批字幕分析任务 — 2026-09-05（给字幕拉取 agent）

## 0. 任务一句话

下面 30 条视频是当日**爆款预警∪24h增量热榜**命中且**尚未入库**的视频。请逐条：拉字幕 → 用第 3 节的 extract_v2 提示词跑 LLM 分析 → 按第 4 节格式输出 JSONL 回传。这是新版 v2 提示词的正式批次（已在两条实测视频上验证通过：合辑 `oqvm2thQcK0`、单集 `gWeTej3is4w`）。

## 1. 视频清单（30 条，按 delta_24h 降序）

| video_id | 语言 | 频道 | 总播放 | 24h增量 | 标题 |
|---|---|---|---|---|---|
| `GFjx-QTdgCU` | 印尼 | Kisah Mini Nini | 1,776,839 | +95,435 | Dikhianati & ditinggal suami, dia selamatkan kakek tua, tanp |
| `A3DWMI5xq6Q` | 印尼 | DramaDuo | 466,470 | +73,386 | Gadis hamil setelah satu malam dan menikah kilat! Tak disang |
| `7jXtblYm7mM` | 印尼 | CintaBangkit | 529,320 | +67,862 | Saat CEO mengetahui bahwa anak itu adalah darah dagingnya se |
| `aad93zkhJWw` | 印尼 | Drama Berdebar | 452,840 | +63,977 | Turun gunung mancing, gembel selamatkan CEO tenggelam & obat |
| `E8ylrfF5i2Q` | 西语 | Teatro Sweetheart | 76,206 | +54,921 | 💕Obligado a Casarse, Frío CEO Elige por Error a Doctora Prod |
| `wNU6YNPr8iQ` | 印尼 | Teater Pendek Suns | 260,570 | +53,018 | Pemuda miskin sentuh pantat bintang sekolah, aktifkan 7 keku |
| `j1VrEG0dk6Q` | 印尼 | Jendela Drama Pend | 221,629 | +45,728 | Tunangan Salah Hina Mertua & Putri Pewaris, Sang CEO Muncul |
| `8ckXu-dYbdE` | 印尼 | Drama Berdebar | 284,633 | +26,054 | Gembel aktif Dewa Laut, panggil lumba-lumba! Putri taipan ne |
| `K8D_WbCYJiI` | 英文 | DesireDrama | 215,445 | +23,467 | 【FULL】My Boyfriend Sold Me to a Mafia King… Then the King Ga |
| `T4MAoTrZNuE` | 英文 | CherryWine Drama | 269,789 | +22,405 | After Mom Died, She Was Alone—Until Her Billionaire Dad Foun |
| `mEVwOuc7Krk` | 印尼 | Semesta Drama | 455,284 | +22,300 | Pelayan menikahi pria sekarat, satu ciuman membuatnya sadar, |
| `UUPp6aoEM4k` | 印尼 | Kisah Mini Nini | 244,408 | +20,942 | 1 tahun pernikahan dingin, dia minta cerai! CEO baru sadar d |
| `JYWh23cb8Gk` | 英文 | Phoenix Drama | 275,578 | +19,729 | 🔥Wild Girl Returns as the REAL Heiress—Now the Fake Daughter |
| `fOKjU2mrpdg` | 繁中 | 槱光短剧NO1sweet | 165,534 | +19,296 | 그녀는 남편이 저녁 식사에 오기를 밤새 기다렸지만…（韩语标题） |
| `6EJgs2fXss0` | 英文 | MoMoDrama | 68,362 | +19,177 | She Infiltrated the Rich Family as a Bodyguard… No One Knew |
| `l5BkVF_oudc` | 西语 | Sofá Romance Españ | 104,039 | +19,122 | El CEO creía que su esposa era aburrida, pero tras el divorc |
| `0GBufXEp5bA` | 英文 | Moonlight Drama | 91,723 | +19,035 | CEO Poses As Guard To Reject Marriage. But Rural Heiress Did |
| `xMTRSOhdTjc` | 印尼 | Teater Pudding | 166,901 | +18,553 | 💗Semua takut sama 3 CEO kejam!Tapi satu-satunya adik angkat |
| `9qlRGHpPAjk` | 英文 | Girl's Heart Short | 270,085 | +18,282 | [ENG SUB] A Baby With a System and a Plan — She Made Her Col |
| `aOoAlyeW_IY` | 印尼 | Warung Drama Manda | 78,601 | +17,737 | Dari Budak Hukuman Menjadi Istri Jenderal Perang, Bangkit De |
| `cwm6kxsefX8` | 西语 | Películas Romántic | 87,130 | +17,643 | LA RELACIÓN PROHIBIDA ENTRE UN PSICÓLOGO Y SU CLIENTE |
| `2uFtOivVDIA` | 英文 | Heartthrob Dramas | 120,052 | +16,835 | Her Boyfriend Left Her for Another Woman—She Married Her One |
| `k-FxGVKhDyM` | 葡萄牙 | Drama Doce em Curt | 130,637 | +16,688 | 💗A garota é forçada a casar, entra no banheiro errado, e o C |
| `ILLy9orM0Zo` | 印尼 | Qi-MiniDrama | 111,422 | +16,469 | 7 tahun lalu, dia pergi demi masa depan pacar pria 19th. Kin |
| `z6kSWf9FQNM` | 英文 | Drama Rush Time | 184,810 | +16,112 | [FULL] A Mistaken Surrogate for the Ruthless Billionaire / I |
| `NsEtzya7US0` | 印尼 | Drama Berdebar | 170,204 | +15,443 | Kakek sakit, gembel turun gunung ternyata dewa medis! Sekali |
| `mYD_0iqy9Dg` | 西语 | MiniDrama Latino | 79,447 | +15,350 | Joven pobre salva a una CEO perseguida mientras pesca; ¡ella |
| `dVfQCp0zSgc` | 英文 | Molly Drama | 180,302 | +15,059 | [FULL] I Woke Up Married to My Worst Office Enemy😤❤️‍🔥 |
| `rEbY2Rk8Y5w` | 英文 | MuseMood Drama | 255,210 | +14,712 | Poor Girl Risked Missing Job Interview To Help An Injured El |
| `CCTIM4ojSac` | 印尼 | NanaZone-Minidrama | 320,894 | +14,404 | Kawin kontrak demi kakek dengan CEO yang diam-diam dia suka— |

选片口径：`scripts/select_alert_batch.py`（预警∪热榜Top100 − 已在库），manifest 在 VPS `data/alert_sub_batch/manifest_2026-09-05.json`。**语言标签来自频道元数据，可能与实际字幕语言不符**（如 `fOKjU2mrpdg` 标繁中但标题是韩语）——以实际可拉到的字幕轨道为准。

## 2. 第一步：拉字幕

```bash
yt-dlp --skip-download --write-auto-subs --write-subs \
  --sub-langs "<语言码>.*,en.*" \
  -o "{video_id}.%(ext)s" \
  "https://www.youtube.com/watch?v={video_id}"
```

- 语言码优先级：**频道语言码 → 标题实际语言码 → en**；同视频多轨道时**优先原生轨（`-orig` 后缀）**，其次该语言自动轨，最后 en 自动翻译轨。
- 语言码对照：印尼=`id`，英文=`en`，西语=`es`，葡萄牙=`pt`，繁中=`zh-Hant`（韩语标题试 `ko`）。
- ⚠️ **VPS 上直接抓会被 YouTube bot 校验拦截**（实测 `Sign in to confirm you're not a bot`），请在你们自己的环境抓取后回传。
- 质量门禁：正文 ≥400 字；非文字字符占比 >40% 判 garbled 弃用。无法拉到可用字幕的视频记入失败清单（见第 5 节），跳过即可。
- 产出文件命名：`{video_id}.vtt`（或 .srt）。

## 3. 第二步：跑分析（extract_v2 提示词全文）

### 3.1 变量填充与分段规则

| 变量 | 取值 |
|---|---|
| `{language}` | 频道语言标签（印尼语/英语/西语…） |
| `{title}` / `{channel}` | 视频标题 / 频道名 |
| `{duration_min}` | 时长分钟数（四舍五入到 0.1） |
| `{opening}` | 字幕 **0~3 分钟** 原文（超 4000 字符截断） |
| `{middle}` | 中段原文；超 6000 字符时**均匀抽 3 块**、每块 2000 字符，用 `\n…\n` 连接 |
| `{ending}` | **最后 2 分钟** 原文（超 3000 字符截断） |

时间轴分段按 cue 的起止秒判断；短素材自适应（前段=min(180s, 20%片长)，尾段=最后 120s）。

### 3.2 提示词（逐字使用，双大括号保持原样）

```text
你是短剧内容分析专家。本视频来自当日播放增量榜（爆款信号视频），请以"为什么是它爆了"为核心视角做内容级分析。下面是一部{language}语YouTube短剧视频的**自动字幕文本**（按时间轴分段提供）。自动字幕可能有错别字和断句问题，请基于语义理解容错分析。

【标题】{title}
【频道】{channel}
【时长】约{duration_min}分钟
【开场前3分钟字幕】
{opening}
【中段字幕（抽样）】
{middle}
【结尾2分钟字幕】
{ending}

任务：只依据字幕内容分析，字幕没有的信息一律输出null或空数组，禁止根据标题脑补。
**语言规范（两条同时满足，缺一不可）**：①所有描述性字段（synopsis/event/desc/reason/gap/basis）一律用简体中文；②引用类字段（evidence/quote/distinctive_lines原句）必须保留字幕原语言逐字摘录。

输出JSON：
{{
  "genre_l1": ["一级题材，1-3个，按观众'为什么点这类剧'的大盘分类：霸总/甜宠/复仇/家庭伦理/逆袭打脸/豪门恩怨/身份反转/萌宝/重生/玄幻修仙/穿越/战神/神医/追妻火葬场/悬疑/职场/系统异能/马甲大佬/宫斗/校园/年代…词表外自创的放 genre_l1_emergent"],
  "genre_l1_emergent": [],
  "genre_l2": ["二级剧情模式，1-4个：契约婚姻/先婚后爱/闪婚/替嫁/真假千金/追妻火葬场/破镜重圆/身份揭露/隐藏大佬/赘婿/神医/带球跑/豪门争产/复仇打脸/重生改命/系统降临/异能觉醒/亲子悬念…可自创"],
  "genre_l2_emergent": [],
  "audience": "女频/男频/合家欢（按主角性别与核心爽点判断）",
  "synopsis": "60字以内中文剧情梗概（谁+遭遇+转折+走向）",
  "confidence": 0.0到1.0,
  "evidence": {{"字段名": "支撑该判断的字幕原句（≤30字，必须逐字来自上面字幕，保留原语言）"}},
  "opening_hook": {{
    "type": "身份反差/关系背叛/情绪爆点/反转打脸/补偿回报/时间改命/系统异能/其他",
    "event": "一句话中文描述钩子事件",
    "appears_at_sec": 秒数（必填，按视频实际秒数估计；全片确实无法定位才填null）,
    "duration_sec": 钩子情节持续到第几秒（整数估计，拿不准null）,
    "strength": "强/中/弱（强=前30秒出现死亡/背叛/羞辱/穿越等重级事件并直接推进主线；中=30秒-2分钟内成型；弱=铺垫型）"
  }},
  "opening_style": "强冲突开场/悬念先行/回顾衔接(含上集回顾)/日常转冲突（四选一）",
  "key_reveals": [{{"event": "中文描述重大揭露/反转", "at_sec": 秒数（必填，按视频实际秒数估计，反转时间轴展示依赖它）}}],
  "payoffs": ["本剧兑现的爽点类型，1-3个：打脸/逆袭/团圆/复仇得逞/恶人受罚/身份揭露/绝地翻盘/甜宠日常/财富自由/装逼社交…确实全无才输出['无明确爽点']并在evidence里说明，禁止普通空数组"],
  "emotion_tags": ["≤3个主导情绪：爽/虐/甜/燃/悬疑/哭/搞笑"],
  "cliffhanger_loop": {{
    "present": true/false,
    "interval_sec": 卡点循环平均间隔秒数；**仅当字幕文本内可见≥2个卡点切黑/转场标记才填，禁止按抽样推算全片**（非循环结构null）,
    "desc": "卡点方式一句话（如'每段结尾主角命悬一线切黑'）"
  }},
  "episode_structure": {{
    "is_compilation": "true/false（判断依据=片头重复/回顾转场/剧情跳跃/集数标记，不以时长论）",
    "episode_count_est": "估计集数；**仅当字幕出现≥2个明确集边界标记（片头重复/集数字幕）才填，否则null**",
    "avg_episode_min": "估计单集分钟数；同上门禁",
    "evidence": "判断依据（≤30字字幕原句）"
  }},
  "ending_cliffhanger": {{"present": true/false, "pattern": "结尾悬念句式一句话", "quote": "字幕原句（逐字）"}},
  "reversal_density": 每10分钟反转/冲突转折次数（整数估计）,
  "characters": [{{"name": "角色名（按发音还原最可能写法；字幕内出现中文原名时用'外文名（中文名）'格式）", "role": "主角/反派/配角+一句话中文身份", "cn_name": "能高置信还原的中文名；还原不了输出null，禁止编造"}}],
  "distinctive_lines": ["3-5句最有辨识度的台词原句（逐字，选专有名词/独特说法/情绪重句，避开泛泛表达）"],
  "distinctive_lines_cn": ["与上数组**同顺序同长度**的中文直译（逐句对应，不是意译）；两条数组长度必须一致"],
  "origin_signals": {{
    "feels_translated": true/false,
    "reason": "中文判断依据：人名发音/货币单位/场景设定",
    "region_signals": ["货币/城市/姓氏等具体地域线索"]
  }},
  "title_match": {{
    "promise": "标题承诺的题材/看点（中文）",
    "delivers": true/false,
    "gap": "不一致时说明差距（如'标题主打战神实则都市甜宠'），一致则null"
  }},
  "cn_title_guess": {{
    "title": "可能的中文原名；无把握输出null",
    "confidence": 0.0到1.0,
    "basis": "判定依据。**门禁：仅当字幕文本出现明确中文原名标注（如'袁毅'）或繁中字幕直给剧名时才允许填写；仅凭题材/剧情推测一律null**"
  }},
  "antagonist": {{"archetype": "极品反派模板（如有）：恶毒婆婆/白莲花养女/势利丈母娘/绿茶闺蜜/黑心 uncle/小三/控制狂父亲…", "desc": "一句话中文画像（谁+使什么坏）"}},
  "hit_signals": ["为什么是它爆了：2-3个可见内容信号，每条'信号+出现时间'，如'第15秒女儿寻父泪点开场，情感钩子前置'；只写字幕里看得见的，禁止用播放数据反推"]
}}

规则：
1. 只输出JSON，不要其他文字。
2. 数组≤5项；引用字段逐字保留原语言；描述字段一律简体中文。
3. null 优先于编造：cn_name/cn_title_guess/episode_structure 拿不准就 null/false。
4. payoffs 禁止普通空数组（用['无明确爽点']哨兵值）。
```

## 4. 第三步：输出要求

### 4.1 文件与行格式

合并成**一个 JSONL 文件**，每行一条视频：

```
analyses_alert_20260905.jsonl
```

每行结构（外层 wrapper + `analysis` 对象装 LLM 输出，与历史 `analyses_merged_4497.jsonl` 同构）：

```json
{
  "video_id": "GFjx-QTdgCU",
  "lang": "印尼",
  "lang_code": "id",
  "duration_sec": 5400,
  "views": 1776839,
  "title": "完整标题",
  "channel": "Kisah Mini Nini",
  "tier": "alert",
  "source": "alert_sub_batch",
  "alert_types": ["spike"],
  "model": "实际使用的模型名",
  "analysis": { …extract_v2 输出的 JSON 原样… }
}
```

`lang` 用清单里的语言标签（印尼/英文/西语/葡萄牙/繁中），`lang_code` 用对应字幕轨道语言码。`alert_types`/`source` 从清单带过来。

### 4.2 写入前自检清单（每条都要过）

1. **JSON 合法**：LLM 输出只含 JSON，parse 成功；parse 失败重试 1 次，仍失败记入失败清单。
2. **evidence 回查**：`analysis.evidence` 里每条引用、`ending_cliffhanger.quote`，去掉空白后必须能在字幕全文里找到（逐字摘录）；找不到的重新生成或置 null 并标注 warning。
3. **双数组同长**：`distinctive_lines` 与 `distinctive_lines_cn` 同序同长。
4. **payoffs 哨兵**：全无爽点时输出 `["无明确爽点"]`，禁止空数组。
5. **时间戳**：`opening_hook.appears_at_sec` 与每个 `key_reveals[].at_sec` 尽量给整数秒（时间轴展示依赖它）。
6. **防幻觉门禁**：`cn_name`/`cn_title_guess.title` 拿不准输出 null；`episode_structure.episode_count_est` 仅在有明确集边界标记时填。
7. **描述字段全部简体中文**；引用字段逐字保留原语言。
8. **每行标注 `model`** 实际模型名（便于后续按模型切片比对质量）。

### 4.3 交付方式

- 产出 `analyses_alert_20260905.jsonl` 放到 VPS `~/duanju/data/subtitle_analysis/incoming/`，或直接回传给 ZCode。
- **失败清单**随文件附一份 `analyses_alert_20260905_failures.txt`，每行 `video_id\t原因`（无字幕轨/字幕不可用/LLM parse 失败）。
- 抓取 agent 到此为止。后续的题材归一化、五步聚合（aggregate→内容库→词表治理→图谱→姊妹簇）、面板刷新由 VPS 侧处理。

## 5. 背景参考

- 提示词源文件：`scripts/l1_calibration/prompts.md` 的 `--- prompt:extract_v2 ---` 段（git 最新版含时间戳必填修订，commit `dcbcbea`）。本文件 3.2 节即其全文，直接复制使用即可。
- 上一批（4497 条）是 v1 提示词产物；本批 v2 输出维度更多（hit_signals/key_reveals 带秒时间轴/antagonist/title_match/台词中文直译等），入库后面板爆款预警卡、知识图谱钩子与剧情模式链都会用上新字段。
- 两条实测样例结论：合辑能正确判定 `is_compilation:true` 并给出结尾更大 BOSS 钩子；单集能给出 4 个带秒数的反转事件；译制剧 `cn_title_guess`/`cn_name` 门禁均正确留空。
