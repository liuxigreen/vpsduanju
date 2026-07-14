#!/usr/bin/env python3
"""
diagnose_channel.py — 自有频道诊断引擎 v2

三层诊断：
  Layer 1: Python逐视频打分（用蒸馏数据做标杆）
  Layer 2: LLM标题优化（对问题视频生成2个优化标题）
  输出：data/channel_diagnosis/{name}_latest.json

用法：
  python3 scripts/diagnose_channel.py --channel Apocalyptic_Films
  python3 scripts/diagnose_channel.py --all
  python3 scripts/diagnose_channel.py --channel Apocalyptic_Films --no-llm
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# ── 标题脱敏：替换触发内容安全过滤的敏感词 ──
# 长词优先匹配（避免短词先替换导致长词匹配失败）
_SANITIZE_MAP = {
    # 繁体变体（必须在简体之前匹配，或用长词避免冲突）
    '出軌': '变心', '出轨': '变心',
    '入獄': '入狱', '入狱': '入狱',
    '車禍': '车祸', '车祸': '交通事故',
    '欺負': '欺负', '欺负': '欺负',
    '拋棄': '抛弃', '抛弃': '抛弃',
    '裝病': '装病', '断親': '断亲',
    '騙局': '骗局', '羞辱': '侮辱',
    '殭屍': '丧屍', '蟑螂': '异物',
    '背叛': '背离', '黑道大佬': '神秘男主', '恶毒': '恶劣',
    '小三': '第三者', '第三者': '第三者',
    '陷害': '设计', '逼死': '逼迫', '逼迫': '逼迫',
    '不孕': '不育', '不育': '不育',
    '血包': '工具人', '渣男': '负心人', '劈腿': '花心',
    # 单字脱敏已删除（'殺'→'杀' / '死'→'亡'）：会把"死心塌地"→"亡心塌地"等正常词误伤，污染 LLM 输入
    # 追劇姐妹高频敏感词
    '重病': '重恙', '打臉': '反击', '打脸': '反击', '出醜': '出洋相',
    '淒慘': '凄凉', '瘫软': '腿软', '癱軟': '腿軟',
    '净身出户': '净身出门', '淨身出戶': '淨身出門',
    '崩潰': '崩溃', '崩溃': '崩溃',
    '捨去性命': '牺牲自己', '舍去性命': '牺牲自己',
    # 2026-07-09 补：hk 频道级 LLM 被审核拒的高危词
    '墮胎': '流产', '堕胎': '流产',
    '警局': '警署', '拘留所': '看守所',
    '威脅': '恐吓', '威胁': '恐吓',
    '騙簽': '诱签', '骗签': '诱签',
    '被抓': '被带走', '被打': '被伤',
    '報復': '反制', '报复': '反制',
    '毒打': '殴打', '暴打': '重击',
    '虐待': '苛待', '毒手': '狠手',
    '性侵': '侵犯', '强姦': '侵犯', '强奸': '侵犯',
    '自殺': '轻生', '自杀': '轻生',
    # 英文
    'zombie': 'undead', 'betrayed': 'abandoned', 'left for dead': 'left behind',
    'kill': 'defeat', 'killed': 'defeated', 'murder': 'conflict',
    'dead': 'gone', 'death': 'loss', 'suicide': 'despair',
    'abuse': 'mistreat', 'revenge': 'payback',
}
def _sanitize_title(t: str) -> str:
    for k, v in _SANITIZE_MAP.items():
        t = t.replace(k, v)
    return t

# ── 频道→语种映射 ──
CHANNEL_TO_LANG = {
    "Apocalyptic Films": "en",
    "Moonlit Drama Studio": "en",
    "DramaCipher": "id",
    "DramaVerve": "葡萄牙",
    "Luna Drama Estudio": "es",
    "追劇姐妹": "繁中",
}

# ── 频道→OAuth slug映射（仅已授权频道） ──
CHANNEL_TO_SLUG = {
    "追劇姐妹": "hk",
    "Apocalyptic Films": "en_global",
    "劇糖剧场": "ch_8f82d2",
    "DramaCipher": "id",
}


def _resolve_oauth_slug(channel_name: str, slug_r: str) -> str:
    """P3-11: 统一 slug 解析。

    优先级：
      1. accounts.json 反查 channel_id -> oauth_slug（yt_analytics 文件名用此 slug）
      2. CHANNEL_TO_SLUG.get(channel_name)（硬编码 fallback）
      3. slug_r（频道名下划线化，最后兜底）

    accounts.json 的 key 是 oauth_slug，value 含 channel_id；
    channel_name -> channel_id 通过 our_channels.json 注册表反查。
    """
    try:
        accounts_path = Path.home() / ".hermes" / "duanju" / "accounts.json"
        registry_path = ROOT / "data" / "own" / "our_channels.json"
        if accounts_path.exists() and registry_path.exists():
            acc = json.loads(accounts_path.read_text(encoding="utf-8"))
            reg = json.loads(registry_path.read_text(encoding="utf-8"))
            # channel_name -> channel_id（从注册表）
            ch_id = ""
            for ch in reg.get("channels", []):
                if ch.get("name", "") == channel_name:
                    ch_id = ch.get("channel_id", "")
                    break
            # channel_id -> oauth_slug（从 accounts.json 反查）
            if ch_id:
                for slug, info in acc.items():
                    if info.get("channel_id") == ch_id:
                        return slug
    except Exception:
        pass
    return CHANNEL_TO_SLUG.get(channel_name, slug_r)

SNAPSHOT_DIR = ROOT / "data" / "own" / "channel_snapshots"
DIAGNOSIS_DIR = ROOT / "data" / "own" / "channel_diagnosis"
KNOWLEDGE_DIR = Path.home() / ".hermes" / "profiles" / "duanju" / "knowledge"


def _atomic_write_json(path: Path, data: dict, indent: int = 2, ensure_ascii: bool = False) -> None:
    """原子写 JSON：写 .tmp → fsync → os.replace。

    POSIX 上 os.replace 是原子的，避免 panel 在写入中途读到截断的 JSON。
    用于 our_channels.json / *_latest.json / channel_analysis_latest.json 等并发热点。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass  # 某些文件系统不支持 fsync，忽略
    os.replace(tmp, path)

# ── OAuth分段留存数据 ──
def fetch_retention_data(channel_name: str, days: int = 30) -> dict | None:
    """为已授权频道拉取分段留存曲线（audienceWatchRatio）

    返回: {has_data, video_count, avg_retention_1pct, avg_retention_3min, avg_retention_5min, videos: [...]}
    未授权频道返回 None。
    """
    import keychain_helper as kc
    import urllib.parse as _up
    import urllib.request as _ur
    from datetime import timedelta as _td

    slug = CHANNEL_TO_SLUG.get(channel_name)
    if not slug:
        return None

    token = kc.load_youtube_token(slug)
    if not token:
        return None
    if token.get("expires_at", 0) < time.time():
        # 尝试刷新token
        try:
            import urllib.parse as _up2, urllib.request as _ur2
            client = kc.load_google_client()
            refresh_token = token.get("refresh_token")
            if client and refresh_token:
                data = _up2.urlencode({
                    "client_id": client["client_id"],
                    "client_secret": client["client_secret"],
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                }).encode()
                req = _ur2.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
                req.add_header("Content-Type", "application/x-www-form-urlencoded")
                with _ur2.urlopen(req, timeout=30) as resp:
                    new_token = json.loads(resp.read().decode())
                if "refresh_token" not in new_token:
                    new_token["refresh_token"] = refresh_token
                new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
                kc.save_youtube_token(slug, new_token)
                token = new_token
            else:
                return None
        except Exception:
            return None

    access_token = token["access_token"]

    # 获取 channel_id
    our_channels = ROOT / "data" / "own" / "our_channels.json"
    if not our_channels.exists():
        return None
    try:
        registry = json.loads(our_channels.read_text(encoding="utf-8"))
        channel_id = ""
        for ch in registry.get("channels", []):
            if ch.get("slug") == slug:
                channel_id = ch.get("channel_id", "")
                break
    except Exception:
        return None
    if not channel_id:
        return None

    end_date = datetime.utcnow().strftime("%Y-%m-%d")
    start_date = (datetime.utcnow() - _td(days=days)).strftime("%Y-%m-%d")

    def _query(params_dict):
        url = f"https://youtubeanalytics.googleapis.com/v2/reports?{_up.urlencode(params_dict)}"
        req = _ur.Request(url)
        req.add_header("Authorization", f"Bearer {access_token}")
        with _ur.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode())

    # 1. Top视频列表
    try:
        top = _query({
            "ids": f"channel=={channel_id}",
            "startDate": start_date, "endDate": end_date,
            "metrics": "views,averageViewPercentage,averageViewDuration",
            "dimensions": "video", "sort": "-views", "maxResults": "10",
        })
    except Exception:
        return None

    rows = top.get("rows", [])
    if not rows:
        return None

    # 2. 逐视频拉留存曲线
    retention_videos = []
    for row in rows:
        vid_id, views, avg_pct, avg_dur = row[0], row[1], row[2] or 0, row[3] or 0
        est_duration = avg_dur / (avg_pct / 100) if avg_pct > 0 else 0

        try:
            ret = _query({
                "ids": f"channel=={channel_id}",
                "startDate": start_date, "endDate": end_date,
                "metrics": "audienceWatchRatio",
                "dimensions": "elapsedVideoTimeRatio",
                "filters": f"video=={vid_id}",
            })
            curve = ret.get("rows", [])
        except Exception:
            curve = []

        ret_1pct = ret_3min = ret_5min = None
        min_point = None
        rebounds = []

        if curve:
            # 1%处（短剧1-2小时，1%≈60-80秒，等效MrBeast的"前30秒"）
            best_1pct = min(curve, key=lambda x: abs(x[0] - 0.01))
            if abs(best_1pct[0] - 0.01) < 0.02:
                ret_1pct = best_1pct[1]

            # 3分钟处
            ratio_3min = 180 / est_duration if est_duration > 0 else 0
            best_3min = min(curve, key=lambda x: abs(x[0] - ratio_3min)) if ratio_3min > 0 else None
            if best_3min and abs(best_3min[0] - ratio_3min) < 0.03:
                ret_3min = best_3min[1]

            # 5分钟处
            ratio_5min = 300 / est_duration if est_duration > 0 else 0
            best_5min = min(curve, key=lambda x: abs(x[0] - ratio_5min)) if ratio_5min > 0 else None
            if best_5min and abs(best_5min[0] - ratio_5min) < 0.03:
                ret_5min = best_5min[1]

            # 最低点
            min_point = min(curve, key=lambda x: x[1])

            # 回弹点（留存上升>15%）
            for i in range(1, len(curve)):
                if curve[i][1] > curve[i - 1][1] * 1.15:
                    rebounds.append({"ratio": round(curve[i][0], 2), "value": round(curve[i][1], 3)})

        retention_videos.append({
            "video_id": vid_id, "views": views,
            "avg_view_pct": round(avg_pct, 1),
            "avg_view_duration": round(avg_dur, 0),
            "est_duration": round(est_duration, 0),
            "retention_1pct": round(ret_1pct, 3) if ret_1pct else None,
            "retention_3min": round(ret_3min, 3) if ret_3min else None,
            "retention_5min": round(ret_5min, 3) if ret_5min else None,
            "min_retention": {"ratio": round(min_point[0], 2), "value": round(min_point[1], 3)} if min_point else None,
            "rebounds": rebounds[:3],
        })
        time.sleep(1)

    # 汇总
    valid_1pct = [v["retention_1pct"] for v in retention_videos if v["retention_1pct"]]
    valid_3min = [v["retention_3min"] for v in retention_videos if v["retention_3min"]]
    valid_5min = [v["retention_5min"] for v in retention_videos if v["retention_5min"]]

    return {
        "has_data": True,
        "period_days": days,
        "video_count": len(retention_videos),
        "avg_retention_1pct": round(sum(valid_1pct) / len(valid_1pct), 3) if valid_1pct else None,
        "avg_retention_3min": round(sum(valid_3min) / len(valid_3min), 3) if valid_3min else None,
        "avg_retention_5min": round(sum(valid_5min) / len(valid_5min), 3) if valid_5min else None,
        "videos": retention_videos,
    }


# ── 通用钩子词（跨题材） ──
GENERIC_HOOKS = [
    # 情绪钩子
    "betray", "revenge", "secret", "reborn", "shame", "begged", "cried",
    "regret", "divorce", "pregnant", "abandoned", "cheated", "lied",
    # 结构钩子
    "but then", "until", "only to", "turned out", "little did",
    "what happened next", "you won't believe",
    # 身份钩子
    "hidden", "real identity", "billionaire", "ceo", "heir", "prince",
    "rich", "poor", "servant", "maid", "nobody", "somebody",
    # 末世/奇幻通用钩子
    "reborn", "system", "survive", "apocalypse", "zombie", "fortress",
    "awakened", "transmigrated", "doomsday", "queen", "king",
    # 结构词
    "full", "part", "episode", "season",
]


def load_distill(lang: str) -> dict:
    """加载蒸馏数据"""
    fp = KNOWLEDGE_DIR / lang / "distill.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_snapshot(channel_name: str) -> dict:
    """加载频道快照"""
    slug = channel_name.replace(" ", "_")
    fp = SNAPSHOT_DIR / f"{slug}_latest.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_market_insights(lang: str) -> dict:
    """加载市场洞察"""
    # 语言名映射
    lang_map = {
        "en": "英文", "es": "西语", "id": "印尼",
        "繁中": "繁中", "葡萄牙": "葡萄牙",
    }
    lang_cn = lang_map.get(lang, lang)
    fp = ROOT / "data" / f"market_insights_{lang_cn}.json"
    if not fp.exists():
        return {}
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return {}


# ══════════════════════════════════════════════
# Layer 1: Python 逐视频打分
# ══════════════════════════════════════════════

def score_title_length(title: str, distill: dict) -> tuple[float, list[str]]:
    """标题长度评分 (0-10)"""
    target = distill.get("stats", {}).get("avg_title_length", 80)
    if target <= 0:
        target = 80
    length = len(title)
    diff_pct = abs(length - target) / target

    issues = []
    if diff_pct <= 0.15:
        score = 9.0
    elif diff_pct <= 0.30:
        score = 7.0
    elif diff_pct <= 0.50:
        score = 5.0
        issues.append(f"标题长度{length}字符，偏离最佳{target}字符{diff_pct:.0%}")
    else:
        score = 3.0
        direction = "过长" if length > target else "过短"
        issues.append(f"标题{direction}（{length}字符，最佳{target}）")
    return score, issues


# 题材中英文映射表
_GENRE_MAP = {
    # 中文 → 英文
    '虐恋': ['toxic', 'abusive', 'dark romance', 'pain'],
    '背叛': ['betray', 'cheat', 'affair', 'betrayal'],
    '错爱': ['wrong', 'mistaken', 'regret'],
    '逆袭': ['revenge', 'payback', 'turnaround'],
    '复仇': ['revenge', 'vengeance', 'payback'],
    '大女主': ['strong female', 'independent', 'ceo', 'boss'],
    '霸总': ['ceo', 'billionaire', 'boss', 'tycoon'],
    '甜宠': ['sweet', 'romance', 'love'],
    '恋爱': ['romance', 'love', 'dating'],
    '家庭': ['family', 'household'],
    '伦理': ['ethics', 'moral', 'family', 'betrayal'],
    '亲情': ['family', 'kinship', 'parent', 'mother', 'father'],
    '萌宝': ['baby', 'child', 'kid', 'cute'],
    '重生': ['reborn', 'rebirth', 'second chance'],
    '系统': ['system', 'game', 'level', 'apocalypse'],
    '末世': ['apocalypse', 'post-apocalyptic', 'end of world', 'survival'],
    '契约': ['contract', 'agreement', 'deal'],
    '豪门': ['wealthy', 'rich', 'billionaire', 'aristocrat'],
    '总裁': ['ceo', 'president', 'boss'],
    '千金': ['heiress', 'princess', 'rich girl'],
    # 英文 → 中文（反向）
    'ceo': ['霸总', '总裁', '大女主'],
    'billionaire': ['霸总', '豪门'],
    'romance': ['甜宠', '恋爱', '虐恋'],
    'revenge': ['复仇', '逆袭'],
    'betrayal': ['背叛', '错爱', '伦理'],
    'betray': ['背叛', '错爱'],
    'family': ['家庭', '亲情', '伦理'],
    'reborn': ['重生'],
    'contract': ['契约'],
    'sweet': ['甜宠'],
    'apocalypse': ['末世', '系统'],
    'secret': ['秘密', '隐藏'],
}


def _get_distill_genres(distill: dict) -> list[str]:
    """从蒸馏数据提取覆盖的题材"""
    genres = distill.get("meta", {}).get("genre_tags", [])
    if genres:
        return [g.lower() for g in genres]
    # fallback: 从 what.top_themes 提取
    themes = distill.get("what", [])
    result = []
    for t in themes:
        if isinstance(t, dict):
            result.append(t.get("theme", "").lower())
        elif isinstance(t, str):
            result.append(t.lower())
    return result[:10]


def _channel_genre_match(channel_genres: list[str], distill_genres: list[str]) -> float:
    """计算频道题材与蒸馏题材的匹配度 (0-1)，支持中英文交叉匹配"""
    if not channel_genres or not distill_genres:
        return 0.0
    
    def _get_mapped_terms(genre: str) -> list[str]:
        """获取题材的所有映射词（含拆分）"""
        g = genre.lower()
        terms = []
        # 直接映射
        if g in _GENRE_MAP:
            terms.extend(_GENRE_MAP[g])
        # 拆分复合题材（如"家庭伦理"→["家庭", "伦理"]）
        for key in _GENRE_MAP:
            if key in g and key != g:
                terms.extend(_GENRE_MAP[key])
        return terms
    
    matched = 0
    for g in channel_genres:
        g_lower = g.lower()
        # 直接匹配
        if any(g_lower in d or d in g_lower for d in distill_genres):
            matched += 1
            continue
        # 通过映射表匹配（含拆分）
        mapped = _get_mapped_terms(g)
        if mapped and any(m in d or d in m for m in mapped for d in distill_genres):
            matched += 1
            continue
        # 反向：检查蒸馏题材是否映射到频道题材
        for d in distill_genres:
            d_mapped = _GENRE_MAP.get(d, [])
            if d_mapped and any(g_lower in m or m in g_lower for m in d_mapped):
                matched += 1
                break
    
    return matched / max(len(channel_genres), 1)


def score_hook_words(title: str, distill: dict, channel_genres: list[str] | None = None, llm_hook_score: dict | None = None) -> tuple[float, list[str]]:
    """钩子词命中评分 (0-10)

    优先使用LLM语义评分（llm_hook_score），fallback到Python关键词匹配。
    """
    # 如果有LLM评分结果，直接用
    if llm_hook_score and title in llm_hook_score:
        info = llm_hook_score[title]
        score = info.get("score", 5)
        hooks = info.get("hooks", [])
        issues = []
        if score <= 3:
            issues.append(f"钩子弱：{', '.join(hooks[:2]) if hooks else '无明显情绪/冲突钩子'}")
        elif score <= 5:
            issues.append(f"钩子偏少：{', '.join(hooks[:2]) if hooks else '仅基础冲突'}")
        return float(score), issues

    # Fallback: Python关键词匹配（无LLM数据时）
    key_words = distill.get("how", {}).get("title_constraints", {}).get("key_words", [])
    title_lower = title.lower()
    generic_matched = [h for h in GENERIC_HOOKS if h in title_lower]
    pair_keywords = ["betray", "revenge", "secret", "pregnant", "billionaire", "ceo",
                     "reborn", "contract", "heir", "spoiled", "begged", "alpha",
                     "shame", "humble", "hidden", "dna", "marriage"]
    pair_matched = [kw for kw in pair_keywords if kw in title_lower]
    distill_kw_matched = []
    if key_words:
        for kw in key_words:
            kw_lower = kw.lower()
            if kw_lower in title_lower:
                distill_kw_matched.append(kw)
            elif len(kw_lower) >= 5:
                stem = kw_lower[:5]
                if stem in title_lower:
                    distill_kw_matched.append(kw)

    total = len(set(generic_matched + pair_matched + distill_kw_matched))
    issues = []
    if total >= 4:
        score = 9.0
    elif total >= 3:
        score = 8.0
    elif total >= 2:
        score = 6.5
    elif total >= 1:
        score = 5.0
        issues.append(f"钩子偏少（命中{total}个）")
    else:
        score = 2.0
        issues.append("无钩子词命中（通用词+蒸馏词均无）")
    return score, issues


def batch_score_hooks_llm(videos: list, distill: dict) -> dict | None:
    """批量用LLM评估所有标题的钩子强度（1次调用/频道）

    返回: {title: {"score": int, "hooks": [str], "emotion": str}} 或 None
    """
    from edgefn_models import call_for_task, parse_json_response

    how = distill.get("how", {})
    hooks = how.get("hook_combination", {})
    key_words = how.get("title_constraints", {}).get("key_words", [])
    golden = hooks.get("golden_triangle", "")
    pairs = hooks.get("strongest_pairs", [])[:5]

    titles_text = "\n".join(f"{i+1}. {v['title'][:100]}" for i, v in enumerate(videos))

    prompt = f"""你是YouTube短剧标题分析师。用严格标准评估每个标题的钩子强度。大部分标题应该得4-6分，只有极少数能得8分以上。

钩子 = 能让观众立刻想点击的元素。"有冲突词"不等于"有钩子"——冲突必须具体、有画面感、有悬念。

严格评判标准：
- 9-10: 三重钩子齐备（身份反差+强烈冲突+悬念），且有"不得不看"的紧迫感（如"被开除当天，我成了CEO"）
- 7-8: 有两个明确钩子（如身份反差+冲突），有具体场景（如"她跪在婚礼上求我原谅"）
- 5-6: 有一个钩子但表述平淡（如"他背叛了她"——有冲突但太泛，谁都会写）
- 3-4: 概述型标题（如"两个被命运捉弄的人"——有情绪但无具体场景、无悬念）
- 1-2: 无任何钩子（如"第3集"、"完整版"）

关键区分：
- "He betrayed her" = 3分（泛冲突，无场景）
- "He betrayed her at their wedding" = 5分（有场景但无反转）
- "He betrayed her at their wedding—hours later he was on his knees" = 8分（场景+反转+悬念）
- "He betrayed her at their wedding—she was the real CEO all along" = 9分（场景+身份反差+悬念）

参考钩子模式：{golden}
高频关键词：{', '.join(key_words[:10])}

标题列表：
{titles_text}

对每个标题输出严格评分和识别到的钩子。评分应呈正态分布，均值在5左右。
输出JSON：{{"scores": [{{"n": 1, "score": 8, "hooks": ["身份反差", "复仇"], "emotion": "愤怒转爽"}}, ...]}}"""

    result = call_for_task("title_optimize", prompt, max_tokens=4096, temperature=0.3)
    if result.get("error"):
        print(f"  ⚠️ 钩子LLM调用失败: {result['error']}")
        return None

    parsed = parse_json_response(result)
    if "error" in parsed or "scores" not in parsed:
        print(f"  ⚠️ 钩子LLM解析失败")
        return None

    # 映射回 title → score
    hook_scores = {}
    for item in parsed["scores"]:
        n = item.get("n", 0) - 1
        if 0 <= n < len(videos):
            title = videos[n]["title"]
            hook_scores[title] = {
                "score": item.get("score", 5),
                "hooks": item.get("hooks", []),
                "emotion": item.get("emotion", ""),
            }
    return hook_scores


