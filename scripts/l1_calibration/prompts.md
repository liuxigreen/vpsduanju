# L1 字幕抽取 Prompt 模板（v1 定稿待用户审）
# 占位符由 analyze_subs.py 填充。设计原则沿用市场洞察 PR 定论：
# 无诱导示例、数据锚定、禁止编造、数组≤5项、evidence 强制引用原句。

--- prompt:extract ---
你是短剧内容分析专家。下面是一部{language}语YouTube短剧视频的**自动字幕文本**（按时间轴分段提供）。自动字幕可能有错别字和断句问题，请基于语义理解容错分析。

【标题】{title}
【频道】{channel}
【时长】约{duration_min}分钟
【开场前3分钟字幕】
{opening}
【中段字幕（抽样）】
{middle}
【结尾2分钟字幕】
{ending}

任务：只依据字幕内容分析，字幕没有的信息一律输出null或空数组，禁止根据标题脑补。输出JSON：

{{
  "genre_l1": ["一级题材，1-3个，从观众'为什么点这类剧'的大盘分类选：如霸总/复仇/穿越/萌宝/狼人/战神/家庭伦理…可用下列参考词表，词表不覆盖时可自创并加emergent标记"],
  "genre_l1_emergent": ["自创的一级题材，无则空数组"],
  "genre_l2": ["二级题材/钩子细分，1-4个：如契约婚姻/替嫁/追妻火葬场/身份揭露/先婚后爱/带球跑…可自创"],
  "genre_l2_emergent": ["自创的二级题材，无则空数组"],
  "synopsis": "50字以内剧情梗概（谁+遭遇+转折+走向）",
  "confidence": 0.0到1.0,
  "evidence": {{"字段名": "支撑该判断的字幕原句引用（截取≤30字，必须逐字来自上面提供的字幕文本）"}},
  "opening_hook": {{"type": "开场3分钟内的主导钩子类型：身份反差/关系背叛/情绪爆点/反转打脸/补偿回报/时间改命/系统异能/其他", "event": "一句话描述该钩子事件", "appears_at_sec": 秒数}},
  "key_reveals": [{{"event": "重大揭露/反转事件", "at_sec": 秒数}}],
  "ending_cliffhanger": {{"present": true/false, "pattern": "结尾悬念的句式模式一句话描述", "quote": "字幕原句"}},
  "reversal_density": 每10分钟的反转/冲突转折次数（整数估计）,
  "characters": [{{"name": "角色名（按发音从字幕还原，含错拼变体取最可能写法）", "role": "主角/反派/配角+一句话身份"}}],
  "distinctive_lines": ["3-5句最有辨识度的台词原句（用于反查国内原剧，选专有名词/独特说法，避开泛泛的'我爱你'）"],
  "origin_signals": {{"feels_translated": true/false, "reason": "判断这是中文剧翻译配音还是本地原创：人名发音/货币单位/场景设定（如'集团总裁+人民币语境+华人姓名'→翻译剧）"}}
}}

只输出JSON，不要其他文字。

--- prompt:trace ---
（维度5 国内原剧溯源 —— 无豆包版：证据候选由 trace_drama.py 用 ytsearch中文搬运频道 + 本地竞品库互查 + bai还原query 三路生成，本段是bai裁决prompt：）

一部海外YouTube短剧频道的视频，字幕分析提取出以下特征。请在**红果短剧、抖音短剧、快手星芒、番茄畅听/悟空短剧**等国内短剧库中找出它对应的原剧。

【视频标题】{title}
【频道/语种】{channel} / {language}
【剧情梗概】{synopsis}
【角色名（外语拼写，需还原中文名）】{characters}
【高辨识度台词（外语，需还原中文原句）】{lines}
【题材】{genres}
【翻译剧判断】{origin_reason}

判断线索优先级：①角色名音译还原（如 Su Nian→苏念）②台词直译还原成中文爆款句式 ③剧情梗概匹配 ④题材+人设组合。
搜索候选（由联网搜索给出，可能含噪声）：
{candidates}

