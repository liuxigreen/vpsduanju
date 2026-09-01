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