def llm_analyze_and_optimize(videos: list, distill: dict, lang: str = "英文", save_callback=None, growth: dict = None, covers: list = None, quadrant_map: dict = None) -> dict | None:
    """逐批LLM调用（每批2条）：评分 + 问题识别 + 优化标题

    Args:
        save_callback: 每批次完成后回调(all_analyses)，用于增量保存

    # 确保视频按发布时间排序（最新的在最后），避免LLM误判趋势
    videos = sorted(videos, key=lambda x: x.get("published_at", ""))
        quadrant_map: video_id → bucket 名（爆款基因/标题超卖_开头型/标题超卖_中段型/门面拖累/选题失败/表现平庸/样本不足/数据异常待核实）
                       用于给 LLM 单视频建议注入象限对症纪律。缺失时按"表现平庸"处理。

    返回: {video_index: {"score": 6.5, "title_analysis": {...}, "issues": [...], "optimized": [...]}}
    """
    from edgefn_models import call_for_task, parse_json_response, CALL_INTERVAL
    import time

    # 语言映射：中文名→英文名（让LLM用正确语言输出）
    LANG_MAP = {"英文": "English", "en": "English", "西语": "Spanish", "es": "Spanish",
                "繁中": "Traditional Chinese", "印尼": "Indonesian", "id": "Indonesian",
                "葡萄牙": "Portuguese", "pt": "Portuguese", "日语": "Japanese"}
    lang_en = LANG_MAP.get(lang, lang)
    how = distill.get("how", {})
    tc = how.get("title_constraints", {})
    skeletons = how.get("title_skeletons", [])
    hooks = how.get("hook_combination", {})
    rhetorical = how.get("rhetorical_patterns", {})
    key_words = tc.get("key_words", [])
    avg_len = tc.get("avg_length", 80)

    # 构建骨架摘要
    skel_text = ""
    for sk in skeletons[:5]:
        name = sk.get("name", "")
        pattern = sk.get("pattern", "")
        examples = sk.get("examples", [])[:1]
        skel_text += f"- {name}: {pattern}"
        if examples:
            skel_text += f"  例: {examples[0]}"
        skel_text += "\n"

    golden = hooks.get("golden_triangle", "")
    pairs = hooks.get("strongest_pairs", [])[:5]

    # 封面×标题协同规则（通用参考框架）
    SYNERGY_RULES = """## 封面×标题协同（参考框架，不限于此）
封面和标题围绕同一个"核心钩子"分工协作：标题说清身份反差/情节反转/情绪爆点，封面把最有张力的一瞬间视觉化。

8个协同模式：
1. 标题给反差，封面给证据：标题用"表面身份→真实身份"反转，封面放证明反转的视觉符号（金龙/豪车/保镖/能量光效）
2. 封面定格冲突高潮，标题补全前因后果：封面抓最紧张一帧（对峙/受伤/挽留），标题说明为什么发生、接下来怎样
3. 情绪反转视觉化：封面直接呈现转折后的强烈情绪（冷酷→慌张、拒绝→宠爱）
4. 男女主关系用肢体距离表达：封面通过靠近/搂抱/壁咚/对峙表达关系阶段
5. 阶层符号强化爽感：低位身份（女佣/秘书/穷小子）与高位符号（总裁/豪车/保镖）同框对比
6. 奇观元素服务男频战力：金龙/光球/火焰等奇观元素可视化"强""秒杀"
7. 标题负责信息密度，封面负责情绪密度：标题可长可复杂，封面只突出1个主冲突+2-3个关键符号
8. 互补优于重复：封面展示标题中最有画面感的一段，二者拼起来才完整

6个反模式：
- 封面与标题题材错位（标题讲CEO，封面是古装）
- 只美不钩（封面漂亮但没冲突/动作/表情）
- 标题有爆点封面无（标题承诺怀孕/秒杀，封面没表现）
- 封面信息过散（核心钩子不突出）
- 情绪强度不匹配（标题极端冲突，封面轻松平淡）
- 关键身份缺少视觉锚点（CEO/继承人/兵王没可见符号）

以上是参考，不是限制。从实际标题+封面出发分析，如果发现新模式，直接命名。"""


    # 构建封面数据索引（video_title → cover info）
    cover_index = {}
    if covers:
        for c in covers:
            title = c.get("video_title", "")
            if title:
                cover_index[title] = {
                    "overall": c.get("overall_score", 0),
                    "person": c.get("person_score", 0),
                    "emotion": c.get("emotion_score", 0),
                    "prop": c.get("prop_score", 0),
                    "color": c.get("color_score", 0),
                    "text": c.get("text_score", 0),
                    "composition": c.get("composition_score", 0),
                    "suggestions": c.get("suggestions", [])[:2],
                    "synergy": c.get("封面×标题协同", {}),
                    "person_detail": c.get("person_detail", ""),
                    "emotion_detail": c.get("emotion_detail", ""),
                    "prop_detail": c.get("prop_detail", ""),
                    "text_detail": c.get("text_detail", ""),
                }

    # 市场参考数据（共享prompt片段）
    market_ref = f"""## 市场参考数据（来自同语种竞品Top视频蒸馏，仅供参考）
最佳标题长度：{avg_len}字符（±15%）
高频钩子词：{', '.join(key_words[:12])}
高频配对：{', '.join(pairs[:3])}
高频句式：
{chr(10).join(f'- {s.get("name", "")}: {s.get("pattern", "")}' for s in rhetorical.get("sentence_structures", [])[:5])}
标点策略：{rhetorical.get("punctuation_strategy", "")}
标题骨架：
{skel_text}"""

    synergy_text = SYNERGY_RULES

    # 增长趋势数据
    growth_text = ""
    if growth and growth.get("has_prev"):
        growth_text = f"""## 频道增长趋势（{growth.get('prev_date', '?')} → 今日，{growth.get('days_diff', '?')}天）
订阅：+{growth.get('subscribers_change', 0)}（{growth.get('subscribers_change_pct', 0)}%），日增{growth.get('daily_sub_growth', 0)}
播放：+{growth.get('views_change', 0):,}（{growth.get('views_change_pct', 0)}%），日增{growth.get('daily_view_growth', 0):,}
视频：+{growth.get('videos_change', 0)}
赞率：{growth.get('like_rate_prev', 0)}% → {growth.get('like_rate_curr', 0)}%（{growth.get('like_rate_change', 0):+}pp）
诊断时结合增长趋势判断：增长停滞/下降的频道需要更激进的标题策略；增长健康的频道保持风格微调。"""

    # 逐批处理（每批2条，更稳定）
    BATCH_SIZE = 1
    all_analyses = {}
    total = len(videos)

    for batch_start in range(0, total, BATCH_SIZE):
        batch = videos[batch_start:batch_start + BATCH_SIZE]
        batch_end = min(batch_start + BATCH_SIZE, total)

        # 构建本批视频列表（含封面数据 + 象限归类）
        vids_text = ""
        cover_text = ""
        quadrant_text = ""
        for i, v in enumerate(batch):
            views = v.get("views", 0)
            likes = v.get("likes", 0)
            lr = round(likes / max(views, 1) * 100, 2)
            vids_text += f"{i+1}. \"{_sanitize_title(v['title'])}\" | 播放:{views:,} 赞率:{lr}%\n"

            # 象限归类（批3.1 findings 输出）
            vid = v.get("video_id", "")
            bucket = (quadrant_map or {}).get(vid, "表现平庸")
            quadrant_text += f"视频{i+1} 象限归类：**{bucket}**\n"

            # 匹配封面数据
            title = v.get("title", "")
            cover_info = None
            for ct, ci in cover_index.items():
                if ct[:30] in title or title[:30] in ct:
                    cover_info = ci
                    break
            if cover_info:
                cover_text += f"视频{i+1}封面数据：\n"
                cover_text += f"  总分{cover_info['overall']}/10 | 构图{cover_info['composition']} 人物{cover_info['person']} 色彩{cover_info['color']} 情绪{cover_info['emotion']} 道具{cover_info['prop']} 文字{cover_info['text']}\n"
                # 详细分析文字（截取前150字符避免token爆炸）
                for dim, key in [("人物", "person_detail"), ("情绪", "emotion_detail"), ("道具", "prop_detail"), ("文字", "text_detail")]:
                    detail = cover_info.get(key, "")
                    if detail:
                        cover_text += f"  {dim}: {detail[:150]}\n"
                if cover_info['suggestions']:
                    cover_text += f"  封面建议: {'; '.join(cover_info['suggestions'])}\n"
                syn = cover_info.get('synergy', {})
                if syn and syn.get('score') is not None:
                    cover_text += f"  封面×标题协同（已有分析）: 协同分{syn['score']}/10 | 模式: {syn.get('synergy_pattern','')} | 反模式: {syn.get('anti_pattern','')}\n"
                    cover_text += f"  协同评估: {syn.get('assessment','')[:200]}\n"
            else:
                cover_text += f"视频{i+1}：无封面数据\n"

        prompt = f"""你是YouTube短剧频道诊断专家。分析以下视频的标题+封面，给出综合诊断。

⚠️ 输出语言要求：所有分析文字（title_analysis、cover_synergy、issues、optimized的reason）必须用中文输出。只有优化标题本身保持对应语言（{lang_en}）。

## 象限对症纪律（必须遵守，覆盖以下所有通用规则）
每条视频在数据区已标注"象限归类"（Python 层判定，你只解读，禁止重新归类）。
**直接使用给定的象限，不要自行判断阈值。**各象限行动规则：

- **爆款基因**：标题+封面都成立，issues 只列"可微调点"，optimized 出的两个新标题必须与原标题**同骨架同钩子**（复制模板量产），不要重构。
- **标题超卖_开头型**：标题吸引点击但开头 hook 太弱→ issues 聚焦"标题承诺 vs 开头兑现"落差，optimized 给"降调版"（钩子强度降 20-30%，与开头能兑现的强度匹配）。**禁止只夸标题不改**。
- **标题超卖_中段型**：标题+开头都 OK，中段掉链子 → issues 不要指标题问题，optimized 可以保留原标题，reason 写"标题保留，问题在中段节奏"。**禁止改标题**（改也白改）。
- **门面拖累**：内容好点击差 → issues 聚焦"标题+封面吸引力不足"，optimized 必须**大幅重写标题**（换骨架、加更强钩子），reason 说"重置门面"。
- **选题失败**：题材本身不适合此频道 → issues 写"选题偏离定位"，optimized 给"如果非要拍此类题材应该怎么写"但明确标注"建议不再拍此类"。
- **表现平庸**：常规优化建议。
- **样本不足**：optimized 可以出，但 issues 里写"数据样本不足，仅供参考"，score 不能超过 6。
- **数据异常待核实**：不出 optimized 建议，issues 写"数据异常，需人工核实"。

## 诊断框架：骨架 × 血肉 × 创新
- **骨架**= 叙事原型（先抑后扬、低位闯高位、隐藏身份、第一人称极端遭遇等）。骨架是标题的叙事结构，决定观众的期待类型。
- **血肉**= 包装手法（钩子词、标点策略、emoji、身份词等）。血肉是骨架上的具体表达，让标题有画面感和情绪冲击。
- **创新**= 根据具体剧情在骨架上灵活发挥，不是复制模板。每个剧的剧情不同，骨架可以变形、血肉可以取舍。
诊断时：先识别原标题的骨架是什么、血肉缺什么，再针对性优化。

## 核心规则（必须遵守）
1. 只使用标题中已有的剧情元素，不要编造新剧情（如标题没提怀孕就不要加pregnant）
2. 保持原标题的视角（第一人称/第三人称不要混用）
3. 优先解决标题的核心问题（缺反转就加反转，缺身份就加身份，概述型就改成有悬念）
4. 参考下面的市场数据，但根据具体剧情灵活运用，不要机械套模板
5. 优化标题长度接近{avg_len}字符，不要超过100字符

## 钩子分类（6类，不限于此，从标题语义中识别，不要做单词匹配）
- **情绪钩子**：能引发观众强烈情绪反应的元素——愤怒、心碎、恐惧、爽感、嫉妒、绝望、狂喜等。判断标准：读完标题是否能感受到情绪波动
- **身份钩子**：身份落差、隐藏身份、低位→高位反转——穷vs富、弱vs强、假vs真、养女vs亲生等。判断标准：标题是否暗示人物身份与表面不符
- **反转钩子**：剧情反转、意想不到的真相揭露——but/however/结果发现/其实/岂料/正体等。判断标准：标题是否有前后转折
- **时间钩子**：时间跨度、重生、回到过去、未来预言——N年后/after离婚/reborn/从未来/前世等。判断标准：标题是否涉及时间线变化
- **冲突钩子**：背叛、抛弃、被迫、囚禁、抢夺、羞辱等冲突动作。判断标准：标题中是否有人物遭受不公或暴力对待
- **关系钩子**：家庭关系、婚恋关系、师生关系等人际纠葛——ex-husband/继兄/契约婚姻/养父/婆婆等。判断标准：标题是否涉及复杂人际关系
- **其他**：不限于以上6类，从标题中自行发现新钩子类型（如权力钩子、命运钩子、灾难钩子、悬念钩子、系统觉醒钩子等），直接命名并标注

钩子可以组合，但每个标题最多突出2个主钩子，第三个作为辅助。

## 标题公式参考（5种高频模式，不限于此，从标题结构中识别）
- **身份落差**：低位身份→高位身份反转。核心是反差越大越爽。如：养女→真千金、穷小子→隐藏富豪
- **极端遭遇**：第一人称遭遇极端事件。核心是具体场景+情绪冲击。如：被囚禁/被背叛/被迫嫁
- **时间压力**：时间限制制造紧迫感。核心是倒计时+赌注。如：24小时内/只剩3天/死前最后一刻
- **冲突对峙**：两方直接对抗。核心是力量悬殊+悬念。如：弱者vs强者/一个人vs所有人
- **秘密揭露**：隐藏真相被揭开。核心是信息差+震惊。如：发现丈夫是/原来她才是/真相是

以上是参考框架，不是限制。从标题实际结构中识别使用的公式，如果发现新公式直接命名。

## 评分标准（严格，均值应在5-6左右）
- 9-10: 爆款——三重钩子+具体场景+悬念，几乎完美
- 7-8: 好标题——两个钩子+具体场景+点击欲望
- 5-6: 合格——一个钩子但表述可以更有力
- 3-4: 弱——概述型/泛冲突/缺少悬念
- 1-2: 差——无钩子/纯描述/完全无点击欲望

## 频道数据
{vids_text}

## 视频象限归类（Python 已归类，你必须按此对症下药）
{quadrant_text}
{growth_text}

{market_ref}

## 封面数据（来自封面分析）
{cover_text}

{synergy_text}

对每条视频：
1. 分析标题的骨架类型、钩子组合（6+1类）、包装模式，标注缺失
2. **必须评估封面×标题协同**：如果上面的封面数据中已有"封面×标题协同（已有分析）"，直接采用其协同分和评估，在此基础上补充你的改进建议。如果没有已有分析，结合封面数据和协同规则自行评估。封面数据缺失时score填null但仍需写assessment说明缺失影响
3. 出2个优化标题，每个标注骨架和钩子组合

⚠️ 关键字段要求：title_analysis和cover_synergy都是必填项，缺失任何一个都会导致诊断失败。

输出JSON：
{{"analyses": [{{"n": 1, "score": 6.5, "title_analysis": {{"skeleton": "骨架类型", "hooks": {{"emotion": true, "identity": false, "reversal": false, "time": false, "conflict": false, "relationship": false, "other": []}}, "hook_types_found": ["情绪:terrifying", "时间:tomorrow's me"], "packaging": "句式/标点", "missing": ["反转钩子"]}}, "cover_synergy": {{"score": 5, "synergy_pattern": "使用的协同模式", "anti_pattern": "存在的反模式", "assessment": "封面和标题的协同分析", "improvement": "改进建议"}}, "issues": ["标题概述型，缺少具体场景"], "optimized": [{{"title": "优化标题1", "skeleton": "骨架名", "hooks": "钩子组合", "reason": "改了什么为什么"}}, {{"title": "优化标题2", "skeleton": "骨架名", "hooks": "钩子组合", "reason": "原因"}}}}]}}"""

        print(f"    📝 批次 {batch_start//BATCH_SIZE + 1}/{(total + BATCH_SIZE - 1)//BATCH_SIZE}（视频 {batch_start+1}-{batch_end}）...", end="", flush=True)

        result = call_for_task("title_optimize", prompt, max_tokens=8192, temperature=0.5)
        if result.get("error"):
            print(f" ⚠️ 失败: {result['error'][:50]}")
            continue

        parsed = parse_json_response(result)
        if "error" in parsed or "analyses" not in parsed:
            print(f" ⚠️ 解析失败")
            continue

        # 映射回全局 video index
        for item in parsed["analyses"]:
            n = item.get("n", 0) - 1  # 本批内偏移
            global_idx = batch_start + n
            if 0 <= global_idx < total:
                all_analyses[global_idx] = item

        print(f" ✅ {len(parsed['analyses'])}条")

        # 每批次完成后增量保存
        if save_callback:
            save_callback(all_analyses)

        # 批次间隔（RPM限制）
        if batch_end < total:
            time.sleep(CALL_INTERVAL)

    return all_analyses if all_analyses else None


def score_tags(description_tags: list[str], distill: dict, channel_genres: list[str] | None = None) -> tuple[float, list[str]]:
    """标签覆盖评分 (0-10)"""
    tag_groups = distill.get("how", {}).get("hashtag_strategy", {})
    recommended = set()
    if isinstance(tag_groups, dict):
        for group in tag_groups.values():
            if isinstance(group, list):
                recommended.update(t.lower().lstrip('#') for t in group)
    elif isinstance(tag_groups, list):
        recommended.update(t.lower().lstrip('#') for t in tag_groups)

    tag_count = len(description_tags) if description_tags else 0
    tags_lower = [t.lower() for t in description_tags] if description_tags else []

    issues = []
    if tag_count == 0:
        return 1.0, ["无标签，SEO完全空白"]
    elif tag_count < 3:
        score = 3.0
        issues.append(f"仅{tag_count}个标签，建议≥5个")
    elif tag_count < 5:
        score = 5.0
    elif tag_count < 8:
        score = 7.0
    else:
        score = 8.0

    # 蒸馏标签重合：精确匹配 + 模糊匹配（子串包含）
    if recommended:
        exact = [t for t in tags_lower if t in recommended]
        fuzzy = [t for t in tags_lower if any(r in t or t in r for r in recommended if len(r) >= 4)]
        matched = set(exact + fuzzy)
        if len(matched) >= 3:
            score = min(10, score + 2)
        elif len(matched) >= 1:
            score = min(10, score + 1)
        # 不扣分，只加分

    return score, issues


def score_publish_time(published_at: str, distill: dict) -> tuple[float, list[str]]:
    """发布时间评分 (0-10)"""
    best_hours = distill.get("stats", {}).get("best_hours", [])
    if not best_hours or not published_at:
        return 5.0, []

    try:
        dt = datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        hour = dt.hour
    except Exception:
        return 5.0, []

    if hour in best_hours:
        return 9.0, []
    # 邻近小时
    near = [h for h in best_hours if abs(h - hour) <= 2]
    if near:
        return 7.0, []
    return 4.0, [f"发布时间UTC {hour}:00，市场最佳时段：{best_hours}"]


def score_engagement(video: dict, channel_avg_like_rate: float) -> tuple[float, list[str]]:
    """互动率评分 (0-10)"""
    views = video.get("views", 0)
    likes = video.get("likes", 0)
    if views == 0:
        return 0.0, ["无播放数据"]

    like_rate = likes / views * 100
    issues = []

    if like_rate >= channel_avg_like_rate * 1.5:
        score = 9.0
    elif like_rate >= channel_avg_like_rate:
        score = 7.0
    elif like_rate >= channel_avg_like_rate * 0.5:
        score = 5.0
        issues.append(f"点赞率{like_rate:.2f}%，低于频道均值{channel_avg_like_rate:.2f}%")
    else:
        score = 2.0
        issues.append(f"点赞率极低{like_rate:.2f}%（频道均值{channel_avg_like_rate:.2f}%）")
    return score, issues


def score_video(video: dict, distill: dict, channel_avg_like_rate: float, channel_genres: list[str] | None = None, llm_hook_score: dict | None = None) -> dict:
    """单视频综合评分"""
    title = video.get("title", "")
    tags = video.get("description_tags", [])
    published = video.get("published_at", "")

    # 各维度评分
    s_title, i_title = score_title_length(title, distill)
    s_hook, i_hook = score_hook_words(title, distill, channel_genres, llm_hook_score)
    s_tags, i_tags = score_tags(tags, distill, channel_genres)
    s_time, i_time = score_publish_time(published, distill)
    s_engage, i_engage = score_engagement(video, channel_avg_like_rate)

    # 加权平均
    weights = {"title": 0.25, "hook": 0.25, "tags": 0.20, "time": 0.10, "engage": 0.20}
    total = (
        s_title * weights["title"]
        + s_hook * weights["hook"]
        + s_tags * weights["tags"]
        + s_time * weights["time"]
        + s_engage * weights["engage"]
    )

    all_issues = []
    for dim, issues in [("标题", i_title), ("钩子", i_hook), ("标签", i_tags), ("时间", i_time), ("互动", i_engage)]:
        for issue in issues:
            all_issues.append({"dimension": dim, "issue": issue})

    result = {
        "video_id": video.get("video_id", ""),
        "title": title,
        "views": video.get("views", 0),
        "likes": video.get("likes", 0),
        "like_rate": round(video.get("likes", 0) / max(video.get("views", 1), 1) * 100, 2),
        "published_at": published,
        "score": round(total, 1),
        "scores": {
            "title_length": round(s_title, 1),
            "hook_words": round(s_hook, 1),
            "tags": round(s_tags, 1),
            "publish_time": round(s_time, 1),
            "engagement": round(s_engage, 1),
        },
        "issues": all_issues,
        "needs_optimization": total < 6.0,
    }

    # 如果有LLM钩子详情，附加到输出
    if llm_hook_score and title in llm_hook_score:
        info = llm_hook_score[title]
        result["hook_detail"] = {
            "hooks": info.get("hooks", []),
            "emotion": info.get("emotion", ""),
        }

    return result