输出JSON：
{{
  "cn_title": "国内原剧名（无把握则null）",
  "aliases": ["曾用名/改名，短剧出海常改名，如《闪婚X总》→《总裁的隐婚娇妻》"],
  "platform": "红果/抖音/快手/腾讯/芒果/其他/null",
  "platform_url": "找到的链接，没有则null",
  "original_characters": {{"外文名": "还原中文名"}},
  "title_changed": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "判定依据链，引用具体对应点（角色名/台词/剧情）",
  "alternatives": [{{"cn_title": "次选", "confidence": 0.x}}]
}}

规则：候选里没有能对上≥2个独立线索（角色名+台词、或角色名+剧情）的，cn_title输出null——宁可空，不可错认。只输出JSON。

--- prompt:extract_v2 ---
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
    "appears_at_sec": 秒数,
    "duration_sec": 钩子情节持续到第几秒（整数估计，拿不准null）,
    "strength": "强/中/弱（强=前30秒出现死亡/背叛/羞辱/穿越等重级事件并直接推进主线；中=30秒-2分钟内成型；弱=铺垫型）"
  }},
  "opening_style": "强冲突开场/悬念先行/回顾衔接(含上集回顾)/日常转冲突（四选一）",
  "key_reveals": [{{"event": "中文描述重大揭露/反转", "at_sec": 秒数}}],
  "payoffs": ["本剧兑现的爽点类型，1-3个：打脸/逆袭/团圆/复仇得逞/恶人受罚/身份揭露/绝地翻盘/甜宠日常/财富自由/装逼社交…确实全无才输出['无明确爽点']并在evidence里说明，禁止普通空数组"],
  "emotion_tags": ["≤3个主导情绪：爽/虐/甜/燃/悬疑/哭/搞笑"],
  "cliffhanger_loop": {{
    "present": true/false,
    "interval_sec": 卡点循环平均间隔秒数（估计；非循环结构null）,
    "desc": "卡点方式一句话（如'每段结尾主角命悬一线切黑'）"
  }},
  "episode_structure": {{
    "is_compilation": "true/false（判断依据=片头重复/回顾转场/剧情跳跃/集数标记，不以时长论）",
    "episode_count_est": "估计集数或null",
    "avg_episode_min": "估计单集分钟数或null",
    "evidence": "判断依据（≤30字字幕原句）"
  }},
  "ending_cliffhanger": {{"present": true/false, "pattern": "结尾悬念句式一句话", "quote": "字幕原句（逐字）"}},
  "reversal_density": 每10分钟反转/冲突转折次数（整数估计）,
  "characters": [{{"name": "角色名（按发音还原最可能写法；字幕内出现中文原名时用'外文名（中文名）'格式）", "role": "主角/反派/配角+一句话中文身份", "cn_name": "能高置信还原的中文名；还原不了输出null，禁止编造"}}],
  "distinctive_lines": ["3-5句最有辨识度的台词原句（逐字，选专有名词/独特说法/情绪重句，避开泛泛表达）"],
  "distinctive_lines_cn": ["与上数组同顺序的中文直译（逐句对应，不是意译）"],
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
    "basis": "判定依据（角色名中文标注/繁中字幕直给/高辨识台词直译可还原）；无依据禁止填"
  }},
  "hit_signals": ["为什么是它爆了：2-3个可见内容信号，每条'信号+出现时间'，如'第15秒女儿寻父泪点开场，情感钩子前置'；只写字幕里看得见的，禁止用播放数据反推"]
}}

规则：
1. 只输出JSON，不要其他文字。
2. 数组≤5项；引用字段逐字保留原语言；描述字段一律简体中文。
3. null 优先于编造：cn_name/cn_title_guess/episode_structure 拿不准就 null/false。
4. payoffs 禁止普通空数组（用['无明确爽点']哨兵值）。
