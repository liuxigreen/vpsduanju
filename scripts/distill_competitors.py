#!/usr/bin/env python3
"""
竞品频道逐日深度分析

每天从统一数据源 latest.json 中每个语种挑 1 个未分析的新频道，
用 build_50channels.py 的分析逻辑做详细分析，
累积存入 data/competitor_insights/channel_*.json，
更新面板数据源 data/competitors_channels_all.json。

用法：
    python3 scripts/distill_competitors.py              # 每语种1个新频道
    python3 scripts/distill_competitors.py --all         # 全量
    python3 scripts/distill_competitors.py --language 英文
    python3 scripts/distill_competitors.py --migrate     # 迁移旧50频道
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# 复用旧脚本的分析函数（从 build_50channels.py 移入）


def extract_content_tags(titles, description_tags=None):
    """从标题+描述hashtag中提取内容标签"""
    keywords = {
        'romantic': '浪漫爱情', 'billionaire': '豪门', 'ceo': '霸总', 'boss': '霸总',
        'revenge': '复仇', 'secret': '秘密身份', 'contract': '契约婚姻',
        'pregnant': '怀孕', 'baby': '萌宝', 'military': '军婚',
        'werewolf': '狼人', 'vampire': '吸血鬼', 'mafia': '黑帮',
        'sweet': '甜宠', 'love': '爱情', 'rich': '豪门',
        'divorce': '离婚', 'betrayed': '背叛', 'abandoned': '弃养',
        'adopted': '领养', 'orphan': '孤儿', 'twins': '双胞胎',
        'cinderella': '灰姑娘', 'fake': '假身份', 'hidden': '隐藏身份',
        '战神': '战神', '逆袭': '逆袭', '重生': '重生', '穿越': '穿越',
        '甜宠': '甜宠', '虐恋': '虐恋', '复仇': '复仇', '豪门': '豪门',
        '霸总': '霸总', '萌宝': '萌宝',
        'corto': '短剧', 'dulce': '甜宠', 'romance': '爱情',
        'acción': '动作', 'comedia': '喜剧', 'drama': '剧情',
        '女頻': '女频', '男頻': '男频', '古裝': '古装',
        'chinesedrama': '中文短剧', '短劇推薦': '短剧推荐',
        '爱情': '爱情', '宫廷': '宫廷', '玄幻': '玄幻',
    }
    all_text = ' '.join(titles).lower()
    if description_tags:
        all_text += ' ' + ' '.join(description_tags).lower()
    found = []
    for kw, label in keywords.items():
        if kw in all_text and label not in found:
            found.append(label)
    return found[:5]


def analyze_title_patterns(titles):
    """分析标题模式"""
    patterns = []
    for t in titles[:10]:
        t_lower = t.lower()
        if any(w in t_lower for w in ['ceo', 'boss', 'billionaire', 'rich', 'tycoon']):
            patterns.append('霸总/豪门')
        if any(w in t_lower for w in ['revenge', 'betrayed', 'cheat']):
            patterns.append('复仇/背叛')
        if any(w in t_lower for w in ['baby', 'pregnant', 'twins', 'child']):
            patterns.append('萌宝/怀孕')
        if any(w in t_lower for w in ['secret', 'hidden', 'fake', 'identity']):
            patterns.append('秘密身份')
        if any(w in t_lower for w in ['sweet', 'love', 'romantic', 'heart']):
            patterns.append('甜宠/爱情')
        if any(w in t_lower for w in ['战神', '至尊', '龙王']):
            patterns.append('战神/至尊')
        if any(w in t_lower for w in ['逆袭', '翻身', '崛起']):
            patterns.append('逆袭')
    return list(set(patterns))[:3]


def generate_growth_reasons(ch, enriched_data, sample_data):
    """生成增长原因分析"""
    reasons = []
    subs = ch.get('subscribers', 0)
    tier = ch.get('tier', '')
    breakout = ch.get('breakout_count', 0)

    if tier in ('new', 'micro', 'rising'):
        if breakout > 30:
            reasons.append(f'新号但爆款率极高（{breakout}个视频表现突出），内容策略精准')
        elif breakout > 10:
            reasons.append(f'近期{breakout}个视频表现突出，增长势头强劲')
        elif breakout > 0:
            reasons.append(f'{breakout}个视频表现突出')

    if tier == 'head':
        reasons.append(f'头部频道，品牌效应强，订阅基数{subs/10000:.0f}万')

    titles = [v.get('title', '') for v in ch.get('recent_videos', [])[:10]]
    patterns = analyze_title_patterns(titles)
    if patterns:
        reasons.append(f'内容主打{"、".join(patterns)}题材，精准定位目标受众')

    if enriched_data:
        videos = enriched_data.get('videos', [])
        if videos:
            avg_views = sum(v.get('view_count', 0) for v in videos) / len(videos)
            if subs > 0 and avg_views > subs * 0.5:
                reasons.append(f'平均播放{avg_views/1000:.0f}K，超过订阅数50%，内容传播力强')
            top_tags = []
            for v in videos:
                top_tags.extend(v.get('tags', []))
            tag_counts = Counter(top_tags).most_common(3)
            if tag_counts:
                reasons.append(f'标签策略：{"、".join(t[0] for t in tag_counts)}')

    if sample_data:
        sv = sample_data.get('search_views', 0)
        if sv > 10000000:
            reasons.append(f'搜索热度{sv/10000000:.0f}千万，SEO表现优秀')
        elif sv > 1000000:
            reasons.append(f'搜索热度{sv/1000000:.0f}百万，有自然流量')

    if not reasons:
        reasons.append('数据待补充')

    return reasons


def generate_video_analysis(ch, enriched_data):
    """生成爆款视频分析"""
    videos = ch.get('recent_videos', [])
    breakout_videos = ch.get('breakout_videos', [])

    result = {
        'total_videos': ch.get('total_videos', 0),
        'breakout_count': ch.get('breakout_count', 0),
        'sample_titles': [v.get('title', '') for v in videos[:5]],
    }

    if enriched_data:
        evideos = enriched_data.get('videos', [])
        if evideos:
            sorted_by_views = sorted(evideos, key=lambda x: x.get('view_count', 0), reverse=True)
            top3 = sorted_by_views[:3]
            result['top_videos'] = [{
                'title': v.get('title', '')[:80],
                'views': v.get('view_count', 0),
                'likes': v.get('like_count', 0),
                'comments': v.get('comment_count', 0),
                'tags': v.get('tags', [])[:5],
            } for v in top3]

            avg = sum(v.get('view_count', 0) for v in evideos) / len(evideos)
            result['avg_views'] = int(avg)
            result['max_views'] = max(v.get('view_count', 0) for v in evideos)

    hit_titles = [v.get('title', '') for v in breakout_videos[:10]]
    if hit_titles:
        result['hit_title_patterns'] = analyze_title_patterns(hit_titles)
        result['hit_content_tags'] = extract_content_tags(hit_titles)

    return result

DATA_DIR = ROOT / "data"
COMPETITOR_DATA_DIR = DATA_DIR / "competitor_data"
LATEST_FILE = COMPETITOR_DATA_DIR / "latest.json"
INSIGHT_DIR = DATA_DIR / "competitor_insights"
INSIGHT_DIR.mkdir(exist_ok=True)

TRACKER_FILE = INSIGHT_DIR / "_analyzed_channels.json"
PANEL_DATA_FILE = DATA_DIR / "competitors_channels_all.json"
TIERS_FILE = DATA_DIR / "competitor_tiers.json"
TRACKING_DIR = DATA_DIR / "competitor_tracking"
TRACKING_DIR.mkdir(exist_ok=True)

CHANNELS_PER_LANG_PER_DAY = 1

# 五层筛选定义
TIER_DEFS = [
    # (tier_key, min_subs, max_subs, label, pick_count)
    ("top",    1000000, float("inf"), "顶级", 1),
    ("head",   300000,  1000000,      "头部", 2),
    ("mid",    10000,   300000,       "中部", 3),
    ("rising", 1000,    10000,        "起步", 4),
    ("new",    0,       1000,         "新号", 5),
]

TIER_LABELS = {tier_key: label for tier_key, _, _, label, _ in TIER_DEFS}


def get_tier_from_subscribers(subscribers: int) -> tuple[str, str]:
    """按订阅数返回 (tier_key, tier_label)。"""
    subs = int(subscribers or 0)
    for tier_key, min_s, max_s, label, _ in TIER_DEFS:
        if min_s <= subs < max_s:
            return tier_key, label
    return "new", TIER_LABELS["new"]

sys.stdout.reconfigure(line_buffering=True)


# ═══════════════════════════════════════════════
#  追踪
# ═══════════════════════════════════════════════

def _load_tracker() -> dict:
    if TRACKER_FILE.exists():
        try:
            return json.loads(TRACKER_FILE.read_text())
        except:
            pass
    return {"analyzed": {}, "last_updated": ""}


def _save_tracker(tracker: dict):
    tracker["last_updated"] = datetime.now().isoformat()
    TRACKER_FILE.write_text(json.dumps(tracker, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════
#  五层筛选
# ═══════════════════════════════════════════════

def _pick_stratified(channels: list, count: int) -> list:
    """从已排序的频道列表中取高/中/低样本"""
    if len(channels) <= count:
        return channels
    if count == 1:
        return [channels[len(channels) // 2]]  # 取中间的
    if count == 2:
        return [channels[0], channels[-1]]  # 取最高+最低
    # 3+: 取高、中、低分布
    picks = []
    step = (len(channels) - 1) / (count - 1)
    for i in range(count):
        idx = min(round(i * step), len(channels) - 1)
        picks.append(channels[idx])
    return picks


def _extract_genres(ch: dict) -> list:
    """从频道数据中提取题材标签（多来源）"""
    genres = set()

    # 1. LLM分析的top_themes（最准）
    llm = ch.get("llm_analysis", {}).get("distill", {})
    for t in llm.get("what", {}).get("top_themes", []):
        genres.add(t)

    # 2. 规则分析的content_tags
    for t in ch.get("content_tags", []):
        genres.add(t)

    # 3. 视频的description_tags（从latest.json）
    for v in ch.get("videos", []):
        for dt in v.get("description_tags", []):
            dt_lower = dt.lower()
            # 映射常见hashtag到题材
            TAG_GENRE_MAP = {
                "sweetpet": "甜宠", "sweetlove": "甜宠", "romance": "爱情",
                "sadromance": "虐恋", "revenge": "复仇", "ceo": "霸总",
                "billionaire": "豪门", "werewolf": "狼人", "mafia": "黑帮",
                "military": "军婚", "pregnant": "怀孕", "baby": "萌宝",
                "reborn": "重生", "timetravel": "穿越", "fantasy": "奇幻",
                "action": "动作", "thriller": "悬疑", "horror": "恐怖",
                "comedy": "喜剧", "drama": "剧情", "family": "家庭",
            }
            for kw, genre in TAG_GENRE_MAP.items():
                if kw in dt_lower:
                    genres.add(genre)

    # 4. 标题关键词（fallback）
    if not genres:
        for v in ch.get("videos", [])[:5]:
            title = v.get("title", "").lower()
            TITLE_GENRE_MAP = {
                "ceo": "霸总", "boss": "霸总", "billionaire": "豪门",
                "revenge": "复仇", "baby": "萌宝", "pregnant": "怀孕",
                "werewolf": "狼人", "vampire": "吸血鬼", "mafia": "黑帮",
                "sweet": "甜宠", "love": "爱情", "rich": "豪门",
                "divorce": "离婚", "secret": "秘密身份", "military": "军婚",
                "战神": "战神", "逆袭": "逆袭", "重生": "重生", "穿越": "穿越",
                "豪门": "豪门", "霸总": "霸总", "甜宠": "甜宠", "复仇": "复仇",
            }
            for kw, genre in TITLE_GENRE_MAP.items():
                if kw in title:
                    genres.add(genre)

    # 5. 多语种标题关键词（新增）
    if not genres:
        for v in ch.get("videos", [])[:5]:
            title = v.get("title", "").lower()
            MULTILINGUAL_GENRE_MAP = {
                # 土耳其语
                "aşk": "爱情", "intikam": "复仇", "zengin": "豪门",
                "koca": "丈夫", "karı": "妻子", "bebek": "萌宝",
                "evlilik": "婚姻", "ihanet": "背叛", "gizli": "秘密身份",
                "dizi": "剧情", "dram": "剧情",
                # 德语
                "liebe": "爱情", "rache": "复仇", "reich": "豪门",
                "ehe": "婚姻", "baby": "萌宝", "geheim": "秘密身份",
                # 西语
                "amor": "爱情", "venganza": "复仇", "rico": "豪门",
                "matrimonio": "婚姻", "bebé": "萌宝", "secreto": "秘密身份",
                # 葡萄牙语
                "amor": "爱情", "vingança": "复仇", "rico": "豪门",
                "casamento": "婚姻", "bebê": "萌宝", "segredo": "秘密身份",
                # 日语
                "愛": "爱情", "復讐": "复仇", "社長": "霸总",
                "婚約": "婚姻", "秘密": "秘密身份",
                # 韩语
                "사랑": "爱情", "복수": "复仇", "재벌": "豪门",
                "결혼": "婚姻", "비밀": "秘密身份",
            }
            for kw, genre in MULTILINGUAL_GENRE_MAP.items():
                if kw in title:
                    genres.add(genre)

    return list(genres)[:5]


# 每个语种内同类题材最大保留数
MAX_SAME_GENRE = 5


def filter_by_tier() -> dict[str, list]:
    """从 latest.json 按五层筛选频道，已追踪的频道不踢出，题材去重"""
    if not LATEST_FILE.exists():
        return {}
    data = json.loads(LATEST_FILE.read_text())

    # 加载已追踪的频道列表
    existing_tracked = {}
    if TIERS_FILE.exists():
        try:
            old = json.loads(TIERS_FILE.read_text())
            for ch in old.get("channels", []):
                existing_tracked[ch["channel_id"]] = ch
        except:
            pass

    # 1. 更新已追踪频道的订阅数、tier、题材
    for ch in data:
        cid = ch.get("channel_id", "")
        if cid in existing_tracked:
            subs = ch.get("subscribers", 0)
            tier_key, tier_label = get_tier_from_subscribers(subs)
            existing_tracked[cid]["subscribers"] = subs
            existing_tracked[cid]["avg_views"] = ch.get("avg_views", 0)
            existing_tracked[cid]["language"] = ch.get("language", "")
            existing_tracked[cid]["country"] = ch.get("country", "")
            existing_tracked[cid]["tier_key"] = tier_key
            existing_tracked[cid]["tier_label"] = tier_label
            # 更新题材
            genres = _extract_genres(ch)
            if genres:
                existing_tracked[cid]["genres"] = genres

    # 3. 统计已追踪频道的题材覆盖（按语种+地区）
    tracked_ids = set(existing_tracked.keys())
    genre_coverage = defaultdict(lambda: defaultdict(int))  # {lang_country: {genre: count}}
    for cid, info in existing_tracked.items():
        lang = info.get("language", "未知")
        country = info.get("country", "")
        key = f"{lang}_{country}" if country else lang
        for g in info.get("genres", []):
            genre_coverage[key][g] += 1

    # 3. 从 latest.json 中找新频道
    new_candidates = [ch for ch in data if ch.get("channel_id", "") not in tracked_ids]

    new_added = 0
    genre_added = 0
    if new_candidates:
        # 给每个新频道提取题材
        for ch in new_candidates:
            ch["_genres"] = _extract_genres(ch)

        new_by_lang = defaultdict(list)
        for ch in new_candidates:
            new_by_lang[ch.get("language", "未知")].append(ch)

        for lang, channels in new_by_lang.items():
            # 3a. 先按tier规则筛选（不限数量，第一次补充采集）
            for tier_key, min_subs, max_subs, label, pick_count in TIER_DEFS:
                tier_chans = [c for c in channels if min_subs <= c.get("subscribers", 0) < max_subs]
                if not tier_chans:
                    continue
                tier_chans.sort(key=lambda x: x.get("avg_views", 0), reverse=True)
                # 按pick_count限制每个tier的频道数
                picked = tier_chans[:pick_count]
                for ch in picked:
                    cid = ch.get("channel_id", "")
                    if cid and cid not in tracked_ids:
                        genres = ch.get("_genres", [])
                        country = ch.get("country", "")
                        gkey = f"{lang}_{country}" if country else lang
                        # 第一次补充采集：跳过题材去重
                        existing_tracked[cid] = {
                            "channel_id": cid,
                            "name": ch.get("name", ""),
                            "language": lang,
                            "country": country,
                            "subscribers": ch.get("subscribers", 0),
                            "avg_views": ch.get("avg_views", 0),
                            "tier_key": tier_key,
                            "tier_label": label,
                            "genres": genres,
                        }
                        tracked_ids.add(cid)
                        for g in genres:
                            genre_coverage[gkey][g] += 1
                        new_added += 1

            # 3b. 题材补充：筛选有新题材的频道（突破tier限制）
            for ch in channels:
                cid = ch.get("channel_id", "")
                if cid in tracked_ids:
                    continue
                genres = ch.get("_genres", [])
                if not genres:
                    continue
                country = ch.get("country", "")
                gkey = f"{lang}_{country}" if country else lang
                # 只要有1个未覆盖或未满的题材就选入
                new_genre = any(genre_coverage[gkey].get(g, 0) < MAX_SAME_GENRE for g in genres)
                if not new_genre:
                    continue
                subs = ch.get("subscribers", 0)
                tier_key, tier_label = get_tier_from_subscribers(subs)
                existing_tracked[cid] = {
                    "channel_id": cid,
                    "name": ch.get("name", ""),
                    "language": lang,
                    "country": country,
                    "subscribers": subs,
                    "avg_views": ch.get("avg_views", 0),
                    "tier_key": tier_key,
                    "tier_label": tier_label,
                    "genres": genres,
                }
                tracked_ids.add(cid)
                for g in genres:
                    genre_coverage[gkey][g] += 1
                new_added += 1
                genre_added += 1

    # 4. 保存（只增不减）
    result_by_lang = defaultdict(list)
    for ch in existing_tracked.values():
        result_by_lang[ch.get("language", "未知")].append(ch)

    tiers_data = {
        "updated_at": datetime.now().isoformat(),
        "total": len(existing_tracked),
        "by_language": {lang: len(v) for lang, v in result_by_lang.items()},
        "channels": list(existing_tracked.values()),
    }

    TIERS_FILE.write_text(json.dumps(tiers_data, indent=2, ensure_ascii=False))
    total = tiers_data["total"]
    print(f"📋 筛选完成: {total} 个频道 (新增 {new_added}, 其中题材补充 {genre_added})")
    for lang in sorted(result_by_lang.keys()):
        labels = Counter(ch.get("tier_label", "") for ch in result_by_lang[lang])
        summary = ", ".join(f"{l}×{n}" for l, n in labels.most_common())
        lang_genres = Counter()
        for ch in result_by_lang[lang]:
            for g in ch.get("genres", []):
                lang_genres[g] += 1
        g_summary = ", ".join(f"{g}({c})" for g, c in lang_genres.most_common(5))
        print(f"  {lang}: {len(result_by_lang[lang])}个 ({summary}) 题材: {g_summary}")

    return result_by_lang


# ═══════════════════════════════════════════════
#  每日追踪（订阅 + 播放量）
# ═══════════════════════════════════════════════

def track_daily(selected: dict[str, list]):
    """为筛选出的频道记录每日订阅+播放量"""
    today = datetime.now().strftime("%Y-%m-%d")
    tracked = 0
    skipped = 0

    for lang, channels in selected.items():
        for ch in channels:
            cid = ch.get("channel_id", "")
            if not cid:
                continue

            tracking_file = TRACKING_DIR / f"{cid}.json"
            history = []
            if tracking_file.exists():
                try:
                    history = json.loads(tracking_file.read_text())
                except:
                    history = []

            # 检查今天是否已记录
            if history and history[-1].get("date") == today:
                skipped += 1
                continue

            subs = ch.get("subscribers", 0)
            avg_views = ch.get("avg_views", 0)

            history.append({
                "date": today,
                "subscribers": subs,
                "avg_views": avg_views,
            })
            tracking_file.write_text(json.dumps(history, indent=2, ensure_ascii=False))
            tracked += 1

    print(f"📊 每日追踪: 记录 {tracked} 个频道, 跳过 {skipped} 个(已记录)")


# ═══════════════════════════════════════════════
#  加载数据
# ═══════════════════════════════════════════════

def _is_drama_channel(name: str, videos: list = None) -> bool:
    """非短剧频道过滤"""
    non_drama_kw = [
        "official music", "music video", "lyric video", "audio official",
        "bank", "finance", "crypto", "trading", "forex",
        "gaming", "gameplay", "minecraft", "fortnite", "pubg", "mobile legends",
        "cooking", "recipe", "travel vlog", "daily vlog",
        "news channel", "podcast", "tech review", "unboxing", "gadget",
        "telemundo", "sinetron",
        "anime", "manga", "kdrama", "bollywood", "reality tv",
    ]
    drama_kw = [
        # 英文
        "ceo", "billionaire", "revenge", "reborn", "secret", "obsessed", "mafia",
        "boss", "husband", "wife", "pregnant", "divorce", "wedding",
        "drama", "dramabox", "werewolf", "vampire", "romance", "romantic",
        "full movie", "episode", "contract wife", "arranged marriage",
        # 中文
        "总裁", "復仇", "重生", "逆襲", "甜寵", "豪門", "霸總", "逆袭",
        "短剧", "短劇", "微短剧", "爽剧", "穿越", "战神", "赘婿", "追妻",
        # 印尼语
        "pendek", "cinta", "cerita", "kisah", "sub indo",
        # 土耳其语
        "dizi", "mini dizi", "dram", "kısa dizi", "bölüm",
        # 德语
        "kurzdrama", "kurze drama", "drama serie",
        # 西语/葡语
        "drama corto", "drama curto", "telenovela", "novela", "novelas",
        # 日语
        "ドラマ", "短編", "ショートドラマ",
    ]
    name_lower = name.lower()
    if any(kw in name_lower for kw in non_drama_kw):
        return False
    if any(kw in name_lower for kw in drama_kw):
        return True
    if videos:
        titles = [v.get("title", "").lower() for v in videos[:20]]
        hits = sum(1 for t in titles if any(kw in t for kw in drama_kw))
        if hits >= 2:
            return True
    return False


def load_all_channels() -> dict[str, list]:
    """从统一数据源 latest.json 加载频道，按语种分组，过滤非短剧"""
    if not LATEST_FILE.exists():
        return {}
    data = json.loads(LATEST_FILE.read_text())
    by_lang = defaultdict(list)
    for ch in data:
        name = ch.get("name", "")
        videos = ch.get("videos", [])
        if not _is_drama_channel(name, videos):
            continue
        lang = ch.get("language", "未知")
        by_lang[lang].append(ch)
    return dict(by_lang)


def load_snapshots_for_channel(channel_id: str) -> dict:
    """从统一数据源 latest.json 中找某个频道的数据"""
    if not LATEST_FILE.exists():
        return {}
    data = json.loads(LATEST_FILE.read_text())
    for ch in data:
        if ch.get("channel_id") == channel_id:
            return ch
    return {}


def load_enriched_for_channel(channel_id: str) -> dict:
    """从 channel_enriched/ 加载真实播放量数据"""
    enriched_dir = DATA_DIR / "channel_enriched"
    if not enriched_dir.exists():
        return {}
    for f in enriched_dir.glob("*.json"):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text())
            if data.get("channel_id") == channel_id:
                return data
        except:
            continue
    return {}


# ═══════════════════════════════════════════════
#  核心分析（复用 build_50channels.py 逻辑）
# ═══════════════════════════════════════════════

def analyze_single_channel(channel_info: dict, snapshot: dict, enriched_data: dict = None) -> dict:
    """
    用 build_50channels.py 的分析逻辑做单频道深度分析。
    将 snapshot 数据转换为旧脚本期望的格式，调用旧函数。
    """
    channel_id = channel_info.get("channel_id", "")
    name = channel_info.get("name", snapshot.get("name", "未知"))
    lang = channel_info.get("language", snapshot.get("language", "未知"))
    subs = snapshot.get("subscribers", channel_info.get("subscribers", 0))
    tier = snapshot.get("tier", channel_info.get("tier", ""))

    # 构造旧脚本期望的 ch 格式
    videos = snapshot.get("videos", [])
    for v in videos:
        if not v.get("thumbnail") and v.get("video_id"):
            v["thumbnail"] = f"https://i.ytimg.com/vi/{v['video_id']}/maxresdefault.jpg"

    ch = {
        "channel_id": channel_id,
        "name": name,
        "language": lang,
        "subscribers": subs,
        "tier": tier,
        "total_videos": snapshot.get("video_count", len(videos)),
        "breakout_count": len([v for v in videos if v.get("view_count", v.get("views", 0)) >= 10000]),
        "recent_videos": videos,
        "breakout_videos": videos,
    }

    # 用 latest.json 的视频数据构造 enriched_data（补全播放量/标签分析）
    if not enriched_data and videos:
        enriched_data = {"videos": [
            {"view_count": v.get("view_count", v.get("views", 0)),
             "tags": v.get("tags", [])}
            for v in videos
        ]}
    # 调用旧脚本的分析函数
    growth_reasons = generate_growth_reasons(ch, enriched_data or {}, None)
    video_analysis = generate_video_analysis(ch, enriched_data or {})
    titles = [v.get("title", "") for v in videos if v.get("title")]
    content_tags = extract_content_tags(titles)

    # 封面
    sorted_videos = sorted(videos, key=lambda x: x.get("view_count", x.get("views", 0)), reverse=True)
    top_covers = []
    for v in sorted_videos[:3]:
        cover_url = v.get("thumbnail", "")
        if cover_url:
            top_covers.append({
                "title": v.get("title", "")[:60],
                "views": v.get("view_count", v.get("views", 0)),
                "thumbnail": cover_url,
                "video_id": v.get("video_id", ""),
            })

    # 视频详情（旧格式 videos_detail）
    videos_detail = []
    for v in sorted_videos[:5]:
        videos_detail.append({
            "title": v.get("title", "")[:100],
            "views": v.get("view_count", v.get("views", 0)),
            "likes": v.get("like_count", v.get("likes", 0)),
            "comments": v.get("comment_count", v.get("comments", 0)),
            "tags": v.get("tags", [])[:5],
            "thumbnail": v.get("thumbnail", ""),
            "published_at": v.get("published_at", ""),
            "duration": v.get("duration", 0),
            "description_tags": v.get("description_tags", []),
        })

    # 分析文本（旧格式 analysis_text）
    analysis_text = []
    patterns = analyze_title_patterns(titles)
    if patterns:
        analysis_text.append(f"标题主打「{'、'.join(patterns[:2])}」题材")
    if content_tags:
        analysis_text.append(f"内容标签：{'、'.join(content_tags[:3])}")

    # deep_analysis（旧格式）
    deep_analysis = video_analysis.copy()

    return {
        # 基础信息
        "channel_id": channel_id,
        "name": name,
        "language": lang,
        "subscribers": subs,
        "tier": tier or ch.get("tier", ""),
        "url": f"https://www.youtube.com/channel/{channel_id}",
        "total_videos": ch["total_videos"],
        # 详细分析（旧格式）
        "growth_reasons": growth_reasons,
        "video_analysis": video_analysis,
        "content_tags": content_tags,
        "deep_analysis": deep_analysis,
        "videos_detail": videos_detail,
        "analysis_text": analysis_text,
        "thumbnail_url": top_covers[0]["thumbnail"] if top_covers else "",
        # 新增字段
        "analyzed_at": datetime.now().isoformat(),
        "avg_views": video_analysis.get("avg_views", 0),
        "top_covers": top_covers,
    }


# ═══════════════════════════════════════════════
#  选择未分析的新频道
# ═══════════════════════════════════════════════

def pick_new_channels(registry: dict, tracker: dict, per_lang: int = 1) -> list:
    analyzed_ids = set(tracker.get("analyzed", {}).keys())
    picks = []

    for lang, channels in registry.items():
        candidates = [ch for ch in channels if ch.get("channel_id") not in analyzed_ids]
        if not candidates:
            continue
        with_real_views = []
        with_videos = []
        without_data = []
        for ch in candidates:
            snap = load_snapshots_for_channel(ch["channel_id"])
            if not snap:
                without_data.append(ch)
                continue
            videos = snap.get("breakout_videos", snap.get("recent_videos", []))
            has_views = any(v.get("view_count", v.get("views", 0)) > 0 for v in videos)
            if has_views:
                with_real_views.append(ch)
            elif videos:
                with_videos.append(ch)
            else:
                without_data.append(ch)
        for ch in (with_real_views + with_videos + without_data)[:per_lang]:
            picks.append({**ch, "language": lang})

    return picks


# ═══════════════════════════════════════════════
#  更新面板数据
# ═══════════════════════════════════════════════

def _load_tracking_changes(channel_id: str) -> dict:
    """加载频道的追踪数据，计算日环比和周环比"""
    tracking_file = TRACKING_DIR / f"{channel_id}.json"
    if not tracking_file.exists():
        return {}
    try:
        history = json.loads(tracking_file.read_text())
    except:
        return {}
    if len(history) < 2:
        return {"tracking_days": len(history)}

    today = history[-1]
    yesterday = history[-2] if len(history) >= 2 else None
    week_ago = history[-8] if len(history) >= 8 else None

    result = {"tracking_days": len(history)}

    if yesterday:
        result["subs_change_day"] = today["subscribers"] - yesterday["subscribers"]
        result["views_change_day"] = today["avg_views"] - yesterday["avg_views"]
    if week_ago:
        result["subs_change_week"] = today["subscribers"] - week_ago["subscribers"]
        result["views_change_week"] = today["avg_views"] - week_ago["avg_views"]

    return result


def update_panel_data():
    # 加载筛选过的频道列表
    tiers_data = {}
    if TIERS_FILE.exists():
        try:
            tiers_data = json.loads(TIERS_FILE.read_text())
        except:
            pass
    tier_channels = {ch["channel_id"]: ch for ch in tiers_data.get("channels", [])}

    # 加载 latest.json 获取 country 等字段
    latest_map = {}
    if LATEST_FILE.exists():
        try:
            for ch in json.loads(LATEST_FILE.read_text()):
                if ch.get("channel_id"):
                    latest_map[ch["channel_id"]] = ch
        except:
            pass

    all_channels = []
    for f in sorted(INSIGHT_DIR.glob("channel_*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text())
            if "error" not in data:
                da = data.get("deep_analysis", {})
                cid = data.get("channel_id", "")
                # 筛选过的频道：有深度分析就用，没有就用基础数据
                if cid in tier_channels:
                    tier_info = tier_channels[cid]
                    # 用筛选结果的tier/订阅数覆盖分析文件里的旧字段；latest.json 有值时再补充地区/均播
                    data["tier"] = tier_info.get("tier_key", data.get("tier", ""))
                    data["subscribers"] = tier_info.get("subscribers", data.get("subscribers", 0))
                    data["language"] = tier_info.get("language", data.get("language", ""))
                    data["avg_views"] = tier_info.get("avg_views", data.get("avg_views", 0))
                    if cid in latest_map:
                        data["country"] = latest_map[cid].get("country", data.get("country", ""))
                        data["language"] = latest_map[cid].get("language", data.get("language", ""))
                        data["subscribers"] = latest_map[cid].get("subscribers", data.get("subscribers", 0))
                        data["avg_views"] = latest_map[cid].get("avg_views", data.get("avg_views", 0))
                    # 合入 LLM 分析数据（stats + distill）
                    llm = data.get("llm_analysis", {})
                    if llm:
                        data["llm_stats"] = llm.get("stats", {})
                        data["llm_distill"] = llm.get("distill", {})
                    all_channels.append(data)
        except:
            continue

    # 补充筛选了但还没分析文件的频道
    analyzed_ids = {ch.get("channel_id") for ch in all_channels}
    for cid, tier_info in tier_channels.items():
        if cid not in analyzed_ids:
            ch_data = latest_map.get(cid, {})
            all_channels.append({
                "channel_id": cid,
                "name": tier_info.get("name", ""),
                "language": tier_info.get("language", ""),
                "country": ch_data.get("country", ""),
                "subscribers": tier_info.get("subscribers", 0),
                "avg_views": tier_info.get("avg_views", 0),
                "tier": tier_info.get("tier_key", ""),
                "total_videos": 0,
                "videos_detail": [],
                "content_tags": [],
                "deep_analysis": {},
                "analysis_text": [],
                "top_covers": [],
            })

    # 合入追踪数据（日环比/周环比）
    for ch in all_channels:
        cid = ch.get("channel_id", "")
        if cid:
            tracking = _load_tracking_changes(cid)
            ch["tracking"] = tracking

    by_lang = defaultdict(list)
    for ch in all_channels:
        by_lang[ch.get("language", "未知")].append(ch)

    for lang in by_lang:
        by_lang[lang].sort(key=lambda x: x.get("avg_views", 0), reverse=True)

    tier_dist = Counter(ch.get("tier", "unknown") for ch in all_channels)

    panel_data = {
        "updated_at": datetime.now().isoformat(),
        "generated_at": datetime.now().isoformat(),
        "total": len(all_channels),
        "total_channels": len(all_channels),
        "tier_distribution": dict(tier_dist),
        "by_language": {lang: len(chs) for lang, chs in by_lang.items()},
        "channels": all_channels,
    }

    PANEL_DATA_FILE.write_text(json.dumps(panel_data, indent=2, ensure_ascii=False))
    print(f"  📊 面板数据已更新: {len(all_channels)} 频道")
    return panel_data


# ═══════════════════════════════════════════════
#  迁移旧50频道
# ═══════════════════════════════════════════════

def migrate_old_channels():
    old_file = DATA_DIR / "competitors_50channels.json"
    if not old_file.exists():
        print("❌ 旧数据文件不存在")
        return

    old_data = json.loads(old_file.read_text())
    old_channels = old_data.get("channels", [])
    print(f"📋 迁移旧数据: {len(old_channels)} 频道")

    tracker = _load_tracker()
    migrated = 0
    skipped = 0

    for ch in old_channels:
        cid = ch.get("channel_id", "")
        if not cid:
            continue

        channel_file = INSIGHT_DIR / f"channel_{cid}.json"
        if channel_file.exists():
            skipped += 1
            continue

        # 旧数据直接写入，保留所有字段
        new_entry = {
            "channel_id": cid,
            "name": ch.get("name", ""),
            "language": ch.get("language", ""),
            "subscribers": ch.get("subscribers", 0),
            "tier": ch.get("tier", ""),
            "url": ch.get("url", f"https://www.youtube.com/channel/{cid}"),
            "total_videos": ch.get("total_videos", 0),
            "growth_reasons": ch.get("growth_reasons", []),
            "video_analysis": ch.get("video_analysis", {}),
            "content_tags": ch.get("content_tags", []),
            "deep_analysis": ch.get("deep_analysis", {}),
            "videos_detail": ch.get("videos_detail", []),
            "analysis_text": ch.get("analysis_text", []),
            "thumbnail_url": ch.get("thumbnail_url", ""),
            "analyzed_at": datetime.now().isoformat(),
            "avg_views": ch.get("video_analysis", {}).get("avg_views", 0),
            "top_covers": [],
        }

        if new_entry["avg_views"] == 0 and new_entry["total_videos"] == 0:
            skipped += 1
            continue

        channel_file.write_text(json.dumps(new_entry, indent=2, ensure_ascii=False))
        tracker.setdefault("analyzed", {})[cid] = {
            "name": ch.get("name", ""),
            "language": ch.get("language", ""),
            "analyzed_at": datetime.now().isoformat(),
            "source": "migrated",
        }
        migrated += 1

    _save_tracker(tracker)
    print(f"  ✅ 迁移完成: {migrated} 频道, 跳过 {skipped} 频道")
    update_panel_data()


# ═══════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════

def distill_competitors(language: str = None, pick_new: bool = True, per_lang: int = 1):
    print(f"📋 开始竞品频道分析")

    # ── 1. 五层筛选 ──
    selected = filter_by_tier()
    if not selected:
        print("❌ latest.json 为空或不存在")
        return

    # ── 2. 每日追踪（订阅+播放量）──
    track_daily(selected)

    # ── 3. 逐频道深度分析（只分析未分析过的）──
    tracker = _load_tracker()
    analyzed_ids = set(tracker.get("analyzed", {}).keys())

    channels_to_analyze = []
    skipped_insufficient = 0
    for lang, channels in selected.items():
        if language and lang != language:
            continue
        for ch in channels:
            cid = ch.get("channel_id", "")
            if cid in analyzed_ids:
                continue
            # 新频道：≥3视频即可分析（能被搜进来说明有热度）
            snapshot = load_snapshots_for_channel(cid)
            videos = snapshot.get("videos", []) if snapshot else []
            if len(videos) < 3:
                skipped_insufficient += 1
                continue
            channels_to_analyze.append(ch)
    if skipped_insufficient:
        print(f"  ⏳ {skipped_insufficient} 个新频道数据不足（<5视频或均播<1000），只追踪不分析")

    if channels_to_analyze:
        print(f"\n🔍 逐频道深度分析 ({len(channels_to_analyze)} 个新频道)")
        for ch in channels_to_analyze:
            cid = ch["channel_id"]
            name = ch.get("name", cid[:12])
            lang = ch.get("language", "?")
            print(f"\n  📺 [{lang}] {name[:40]}")

            snapshot = load_snapshots_for_channel(cid)
            if not snapshot:
                print(f"    ⚠️ 无快照数据，跳过")
                continue

            enriched = load_enriched_for_channel(cid)
            result = analyze_single_channel(ch, snapshot, enriched or None)

            channel_file = INSIGHT_DIR / f"channel_{cid}.json"
            channel_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))

            tier = result.get("tier", "?")
            avg = result.get("avg_views", 0)
            va = result.get("video_analysis", {})
            bc = va.get("breakout_count", 0)
            tags = "、".join(result.get("content_tags", [])) or "未分类"
            print(f"    ✅ [{tier}] {result.get('total_videos', 0)}视频, 均播{avg:,}, 爆款{bc}, {tags}")

            tracker.setdefault("analyzed", {})[cid] = {
                "name": name,
                "language": lang,
                "analyzed_at": datetime.now().isoformat(),
            }
            time.sleep(0.5)

        _save_tracker(tracker)
    else:
        print(f"\n  ℹ️ 所有筛选频道都已分析过，只做追踪")

    # ── 4. 更新面板数据 ──
    update_panel_data()

    print(f"\n{'='*50}")
    print(f"✅ 完成")
    print(f"{'='*50}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="竞品频道筛选+分析+追踪")
    parser.add_argument("--language", help="语种")
    parser.add_argument("--all", action="store_true", help="全量分析")
    parser.add_argument("--migrate", action="store_true", help="迁移旧50频道数据")
    parser.add_argument("--filter-only", action="store_true", help="只筛选+追踪，不分析")
    args = parser.parse_args()

    if args.migrate:
        migrate_old_channels()
    elif args.filter_only:
        selected = filter_by_tier()
        if selected:
            track_daily(selected)
            update_panel_data()
    elif args.all:
        distill_competitors(args.language, pick_new=True, per_lang=999)
    elif args.language:
        distill_competitors(args.language, pick_new=True)
    else:
        distill_competitors(pick_new=True)


if __name__ == "__main__":
    main()