def load_channel_genres(channel_name: str, videos: list = None) -> list[str]:
    """加载频道题材：先查注册表缓存，没有则用DeepSeek分类"""
    # 1. 查注册表缓存
    registry_path = ROOT / "data" / "own" / "our_channels.json"
    if registry_path.exists():
        try:
            reg = json.loads(registry_path.read_text())
            for ch in reg.get("channels", []):
                if ch.get("name", "") == channel_name:
                    # 有缓存的genre_tags直接返回
                    cached_genres = ch.get("genre_tags", [])
                    if cached_genres:
                        return [g.lower() for g in cached_genres]
                    # 兼容旧的niche字段
                    niche = ch.get("niche", "")
                    if niche:
                        return [g.strip().lower() for g in niche.split("/")]
        except Exception:
            pass

    # 2. 用DeepSeek分类
    if videos:
        from diagnosis_engine import classify_genre_deepseek
        result = classify_genre_deepseek(videos)
        genres = result.get("genre_tags", [])
        if genres:
            print(f"  🤖 DeepSeek题材: {', '.join(genres)} ({result.get('confidence', '')})")
            # 缓存到注册表
            _cache_genre_tags(channel_name, genres)
            return [g.lower() for g in genres]
    return []


def _cache_genre_tags(channel_name: str, genres: list[str]):
    """将DeepSeek分类结果缓存到注册表"""
    registry_path = ROOT / "data" / "own" / "our_channels.json"
    if not registry_path.exists():
        return
    try:
        reg = json.loads(registry_path.read_text())
        for ch in reg.get("channels", []):
            if ch.get("name", "") == channel_name:
                ch["genre_tags"] = genres
                break
        _atomic_write_json(registry_path, reg, ensure_ascii=False)
    except Exception:
        pass


def score_all_videos(videos: list, distill: dict, channel_genres: list[str] | None = None, llm_hook_score: dict | None = None) -> tuple[list, float]:
    """对所有视频打分，返回(视频评分列表, 频道均点赞率)"""
    # 计算频道平均点赞率
    rates = [v["likes"] / v["views"] * 100 for v in videos if v.get("views", 0) > 0]
    avg_rate = sum(rates) / len(rates) if rates else 0

    scored = []
    for v in videos:
        s = score_video(v, distill, avg_rate, channel_genres, llm_hook_score)
        scored.append(s)

    # 按评分排序（低分在前，优先需要优化的）
    scored.sort(key=lambda x: x["score"])
    return scored, round(avg_rate, 2)


# ══════════════════════════════════════════════
# Layer 2: LLM 标题优化
# ══════════════════════════════════════════════

def build_llm_prompt(video: dict, distill: dict) -> str:
    """构建LLM标题优化prompt（只用how层）"""
    how = distill.get("how", {})
    tc = how.get("title_constraints", {})
    skeletons = how.get("title_skeletons", [])
    hooks = how.get("hook_combination", {})
    rhetorical = how.get("rhetorical_patterns", {})

    # 精简骨架列表（取前5个）
    skel_text = ""
    for sk in skeletons[:5]:
        name = sk.get("name", "")
        pattern = sk.get("pattern", "")
        examples = sk.get("examples", [])[:2]
        skel_text += f"- {name}: {pattern}\n"
        for ex in examples:
            skel_text += f"  例: {ex}\n"

    # 钩子组合
    hook_text = ""
    golden = hooks.get("golden_triangle", "")
    if isinstance(golden, str) and golden:
        hook_text += f"- 黄金三角: {golden}\n"
    pairs = hooks.get("strongest_pairs", [])
    if isinstance(pairs, list):
        for p in pairs[:5]:
            hook_text += f"- {p}\n"
    rules = hooks.get("rules", [])
    if isinstance(rules, list):
        for r in rules[:3]:
            hook_text += f"- 规则: {r}\n"

    # 句式
    rp_text = ""
    structures = rhetorical.get("sentence_structures", [])
    for s in structures[:3]:
        if isinstance(s, dict):
            rp_text += f"- {s.get('name', '')}: {s.get('pattern', '')}\n"
        elif isinstance(s, str):
            rp_text += f"- {s}\n"

    key_words = tc.get("key_words", [])
    avg_len = tc.get("avg_length", 80)

    prompt = f"""你是YouTube短剧标题优化专家。请为以下标题生成2个优化版本。

现有标题："{video.get('title', '')}"
播放量：{video.get('views', 0):,} | 点赞率：{video.get('like_rate', 0)}%

市场规则（蒸馏数据）：
- 最佳标题长度：{avg_len}字符（±15%）
- 高频关键词：{', '.join(key_words[:10])}
- 标题骨架：
{skel_text}
- 钩子组合：
{hook_text}
- 句式结构：
{rp_text}

要求：
1. 保留原视频的核心内容和语义
2. 使用蒸馏数据中的骨架和钩子模式
3. 标题长度接近{avg_len}字符
4. 每个标题用不同的骨架+钩子组合

输出JSON格式：
{{"titles": [{{"title": "优化标题1", "skeleton": "使用的骨架名", "hook": "使用的钩子", "reason": "为什么这样改"}}, {{"title": "优化标题2", "skeleton": "骨架名", "hook": "钩子", "reason": "原因"}}]}}"""

    return prompt


def call_deepseek(prompt: str) -> dict | None:
    """调用edgefn Flash模型做标题优化"""
    from edgefn_models import call_for_task, parse_json_response, CALL_INTERVAL
    result = call_for_task("title_optimize", prompt, max_tokens=4096, temperature=0.7)
    if result.get("error"):
        print(f"  ⚠️ LLM调用失败: {result['error']}")
        return None
    parsed = parse_json_response(result)
    if "error" in parsed:
        print(f"  ⚠️ JSON解析失败: {parsed.get('raw', '')[:100]}")
        return None
    return parsed

def optimize_titles(scored_videos: list, distill: dict, max_llm: int = 10, save_callback=None) -> list:
    """对低分视频用LLM生成优化标题"""
    needs_opt = [v for v in scored_videos if v.get("needs_optimization")]
    if not needs_opt:
        return scored_videos

    to_optimize = needs_opt[:max_llm]
    print(f"  🤖 对{len(to_optimize)}条问题视频调LLM优化...")

    for i, video in enumerate(to_optimize):
        print(f"    [{i+1}/{len(to_optimize)}] {video['title'][:40]}...")
        prompt = build_llm_prompt(video, distill)
        result = call_deepseek(prompt)

        if result and "titles" in result:
            video["optimized_titles"] = result["titles"]
            print(f"      ✅ 生成{len(result['titles'])}个优化标题")
        else:
            video["optimized_titles"] = []

        # 每条LLM完成后增量保存
        if save_callback:
            save_callback()

        # DeepSeek 限制 10 RPM，间隔20秒
        if i < len(to_optimize) - 1:
            time.sleep(CALL_INTERVAL)

    return scored_videos


# ══════════════════════════════════════════════
# 频道级诊断（整合 Layer 2 市场洞察）
# ══════════════════════════════════════════════

def channel_level_diagnosis(snapshot: dict, distill: dict, market: dict) -> dict:
    """频道整体诊断（用market_insights做标杆 + 快照分析数据）"""
    stats = snapshot.get("channel_stats", {})
    videos = snapshot.get("videos", [])
    growth = snapshot.get("growth", {})

    subs = stats.get("subscribers", 0)
    total_views = stats.get("total_views", 0)
    total_videos = stats.get("total_videos", 0)
    avg_views = total_views // max(total_videos, 1)

    diagnosis = {
        "subscribers": subs,
        "total_views": total_views,
        "total_videos": total_videos,
        "avg_views": avg_views,
    }

    # 从快照合并频道级分析数据
    for field in ["posting_pattern", "duration_impact", "view_distribution",
                   "engagement_funnel", "content_consistency", "seo_analysis",
                   "title_patterns"]:
        val = snapshot.get(field)
        if val:
            diagnosis[field] = val

    # 生成频道级诊断建议（diagnostics）
    diagnostics = _generate_channel_diagnostics(snapshot, distill, diagnosis)
    if diagnostics:
        diagnosis["diagnostics"] = diagnostics

    # 市场对标
    llm_insights = market.get("llm_insights", {})
    if llm_insights:
        competition = llm_insights.get("competition", {})
        what = llm_insights.get("what_they_watch", {})
        diagnosis["market_context"] = {
            "top_themes": what.get("hot_themes", [])[:5] if isinstance(what, dict) else [],
            "audience": what.get("audience_profile", "") if isinstance(what, dict) else "",
            "competition": competition.get("top_channels", [])[:3] if isinstance(competition, dict) else [],
        }

    # 增长趋势
    if growth.get("has_prev"):
        diagnosis["growth"] = {
            "sub_change": growth.get("subscribers_change", 0),
            "view_change": growth.get("views_change", 0),
            "sub_change_pct": growth.get("subscribers_change_pct", 0),
            "view_change_pct": growth.get("views_change_pct", 0),
        }

    # ═══ 视频级趋势分析（按发布日期）═══
    if videos:
        from datetime import datetime
        sorted_videos = sorted(videos, key=lambda x: x.get("published_at", ""))

        # 播放量趋势（最近20条）
        recent = sorted_videos[-20:]
        view_trend = []
        for v in recent:
            pub = v.get("published_at", "")[:10]
            views = v.get("views", 0)
            likes = v.get("likes", 0)
            lr = round(likes / max(views, 1) * 100, 2)
            view_trend.append({
                "date": pub,
                "title": v.get("title", "")[:50],
                "views": views,
                "like_rate": lr
            })
        diagnosis["video_trend"] = view_trend

        # 发布频率统计
        if len(sorted_videos) >= 2:
            first_date = datetime.fromisoformat(sorted_videos[0].get("published_at", "").replace("Z", "+00:00"))
            last_date = datetime.fromisoformat(sorted_videos[-1].get("published_at", "").replace("Z", "+00:00"))
            span_days = max((last_date - first_date).days, 1)
            diagnosis["publish_frequency"] = {
                "total_days": span_days,
                "total_videos": len(videos),
                "avg_per_day": round(len(videos) / span_days, 2),
                "avg_per_week": round(len(videos) / span_days * 7, 1),
            }

        # 播放量分布
        views_list = [v.get("views", 0) for v in videos]
        if views_list:
            sorted_views = sorted(views_list, reverse=True)
            top5_avg = sum(sorted_views[:5]) / max(len(sorted_views[:5]), 1)
            bottom5_avg = sum(sorted_views[-5:]) / max(len(sorted_views[-5:]), 1)
            median_idx = len(sorted_views) // 2
            diagnosis["view_stats"] = {
                "max": sorted_views[0],
                "min": sorted_views[-1],
                "median": sorted_views[median_idx],
                "top5_avg": round(top5_avg),
                "bottom5_avg": round(bottom5_avg),
                "top_bottom_ratio": round(top5_avg / max(bottom5_avg, 1), 1),
            }

        # 赞率趋势（最近10条）
        recent_lr = []
        for v in sorted_videos[-10:]:
            views = v.get("views", 0)
            likes = v.get("likes", 0)
            if views > 0:
                recent_lr.append(round(likes / views * 100, 2))
        if recent_lr:
            diagnosis["like_rate_trend"] = {
                "recent_10_avg": round(sum(recent_lr) / len(recent_lr), 2),
                "min": min(recent_lr),
                "max": max(recent_lr),
                "trend": "上升" if len(recent_lr) >= 3 and recent_lr[-1] > recent_lr[0] else "下降" if len(recent_lr) >= 3 and recent_lr[-1] < recent_lr[0] else "稳定",
            }

    return diagnosis


def _load_competitor_insights(lang: str) -> list:
    """加载同语种竞品频道的LLM分析数据"""
    lang_map = {"en": "英文", "es": "西语", "pt": "葡萄牙", "id": "印尼", "繁中": "繁中", "zh-CN": "繁中"}
    lang_cn = lang_map.get(lang, lang)
    insights_dir = ROOT / "data" / "competitor_insights"
    competitors = []
    for f in insights_dir.glob("channel_*.json"):
        try:
            d = json.loads(f.read_text())
            if d.get("language") == lang_cn and "llm_analysis" in d:
                llm = d["llm_analysis"]
                distill = llm.get("distill", {})
                stats = llm.get("stats", {})
                competitors.append({
                    "name": d.get("name", ""),
                    "subscribers": d.get("subscribers", 0),
                    "avg_views": d.get("avg_views", 0),
                    "growth_drivers": distill.get("why", {}).get("growth_drivers", []),
                    "trajectory": distill.get("why", {}).get("trajectory", ""),
                    "content_strategy": distill.get("what", {}).get("content_strategy", ""),
                    "top_themes": distill.get("what", {}).get("top_themes", []),
                    "hook_patterns": distill.get("what", {}).get("hook_patterns", []),
                    "like_rate": stats.get("like_rate", 0),
                })
        except Exception:
            continue
    return sorted(competitors, key=lambda x: x.get("subscribers", 0), reverse=True)


def _discover_genre(videos: list) -> dict:
    """Step 1: 从视频标题自动发现频道题材"""
    from collections import Counter
    titles = ' '.join(v.get('title', '') for v in videos).lower()
    tags = []
    for v in videos:
        tags.extend(v.get('description_tags', []))
    tags_text = ' '.join(tags).lower()
    all_text = f"{titles} {tags_text}"

    genre_signals = {
        '末世/灾难': ['apocalypse', 'doomsday', 'disaster', 'frozen', 'blizzard', 'flood', 'zombie', 'catastrophe', 'wasteland'],
        '重生/穿越': ['reborn', 'transmigrated', 'rebirth', 'transmigration', 'time travel'],
        '空间/系统': ['spatial', 'space ability', 'storage', 'system', 'stockpil', 'safe house', 'inventory'],
        '复仇/打脸': ['revenge', 'traitor', 'hell', 'begs', 'kneeling', 'slap', 'strike back', 'payback'],
        'CEO/豪门': ['ceo', 'billionaire', 'tycoon', 'mogul', 'heir', 'wealthy', 'rich', '豪门', '总裁'],
        '甜宠/恋爱': ['love', 'romance', 'sweet', 'husband', 'wife', 'marry', 'pregnant', 'contract'],
        '女性向': ['queen', 'concubine', 'girlfriend', 'princess', 'goddess', 'beauty'],
        '男频/逆袭': ['underdog', 'loser', 'nobody', 'weak', 'trash', 'awakening', 'power up'],
    }

    detected = {}
    for genre, keywords in genre_signals.items():
        hits = [k for k in keywords if k in all_text]
        if hits:
            detected[genre] = hits

    sorted_genres = sorted(detected.items(), key=lambda x: -len(x[1]))
    primary = sorted_genres[0][0] if sorted_genres else '未分类'
    sub_genres = [g[0] for g in sorted_genres[:3]]

    return {
        'primary': primary,
        'sub_genres': sub_genres,
        'signals': {g: h for g, h in sorted_genres},
    }


def _load_ctr_cache(slug: str) -> dict:
    """读 data/own/analytics/{slug}_ctr.json；不存在返回 {}。"""
    if not slug:
        return {}
    p = ROOT / "data" / "own" / "analytics" / f"{slug}_ctr.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _channel_ctr_slug(stats: dict, snapshot: dict) -> str:
    """从 snapshot/stats 反解 CTR 缓存的 slug。"""
    # snapshot 里可能直接带 slug
    for key in ("_slug", "slug", "channel_slug"):
        s = snapshot.get(key) or stats.get(key)
        if s:
            return s
    # 用频道名反解（复用 _resolve_oauth_slug 的逻辑）
    name = stats.get("name", "")
    if not name:
        return ""
    try:
        return _resolve_oauth_slug(name, name.replace(" ", "_"))
    except Exception:
        return ""


def _compute_ctr_findings(stats: dict, yt_analytics: dict, snapshot: dict) -> dict:
    """批3.1: findings["ctr"] — 每视频 {videoId, impressions, ctr, status} + 频道汇总。"""
    slug = _channel_ctr_slug(stats, snapshot)
    cache = _load_ctr_cache(slug)
    if not cache or cache.get("status") == "pending":
        return {
            "status": "pending" if cache else "no_data",
            "slug": slug,
            "videos": [],
            "channel": {"impressions_28d": 0, "ctr_median_28d": 0.0,
                        "impressions_to_views_ratio": None},
            "note": "CTR job pending (报表 24-48h 后可用)" if cache
                    else "无 CTR job，未接入 Reporting API",
        }
    vids_map = cache.get("videos", {})
    ctr_videos = []
    for vid, d in vids_map.items():
        imp = d.get("impressions_28d", 0)
        if imp < 500:
            status = "样本不足"
        elif imp < 2000:
            status = "低置信"
        else:
            status = "ok"
        ctr_videos.append({
            "video_id": vid,
            "impressions": imp,
            "ctr": d.get("ctr_28d", 0.0),
            "days_with_data": d.get("days_with_data", 0),
            "status": status,
        })
    # 频道级：展示总量 + 中位数 + 展示:播放比
    ch = cache.get("channel_totals", {})
    total_imp = ch.get("impressions_28d", 0)
    # 从 yt_analytics.summary 拿 28d 播放（近似：collect 用 30d，用其 views）
    period_views = 0
    if yt_analytics and yt_analytics.get("summary"):
        srow = yt_analytics["summary"].get("rows", [[]])[0] if yt_analytics["summary"].get("rows") else []
        sheaders = yt_analytics["summary"].get("headers", [])
        if "views" in sheaders and srow:
            period_views = srow[sheaders.index("views")] or 0
    imp_to_view = (total_imp / period_views) if period_views > 0 else None
    return {
        "status": "ok",
        "slug": slug,
        "videos": ctr_videos,
        "channel": {
            "impressions_28d": total_imp,
            "ctr_median_28d": ch.get("ctr_median_28d", 0.0),
            "impressions_to_views_ratio": round(imp_to_view, 2) if imp_to_view else None,
            "video_count": ch.get("video_count", 0),
        },
        "date_range": cache.get("date_range", {}),
    }


def _compute_quadrant_findings(ctr_findings: dict, yt_analytics: dict, videos: list, snapshot: dict) -> dict:
    """批3.1: findings["quadrant"] — 四象限归类。含降级规则（第一条判定）。

    降级判定（按顺序）：
      1. 无 OAuth token 且无 CTR → status: "skipped"
      2. 有 OAuth 但 CTR pending → status: "provisional"，横轴用 7日播放/28日中位数代理
      3. 完整数据 → status: "ok"，CTR × AVD占比 归类

    输出 _quadrant_source: "python" 标记。
    """
    ctr_status = ctr_findings.get("status", "no_data")
    has_oauth = bool(yt_analytics) and bool(yt_analytics.get("summary"))

    # 降级1：无 OAuth 且无 CTR
    if not has_oauth and ctr_status in ("no_data", "pending"):
        return {
            "_quadrant_source": "python",
            "status": "skipped",
            "reason": "无OAuth/CTR数据",
            "buckets": {},
        }

    # 降级2：有 OAuth 但 CTR pending → provisional，横轴用播放代理
    if ctr_status == "pending" and has_oauth:
        return _quadrant_provisional(yt_analytics, videos)

    # 降级3：无 OAuth 但有 CTR（罕见）→ 也按 provisional 处理
    if ctr_status == "ok" and not has_oauth:
        return _quadrant_provisional_ctr_only(ctr_findings, videos)

    # 正常路径：CTR × AVD占比
    return _quadrant_ok(ctr_findings, yt_analytics, videos)


def _title_lookup(videos: list, yt_analytics: dict) -> dict:
    """videoId -> title，多级回退。"""
    title_map = {}
    for v in videos:
        vid = v.get("id") or v.get("video_id")
        if vid:
            title_map[vid] = v.get("title", "")
    # 从 yt_analytics.video_meta 补
    vm = (yt_analytics or {}).get("video_meta", {}).get("titles", {})
    for vid, t in vm.items():
        if vid not in title_map or not title_map[vid]:
            title_map[vid] = t
    return title_map


def _video_duration_sec(videos: list) -> dict:
    """videoId -> 时长(秒)，读 ISO8601 duration。"""
    import re as _re
    out = {}
    for v in videos:
        vid = v.get("id") or v.get("video_id")
        dur = v.get("duration", "") or v.get("duration_iso", "")
        if not vid or not dur:
            continue
        m = _re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur)
        if m:
            out[vid] = int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)
    return out


def _quadrant_ok(ctr_findings: dict, yt_analytics: dict, videos: list) -> dict:
    """CTR × AVD占比 正常归类。"""
    # AVD 数据从 top_videos 读（headers 含 averageViewDuration/averageViewPercentage）
    tv = (yt_analytics or {}).get("top_videos", {})
    headers = tv.get("headers", [])
    rows = tv.get("rows", [])
    idx = {h: i for i, h in enumerate(headers)}
    avd_map = {}
    for r in rows:
        vid = r[idx.get("video", 0)]
        dur_s = r[idx["averageViewDuration"]] if "averageViewDuration" in idx else 0
        pct = r[idx["averageViewPercentage"]] if "averageViewPercentage" in idx else 0
        avd_map[vid] = {"avg_duration_s": dur_s, "avg_pct": pct}

    # 视频时长（用于 avg_pct 缺失时回退）
    dur_map = _video_duration_sec(videos)
    title_map = _title_lookup(videos, yt_analytics)

    # 留存 1pct（存入每视频的 hook_1pct 供 LLM 分型，但不参与归类）
    ret_videos = ((yt_analytics or {}).get("retention", {}) or {}).get("videos", [])
    hook_1pct_map = {v.get("video_id"): v.get("retention_1pct") for v in ret_videos}

    buckets = {
        "爆款基因": [], "标题超卖_开头型": [], "标题超卖_中段型": [],
        "门面拖累": [], "选题失败": [], "表现平庸": [],
        "样本不足": [], "数据异常待核实": [],
    }

    for cv in ctr_findings.get("videos", []):
        vid = cv["video_id"]
        imp = cv["impressions"]
        ctr = cv["ctr"]  # 小数
        status = cv["status"]
        title = title_map.get(vid, vid)
        avd = avd_map.get(vid, {})
        avd_pct = avd.get("avg_pct") or 0
        avd_s = avd.get("avg_duration_s") or 0
        hook_1pct = hook_1pct_map.get(vid)

        # 异常隔离
        if hook_1pct is not None and hook_1pct < 0.05:
            buckets["数据异常待核实"].append(_qv(vid, title, imp, ctr, avd_pct, hook_1pct, "1%留存<5%"))
            continue
        if status == "样本不足":
            buckets["样本不足"].append(_qv(vid, title, imp, ctr, avd_pct, hook_1pct, "展示<500"))
            continue

        # CTR 横轴阈值（1-2h 超长短剧）
        ctr_pct = ctr * 100
        if ctr_pct >= 6:
            ctr_band = "high"
        elif ctr_pct < 2.5:
            ctr_band = "low"
        else:
            ctr_band = "mid"

        # AVD 纵轴：avg_pct，缺失回退到 AVD 秒数
        if avd_pct > 0:
            if avd_pct >= 15:
                avd_band = "high"
            elif avd_pct < 10:
                avd_band = "low"
            else:
                avd_band = "mid"
        elif avd_s > 0:
            if avd_s >= 900:
                avd_band = "high"
            elif avd_s < 480:
                avd_band = "low"
            else:
                avd_band = "mid"
        else:
            avd_band = "mid"  # 无 AVD 数据保守走中间带

        # 归类
        if ctr_band == "mid" or avd_band == "mid":
            bucket = "表现平庸"
        elif ctr_band == "high" and avd_band == "high":
            bucket = "爆款基因"
        elif ctr_band == "high" and avd_band == "low":
            # 分型：hook_1pct<80% 开头型；≥80% 中段型
            if hook_1pct is not None and hook_1pct < 0.80:
                bucket = "标题超卖_开头型"
            else:
                bucket = "标题超卖_中段型"
        elif ctr_band == "low" and avd_band == "high":
            bucket = "门面拖累"
        else:  # low, low
            bucket = "选题失败"

        note = "低置信" if status == "低置信" else ""
        buckets[bucket].append(_qv(vid, title, imp, ctr, avd_pct, hook_1pct, note))

    return {
        "_quadrant_source": "python",
        "status": "ok",
        "buckets": buckets,
        "axis_meta": {
            "x": "CTR (阈值: <2.5% low / 2.5-6% mid / ≥6% high)",
            "y": "AVD占比 (阈值: <10% low / 10-15% mid / ≥15% high)",
            "note": "1%留存不参与归类，仅供分型标题超卖开头型/中段型",
        },
    }


def _qv(vid, title, imp, ctr, avd_pct, hook_1pct, note):
    return {
        "video_id": vid, "title": title,
        "impressions": imp, "ctr": round(ctr, 4),
        "avd_pct": round(avd_pct or 0, 1),
        "hook_1pct": round(hook_1pct, 3) if hook_1pct else None,
        "note": note,
    }


def _quadrant_provisional(yt_analytics: dict, videos: list) -> dict:
    """有 OAuth 但 CTR pending：横轴用 7日播放/频道28日播放中位数 代理。"""
    tv = (yt_analytics or {}).get("top_videos", {})
    headers = tv.get("headers", [])
    rows = tv.get("rows", [])
    idx = {h: i for i, h in enumerate(headers)}
    if not rows or "views" not in idx:
        return {"_quadrant_source": "python", "status": "provisional",
                "reason": "无 top_videos 数据", "buckets": {}}
    views_all = sorted([r[idx["views"]] for r in rows if r[idx["views"]]])
    median_views = views_all[len(views_all) // 2] if views_all else 1

    title_map = _title_lookup(videos, yt_analytics)
    buckets = {
        "爆款基因_provisional": [], "标题超卖_provisional": [],
        "门面拖累_provisional": [], "选题失败_provisional": [],
        "表现平庸_provisional": [],
    }
    for r in rows:
        vid = r[idx["video"]]
        views = r[idx["views"]]
        avd_pct = r[idx["averageViewPercentage"]] if "averageViewPercentage" in idx else 0
        title = title_map.get(vid, vid)
        # 横轴代理：views / median_views
        ratio = views / median_views if median_views > 0 else 1
        if ratio >= 1.5:
            x = "high"
        elif ratio < 0.5:
            x = "low"
        else:
            x = "mid"
        if avd_pct >= 15:
            y = "high"
        elif avd_pct < 10:
            y = "low"
        else:
            y = "mid"
        item = {"video_id": vid, "title": title, "views": views,
                "avd_pct": round(avd_pct, 1), "views_ratio": round(ratio, 2)}
        if x == "mid" or y == "mid":
            buckets["表现平庸_provisional"].append(item)
        elif x == "high" and y == "high":
            buckets["爆款基因_provisional"].append(item)
        elif x == "high" and y == "low":
            buckets["标题超卖_provisional"].append(item)
        elif x == "low" and y == "high":
            buckets["门面拖累_provisional"].append(item)
        else:
            buckets["选题失败_provisional"].append(item)
    return {
        "_quadrant_source": "python", "status": "provisional",
        "reason": "CTR job pending，横轴用播放代理",
        "buckets": buckets,
        "axis_meta": {"x": "7日播放÷28日中位数 (临时代理，等CTR数据)",
                      "y": "AVD占比"},
    }


def _quadrant_provisional_ctr_only(ctr_findings, videos):
    return {"_quadrant_source": "python", "status": "provisional",
            "reason": "有 CTR 无 OAuth AVD（罕见）", "buckets": {}}


def _compute_sub_conversion(yt_analytics: dict, snapshot: dict) -> dict:
    """批3.1: findings["sub_conversion"] — 每视频 sub_conversion + Top3/Bottom3 排序。"""
    tv = (yt_analytics or {}).get("top_videos", {})
    headers = tv.get("headers", [])
    rows = tv.get("rows", [])
    idx = {h: i for i, h in enumerate(headers)}
    if not rows or "subscribersGained" not in idx or "views" not in idx:
        return {"status": "no_data", "reason": "top_videos 无 subscribersGained 字段（需重跑采集）"}

    videos = snapshot.get("videos", [])
    title_map = _title_lookup(videos, yt_analytics)

    per_video = []
    total_gained = 0
    total_lost = 0
    for r in rows:
        vid = r[idx["video"]]
        views = r[idx["views"]] or 0
        gained = r[idx["subscribersGained"]] or 0
        lost = r[idx["subscribersLost"]] if "subscribersLost" in idx else 0
        total_gained += gained
        total_lost += lost
        if views <= 0:
            continue
        conv = gained / views  # 小数
        per_video.append({
            "video_id": vid,
            "title": title_map.get(vid, vid),
            "views": views,
            "subs_gained": gained,
            "subs_lost": lost,
            "sub_conversion": round(conv, 5),
        })
    per_video.sort(key=lambda x: x["sub_conversion"], reverse=True)
    # 频道级
    if total_gained > 0:
        overall_conv = sum(v["subs_gained"] for v in per_video) / max(sum(v["views"] for v in per_video), 1)
        if overall_conv >= 0.005:
            level = "优秀"
        elif overall_conv >= 0.002:
            level = "一般"
        else:
            level = "较差"
    else:
        overall_conv = 0
        level = "无数据"
    return {
        "status": "ok",
        "top3": per_video[:3],
        "bottom3": [v for v in per_video[-3:] if v["sub_conversion"] > 0] or per_video[-3:],
        "channel_overall_conversion": round(overall_conv, 5),
        "channel_level": level,
        "total_gained": total_gained,
        "total_lost": total_lost,
    }


def _compute_monetization(stats: dict, yt_analytics: dict) -> dict:
    """批3.1: findings["monetization"] — YPP门槛分项判定，达标标 ✅。"""
    subs = stats.get("subscribers", 0)
    # 近12月观看时长（小时）：优先从 stats/yt_analytics 拿
    watch_hours = None
    if yt_analytics and yt_analytics.get("summary"):
        srow = yt_analytics["summary"].get("rows", [[]])[0] if yt_analytics["summary"].get("rows") else []
        sheaders = yt_analytics["summary"].get("headers", [])
        if "estimatedMinutesWatched" in sheaders and srow:
            # 注意：summary 是 30d 窗口，非 12mo，这里只作参考
            minutes = srow[sheaders.index("estimatedMinutesWatched")] or 0
            watch_hours = round(minutes / 60, 1)
    # 分项判定
    subs_ok = subs >= 1000
    subs_gap = max(0, 1000 - subs)
    hours_status = None
    hours_gap = None
    hours_ok = False
    if watch_hours is not None:
        # 保守：只标注 30d 窗口，YPP 阈值是 4000h/12mo，这里给参考
        hours_status = f"30d窗口={watch_hours}h（YPP阈值4000h/12mo，需另计算）"
        # 不做 ok 判定（数据窗口不匹配）
    return {
        "subscribers": {
            "value": subs, "threshold": 1000,
            "ok": subs_ok,
            "display": f"订阅 {subs}/1000 {'✅已达标' if subs_ok else f'缺口{subs_gap}'}",
        },
        "watch_hours": {
            "value_30d": watch_hours,
            "threshold_12mo": 4000,
            "note": hours_status or "无 OAuth 数据，无法评估",
            "display": "观看时长: 30d 采集窗口不等于 YPP 的 12mo 累计，需另跑长窗口查询",
        },
        "ypp_ready": subs_ok,  # 只以订阅达标作为初判（时长口径不匹配）
    }


def prepare_channel_findings(snapshot: dict, distill: dict, lang: str) -> dict:
    """Step 2: 研究 — 采集所有数据，输出结构化findings

    按维度逐个分析，每个维度输出标准化结论。
    LLM不参与此步骤，纯Python确定性计算。
    """
    import re
    from datetime import datetime
    from collections import Counter

    stats = snapshot.get("channel_stats", {})
    videos = sorted(snapshot.get("videos", []), key=lambda x: x.get("published_at", ""))
    growth = snapshot.get("growth", {})
    channel_diag = snapshot.get("_channel_diag", {})
    analytics = snapshot.get("analytics", {})
    yt_analytics = snapshot.get("yt_analytics", {})

    if not videos:
        return {}

    # ── 基础信息 ──
    subs = stats.get("subscribers", 0)
    total_views = stats.get("total_views", 0)
    total_videos = stats.get("total_videos", 0)
    avg_views = total_views // max(total_videos, 1)

    channel_created = stats.get("published_at", "")
    channel_age_days = 0
    channel_age_text = "未知"
    if channel_created:
        try:
            created_dt = datetime.fromisoformat(channel_created.replace("Z", "+00:00"))
            now = datetime.now(created_dt.tzinfo)
            channel_age_days = (now - created_dt).days
            months = channel_age_days // 30
            channel_age_text = f"{months}个月（{channel_age_days}天）" if months > 0 else f"{channel_age_days}天"
        except:
            pass

    # ── 题材发现（Step 1）──
    genre = _discover_genre(videos)

    # ── 视频时长分布 ──
    duration_buckets = {"Shorts(<60s)": 0, "1-5min": 0, "5-30min": 0, "30-60min": 0, "1hr+": 0}
    for v in videos:
        dur = v.get("duration", "")
        if not dur:
            continue
        try:
            match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', dur)
            if match:
                total_seconds = int(match.group(1) or 0) * 3600 + int(match.group(2) or 0) * 60 + int(match.group(3) or 0)
                if total_seconds < 60: duration_buckets["Shorts(<60s)"] += 1
                elif total_seconds < 300: duration_buckets["1-5min"] += 1
                elif total_seconds < 1800: duration_buckets["5-30min"] += 1
                elif total_seconds < 3600: duration_buckets["30-60min"] += 1
                else: duration_buckets["1hr+"] += 1
        except: pass
    duration_text = "，".join(f"{k}:{v}条" for k, v in duration_buckets.items() if v > 0)

    # ── 标题分析（骨架/钩子/包装/长度）──
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).parent.parent / '.hermes' / 'skills' / 'automation' / 'duanju-youtube-expert' / 'scripts'))
        from analyze_titles_short_drama import score_title, identify_skeleton, analyze_hooks
        use_skill_script = True
    except:
        use_skill_script = False

    hook_stats = {"三重": 0, "双重": 0, "单一": 0, "无": 0}
    skeleton_counter = Counter()
    title_lengths = []
    title_scores = []
    for v in videos:
        t = v.get("title", "")
        title_lengths.append(len(t))
        if use_skill_script:
            result = score_title(t, 'en')
            hook_stats[result['hooks']['hook_type']] += 1
            for sk in result['skeletons']:
                skeleton_counter[sk] += 1
            title_scores.append(result['score'])

    avg_title_len = sum(title_lengths) / len(title_lengths) if title_lengths else 0
    how = distill.get("how", {})
    tc = how.get("title_constraints", {})
    best_len = tc.get("avg_length", 84)

    title_findings = {
        "avg_length": round(avg_title_len, 1),
        "best_length": best_len,
        "hook_distribution": dict(hook_stats),
        "skeleton_distribution": dict(skeleton_counter.most_common()),
        "double_triple_hook_pct": round((hook_stats["双重"] + hook_stats["三重"]) / max(len(videos), 1) * 100, 1),
        "unidentified_skeleton_pct": round(skeleton_counter.get("未识别", 0) / max(len(videos), 1) * 100, 1),
    }

    # ── 从 video_scores 聚合 LLM 分析结果（如果有）──
    llm_hook_stats = {"emotion": 0, "identity": 0, "reversal": 0, "time": 0, "conflict": 0, "relationship": 0}
    llm_hook_types = []  # 所有发现的钩子类型
    llm_skeleton_counter = Counter()
    cover_synergy_scores = []
    video_scores = snapshot.get("video_scores", [])
    if video_scores:
        for vs in video_scores:
            # 聚合钩子
            ta = vs.get("title_analysis") or {}
            hooks = ta.get("hooks", {})
            for htype in llm_hook_stats:
                if hooks.get(htype):
                    llm_hook_stats[htype] += 1
            llm_hook_types.extend(ta.get("hook_types_found", []))
            # 聚合骨架
            skel = ta.get("skeleton", "")
            if skel:
                llm_skeleton_counter[skel] += 1
            # 聚合封面协同
            cs = vs.get("cover_synergy", {})
            if cs and cs.get("score"):
                cover_synergy_scores.append(cs["score"])

    title_findings["llm_hook_distribution"] = llm_hook_stats
    title_findings["llm_hook_types"] = llm_hook_types[:20]  # 保留前20个
    title_findings["llm_skeleton_distribution"] = dict(llm_skeleton_counter.most_common(5))
    if cover_synergy_scores:
        title_findings["avg_cover_synergy"] = round(sum(cover_synergy_scores) / len(cover_synergy_scores), 1)

    # ── 从LLM hooks计算双重/三重钩子占比（替代Python score_title的不准统计）──
    llm_hook_level_stats = {"三重": 0, "双重": 0, "单一": 0, "无": 0}
    llm_hook_count_total = 0
    if video_scores:
        for vs in video_scores:
            ta = vs.get("title_analysis") or {}
            hooks = ta.get("hooks", {})
            active = sum(1 for k in ("emotion", "identity", "reversal", "time", "conflict", "relationship") if hooks.get(k))
            other = hooks.get("other", [])
            if isinstance(other, list):
                active += len(other)
            llm_hook_count_total += 1
            if active >= 3:
                llm_hook_level_stats["三重"] += 1
            elif active == 2:
                llm_hook_level_stats["双重"] += 1
            elif active == 1:
                llm_hook_level_stats["单一"] += 1
            else:
                llm_hook_level_stats["无"] += 1
    title_findings["llm_hook_level_distribution"] = llm_hook_level_stats
    title_findings["llm_double_triple_hook_pct"] = round(
        (llm_hook_level_stats["双重"] + llm_hook_level_stats["三重"]) / max(llm_hook_count_total, 1) * 100, 1
    ) if llm_hook_count_total > 0 else 0

    # ── 赞率分析（加权平均：总赞/总播，而非各视频简单平均）──
    total_likes = sum(v.get("likes", 0) for v in videos)
    total_views_lr = sum(v.get("views", 0) for v in videos)
    avg_lr = total_likes / max(total_views_lr, 1) * 100

    like_rates = []
    for v in videos:
        views = v.get("views", 0)
        likes = v.get("likes", 0)
        if views > 0:
            like_rates.append(likes / views * 100)

    like_rate_findings = {
        "avg_like_rate": round(avg_lr, 2),
        "max": round(max(like_rates), 2) if like_rates else 0,
        "min": round(min(like_rates), 2) if like_rates else 0,
        "benchmark": ">3%标杆 | 1.5-3%健康 | 1-1.5%一般 | <1%转化差",
        "status": "标杆" if avg_lr > 3 else "健康" if avg_lr > 1.5 else "一般" if avg_lr > 1 else "转化差",
    }

    # ── 赞率趋势 ──
    like_rate_trend = "数据不足"
    if len(videos) >= 10:
        recent_5 = videos[-5:]
        prev_5 = videos[-10:-5]
        recent_lr = sum(v.get("likes", 0) / max(v.get("views", 1), 1) for v in recent_5) / 5 * 100
        prev_lr = sum(v.get("likes", 0) / max(v.get("views", 1), 1) for v in prev_5) / 5 * 100
        if recent_lr > prev_lr * 1.1: like_rate_trend = f"上升（{prev_lr:.1f}% → {recent_lr:.1f}%）"
        elif recent_lr < prev_lr * 0.9: like_rate_trend = f"下降（{prev_lr:.1f}% → {recent_lr:.1f}%）"
        else: like_rate_trend = f"稳定（{prev_lr:.1f}% → {recent_lr:.1f}%）"

    # ── 播放分布 ──
    sorted_views = sorted([v.get("views", 0) for v in videos], reverse=True)
    top3_views = sum(sorted_views[:3])
    top3_ratio = top3_views / max(sum(sorted_views), 1) * 100

    view_dist_findings = {
        "top3_ratio": round(top3_ratio, 1),
        "top3_videos": sorted_views[:3],
        "benchmark": "头部集中是YouTube正常现象，关注可复制模式",
        "status": "头部集中" if top3_ratio > 50 else "有集中" if top3_ratio > 30 else "均匀",
    }

    # ── SEO分析 ──
    tag_counts = [len(v.get("description_tags", [])) for v in videos]
    avg_tags = sum(tag_counts) / len(tag_counts) if tag_counts else 0
    all_tags = []
    for v in videos:
        all_tags.extend(v.get("description_tags", []))
    tag_freq = Counter(all_tags)

    seo_findings = {
        "avg_tags_per_video": round(avg_tags, 1),
        "zero_tag_videos": sum(1 for t in tag_counts if t == 0),
        "top_tags": dict(tag_freq.most_common(10)),
        "all_same_tags": len(tag_freq) <= 7,
        "benchmark": "每条≥5标签",
    }

    # ── 增长数据 ──
    growth_findings = {"has_prev": growth.get("has_prev", False)}
    if growth.get("has_prev"):
        growth_findings.update({
            "sub_change": growth.get("subscribers_change", 0),
            "sub_change_pct": growth.get("subscribers_change_pct", 0),
            "view_change": growth.get("views_change", 0),
            "view_change_pct": growth.get("views_change_pct", 0),
            "like_rate_change": f"{growth.get('like_rate_prev', 0)}% → {growth.get('like_rate_curr', 0)}%",
        })

    # ── 蒸馏匹配 ──
    key_words = tc.get("key_words", [])
    skeletons = how.get("title_skeletons", [])
    growth_strategy = how.get("growth_strategy", [])
    rhetorical = how.get("rhetorical_patterns", {})
    hooks = how.get("hook_combination", {})

    distill_findings = {
        "best_title_length": best_len,
        "hook_words": key_words[:12],
        "skeletons": [s.get("name", "") for s in skeletons[:5]],
        "growth_strategy": growth_strategy,
        "rhetorical_patterns": {
            "sentence_structures": [s.get("name", "") for s in rhetorical.get("sentence_structures", [])[:5]],
            "punctuation_strategy": rhetorical.get("punctuation_strategy", ""),
        },
        "hook_combination": {
            "golden_triangle": hooks.get("golden_triangle", ""),
            "strongest_pairs": hooks.get("strongest_pairs", [])[:5],
        },
    }

    # ── 竞品匹配 ──
    competitors = _load_competitor_insights(lang)
    comp_findings = []
    if competitors:
        for c in competitors[:3]:
            comp_findings.append({
                "name": c.get("name", ""),
                "subscribers": c.get("subscribers", 0),
                "avg_views": c.get("avg_views", 0),
                "like_rate": c.get("like_rate", 0),
                "growth_drivers": c.get("growth_drivers", [])[:2],
                "content_strategy": c.get("content_strategy", "")[:100],
            })

    # ── OAuth分析 ──
    oauth_findings = {"has_data": bool(analytics)}
    if analytics:
        avg_pct = min(analytics.get("averageViewPercentage", 0), 100)  # clamp >100 API异常
        avg_dur = analytics.get("averageViewDuration", 0)
        ratios = analytics.get("traffic_ratios", {})
        traffic_raw = analytics.get("traffic_sources", {})
        browse = ratios.get("RELATED_VIDEO", 0)
        sub_pct = ratios.get("SUBSCRIBER", 0)
        search_pct = ratios.get("YT_SEARCH", 0)
        other_page_pct = ratios.get("YT_OTHER_PAGE", 0)
        channel_page_pct = ratios.get("YT_CHANNEL", 0)
        playlist_pct = ratios.get("PLAYLIST", 0)
        ext_url_pct = ratios.get("EXT_URL", 0)
        notification_pct = ratios.get("NOTIFICATION", 0)
        geo = analytics.get("geo", {})
        demo = analytics.get("demographics", [])

        # 流量健康度
        browse_health = "强（算法在推）" if browse > 50 else "中（有推荐但不稳定）" if browse > 30 else "弱（算法信任度低）"
        sub_health = "强（粉丝粘性好）" if sub_pct > 30 else "中" if sub_pct > 15 else "弱"

        # 频道权重判断（综合指标）
        weight_score = 0
        if browse > 50: weight_score += 3
        elif browse > 30: weight_score += 2
        elif browse > 15: weight_score += 1
        if avg_pct > 25: weight_score += 3
        elif avg_pct > 15: weight_score += 2
        elif avg_pct > 10: weight_score += 1
        if sub_pct > 30: weight_score += 2
        elif sub_pct > 15: weight_score += 1
        weight_label = "强（算法高度信任）" if weight_score >= 7 else "中（算法在测试）" if weight_score >= 4 else "弱（算法信任度低）"

        # 受众完整分布
        female_pct = sum(d['pct'] for d in demo if d.get('gender') == 'female')
        male_pct = sum(d['pct'] for d in demo if d.get('gender') == 'male')
        age_groups = {}
        for d in demo:
            age = d.get('age', '')
            age_groups[age] = age_groups.get(age, 0) + d.get('pct', 0)
        top_age = max(age_groups.items(), key=lambda x: x[1]) if age_groups else ('?', 0)
        # 按性别分的年龄分布
        female_ages = {d['age']: d['pct'] for d in demo if d.get('gender') == 'female'}
        male_ages = {d['age']: d['pct'] for d in demo if d.get('gender') == 'male'}

        oauth_findings.update({
            "period": analytics.get("period", "30d"),
            "total_views": analytics.get("views", 0),
            "total_likes": analytics.get("likes", 0),
            "total_comments": analytics.get("comments", 0),
            "retention_pct": avg_pct,
            "avg_view_duration_sec": avg_dur,
            "total_watch_minutes": analytics.get("estimatedMinutesWatched", 0),
            "subscribers_gained": analytics.get("subscribersGained", 0),
            "subscribers_lost": analytics.get("subscribersLost", 0),
            "net_subscribers": analytics.get("subscribersGained", 0) - analytics.get("subscribersLost", 0),
            "shares": analytics.get("shares", 0),
            "traffic": {
                "browse_pct": browse,
                "subscriber_pct": sub_pct,
                "search_pct": search_pct,
                "other_page_pct": other_page_pct,
                "channel_page_pct": channel_page_pct,
                "playlist_pct": playlist_pct,
                "ext_url_pct": ext_url_pct,
                "notification_pct": notification_pct,
                "browse_health": browse_health,
                "subscriber_health": sub_health,
            },
            "channel_weight": {
                "score": weight_score,
                "label": weight_label,
                "indicators": {
                    "browse_pct": browse,
                    "retention_pct": avg_pct,
                    "subscriber_pct": sub_pct,
                },
            },
            "geo": dict(geo),
            "audience": {
                "female_pct": round(female_pct, 1),
                "male_pct": round(male_pct, 1),
                "top_age_group": top_age[0],
                "top_age_pct": round(top_age[1], 1),
                "age_distribution": {age: round(age_groups.get(age, 0), 1) for age in ['age13-17', 'age18-24', 'age25-34', 'age35-44', 'age45-54', 'age55-64', 'age65-']},
                "female_ages": dict(female_ages),
                "male_ages": dict(male_ages),
            },
        })

    # ── 封面分析 ──
    cover_findings = {"has_data": False}
    slug = stats.get("name", "").replace(" ", "_")
    cover_path = ROOT / "data" / "own" / "channel_diagnosis" / f"{slug}_covers.json"
    if cover_path.exists():
        try:
            cover_data = json.loads(cover_path.read_text(encoding="utf-8"))
            avg_scores = cover_data.get("avg_scores", {})
            if avg_scores:
                # 计算封面×标题协同平均分
                synergy_scores = []
                for cover in cover_data.get("covers", cover_data.get("details", [])):
                    syn = cover.get("封面×标题协同", {})
                    if syn.get("score"):
                        synergy_scores.append(syn["score"])
                avg_synergy = sum(synergy_scores) / len(synergy_scores) if synergy_scores else 0
                
                cover_findings = {
                    "has_data": True,
                    "overall": avg_scores.get("avg_overall_score", 0),
                    "composition": avg_scores.get("avg_composition_score", 0),
                    "person": avg_scores.get("avg_person_score", 0),
                    "color": avg_scores.get("avg_color_score", 0),
                    "emotion": avg_scores.get("avg_emotion_score", 0),
                    "prop": avg_scores.get("avg_prop_score", 0),
                    "text": avg_scores.get("avg_text_score", 0),
                    "title_synergy": round(avg_synergy, 1),
                    "top_suggestions": cover_data.get("top_suggestions", [])[:3],
                }
        except: pass

    # ── 分段留存分析（OAuth） ──
    retention_findings = {"has_data": False}
    retention_data = snapshot.get("retention_data")
    if retention_data and retention_data.get("has_data"):
        avg_1pct = retention_data.get("avg_retention_1pct")
        avg_3min = retention_data.get("avg_retention_3min")
        avg_5min = retention_data.get("avg_retention_5min")

        # 短剧留存基准（1-2小时视频）
        # 1%处（≈60-80秒）: >80%=hook强 60-80%=一般 <60%=流失严重
        # 3分钟: >30%=好 20-30%=一般 <20%=差
        # 5分钟: >25%=好 15-25%=一般 <15%=差
        hook_health = "未知"
        if avg_1pct is not None:
            hook_health = "强（前1分钟hook好）" if avg_1pct > 0.8 else "一般" if avg_1pct > 0.6 else "弱（开头流失严重）"

        retention_3min_health = "未知"
        if avg_3min is not None:
            retention_3min_health = "好" if avg_3min > 0.3 else "一般" if avg_3min > 0.2 else "差（3分钟大量流失）"

        # 找回弹最多的视频（说明中段有钩子）
        rebound_videos = [v for v in retention_data.get("videos", []) if v.get("rebounds")]

        retention_findings = {
            "has_data": True,
            "video_count": retention_data["video_count"],
            "avg_retention_1pct": avg_1pct,
            "avg_retention_3min": avg_3min,
            "avg_retention_5min": avg_5min,
            "hook_health": hook_health,
            "retention_3min_health": retention_3min_health,
            "rebounds_count": len(rebound_videos),
            "videos": retention_data.get("videos", []),
        }

    # ── 单视频AVD（从yt-analytics top_videos提取） ──
    avd_detail = {"has_data": False}
    _raw_top2 = yt_analytics.get("top_videos") if yt_analytics else None
    if _raw_top2:
        rows = _raw_top2.get("rows", [])
        avd_list = []
        for r in rows:
            if len(r) >= 6:
                vid_id = r[0]
                avg_sec = r[4]  # averageViewDuration in seconds
                avg_pct = min(r[5], 100)  # averageViewPercentage, clamp >100 API异常
                views = r[1]
                minutes = avg_sec // 60
                seconds = avg_sec % 60
                avd_list.append({
                    "video_id": vid_id,
                    "avg_duration_sec": avg_sec,
                    "avg_duration_text": f"{minutes}分{seconds:02d}秒({avg_pct}%)",
                    "avg_pct": avg_pct,
                    "views": views,
                })
        if avd_list:
            avd_detail = {"has_data": True, "videos": avd_list[:10]}

    # ── 设备类型分析（yt-analytics缓存） ──
    device_findings = {"has_data": False}
    if yt_analytics and yt_analytics.get("device"):
        device_rows = yt_analytics["device"]
        total_device_views = sum(d.get("views", 0) for d in device_rows)
        device_findings = {
            "has_data": True,
            "devices": [
                {"type": d.get("type", "UNKNOWN"), "views": d.get("views", 0),
                 "pct": round(d.get("views", 0) / total_device_views * 100, 1) if total_device_views else 0,
                 "minutes": d.get("minutes", 0)}
                for d in sorted(device_rows, key=lambda x: x.get("views", 0), reverse=True)
            ],
            "total_views": total_device_views,
        }

    # ── 流量来源详情（yt-analytics缓存，headers+rows格式） ──
    traffic_detail = {"has_data": False}
    _raw_traffic = yt_analytics.get("traffic") if yt_analytics else None
    if _raw_traffic:
        rows = _raw_traffic.get("rows", [])
        total_tv = sum(r[1] for r in rows if len(r) > 1) if rows else 0
        traffic_detail = {
            "has_data": True,
            "sources": [
                {"source": r[0], "views": r[1] if len(r) > 1 else 0,
                 "pct": round(r[1] / total_tv * 100, 1) if total_tv and len(r) > 1 else 0,
                 "watch_minutes": (r[2] // 60) if len(r) > 2 and r[2] else 0}
                for r in sorted(rows, key=lambda x: x[1] if len(x) > 1 else 0, reverse=True)
            ],
        }

    # ── 地域详情 ──
    geo_detail = {"has_data": False}
    _raw_geo = yt_analytics.get("geo") if yt_analytics else None
    if _raw_geo:
        rows = _raw_geo.get("rows", [])
        geo_detail = {
            "has_data": True,
            "top_regions": [
                {"region": r[0], "views": r[1] if len(r) > 1 else 0,
                 "watch_minutes": (r[2] // 60) if len(r) > 2 and r[2] else 0}
                for r in rows[:10]
            ],
        }

    # ── 热门视频详情 ──
    top_videos_detail = {"has_data": False}
    _raw_top = yt_analytics.get("top_videos") if yt_analytics else None
    if _raw_top:
        rows = _raw_top.get("rows", [])
        top_videos_detail = {
            "has_data": True,
            "videos": [
                {"title": r[0] if len(r) > 0 else "?",
                 "views": r[1] if len(r) > 1 else 0,
                 "watch_minutes": r[3] if len(r) > 3 else 0,
                 "avg_pct": r[5] if len(r) > 5 else 0}
                for r in rows[:10]
            ],
        }

    # ── 受众年龄×观看时长 ──
    demo_watch_detail = {"has_data": False}
    if yt_analytics and yt_analytics.get("demographics"):
        demo_rows = yt_analytics["demographics"]
        demo_watch_detail = {
            "has_data": True,
            "segments": [
                {"age": d.get("age", "?"), "gender": d.get("gender", "?"),
                 "pct": d.get("pct", 0), "est_minutes": d.get("est_minutes", 0)}
                for d in demo_rows
            ],
        }

    # ── 汇总 ──
    # ── CTR / 四象限 / 订阅转化 / 变现（批3新增） ──
    ctr_findings = _compute_ctr_findings(stats, yt_analytics, snapshot)
    quadrant_findings = _compute_quadrant_findings(ctr_findings, yt_analytics, videos, snapshot)
    sub_conv_findings = _compute_sub_conversion(yt_analytics, snapshot)
    monetization_findings = _compute_monetization(stats, yt_analytics)

    return {
        "channel": {
            "name": stats.get("name", ""),
            "subscribers": subs,
            "total_views": total_views,
            "total_videos": total_videos,
            "avg_views": avg_views,
            "language": lang,
            "age_days": channel_age_days,
            "age_text": channel_age_text,
        },
        "genre": genre,
        "duration_distribution": duration_text,
        "title_analysis": title_findings,
        "like_rate": like_rate_findings,
        "like_rate_trend": like_rate_trend,
        "view_distribution": view_dist_findings,
        "seo": seo_findings,
        "growth": growth_findings,
        "distill": distill_findings,
        "competitors": comp_findings,
        "oauth": oauth_findings,
        "cover": cover_findings,
        "retention": retention_findings,
        "device": device_findings,
        "traffic_detail": traffic_detail,
        "geo_detail": geo_detail,
        "top_videos_detail": top_videos_detail,
        "demo_watch": demo_watch_detail,
        "avd": avd_detail,
        "ctr": ctr_findings,
        "quadrant": quadrant_findings,
        "sub_conversion": sub_conv_findings,
        "monetization": monetization_findings,
    }


def llm_strategic_diagnosis(findings: dict, distill: dict) -> dict | None:
    """Step 3: 回答 — 基于findings做战略诊断（DeepSeek Pro）

    LLM只做判断，不做计算。所有数据已在Step 2算好。
    """
    from edgefn_models import call_for_task, parse_json_response

    ch = findings.get("channel", {})
    genre = findings.get("genre", {})
    title = findings.get("title_analysis") or {}
    lr = findings.get("like_rate", {})
    vd = findings.get("view_distribution", {})
    seo = findings.get("seo", {})
    oauth = findings.get("oauth", {})
    cover = findings.get("cover", {})
    dist = findings.get("distill", {})
    comps = findings.get("competitors", [])
    growth = findings.get("growth", {})
    retention = findings.get("retention", {})

    # 竞品文本
    comp_text = "无同赛道竞品"
    if comps:
        lines = []
        for c in comps:
            lines.append(f"  {c['name']}（订阅{c['subscribers']:,}，均播{c['avg_views']:,}，赞率{c['like_rate']}%）\n  增长驱动: {', '.join(c['growth_drivers'][:2])}")
        comp_text = "\n".join(lines)

    # OAuth文本
    oauth_text = "无OAuth数据"
    if oauth.get("has_data"):
        t = oauth.get("traffic", {})
        a = oauth.get("audience", {})
        geo = oauth.get("geo", {})
        geo_text = " / ".join(f"{c} {v:,}" for c, v in list(geo.items())[:5]) if geo else "无"
        w = oauth.get("channel_weight", {})
        age_dist = a.get("age_distribution", {})
        age_text = " / ".join(f"{k.replace('age','')}: {v}%" for k, v in age_dist.items() if v > 0)

        oauth_text = f"""30天数据（{oauth.get('period', '30d')}）:
播放: {oauth.get('total_views', 0):,} | 点赞: {oauth.get('total_likes', 0):,} | 评论: {oauth.get('total_comments', 0):,} | 分享: {oauth.get('shares', 0):,}
留存率: {oauth['retention_pct']}% | 平均观看: {oauth['avg_view_duration_sec']}秒 | 总观看: {oauth.get('total_watch_minutes', 0):,}分钟
订阅: +{oauth['subscribers_gained']}/-{oauth['subscribers_lost']}（净增{oauth.get('net_subscribers', 0)}）
频道权重: {w.get('label', '未知')}（推荐{w.get('indicators', {}).get('browse_pct', 0)}%/留存{w.get('indicators', {}).get('retention_pct', 0)}%/订阅{w.get('indicators', {}).get('subscriber_pct', 0)}%）
流量来源: 推荐{t['browse_pct']}%（{t['browse_health']}）/ 订阅{t['subscriber_pct']}%（{t['subscriber_health']}）/ 搜索{t['search_pct']}% / 其他页面{t.get('other_page_pct', 0)}% / 频道页{t.get('channel_page_pct', 0)}% / 播放列表{t.get('playlist_pct', 0)}% / 外部{t.get('ext_url_pct', 0)}%
CTR代理: 推荐流量{t['browse_pct']}%→{"隐性健康" if t["browse_pct"] > 40 else "可能偏低" if t["browse_pct"] < 20 else "一般"}
回访观众代理: 订阅流量{t['subscriber_pct']}%→{"粉丝回访占比高" if t["subscriber_pct"] > 25 else "主要靠新观众" if t["subscriber_pct"] < 15 else "中等"}
地域Top5: {geo_text}
受众: 女性{a['female_pct']}% / 男性{a['male_pct']}%，主力{a['top_age_group']}（{a['top_age_pct']}%）
年龄分布: {age_text}"""

    # 封面文本
    cover_text = "无封面分析数据"
    if cover.get("has_data"):
        synergy_score = cover.get('title_synergy', 0)
        synergy_text = f" | 封面×标题协同{synergy_score}" if synergy_score else ""
        cover_text = f"总分{cover['overall']}/10 | 构图{cover['composition']} 人物{cover['person']} 色彩{cover['color']} 情绪{cover['emotion']} 道具{cover['prop']} 文字{cover['text']}{synergy_text}"

    # 分段留存文本（OAuth）
    retention_text = "无分段留存数据（频道未OAuth授权）"
    if retention.get("has_data"):
        v1 = retention.get("avg_retention_1pct")
        v3 = retention.get("avg_retention_3min")
        v5 = retention.get("avg_retention_5min")
        lines_r = []
        if v1 is not None:
            lines_r.append(f"1%处（≈1分钟）: {v1:.0%} — {retention.get('hook_health', '')}")
        if v3 is not None:
            lines_r.append(f"3分钟处: {v3:.0%} — {retention.get('retention_3min_health', '')}")
        if v5 is not None:
            lines_r.append(f"5分钟处: {v5:.0%}")
        lines_r.append(f"有回弹的视频: {retention.get('rebounds_count', 0)}条（中段有钩子拉回观众）")
        # 逐视频明细
        for rv in retention.get("videos", [])[:5]:
            r1 = f"1%={rv['retention_1pct']:.0%}" if rv.get("retention_1pct") else ""
            r3 = f"3m={rv['retention_3min']:.0%}" if rv.get("retention_3min") else ""
            rbound = f"回弹{len(rv['rebounds'])}处" if rv.get("rebounds") else ""
            lines_r.append(f"  📹 {rv['video_id']}: {rv['views']}播放 {r1} {r3} {rbound}")
        retention_text = "\n".join(lines_r)

    # 逐视频诊断明细文本（按发布时间排序，最新的在最后）
    vs_list = sorted(findings.get("_video_scores", []), key=lambda x: x.get("published_at", ""))
    per_video_diag_text = "无单视频诊断数据"
    if vs_list:
        pv_lines = []
        for pv in vs_list[:15]:
            pv_vid = pv.get("video_id", "?")
            pv_title = _sanitize_title(pv.get("title", ""))[:45]
            pv_views = pv.get("views", 0)
            pv_lr = pv.get("like_rate", 0)
            pv_score = pv.get("score", 0)
            pv_ta = pv.get("title_analysis") or {}
            pv_cs = pv.get("cover_synergy") or {}
            pv_skeleton = pv_ta.get("skeleton", "—")
            pv_hooks = pv_ta.get("hook_types_found", [])
            pv_missing = pv_ta.get("missing", [])
            pv_hook_str = ", ".join(pv_hooks[:4]) if pv_hooks else "无"
            pv_miss_str = ", ".join(pv_missing[:2]) if pv_missing else "无"
            pv_cs_score = pv_cs.get("score", "—")
            pv_cs_pattern = pv_cs.get("synergy_pattern", "—")
            pv_lines.append(f"  📹 {pv_title} | {pv_views:,}播放 赞率{pv_lr}% 评分{pv_score}")
            pv_lines.append(f"     骨架: {pv_skeleton}")
            pv_lines.append(f"     钩子: {pv_hook_str}")
            pv_lines.append(f"     缺失: {pv_miss_str}")
            pv_lines.append(f"     封面协同: {pv_cs_score}分 | {pv_cs_pattern}")
        per_video_diag_text = "\n".join(pv_lines)

    # 单视频AVD文本
    avd = findings.get("avd", {})
    avd_text = "无单视频AVD数据"
    if avd.get("has_data"):
        avd_lines = []
        for v in avd["videos"][:5]:
            avd_lines.append(f"  {v['video_id']}: {v['avg_duration_text']} | {v['views']:,}播放")
        avd_text = "\n".join(avd_lines)

    # ── 批3新增：CTR / 四象限 / 订阅转化 / 变现 文本 ──
    ctr = findings.get("ctr", {})
    ctr_status_str = ctr.get("status", "no_data")
    ctr_text = "无CTR数据（无 Reporting API job）"
    if ctr_status_str == "pending":
        ctr_text = "CTR job pending — 报表 24-48h 后可用。当前诊断为临时版：门面（标题/封面）判断请用推荐流量占比作代理（>40%=隐性健康）。"
    elif ctr_status_str == "ok":
        ch_ctr = ctr.get("channel", {})
        imp = ch_ctr.get("impressions_28d", 0)
        cmed = ch_ctr.get("ctr_median_28d", 0)
        rat = ch_ctr.get("impressions_to_views_ratio")
        cnt = ch_ctr.get("video_count", 0)
        ctr_text = (f"频道级(28天): 展示量={imp:,} | CTR中位数={cmed*100:.2f}% | "
                    f"展示:播放={rat if rat else 'N/A'} | 覆盖视频数={cnt}\n")
        # 视频级 Top10 CTR + Bottom5 CTR（有数据的）
        vids_ok = [v for v in ctr.get("videos", []) if v["status"] in ("ok", "低置信")]
        vids_ok.sort(key=lambda x: x["ctr"], reverse=True)
        top_lines = [f"  🔥 {v['video_id']}: CTR={v['ctr']*100:.2f}% 展示={v['impressions']:,} ({v['status']})"
                     for v in vids_ok[:8]]
        bot_lines = [f"  💤 {v['video_id']}: CTR={v['ctr']*100:.2f}% 展示={v['impressions']:,} ({v['status']})"
                     for v in vids_ok[-5:] if v['status']=='ok']
        ctr_text += "Top CTR 视频:\n" + "\n".join(top_lines)
        if bot_lines:
            ctr_text += "\nBottom CTR 视频（需要优化门面）:\n" + "\n".join(bot_lines)

    # 四象限
    quadrant = findings.get("quadrant", {})
    q_status = quadrant.get("status", "skipped")
    q_text_parts = [f"归类来源: {quadrant.get('_quadrant_source', 'unknown')} (LLM 只解读，禁止重新归类)"]
    if q_status == "skipped":
        q_text_parts.append(f"状态: SKIPPED — {quadrant.get('reason','')}")
        q_text_parts.append("→ 无 OAuth/CTR 数据，四象限不适用；请只做钩子/骨架/赞率维度的分析。")
    elif q_status == "provisional":
        q_text_parts.append(f"状态: PROVISIONAL — {quadrant.get('reason','')}")
        q_text_parts.append(f"轴: {quadrant.get('axis_meta', {})}")
        for name, items in quadrant.get("buckets", {}).items():
            q_text_parts.append(f"  {name}: {len(items)}条")
            for it in items[:3]:
                q_text_parts.append(f"    • {_sanitize_title(it.get('title',''))[:40]} views={it.get('views',0):,} AVD={it.get('avd_pct',0)}%")
        q_text_parts.append("→ 因是代理数据，行动建议降一档：只给方向不给具体动作（如'重发封面'这类需 CTR 数据支持）。")
    elif q_status == "ok":
        q_text_parts.append(f"轴: {quadrant.get('axis_meta', {})}")
        buckets = quadrant.get("buckets", {})
        total = sum(len(v) for v in buckets.values())
        q_text_parts.append(f"总归类视频数: {total}")
        for name, items in buckets.items():
            q_text_parts.append(f"  【{name}】{len(items)}条")
            for it in items[:3]:
                lc = f" 低置信" if it.get("note") == "低置信" else ""
                hk = f" hook1%={int(it['hook_1pct']*100)}%" if it.get('hook_1pct') else ""
                q_text_parts.append(f"    • {_sanitize_title(it.get('title',''))[:40]} CTR={it['ctr']*100:.2f}% AVD={it.get('avd_pct',0)}%{hk}{lc}")
    quadrant_text = "\n".join(q_text_parts)

    # 订阅转化
    sc = findings.get("sub_conversion", {})
    if sc.get("status") == "ok":
        sc_top = "\n".join(f"  🏆 {_sanitize_title(v['title'])[:40]}: {v['sub_conversion']*100:.3f}% ({v['subs_gained']}订阅/{v['views']:,}播放)"
                           for v in sc.get("top3", []))
        sc_bot = "\n".join(f"  🥶 {_sanitize_title(v['title'])[:40]}: {v['sub_conversion']*100:.3f}% ({v['subs_gained']}订阅/{v['views']:,}播放)"
                           for v in sc.get("bottom3", []))
        sub_conv_text = (f"频道级: 总增订阅={sc.get('total_gained',0)} / 总流失={sc.get('total_lost',0)} | "
                         f"整体转化率={sc.get('channel_overall_conversion',0)*100:.3f}% ({sc.get('channel_level','')})\n"
                         f"Top3(值得继续剪同类):\n{sc_top}\n"
                         f"Bottom3(检查是否偏离定位):\n{sc_bot}")
    else:
        sub_conv_text = f"无订阅转化数据 — {sc.get('reason', '需重跑 collect_yt_analytics 采 subscribersGained')}"

    # 变现
    mn = findings.get("monetization", {})
    sub_disp = mn.get("subscribers", {}).get("display", "")
    hr_disp = mn.get("watch_hours", {}).get("note", "")
    monetization_text = f"{sub_disp}\n观看时长: {hr_disp}\nYPP初判: {'✅ 订阅已达标' if mn.get('ypp_ready') else '❌ 未达标'}"

    # 蒸馏骨架文本
    skel_text = "\n".join(f"- {s}" for s in dist.get("skeletons", [])) or "无"

    # 设备类型文本
    device = findings.get("device", {})
    device_text = "无设备数据"
    if device.get("has_data"):
        device_lines = [f"  {d['type']}: {d['views']:,}播放（{d['pct']}%）| {d['minutes']:,}分钟" for d in device["devices"]]
        device_text = "\n".join(device_lines)

    # 流量来源详情文本
    td = findings.get("traffic_detail", {})
    traffic_detail_text = "无流量详情数据"
    if td.get("has_data"):
        td_lines = [f"  {s['source']}: {s['views']:,}播放（{s['pct']}%）| {s['watch_minutes']:,}分钟" for s in td["sources"]]
        traffic_detail_text = "\n".join(td_lines)

    # 地域详情文本
    gd = findings.get("geo_detail", {})
    geo_detail_text = "无地域详情数据"
    if gd.get("has_data"):
        gd_lines = [f"  {r['region']}: {r['views']:,}播放 | {r['watch_minutes']:,}分钟" for r in gd["top_regions"]]
        geo_detail_text = "\n".join(gd_lines)

    # 热门视频文本
    tv = findings.get("top_videos_detail", {})
    top_videos_text = "无热门视频数据"
    if tv.get("has_data"):
        tv_lines = [f"  {_sanitize_title(v['title'])[:50]}: {v['views']:,}播放 | {v['watch_minutes']:,}分钟 | 完播{v['avg_pct']}%" for v in tv["videos"]]
        top_videos_text = "\n".join(tv_lines)

    # 受众年龄×观看时长文本
    dw = findings.get("demo_watch", {})
    demo_watch_text = "无受众时长数据"
    if dw.get("has_data"):
        dw_lines = [f"  {s['age']} {s['gender']}: {s['pct']}% | ~{s['est_minutes']:,}分钟" for s in dw["segments"]]
        demo_watch_text = "\n".join(dw_lines)

    # 增长文本
    growth_text = "无历史数据"
    if growth.get("has_prev"):
        growth_text = f"订阅{growth['sub_change']:+d}（{growth['sub_change_pct']}%）播放{growth['view_change']:+,}（{growth['view_change_pct']}%）赞率{growth['like_rate_change']}"

    # 最近15条视频
    sorted_vids = sorted(findings.get("_videos", []), key=lambda x: x.get("published_at", ""))
    trend_lines = []
    for i, v in enumerate(sorted_vids[-15:]):
        pub = v.get("published_at", "")[:10]
        views = v.get("views", 0)
        likes = v.get("likes", 0)
        lrate = round(likes / max(views, 1) * 100, 2)
        safe_title = _sanitize_title(v.get("title", ""))[:45]
        trend_lines.append(f"  {pub} | {views:>6,}播放 | {lrate}%赞率 | {safe_title}")
    trend_text = "\n".join(trend_lines) if trend_lines else "无视频数据"

    prompt = f"""你是短剧YouTube频道运营诊断专家。基于以下结构化findings，给出战略诊断。

## 数据纪律（严格执行）
1. **四象限归类已由 Python 完成，你只解读不重新归类**——`findings["quadrant"]` 里的 buckets 是最终归类，禁止改动/重排。你的任务是对每个 bucket 里的视频提出具体动作建议。
2. **归类状态影响诊断口径**：
   - `status: "skipped"` → 无 CTR 数据，四象限相关的诊断段直接说"无 CTR 数据，跳过门面/内容拆分"，不要编。
   - `status: "provisional"` → 用播放代理，行动降一档（只给方向不给具体动作，如"标题超卖"改为"疑似标题超卖，等 CTR 数据 24-48h 后再定"）。
   - `status: "ok"` → 正常归类，可给具体动作。
3. **CTR ≥ 4% 的视频禁止建议改标题/封面**——门面已经在跑，改动风险 > 收益。
4. **CTR < 2.5% 但 AVD 占比 ≥ 15% 的视频（门面拖累）**，行动只写"重置封面+标题"，不评论剧情节奏。
5. **AVD 占比是整体指标，不代表开头 hook**。判断开头 hook 只看 `retention.avg_retention_1pct`（1% 处/≈1分钟）；判断中段只看 3 分钟留存；不要用 AVD 占比推断"前 30 秒 hook"。
6. **样本不足/低置信视频（展示<500 或 <2000）不要给具体动作**，只列出等观察。异常视频（1%留存<5%）标记"数据异常，需要人工核实"。
7. **因果纪律**：结论必须给出"由哪个数据字段推出"。禁止把相关性说成因果（如"发布频率下降导致订阅下降"需要有增长曲线数据支撑，仅有两个数据点不足以下因果结论）。
8. **变现达标必标 ✅**：`findings["monetization"]` 里 `subscribers.ok=true` 意味着订阅门槛已达标，`monetization_detail.subscribers` 必须写"✅ 已达标"。禁止把已达标项写成"接近达标"或"还需努力"。
9. **验证Python结论**：赞率、播放分布等Python预计算值仅供参考。你必须对照"最近15条视频"的逐条数据自行验证趋势。如果Python结论与逐条数据矛盾，以逐条数据为准。禁止引用你无法从逐条数据中验证的趋势结论。

## 诊断框架（必须遵守）

### CTR×AVD（点击率×平均观看时长）
- 点击率由标题和封面决定
- AVD由整体内容质量、中段节奏、时长匹配决定（AVD占比是整体指标，不用于判断开头hook；开头hook只看1分钟留存）
- 两个指标共同决定算法推荐量

### 钩子×骨架×包装
- 钩子：情绪钩子（愤怒/心疼/爽感）、身份钩子（CEO/女帝/替身）、反转钩子（从被虐到打脸）
- 骨架：先抑后扬、低位闯高位、隐藏身份、第一人称极端遭遇、契约交易
- 包装：句式、标点、emoji、长度
- 标题至少命中2个钩子才算合格

### 诊断标准
- 赞率：>3%标杆 | 1.5-3%健康 | 1-1.5%一般 | <1%转化差
- 播放分布：头部集中是YouTube算法的正常现象，关注点应是"如何复制头部的成功模式"而非"集中度是否过高"
- 留存基准（一般视频）：<5min→60% / 5-20min→35% / >20min→25%
- 留存基准（短剧1-2小时）：1%处(≈1分钟)>80%=hook强 / 3分钟>30%=好 / 5分钟>25%=好
- 短剧前3分钟是关键hook窗口——开头流失>40%说明前3分钟剧情/节奏有问题
- 流量基准：推荐>50%=算法在推 / 订阅>30%=粉丝粘性强 / 搜索>20%=SEO好
- CTR代理：推荐流量>40%=CTR隐性健康（算法主动推=点击率不差）/ 推荐<20%=CTR可能偏低
- 回访观众代理：订阅流量>25%=粉丝回访占比高 / 订阅<15%=主要靠新观众

### 短剧频道特性
- 短剧频道开通YPP速度比一般频道快，通常25-30天可达标（一般频道45天）
- 短剧频道的留存曲线与一般长视频不同，观众追剧心理更强
- 短剧频道的核心增长驱动：高频更新+标题钩子+完整故事单集发布（印尼/繁中/英文短剧市场标准）

---

## 频道Findings

### 基础信息
- 名称: {ch.get('name', '')}
- 订阅: {ch.get('subscribers', 0):,} | 总播放: {ch.get('total_views', 0):,} | 视频数: {ch.get('total_videos', 0)} | 均播: {ch.get('avg_views', 0):,}
- 语言: {ch.get('language', '')} | 频道年龄: {ch.get('age_text', '')}（{ch.get('age_days', 0)}天）

### 题材发现（自动识别）
- 主题材: {genre.get('primary', '未知')}
- 子题材: {' / '.join(genre.get('sub_genres', []))}
- 信号: {genre.get('signals', {})}

### 标题分析
- 平均长度: {title.get('avg_length', 0)}字符（最佳{title.get('best_length', 84)}）
- Python钩子分布（旧，仅供参考）: {title.get('hook_distribution', {})}
- LLM钩子分布（6类）: {title.get('llm_hook_distribution', {})}
- LLM钩子层级分布: {title.get('llm_hook_level_distribution', {})}（基于每个视频的活跃钩子数：3+=三重，2=双重，1=单一）
- LLM发现的钩子类型: {', '.join(title.get('llm_hook_types', [])[:10])}
- LLM骨架分布: {title.get('llm_skeleton_distribution', {})}
- LLM双重/三重钩子占比: {title.get('llm_double_triple_hook_pct', 0)}%（基于LLM逐视频分析）
- Python双重/三重钩子占比（旧）: {title.get('double_triple_hook_pct', 0)}%（基于Python关键词匹配，可能不准）
- 未识别骨架占比: {title.get('unidentified_skeleton_pct', 0)}%
- 封面×标题协同均分: {title.get('avg_cover_synergy', '无数据')}

### 赞率
- 基准: >3%标杆 | 1.5-3%健康 | 1-1.5%一般 | <1%转化差
- 逐条赞率见下方"最近15条视频"列表，由你自行计算整体赞率和趋势

### 播放分布（基于近{len(findings.get('_videos', []))}条视频）
- 头部3条占比: {vd.get('top3_ratio', 0)}%
- 头部播放: {vd.get('top3_videos', [])}
- 频道总播放{ch.get('total_views', 0):,}，头部3条占频道总播放约{sum(vd.get('top3_videos', [0])) / max(ch.get('total_views', 1), 1) * 100:.1f}%
- 基准: 头部集中是YouTube正常现象，不要将其列为问题。应关注头部视频的可复制模式。

### SEO
- 平均标签: {seo.get('avg_tags_per_video', 0)}/视频
- 标签全部相同: {'是' if seo.get('all_same_tags') else '否'}
- 高频标签: {seo.get('top_tags', {})}

### 发布频率
频道年龄{ch.get('age_text', '未知')}，总视频{ch.get('total_videos', 0)}条
最近15条发布间隔见下方"最近15条视频"列表

### 增长趋势
{growth_text}

### OAuth Analytics
{oauth_text}

### 封面分析
{cover_text}


### 单视频平均观看时长（AVD，30天Analytics）
{avd_text}
注：百分比=AVD÷视频总时长，短剧（60-120分钟）正常范围15-25%，低于10%说明中段流失严重。

### 分段留存（OAuth实测）
{retention_text}

### CTR / 展示（Reporting API 28天）
{ctr_text}

### 视频四象限归类（Python 已归类，只解读不重排）
{quadrant_text}

### 订阅转化率（每视频 subGained/views）
{sub_conv_text}

### 变现就绪度（YPP 门槛分项）
{monetization_text}

### 蒸馏知识（同语种）
最佳标题长度: {dist.get('best_title_length', 84)}
高频钩子词: {', '.join(dist.get('hook_words', []))}
标题骨架:
{skel_text}
增长策略:
{chr(10).join(f'- {s}' for s in dist.get('growth_strategy', []))}

### 封面×标题协同规则
核心规则: 封面和标题围绕同一个"核心钩子"分工协作——标题说清身份反差/情节反转，封面把最有张力的一瞬间视觉化。
协同模式: 标题给反差封面给证据 / 封面定格高潮标题补前因 / 情绪反转视觉化 / 肢体距离表达关系 / 阶层符号强化爽感 / 奇观元素服务战力 / 标题信息密度vs封面情绪密度 / 互补优于重复
反模式: 题材错位 / 只美不钩 / 标题有爆点封面无 / 信息过散 / 情绪不匹配 / 身份缺视觉锚点
女频重点: 关系张力+情绪反转+身份差，封面优先呈现亲密/拉扯/对峙/挽留/保护瞬间
男频重点: 低位受辱+隐藏强者+瞬间打脸，封面直接给出战力/权力/逆袭证明

### 竞品对标
{comp_text}

### 设备类型（30天Analytics）
{device_text}

### 流量来源详情（30天Analytics，含观看时长）
{traffic_detail_text}

### 地域详情（30天Analytics，含观看时长）
{geo_detail_text}

### 热门视频（30天Analytics，含完播率）
{top_videos_text}

### 受众年龄×性别×观看时长（30天Analytics）
{demo_watch_text}

### 逐视频诊断明细（标题分析+封面协同+骨架+问题）
{per_video_diag_text}

### 最近15条视频
{trend_text}

---

## 健康度评分参考框架

根据数据可用性选择对应评分框架：

### 有OAuth数据的频道（留存权重最高）
| 维度 | 权重 | 说明 |
|------|------|------|
| 30秒/1%留存 | 35% | 开头hook质量，算法推荐的第一信号 |
| 3分钟留存 | 25% | 中段内容质量，决定AVD上限 |
| AVD占比 | 25% | 绝对观看时长，短剧15-25%为健康 |
| CTR代理 | 15% | 推荐流量占比>40%=隐性健康 |

### 无OAuth数据的频道（赞率+播放分布为核心）
| 维度 | 权重 | 说明 |
|------|------|------|
| 赞率 | 30% | 最直接的互动指标，>3%标杆 |
| 播放分布 | 25% | 头部集中度，30-50%健康 |
| 标题质量 | 25% | 钩子数量、骨架完整度 |
| 增长趋势 | 20% | 订阅/播放增速、更新频率 |

以上是参考，根据实际数据灵活调整。有数据的维度权重可以上浮，没数据的维度跳过不计入。

## 输出要求
1. **健康度评分**（1-10）
2. **一句话摘要**
3. **核心优势**（2-3个，数据支撑。如有OAuth留存数据，3分钟留存率必须出现在优势或问题中）
4. **核心问题**（3-5个，severity排序：critical > major > info。如有OAuth留存数据，3分钟留存率必须出现在优势或问题中）
5. **增长诊断**：趋势/根因/瓶颈
6. **频道权重判断**（基于推荐流量/留存/订阅综合判断算法信任度）
7. **变现就绪度**（离YPP多远：观看时长/订阅/互动达标情况）
8. **留存诊断**（如有OAuth数据，必须同时引用1%处和3分钟处留存率，3分钟留存是判断中段内容质量的核心指标）
9. **流量结构分析**（如有OAuth，含完整流量来源）
10. **受众洞察**（如有OAuth，含完整年龄×性别分布）
11. **地域策略**（哪些市场在涨、哪些有潜力）
12. **更新节奏评估**（当前发布频率是否匹配频道年龄和目标）
12b. **视频时长分析**（如有数据，分析最佳时长区间，短剧60-120分钟为基准）
12c. **标题长度效果**（标题长度与播放量的相关性，找到最佳长度区间）
13. **封面×标题协同评估**（封面和标题是否围绕同一个核心钩子分工协作）
14. **行动清单**（3-5条，每条含：priority/action/based_on/concrete_steps/acceptance_criteria/expected_impact/effort）
16. **AI自由发现**（从数据中发现的隐藏规律，不限于以上维度。如：某类标题播放量显著高于平均、某骨架类型系统性优于其他、封面协同分数与播放量的相关性、发布间隔与播放量的关系等。至少2条，用数据支撑）

输出JSON：
{{"health_score": 6.5, "health_grade": "B", "summary": "一句话",
  "strengths": [{{"area": "xxx", "detail": "xxx", "evidence": "数据"}}],
  "problems": [{{"area": "xxx", "detail": "xxx", "severity": "critical/major/info", "evidence": "数据"}}],
  "growth_diagnosis": {{"trend": "增长/稳定/放缓/停滞", "root_cause": "xxx", "bottleneck": "xxx"}},
  "channel_weight": {{"level": "强/中/弱", "indicators": "具体指标", "insight": "算法信任度判断"}},
  "monetization_readiness": {{"status": "已达标/接近/较远", "watch_hours": "达标情况", "subscribers": "达标情况", "gap": "差距描述"}},
  "retention_diagnosis": {{"status": "健康/偏低/严重偏低", "evidence": "数据", "hook_quality": "前30秒评估"}},
  "traffic_analysis": {{"recommend_pct": 0, "subscriber_pct": 0, "search_pct": 0, "health": "强/中/弱", "full_breakdown": "完整流量来源分析", "insight": "分析"}},
  "audience_insight": {{"actual_profile": "受众特征", "age_gender_breakdown": "完整年龄×性别分布", "match_with_content": "匹配度参考"}},
  "geo_strategy": {{"top_markets": "主要市场", "growth_markets": "增长市场", "opportunity_markets": "潜力市场", "insight": "地域策略建议"}},
  "upload_pace": {{"current_rate": "当前频率", "recommended_rate": "建议频率", "assessment": "评估"}},
  "cover_title_synergy": {{"score": 0, "assessment": "封面×标题协同评估", "improvement": "改进建议"}},

  "actions": [{{"priority": 1, "action": "一句话摘要", "based_on": "依据数据（引用problems.evidence或具体指标）", "concrete_steps": "①步骤一 ②步骤二 ③步骤三", "acceptance_criteria": "验收标准（可量化的完成标志）", "expected_impact": "预期效果", "effort": "低/中/高"}}],
  "ai_discoveries": [{{"pattern": "发现的规律", "evidence": "数据支撑", "insight": "这意味着什么"}}],

  "ctr_status": "ok|pending|no_data",
  "quadrant_summary": {{
    "status": "ok|provisional|skipped",
    "total_classified": 0,
    "bucket_takeaways": [
      {{"bucket": "爆款基因", "count": 0, "action": "继续剪同类，量产模板"}},
      {{"bucket": "标题超卖_开头型", "count": 0, "action": "改标题降调（hook<80%）"}},
      {{"bucket": "标题超卖_中段型", "count": 0, "action": "标题OK，中段节奏改"}},
      {{"bucket": "门面拖累", "count": 0, "action": "重置封面+标题"}},
      {{"bucket": "选题失败", "count": 0, "action": "选题方向不适合此频道"}}
    ],
    "note": "只针对 findings.quadrant.buckets 里非空的桶给出 takeaway；每个 takeaway 用 1 句话"
  }},
  "sub_conversion_analysis": {{
    "channel_level": "优秀/一般/较差/无数据",
    "top_pattern": "从 Top3 视频看，什么类型的内容最能带订阅（题材/骨架/钩子）",
    "bottom_pattern": "从 Bottom3 视频看，什么内容拉低转化（是否偏离定位）",
    "action": "1 句话建议"
  }},
  "bottleneck": {{
    "primary": "当前最卡脖子的一件事（订阅/CTR/AVD/发布频率 之一）",
    "evidence": "支撑数据",
    "next_lever": "撬开瓶颈的下一个动作（唯一，非清单）"
  }},
  "monetization_detail": {{
    "subscribers": "✅ 已达标 | ❌ 缺口N（数值）",
    "watch_hours_12mo": "达标情况或说明数据窗口不匹配",
    "engagement_gate": "互动是否健康"
  }},
  "delta": {{
    "vs_last_diagnosis": "对比上次诊断（如无历史，写'首次诊断'）",
    "moved_forward": ["改善维度"],
    "regressed": ["退步维度"],
    "note": "由 Python 填充 vs 历史 diagnosis_latest.json，LLM 只写自然语言说明"
  }}
}}"""

    print(f"  🧠 Step 3: 战略诊断...", end="", flush=True)
    result = call_for_task("channel_analysis", prompt, max_tokens=8192, temperature=0.4)
    if result.get("error"):
        print(f" ⚠️ 失败: {result['error'][:50]}")
        return None

    parsed = parse_json_response(result)
    if "error" in parsed or "health_score" not in parsed:
        print(f" ⚠️ 解析失败: {parsed.get('error', 'no health_score')} | raw: {str(parsed.get('raw', result.get('content', '')))[:200]}")
        return None

    # 批3.3 后校验（Python 层，硬约束）
    parsed = _post_validate_diagnosis(parsed, findings)

    print(f" ✅ 健康度{parsed.get('health_score')}/10 ({parsed.get('health_grade')})")
    return parsed


def _post_validate_diagnosis(parsed: dict, findings: dict) -> dict:
    """批3.3: LLM 输出后校验，硬约束修正 + 冲突检测 + audit trail + Python 兜底 additive 字段。"""
    audit = []
    problems = parsed.get("problems", []) or []
    strengths = parsed.get("strengths", []) or []
    orig_score = parsed.get("health_score", 5)
    has_critical = any((p.get("severity") == "critical") for p in problems)
    audit.append(f"后校验执行: score={orig_score}, critical={has_critical}, problems={len(problems)}, strengths={len(strengths)}")

    # 规则1: 有 critical 且 health_score > 6.5 → 封顶 6.5
    if has_critical and orig_score > 6.5:
        parsed["health_score"] = 6.5
        parsed["health_grade"] = "C"
        audit.append(f"critical 问题存在，health_score 由 {orig_score} 封顶到 6.5")

    # 规则2: 冲突检测
    # 2a: LLM 内部 — 同一维度既在 strengths 又在 problems
    strength_areas = {(s.get("area") or "").strip() for s in strengths}
    problem_areas = {(p.get("area") or "").strip() for p in problems}
    conflicts_set = (strength_areas & problem_areas) - {""}
    conflicts_list = []
    for area in conflicts_set:
        s_entry = next((s for s in strengths if (s.get("area") or "").strip() == area), {})
        p_entry = next((p for p in problems if (p.get("area") or "").strip() == area), {})
        conflicts_list.append({
            "dimension": area,
            "source": "llm_internal",
            "as_strength": s_entry.get("detail", ""),
            "as_problem": p_entry.get("detail", ""),
            "resolution": "需人工判断哪边成立",
        })

    # 2b: 跨层冲突 — Python 规则诊断 vs LLM 结论
    # Python 规则诊断提取的事实（from findings / video_scores）
    python_facts = []
    # 四象限事实
    q_status = (findings.get("quadrant") or {}).get("status", "ok")
    if q_status == "ok":
        q = findings.get("quadrant") or {}
        for bucket in ["爆款基因", "标题超卖_开头型", "标题超卖_中段型", "门面拖累", "选题失败", "表现平庸"]:
            vids = q.get(bucket, [])
            if vids:
                python_facts.append({"area": f"四象限·{bucket}", "detail": f"{len(vids)}条视频归入{bucket}"})
    # CTR 事实
    ctr = findings.get("ctr") or {}
    ctr_median = ctr.get("channel", {}).get("median_ctr")
    if ctr_median is not None:
        if ctr_median >= 6:
            python_facts.append({"area": "CTR", "detail": f"频道CTR中位数{ctr_median}%，处于健康区间"})
        elif ctr_median < 2.5:
            python_facts.append({"area": "CTR", "detail": f"频道CTR中位数{ctr_median}%，低于2.5%阈值"})

    # 留存子类映射（不同子类不算冲突）
    retention_subclasses = {"开头hook": "开头hook", "1分钟留存": "开头hook", "hook": "开头hook",
                            "中段": "中段", "3分钟": "中段", "5分钟": "中段",
                            "整体AVD": "整体AVD", "平均观看": "整体AVD", "AVD占比": "整体AVD"}

    def _retention_subclass(area: str) -> str | None:
        for keyword, subclass in retention_subclasses.items():
            if keyword in area:
                return subclass
        return None

    # 跨层比对：Python 事实 vs LLM problems
    for p in problems:
        p_area = (p.get("area") or "").strip()
        if not p_area:
            continue
        for fact in python_facts:
            f_area = fact["area"]
            # 模糊匹配：area 有交集关键词
            p_sub = _retention_subclass(p_area)
            f_sub = _retention_subclass(f_area)
            # 留存子类不同 → 不算冲突（方案要求：不同子类不构成矛盾）
            if p_sub and f_sub and p_sub != f_sub:
                continue
            # 简单交集匹配
            if any(kw in p_area for kw in f_area.split("·")) or any(kw in f_area for kw in p_area.split("·")):
                conflicts_list.append({
                    "dimension": f"Python/{f_area} vs LLM/{p_area}",
                    "source": "cross_layer",
                    "python_fact": fact["detail"],
                    "llm_conclusion": p.get("detail", ""),
                    "resolution": "两者均真时合并结论；Python优先（有数据支撑）",
                })

    if conflicts_list:
        parsed["conflicts"] = conflicts_list
        llm_c = [c["dimension"] for c in conflicts_list if c.get("source") == "llm_internal"]
        cross_c = [c["dimension"] for c in conflicts_list if c.get("source") == "cross_layer"]
        parts = []
        if llm_c:
            parts.append(f"LLM内部: {sorted(llm_c)}")
        if cross_c:
            parts.append(f"跨层: {sorted(cross_c)}")
        audit.append(f"冲突检测: {'; '.join(parts)}")

    # 规则3: 四象限 skipped 时禁止出现 CTR 相关的具体动作词
    q_status = (findings.get("quadrant") or {}).get("status", "ok")
    if q_status == "skipped":
        actions = parsed.get("actions", []) or []
        banned = ["CTR", "点击率", "重置封面", "重发封面"]
        filtered = []
        for a in actions:
            act_str = a.get("action", "")
            if any(b in act_str for b in banned):
                audit.append(f"删除 CTR 相关动作（quadrant=skipped）: {act_str[:40]}")
                continue
            filtered.append(a)
        parsed["actions"] = filtered

    # 规则4: hood 提"前30秒"但依据是 AVD → 打警告
    for p in problems:
        det = p.get("detail", "") + p.get("evidence", "")
        if ("前30秒" in det or "开头 hook" in det) and "AVD" in det and "1%" not in det and "1分钟" not in det:
            audit.append(f"疑似违规：hood 提及'前30秒'但依据是 AVD（应看1%留存）: {det[:80]}")
            p["_audit_warning"] = "AVD 不能证明开头 hook 问题"

    # 规则5: additive 字段 Python 兜底（LLM 漏填时补上）
    mn = findings.get("monetization") or {}
    subs_info = mn.get("subscribers") or {}
    if "monetization_detail" not in parsed or not isinstance(parsed.get("monetization_detail"), dict):
        parsed["monetization_detail"] = {}
    md = parsed["monetization_detail"]
    # 强制 subscribers 字段说真话
    if subs_info.get("ok"):
        if md.get("subscribers") != subs_info.get("display", "✅ 已达标"):
            audit.append(f"monetization_detail.subscribers 修正为 Python 事实值: {subs_info.get('display')}")
            md["subscribers"] = subs_info.get("display", "✅ 已达标")
    else:
        md.setdefault("subscribers", subs_info.get("display", f"❌ 缺口{max(0, 1000 - subs_info.get('value', 0))}"))
    md.setdefault("watch_hours_12mo", (mn.get("watch_hours") or {}).get("note", "无数据"))
    md.setdefault("engagement_gate", "未评估" if not md.get("engagement_gate") else md["engagement_gate"])

    # ctr_status 兜底
    ctr_s = (findings.get("ctr") or {}).get("status", "no_data")
    if parsed.get("ctr_status") not in ("ok", "pending", "no_data"):
        parsed["ctr_status"] = ctr_s
        audit.append(f"ctr_status 兜底填充为 {ctr_s}")

    # quadrant_summary 兜底 total_classified
    q = findings.get("quadrant") or {}
    total_c = sum(len(v) for v in (q.get("buckets") or {}).values())
    qs = parsed.get("quadrant_summary") or {}
    if not isinstance(qs, dict):
        qs = {}
    qs.setdefault("status", q.get("status", "skipped"))
    qs["total_classified"] = total_c
    parsed["quadrant_summary"] = qs

    # delta 兜底：首次诊断标记
    if "delta" not in parsed or not isinstance(parsed.get("delta"), dict):
        parsed["delta"] = {}
    if not parsed["delta"].get("vs_last_diagnosis"):
        parsed["delta"]["vs_last_diagnosis"] = "首次诊断（无历史对比）"

    if audit:
        parsed["_audit_trail"] = audit
    return parsed


def llm_channel_analysis(snapshot: dict, distill: dict, lang: str) -> dict | None:
    """频道级运营分析 — 3步流程：分类→研究→回答"""
    # Step 2: 研究
    findings = prepare_channel_findings(snapshot, distill, lang)
    if not findings:
        return None
    # 保留原始视频数据给Step 3（用于趋势展示）
    findings["_videos"] = snapshot.get("videos", [])
    findings["_video_scores"] = snapshot.get("video_scores", [])
    # Step 3: 回答
    return llm_strategic_diagnosis(findings, distill)

def _generate_channel_diagnostics(snapshot: dict, distill: dict, diagnosis: dict) -> list:
    """从快照数据生成频道级诊断建议"""
    diagnostics = []

    # 1. 播放分布检查
    vd = diagnosis.get("view_distribution", {})
    if vd:
        top3 = vd.get("top3_ratio", 0)
        if top3 > 50:
            diagnostics.append({
                "severity": "critical",
                "category": "播放分布",
                "issue": f"头部严重集中：前3条视频占总播放{top3:.0f}%",
                "detail": f"除爆款外，其余视频平均播放仅{vd.get('avg_views', 0):,}。内容质量不均或算法推荐不稳定。",
                "action": "① 分析爆款视频的标题/封面/时长特征，复制到后续视频\n② 确保每条视频都有独立的钩子"
            })

    # 2. 互动漏斗检查
    ef = diagnosis.get("engagement_funnel", {})
    if ef:
        like_rate = ef.get("overall_like_rate", 0)
        zero_ratio = ef.get("zero_like_ratio", 0)
        if zero_ratio > 0.3:
            diagnostics.append({
                "severity": "major",
                "category": "互动",
                "issue": f"{zero_ratio:.0%}视频零点赞",
                "detail": f"频道整体赞率{like_rate:.2f}%，{ef.get('zero_like_count', 0)}条视频零互动。",
                "action": "① 检查零赞视频的标题和封面是否有吸引力\n② 视频中设置引导互动的问题"
            })
        comment_rate = ef.get("overall_comment_rate", 0)
        if comment_rate < 0.05 and ef.get("total_views", 0) > 1000:
            diagnostics.append({
                "severity": "info",
                "category": "互动深度",
                "issue": f"评论/点赞比仅{comment_rate:.1f}%",
                "detail": "观众点赞但不评论，说明内容能看但缺乏讨论点。",
                "action": "① 在视频中设置争议性问题\n② 在描述中提问引导评论"
            })

    # 3. SEO检查
    seo = diagnosis.get("seo_analysis", {})
    if seo:
        avg_tags = seo.get("avg_tags_per_video", 0)
        if avg_tags < 3:
            diagnostics.append({
                "severity": "major",
                "category": "SEO",
                "issue": f"平均每视频仅{avg_tags:.1f}个标签",
                "detail": f"{seo.get('videos_without_tags', 0)}条视频无标签，SEO完全空白。",
                "action": "① 每视频至少5个标签：题材词+情绪词+语言词+频道品牌词\n② 参考蒸馏数据的hashtag_strategy"
            })

    # 4. 标题模式检查
    tp = diagnosis.get("title_patterns", {})
    if tp:
        avg_len = tp.get("avg_length", 0)
        emoji_ratio = tp.get("emoji_ratio", 0)
        if emoji_ratio > 0.8:
            diagnostics.append({
                "severity": "major",
                "category": "标题",
                "issue": "所有视频用相同emoji前缀，无区分度",
                "detail": "重复的emoji序列会让观众产生视觉疲劳，降低点击率。",
                "action": "① 每视频只用1-2个相关emoji放末尾\n② 纯文字标题点赞率反而更高"
            })

    # 5. 内容一致性检查（仅当关键词覆盖率足够时才判断）
    cc = diagnosis.get("content_consistency", {})
    if cc:
        consistency = cc.get("consistency_score", 0)
        primary = cc.get("primary_type", "")
        primary_ratio = cc.get("primary_ratio", 0)
        detected = cc.get("detected_types", {})
        detected_count = sum(detected.values())
        total_videos = diagnosis.get("total_videos", 14)
        coverage = detected_count / max(total_videos, 1)
        # 只有当关键词覆盖率>50%且一致性<50%时，才算真正"内容混杂"
        if consistency < 0.5 and primary and coverage > 0.5:
            diagnostics.append({
                "severity": "major",
                "category": "内容定位",
                "issue": f"内容混杂：主要类型'{primary}'仅占{primary_ratio:.0%}",
                "detail": "YouTube算法需要一致的内容标签才能精准推荐。",
                "action": "① 确定1个核心赛道，连续发布同类型内容\n② 用系列标题强化定位"
            })

    # 6. 发布节奏检查
    pp = diagnosis.get("posting_pattern", {})
    if pp:
        by_hour = pp.get("by_hour", {})
        if by_hour:
            peak_hour = max(by_hour, key=by_hour.get)
            total_posts = sum(by_hour.values())
            peak_ratio = by_hour[peak_hour] / max(total_posts, 1)
            if peak_ratio > 0.7:
                diagnostics.append({
                    "severity": "info",
                    "category": "发布节奏",
                    "issue": f"发布时段过度集中：{peak_ratio:.0%}在UTC {peak_hour}点",
                    "detail": "建议分散发布时段，测试不同时段的表现差异。",
                    "action": "① 参考蒸馏数据的best_hours\n② 在最佳时段前后各测试1-2个新时段"
                })

    # ═══ OAuth Analytics 诊断（已授权频道）═══
    analytics = snapshot.get("analytics", {})
    if analytics:
        # --- 留存率（按视频时长分档）---
        avg_pct = min(analytics.get("averageViewPercentage", 0), 100)  # clamp >100 API异常
        avg_dur = analytics.get("averageViewDuration", 0)  # 秒
        if avg_pct > 0 and avg_dur > 0:
            est_video_dur = avg_dur / (avg_pct / 100) if avg_pct > 0 else 0
            if est_video_dur > 1200:  # >20分钟
                bench_low, bench_ok = 15, 25
            elif est_video_dur > 300:  # 5-20分钟
                bench_low, bench_ok = 25, 35
            else:  # <5分钟
                bench_low, bench_ok = 40, 60
            if avg_pct < bench_low:
                diagnostics.append({
                    "severity": "critical",
                    "category": "留存",
                    "issue": f"留存率 {avg_pct}% 低于同长度基准 {bench_low}%",
                    "detail": f"平均观看 {avg_dur//60}分{avg_dur%60}秒，视频预估 {est_video_dur//60} 分钟。平均观看占比 {avg_pct}%，中段流失严重（AVD占比是整体指标，不代表开头hook问题）。",
                    "action": "① 每3-5分钟设置一次re-engagement hook\n② 检查中段是否有拖沓段落\n③ 分析留存曲线找到掉粉节点（1分钟留存判开头，3-5分钟判中段）"
                })
            elif avg_pct < bench_ok:
                diagnostics.append({
                    "severity": "major",
                    "category": "留存",
                    "issue": f"留存率 {avg_pct}% 偏低（同长度健康线 {bench_ok}%）",
                    "detail": f"平均观看 {avg_dur//60}分{avg_dur%60}秒，有提升空间。",
                    "action": "① 每3-5分钟设置一个re-engagement hook\n② 检查中段是否有拖沓段落"
                })

        # --- 订阅健康度 ---
        gained = analytics.get("subscribersGained", 0)
        lost = analytics.get("subscribersLost", 0)
        if gained > 0 and lost > 0:
            churn_rate = lost / gained * 100
            if lost > gained:
                diagnostics.append({
                    "severity": "critical",
                    "category": "订阅",
                    "issue": f"订阅净流失：+{gained}/-{lost}（净增 {gained-lost}）",
                    "detail": "流失超过新增，频道在萎缩。",
                    "action": "① 检查最近内容是否偏离定位\n② 分析流失发生在哪些视频后\n③ 增加发布频率"
                })
            elif churn_rate > 20:
                diagnostics.append({
                    "severity": "major",
                    "category": "订阅",
                    "issue": f"订阅流失率偏高 {churn_rate:.0f}%（+{gained}/-{lost}）",
                    "detail": "新增订阅中有较多取消订阅，可能内容质量不稳定。",
                    "action": "① 保持内容风格一致\n② 在视频结尾引导订阅"
                })

        # --- 流量来源健康度 ---
        ratios = analytics.get("traffic_ratios", {})
        if ratios:
            browse = ratios.get("RELATED_VIDEO", 0)
            sub = ratios.get("SUBSCRIBER", 0)
            search = ratios.get("YT_SEARCH", 0)

            if sub > 50:
                diagnostics.append({
                    "severity": "major",
                    "category": "流量",
                    "issue": f"过度依赖订阅流量 {sub}%（推荐仅 {browse}%）",
                    "detail": "算法信任度低，新观众获取受限。",
                    "action": "① 优化标题+封面提升CTR\n② 增加发布频率触发推荐\n③ 分析推荐流量高的视频特征并复制"
                })
            elif browse < 30:
                diagnostics.append({
                    "severity": "major",
                    "category": "流量",
                    "issue": f"推荐流量偏低 {browse}%",
                    "detail": "算法推荐不足，可能是CTR或留存低于同类频道。",
                    "action": "① 优化标题钩子\n② 封面增加情绪张力\n③ 检查中段节奏（AVD占比反映整体，非前30秒）"
                })

            if search < 5:
                diagnostics.append({
                    "severity": "info",
                    "category": "SEO",
                    "issue": f"搜索流量仅 {search}%",
                    "detail": "搜索优化不足，错失长尾流量。",
                    "action": "① 标题包含搜索关键词\n② 描述区前2行包含核心关键词\n③ 每视频至少5个标签"
                })

    return diagnostics


# ══════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════

def _generate_diagnosis_report(out_path: str | None = None) -> None:
    """从注册表读所有频道，汇总 _latest.json 输出 markdown 报告。
    融合自旧 scripts/_gen_diagnosis_report.py（一次性硬编码 6 频道 → 现在读注册表）
    """
    from datetime import datetime as _dt
    reg_path = ROOT / "data" / "own" / "our_channels.json"
    if not reg_path.exists():
        print(f"❌ 注册表不存在: {reg_path}")
        return
    reg = json.loads(reg_path.read_text(encoding="utf-8"))
    channels = reg.get("channels", [])

    lines = []
    def add(s=""):
        lines.append(s)

    add(f"# 频道诊断综合报告")
    add(f"")
    add(f"生成时间: {_dt.now().isoformat()}")
    add(f"频道数: {len(channels)}")
    add(f"")

    rankings = []
    for ch_reg in channels:
        name = ch_reg.get("name", "")
        lang = ch_reg.get("language_cn") or ch_reg.get("language") or ch_reg.get("market") or "?"
        # 诊断文件名规则：name.replace(" ", "_")（注册表的 slug 是另一套语义）
        fname = name.replace(" ", "_")
        path = DIAGNOSIS_DIR / f"{fname}_latest.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            add(f"\n## ❌ {name} ({lang})\n\n读取失败: `{e}`\n")
            rankings.append((name, 0, 0, "-", 0, 0))
            continue

        ch = data.get("channel", {}) or {}
        scored = data.get("video_scores", []) or []
        ch_llm = data.get("channel_llm", {}) or {}
        summary_txt = data.get("summary", {}) or {}

        scores = [v.get("score", 0) for v in scored if v.get("score") is not None]
        avg_score = sum(scores) / len(scores) if scores else 0.0
        need_opt = sum(1 for v in scored if v.get("needs_optimization", False))
        total = len(scored)

        hs = ch_llm.get("health_score") or 0
        grade = ch_llm.get("health_grade", "")
        subs = ch.get("subscribers", 0)
        views = ch.get("total_views", 0)
        rankings.append((name, avg_score, hs, grade, subs, views))

        add(f"\n## 📊 {name} ({lang})")
        add(f"")
        add(f"- 订阅: **{subs}** | 总播放: **{views:,}** | 视频: {ch.get('total_videos','?')}")
        add(f"- 均分: **{avg_score:.1f}/10** | 需优化: {need_opt}/{total}")
        if hs:
            add(f"- 健康度: **{hs}/10 {grade}**")
        if ch_llm.get("summary"):
            add(f"- 摘要: {ch_llm['summary'][:300]}")

        # additive: bottleneck
        bn = ch_llm.get("bottleneck") or {}
        if isinstance(bn, dict) and bn.get("primary"):
            add(f"")
            add(f"### 🎯 瓶颈")
            add(f"- 主要: **{bn['primary']}**")
            if bn.get("evidence"):
                add(f"- 依据: {bn['evidence']}")
            if bn.get("next_lever"):
                add(f"- 下一步: {bn['next_lever']}")

        # strengths / problems
        strengths = ch_llm.get("strengths") or []
        if isinstance(strengths, list) and strengths:
            add(f"")
            add(f"### ✅ 核心优势")
            for s in strengths[:3]:
                if isinstance(s, dict):
                    text = f"**{s.get('area','')}**: {s.get('detail','')}"
                else:
                    text = str(s)
                add(f"- {text}")

        problems = ch_llm.get("problems") or []
        if isinstance(problems, list) and problems:
            add(f"")
            add(f"### 🚨 核心问题")
            for p in problems[:5]:
                if isinstance(p, dict):
                    text = f"**{p.get('area','')}**: {p.get('detail','')}"
                else:
                    text = str(p)
                add(f"- {text}")

        actions = ch_llm.get("actions") or []
        if isinstance(actions, list) and actions:
            add(f"")
            add(f"### 🎯 行动清单")
            for a in actions[:5]:
                if isinstance(a, dict):
                    text = f"P{a.get('priority','?')} {a.get('action','')}"
                else:
                    text = str(a)
                add(f"- {text}")

        if scored:
            sorted_up = sorted(scored, key=lambda x: x.get("score", 0))
            sorted_down = sorted(scored, key=lambda x: x.get("score", 0), reverse=True)
            add(f"")
            add(f"### 📉 最低分（需优先优化）")
            for v in sorted_up[:3]:
                add(f"- [{v.get('score',0):.1f}] {v.get('views',0):,}播放 · {_sanitize_title(v.get('title','') or '')[:70]}")
            add(f"")
            add(f"### 📈 最高分（标杆）")
            for v in sorted_down[:3]:
                add(f"- [{v.get('score',0):.1f}] {v.get('views',0):,}播放 · {_sanitize_title(v.get('title','') or '')[:70]}")

    # 综合排名
    rankings.sort(key=lambda x: (x[2] or 0) if x[2] else x[1], reverse=True)
    add(f"\n\n---\n\n## 📈 频道综合排名（按健康度/均分）")
    add(f"")
    add(f"| # | 频道 | 均分 | 健康度 | 订阅 | 总播放 |")
    add(f"|---|------|------|--------|------|--------|")
    for i, (name, avg, hs, grade, subs, views) in enumerate(rankings, 1):
        gs = f" {grade}" if grade and grade != "-" else ""
        add(f"| {i} | {name} | {avg:.1f}/10 | {hs}/10{gs} | {subs} | {views:,} |")

    # 输出
    if out_path is None:
        out_path = f"output/channel_diagnosis_report_{_dt.now().strftime('%Y%m%d')}.md"
    out_p = ROOT / out_path
    out_p.parent.mkdir(parents=True, exist_ok=True)
    out_p.write_text("\n".join(lines), encoding="utf-8")
    print(f"✅ 报告已保存: {out_p}")
    print(f"频道数: {len(channels)} | 输出: {len(lines)} 行")


def run_diagnosis(channel_name: str, use_llm: bool = True, force: bool = False, force_channel_llm: bool = False) -> dict:
    """运行完整诊断（支持增量：已有结果的视频跳过，每批次存盘；force=True强制全部重跑）"""
    lang = CHANNEL_TO_LANG.get(channel_name, "en")
    print(f"\n{'='*50}")
    print(f"📊 诊断: {channel_name} ({lang})")
    print(f"{'='*50}")

    # 加载数据
    snapshot = load_snapshot(channel_name)
    if not snapshot:
        print(f"  ❌ 无快照数据: {channel_name}")
        return {}

    distill = load_distill(lang)
    if not distill:
        print(f"  ⚠️ 无蒸馏数据: {lang}，使用默认标杆")

    market = load_market_insights(lang)
    videos = snapshot.get("videos", [])
    if not videos:
        print(f"  ❌ 无视频数据")
        return {}

    print(f"  📹 {len(videos)}条视频")

    # 加载频道题材
    channel_genres = load_channel_genres(channel_name, videos)
    if channel_genres:
        print(f"  🏷️ 题材: {', '.join(channel_genres)}")

    # 加载OAuth分段留存数据（只读本地 yt_analytics 缓存，不调API）
    slug_r = channel_name.replace(" ", "_")
    # P3-11: 统一 slug 解析（accounts.json 反查 > CHANNEL_TO_SLUG > slug_r）
    yt_slug = _resolve_oauth_slug(channel_name, slug_r)
    yt_analytics_path = ROOT / "data" / "yt_analytics" / f"{yt_slug}.json"
    retention_data = None
    if yt_analytics_path.exists():
        try:
            yt_cache = json.loads(yt_analytics_path.read_text(encoding="utf-8"))
            ret = yt_cache.get("retention", {})
            if ret.get("has_data") and ret.get("videos"):
                retention_data = ret
                print(f"  📈 留存数据: 读取yt_analytics缓存 ({retention_data.get('video_count', 0)}条视频)")
        except Exception:
            pass
    # fallback: 从已有诊断文件读取（兼容旧数据）
    if not retention_data:
        existing_ret_path = DIAGNOSIS_DIR / f"{slug_r}_latest.json"
        if existing_ret_path.exists():
            try:
                existing_ret = json.loads(existing_ret_path.read_text(encoding="utf-8"))
                old_ret = existing_ret.get("retention_data", {})
                if old_ret and old_ret.get("has_data") and old_ret.get("videos"):
                    retention_data = old_ret
                    print(f"  📈 留存数据: 读取诊断缓存 ({retention_data.get('video_count', 0)}条视频)")
            except Exception:
                pass
    if not retention_data:
        print(f"  📈 留存数据: 无缓存（需先运行 collect_yt_analytics.py 采集）")
    if retention_data:
        avg_1pct = retention_data.get("avg_retention_1pct")
        print(f"  📈 留存曲线: {retention_data['video_count']}条视频, 1%处={avg_1pct:.0%}" if avg_1pct else f"  📈 留存曲线: {retention_data['video_count']}条视频")
        snapshot["retention_data"] = retention_data  # 注入snapshot

    # 加载已有诊断结果（增量模式）
    slug = channel_name.replace(" ", "_")
    out_path = DIAGNOSIS_DIR / f"{slug}_latest.json"
    existing_result = {}
    existing_scores = {}  # video_id → score entry
    if out_path.exists() and not force:
        try:
            existing_result = json.loads(out_path.read_text(encoding="utf-8"))
            for sv in existing_result.get("video_scores", []):
                vid = sv.get("video_id")
                if vid and sv.get("scores", {}).get("llm") is not None:
                    existing_scores[vid] = sv
            if existing_scores:
                print(f"  📂 已有诊断: {len(existing_scores)}条视频，跳过已分析的")
        except Exception:
            pass
    elif force:
        # --force: 读取existing_result保留video_llm_last_run，但清空scores强制重跑
        if out_path.exists():
            try:
                existing_result = json.loads(out_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        print(f"  🔄 --force: 强制重新分析所有视频")

    # 计算频道统计数据（Python擅长的）
    rates = [v["likes"] / v["views"] * 100 for v in videos if v.get("views", 0) > 0]
    avg_like_rate = round(sum(rates) / len(rates), 2) if rates else 0

    # 筛选需要LLM分析的视频（增量：跳过已有的）
    videos_to_analyze = []
    video_indices = []  # videos_to_analyze在videos中的原始索引
    for i, v in enumerate(videos):
        vid = v.get("video_id", "")
        if vid not in existing_scores:
            videos_to_analyze.append(v)
            video_indices.append(i)

    # 加载封面数据
    slug = channel_name.replace(" ", "_")
    cover_path = ROOT / "data" / "own" / "channel_diagnosis" / f"{slug}_covers.json"
    covers_list = []
    covers_index = {}  # video_id → cover info
    _existing_cover_model = "mimo-v2.5"  # P3-8 fallback，稍后用真实值覆盖
    if cover_path.exists():
        try:
            cover_data = json.loads(cover_path.read_text(encoding="utf-8"))
            _existing_cover_model = cover_data.get("model", _existing_cover_model)  # P3-8 透传
            covers_list = cover_data.get("details", cover_data.get("covers", []))
            for c in covers_list:
                if c.get("video_id"):
                    covers_index[c["video_id"]] = c
            if covers_list:
                print(f"  🎨 封面数据: {len(covers_list)}条")
        except Exception:
            pass

    # 补缺封面：对没有封面数据的视频自动调MiMo分析
    missing_covers = []
    for i, v in enumerate(videos):
        vid = v.get("video_id", "")
        if vid and vid not in covers_index:
            title = v.get("title", "")
            matched = False
            for ct in covers_index:
                if ct[:30] in title or title[:30] in ct:
                    matched = True
                    break
            if not matched:
                missing_covers.append(v)
    if missing_covers:
        print(f"  🎨 补析封面: {len(missing_covers)}条缺失，调MiMo分析...")
        try:
            from cover_analysis_own import load_config as cover_load_config, analyze_cover
            cover_load_config()
            for v in missing_covers:
                vid = v.get("video_id", "")
                thumb = v.get("thumbnail", v.get("thumbnails", [{}])[0].get("url", "") if v.get("thumbnails") else "")
                if not thumb and vid:
                    thumb = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
                if thumb:
                    result = analyze_cover(thumb, v.get("title", ""), v.get("views", 0))
                    if result and not result.get("error"):
                        result["video_id"] = vid
                        result["video_title"] = v.get("title", "")
                        result["views"] = v.get("views", 0)
                        result["image_url"] = thumb
                        covers_list.append(result)
                        covers_index[vid] = result
                        print(f"    ✅ {v.get('title', '')[:30]}")
                    else:
                        print(f"    ⚠️ {v.get('title', '')[:30]}: {result.get('error', '未知')}")
                    time.sleep(2)
            # 更新covers.json
            if covers_list:
                cover_data = {
                    "channel_name": channel_name,
                    "analyzed_at": datetime.now(timezone.utc).isoformat(),
                    "model": _existing_cover_model,  # P3-8: 透传已有 model（cover_analysis_own 写入时已按 USE_VISION_MODEL 动态设置）
                    "total_videos": len(videos),
                    "analyzed_videos": len(covers_list),
                    "details": covers_list,
                }
                # P1-3: 原子写，避免 panel 读到截断 JSON
                _atomic_write_json(cover_path, cover_data)
                print(f"  🎨 封面数据已更新: {len(covers_list)}条")
        except Exception as e:
            print(f"  ⚠️ 封面补析失败: {e}")

    llm_analyses = None
    quadrant_map = {}
    # 视频级LLM：增量跑，只分析新视频（已有LLM评分的自动跳过）

    if use_llm and videos_to_analyze:
        print(f"  🧠 LLM诊断: {len(videos_to_analyze)}条新视频（跳过{len(existing_scores)}条已有）...")

        # 批3.1: 预计算每个视频的象限归类（用于给 LLM 单视频 prompt 注入对症纪律）
        try:
            _snap_slug = _resolve_oauth_slug(channel_name, slug_r) or channel_name.replace(" ", "_")
            _ctr_snapshot = {"_slug": _snap_slug}
            _yt_an = {}
            _yt_path = ROOT / "data" / "own" / "analytics" / f"{_snap_slug}.json"
            if _yt_path.exists():
                _yt_an = json.loads(_yt_path.read_text(encoding="utf-8"))
            _ctr_findings = _compute_ctr_findings({"name": channel_name}, _yt_an, _ctr_snapshot)
            _quad_findings = _compute_quadrant_findings(_ctr_findings, _yt_an, videos, _ctr_snapshot)
            quadrant_map = {}
            for bucket, vlist in (_quad_findings.get("buckets") or {}).items():
                for entry in vlist:
                    vid = entry.get("video_id")
                    if vid:
                        quadrant_map[vid] = bucket
            print(f"  🎯 象限归类: {_quad_findings.get('status')} · {len(quadrant_map)} 视频")
        except Exception as e:
            print(f"  ⚠️ 象限归类失败（LLM 将按'表现平庸'兜底）: {e}")
            quadrant_map = {}

        # 增量保存回调：每批次完成后立即存盘
        def save_incremental(current_analyses):
            # 映射局部索引→全局索引
            mapped = {}
            for local_idx, analysis in current_analyses.items():
                if local_idx < len(video_indices):
                    mapped[video_indices[local_idx]] = analysis
            scored = _build_scored_videos(videos, mapped, video_indices, existing_scores, covers_index)
            _save_result(channel_name, lang, snapshot, distill, market, scored, avg_like_rate, out_path, video_llm_last_run=existing_result.get("video_llm_last_run"), channel_llm_last_run=existing_result.get("channel_llm_last_run"))

        # 映射：llm_analyze_and_optimize返回的索引是videos_to_analyze内的，需要映射回videos的全局索引
        raw_analyses = llm_analyze_and_optimize(videos_to_analyze, distill, lang, save_callback=save_incremental, growth=snapshot.get("growth", {}), covers=covers_list, quadrant_map=quadrant_map)
        if raw_analyses:
            # 映射回全局索引
            llm_analyses = {}
            for local_idx, analysis in raw_analyses.items():
                if local_idx < len(video_indices):
                    llm_analyses[video_indices[local_idx]] = analysis
            print(f"    ✅ {len(llm_analyses)}条新视频已诊断")
        else:
            print(f"    ⚠️ LLM诊断失败，fallback到Python评分")
    elif use_llm:
        print(f"  🧠 所有视频已有诊断，跳过LLM")
    else:
        print(f"  ⏭️ 跳过LLM（--no-llm）")

    # 构建视频评分列表（合并已有+新分析）
    # P-retention-fix: 传入 retention_index，把留存数据 join 回单视频
    retention_index = {
        rv.get("video_id"): rv
        for rv in (snapshot.get("retention_data") or {}).get("videos", [])
        if rv.get("video_id")
    }
    scored_videos = _build_scored_videos(videos, llm_analyses, list(range(len(videos))), existing_scores, covers_index, retention_index, quadrant_map=quadrant_map)
    scored_videos.sort(key=lambda x: x["score"])

    # 统计
    scores = [v["score"] for v in scored_videos]
    needs_opt = sum(1 for v in scored_videos if v["needs_optimization"])
    avg_score = sum(scores) / len(scores) if scores else 0
    print(f"  📊 均分: {avg_score:.1f}/10 | 需优化: {needs_opt}/{len(scored_videos)}")

    # 频道级LLM分析：每周跑一次
    print(f"  🧠 频道级LLM分析...", end="", flush=True)
    channel_llm = existing_result.get("channel_llm")  # 默认保留已有
    channel_llm_due = True
    channel_llm_last_run = existing_result.get("channel_llm_last_run")
    if channel_llm_last_run and not force and not force_channel_llm:
        try:
            last_run_dt = datetime.fromisoformat(channel_llm_last_run.replace("Z", "+00:00"))
            today = datetime.now(timezone.utc).date()
            this_monday = today - timedelta(days=today.weekday())
            monday_dt = datetime(this_monday.year, this_monday.month, this_monday.day, tzinfo=timezone.utc)
            if last_run_dt >= monday_dt:
                channel_llm_due = False
                print(f" 本周已跑过（{last_run_dt.strftime('%m-%d')}），跳过")
        except Exception:
            pass

    if channel_llm_due:
        snapshot_with_diag = dict(snapshot)
        snapshot_with_diag["_channel_diag"] = channel_level_diagnosis(snapshot, distill, market)
        snapshot_with_diag["video_scores"] = scored_videos
        # P3-11: 统一 slug 解析（与留存读取一致）
        llm_slug = _resolve_oauth_slug(channel_name, slug_r)
        yt_analytics = {}
        if llm_slug:
            analytics_path = Path(f"data/own/analytics/{llm_slug}.json")
            if analytics_path.exists():
                yt_analytics = json.loads(analytics_path.read_text(encoding="utf-8"))
                print(f" ✅yt-analytics", end="", flush=True)
        snapshot_with_diag["yt_analytics"] = yt_analytics
        channel_llm = llm_channel_analysis(snapshot_with_diag, distill, lang)
        if channel_llm:
            print(f" ✅")
        else:
            print(f" ⚠️ 失败，保留已有诊断")
            channel_llm = existing_result.get("channel_llm")

    # 保存最终结果
    video_llm_ts = datetime.now(timezone.utc).isoformat() if llm_analyses else existing_result.get("video_llm_last_run")
    channel_llm_ts = datetime.now(timezone.utc).isoformat() if channel_llm_due and channel_llm else existing_result.get("channel_llm_last_run")
    result = _save_result(channel_name, lang, snapshot, distill, market, scored_videos, avg_like_rate, out_path, channel_llm=channel_llm, video_llm_last_run=video_llm_ts, channel_llm_last_run=channel_llm_ts)

    # 历史存档
    today = datetime.now().strftime("%Y%m%d")
    archive_path = DIAGNOSIS_DIR / f"{slug}_{today}.json"
    archive_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"  ✅ 诊断完成 → {out_path}")
    return result


def _match_cover_by_title(title: str, covers_index: dict) -> dict | None:
    """通过标题模糊匹配封面数据。

    P2-6: covers_index 的 key 是 video_id，旧代码拿 video_id 当 title 比永远不匹配。
    改为遍历 covers_index.values()，用 video_title 字段与标题做模糊匹配。
    """
    if not title:
        return None
    title_30 = title[:30]
    for c in covers_index.values():
        ct = c.get("video_title", "")
        if ct and (ct[:30] in title or title_30 in ct):
            return c
    return None


def _build_scored_videos(videos: list, llm_analyses: dict | None, video_indices: list, existing_scores: dict, covers_index: dict | None = None, retention_index: dict | None = None, quadrant_map: dict | None = None) -> list:
    """构建视频评分列表，合并已有LLM结果和新分析结果。
    retention_index: {video_id: retention_video_dict}，若提供则合并单视频留存字段（avg_view_duration/retention_1pct 等）。
    quadrant_map: {video_id: bucket_name}，四象限归类。
    """
    scored_videos = []
    for i, v in enumerate(videos):
        views = v.get("views", 0)
        likes = v.get("likes", 0)
        lr = round(likes / max(views, 1) * 100, 2)
        vid = v.get("video_id", "")

        # 优先用新LLM结果
        if llm_analyses and i in llm_analyses:
            a = llm_analyses[i]
            issues = [{"dimension": "LLM诊断", "issue": iss} for iss in a.get("issues", [])]
            # 封面协同：优先用 _covers.json 的专业分析，LLM结果仅作补充
            cs = None
            if covers_index:
                cover = covers_index.get(vid) or _match_cover_by_title(v.get("title", ""), covers_index)
                if cover and cover.get("封面×标题协同"):
                    cs = cover["封面×标题协同"]
            if not cs:
                cs = a.get("cover_synergy")  # fallback到LLM猜测
            entry = {
                "video_id": vid, "title": v.get("title", ""),
                "views": views, "likes": likes, "like_rate": lr,
                "published_at": v.get("published_at", ""),
                "score": round(a.get("score", 5), 1),
                "scores": {"llm": round(a.get("score", 5), 1)},
                "issues": issues,
                "title_analysis": a.get("title_analysis"),
                "cover_synergy": cs,
                "needs_optimization": a.get("score", 5) < 6.0,
                "optimized_titles": a.get("optimized", []),
                "quadrant": (quadrant_map or {}).get(vid, "表现平庸"),
            }
        elif vid in existing_scores:
            # 复用已有诊断
            entry = existing_scores[vid]
            # 更新播放数据
            entry["views"] = views
            entry["likes"] = likes
            entry["like_rate"] = lr
            # 补四象限
            if "quadrant" not in entry:
                entry["quadrant"] = (quadrant_map or {}).get(vid, "表现平庸")
            # 补封面协同（旧缓存可能没有）
            if not entry.get("cover_synergy") and covers_index:
                cover = covers_index.get(vid) or _match_cover_by_title(v.get("title", ""), covers_index)
                if cover and cover.get("封面×标题协同"):
                    entry["cover_synergy"] = cover["封面×标题协同"]
        else:
            # Fallback: Python基础评分
            entry = {
                "video_id": vid, "title": v.get("title", ""),
                "views": views, "likes": likes, "like_rate": lr,
                "published_at": v.get("published_at", ""),
                "score": 5.0, "scores": {"python_fallback": 5.0},
                "issues": [{"dimension": "诊断", "issue": "LLM未覆盖，使用默认评分"}],
                "needs_optimization": False,
                "quadrant": (quadrant_map or {}).get(vid, "表现平庸"),
            }
            # 补封面协同（fallback也补，不依赖LLM）
            if covers_index:
                cover = covers_index.get(vid) or _match_cover_by_title(v.get("title", ""), covers_index)
                if cover and cover.get("封面×标题协同"):
                    entry["cover_synergy"] = cover["封面×标题协同"]
        # P-retention-fix: 若已授权频道有留存数据，join 单视频留存字段
        if retention_index and vid in retention_index:
            rv = retention_index[vid]
            entry["avg_view_duration"] = rv.get("avg_view_duration")   # 秒
            raw_pct = rv.get("avg_view_pct", 0) or 0
            entry["avg_view_pct"] = min(raw_pct, 100)  # clamp >100 API异常
            entry["retention_1pct"] = rv.get("retention_1pct")         # 0-1
            entry["retention_3min"] = rv.get("retention_3min")
            entry["retention_5min"] = rv.get("retention_5min")
        scored_videos.append(entry)
    return scored_videos


def _save_result(channel_name, lang, snapshot, distill, market, scored_videos, avg_like_rate, out_path, channel_llm=None, video_llm_last_run=None, channel_llm_last_run=None):
    """构建并保存诊断结果。channel_llm=None时跳过频道级LLM（增量保存用）。"""
    rates = [v["likes"] / v["views"] * 100 for v in snapshot.get("videos", []) if v.get("views", 0) > 0]
    channel_diag = channel_level_diagnosis(snapshot, distill, market)

    if channel_llm is None:
        # 增量保存：跳过频道级LLM，用Python诊断占位
        channel_llm = channel_diag
    else:
        pass  # 最终保存：使用调用方传入的channel_llm

    result = {
        "channel_name": channel_name,
        "language": lang,
        "diagnosed_at": datetime.now(timezone.utc).isoformat(),
        "video_llm_last_run": video_llm_last_run,
        "channel_llm_last_run": channel_llm_last_run,
        "channel": channel_diag,
        "channel_llm": channel_llm,
        "distill_benchmark": {
            "avg_title_length": distill.get("stats", {}).get("avg_title_length", 0),
            "key_words": distill.get("how", {}).get("title_constraints", {}).get("key_words", []),
            "best_hours": distill.get("stats", {}).get("best_hours", []),
        },
        "video_scores": scored_videos,
        "summary": {
            "total_videos": len(scored_videos),
            "avg_score": round(sum(v["score"] for v in scored_videos) / len(scored_videos), 1) if scored_videos else 0,
            "needs_optimization": sum(1 for v in scored_videos if v["needs_optimization"]),
            "avg_like_rate": avg_like_rate,
            "top_issues": _summarize_top_issues(scored_videos),
        },
        "retention_data": snapshot.get("retention_data"),
    }

    DIAGNOSIS_DIR.mkdir(parents=True, exist_ok=True)
    # P1-3: 原子写 *_latest.json，避免 panel 读到截断 JSON
    _atomic_write_json(out_path, result)
    return result


def _summarize_top_issues(scored_videos: list) -> list[dict]:
    """汇总最常见的问题"""
    issue_counter = Counter()
    for v in scored_videos:
        for issue in v.get("issues", []):
            key = issue["issue"]
            issue_counter[key] += 1
    return [{"issue": k, "count": v} for k, v in issue_counter.most_common(10)]


def main():
    parser = argparse.ArgumentParser(description="自有频道诊断引擎 v2")
    parser.add_argument("--channel", help="频道名称（如 Apocalyptic_Films）")
    parser.add_argument("--all", action="store_true", help="诊断所有频道")
    parser.add_argument("--no-llm", action="store_true", help="跳过LLM优化")
    parser.add_argument("--force", action="store_true", help="强制重新分析（忽略缓存）")
    parser.add_argument("--force-channel", action="store_true", help="仅强制重跑频道级战略LLM（保留单视频诊断缓存）")
    parser.add_argument("--report", action="store_true", help="不跑 LLM，只读现有 _latest.json 汇总生成 markdown 报告到 output/")
    parser.add_argument("--report-out", default=None, help="报告输出路径（默认 output/channel_diagnosis_report_YYYYMMDD.md）")
    args = parser.parse_args()

    use_llm = not args.no_llm

    # --report: 不跑 LLM，只读所有 _latest.json 汇总生成 markdown 报告
    if args.report:
        _generate_diagnosis_report(args.report_out)
        return

    if args.channel:
        name = args.channel.replace("_", " ")
        run_diagnosis(name, use_llm=use_llm, force=args.force, force_channel_llm=args.force_channel)
    elif args.all:
        # P2-5: 从注册表 our_channels.json 遍历所有频道（不再依赖 CHANNEL_TO_LANG 硬编码，避免 Beer Anime 被漏）
        registry_path = ROOT / "data" / "own" / "our_channels.json"
        names = []
        if registry_path.exists():
            try:
                reg = json.loads(registry_path.read_text(encoding="utf-8"))
                names = [ch.get("name", "") for ch in reg.get("channels", []) if ch.get("name")]
            except Exception as e:
                print(f"⚠️ 读取注册表失败({e})，回退到 CHANNEL_TO_LANG")
        if not names:
            names = list(CHANNEL_TO_LANG.keys())  # fallback
        print(f"📋 待诊断频道({len(names)}): {', '.join(names)}")
        failed = []
        for i, name in enumerate(names):
            print(f"\n{'='*60}\n📺 [{i+1}/{len(names)}] {name}\n{'='*60}")
            try:
                run_diagnosis(name, use_llm=use_llm, force=args.force, force_channel_llm=args.force_channel)
            except Exception as e:
                print(f"❌ {name} 诊断失败: {e}")
                failed.append((name, str(e)))
                continue
        if failed:
            print(f"\n⚠️ {len(failed)} 个频道诊断失败:")
            for name, err in failed:
                print(f"  - {name}: {err[:80]}")
    else:
        print("用法: --channel 频道名 或 --all")


if __name__ == "__main__":
    main()
