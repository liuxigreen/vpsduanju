#!/usr/bin/env python3
"""
短剧竞品每日流水线 — 三层蒸馏架构

流程：
  1. discover_channels()      → 搜索+筛选，发现新频道
  2. collect_data()            → yt-dlp采集频道视频数据
  2b. ai_validate_videos()    → 规则打分（多信号加权评分）
  3. filter_data()             → 过滤非短剧+低播放量
  4. save_snapshots()          → 存到 data/competitor_snapshots/
  5a. distill_local_stats()    → 本地统计（6维JSON）
  5b. analyze_covers_mimo()    → MiMo结构提取（封面+标题骨架+钩子）
  6. distill_three_layer()     → 三层蒸馏（principles+examples+generation-rules）

阈值：
  - 竞品频道：近30天 ≥ 3个视频破 10,000 播放
  - 竞品单视频：≥ 10,000 播放才进入蒸馏
  - 爆款标记：≥ 100,000 播放 或 播放量 > 频道均值 × 3

用法：
  python3 scripts/daily_pipeline.py              # 全流程
  python3 scripts/daily_pipeline.py --step 1     # 只跑发现
  python3 scripts/daily_pipeline.py --step 2b    # 只跑规则打分
  python3 scripts/daily_pipeline.py --step 5a    # 只跑本地统计
  python3 scripts/daily_pipeline.py --step 5b    # 只跑封面分析
  python3 scripts/daily_pipeline.py --step 6     # 只跑蒸馏
  python3 scripts/daily_pipeline.py --lang 英文  # 指定语种
"""

import json
import os
import re
import sys
import time
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DATA_DIR = ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "competitor_snapshots"  # legacy, kept for archive
COMPETITOR_DATA_DIR = DATA_DIR / "competitor_data"
LATEST_FILE = COMPETITOR_DATA_DIR / "latest.json"  # 唯一真相源
STAGING_FILE = COMPETITOR_DATA_DIR / "staging.json"  # 待筛选库（搜索结果写入这里）
DISTILL_DIR = ROOT / "distill"
EVIDENCE_DIR = DISTILL_DIR / "evidence"
OUTPUT_DIR = DISTILL_DIR / "outputs"
REGISTRY_FILE = DATA_DIR / "competitor_registry.json"
SEEN_FILE = DATA_DIR / "discovered_channels" / "seen_channels.json"

for d in [COMPETITOR_DATA_DIR, EVIDENCE_DIR, OUTPUT_DIR]:
    d.mkdir(parents=True, exist_ok=True)

API_KEY_FILE = Path.home() / ".hermes" / "duanju" / "api_key.txt"
API_KEYS_FILE = Path.home() / ".hermes" / "duanju" / "api_keys.json"

sys.stdout.reconfigure(line_buffering=True)

# ─── 阈值配置 ───
MIN_VIEWS_COMPETITOR = 10_000     # 竞品视频最低播放量
MIN_VIEWS_OUR = 1_000             # 自有频道最低播放量
BREAKOUT_VIEWS = 100_000          # 爆款标记阈值
BREAKOUT_RATIO = 3                # 爆款倍率（频道均值 × N）
MIN_BREAKOUT_PER_CHANNEL = 3      # 频道筛选：近30天至少N个视频破万


# ═══════════════════════════════════════════════
#  Step 1: 发现新频道
# ═══════════════════════════════════════════════

SEARCH_QUERIES = [
    # === 精简版：核心赛道词，覆盖自有频道语种 + 缺口语种 ===
    # 繁中 - 家庭伦理赛道（追劇姐妹）- 2个
    "家庭倫理短劇", "婆媳短劇",
    # 英文 - 末世赛道（Apocalyptic Films）- 2个
    "apocalypse drama full episode", "post apocalyptic short drama",
    # 西语 - 复仇/逆袭赛道（Luna Drama Estudio）- 2个
    "drama corto venganza", "drama de mujer empoderada",
    # 葡萄牙 - 甜宠/爱情赛道（DramaVerve）- 2个
    "drama romântico completo", "drama de amor completo",
    # 印尼 - 通用 - 2个
    "drama pendek", "drama pendek full episode",
    # 德语 - 补缺 - 4个
    "kurzdrama deutsch", "drama serie deutsch", "türkische serie deutsch", "kurze drama serie",
    # 土耳其 - 补缺 - 4个
    "kısa dizi türkçe", "kısa dram", "türkçe dizi", "türk drama",
    # 日语 - 补缺 - 4个
    "ショートドラマ 日本語", "短編ドラマ", "日本語ドラマ", "ドラマ 短編",
    # 泰语 - 补缺 - 4个
    "ละครสั้น", "ซีรีส์สั้น", "ละครไทย", "short drama thai",
    # 韩语 - 补缺 - 4个
    "단편 드라마", "단편 영화", "드라마 한국", "short drama korean",
    # 英文通用 - 2个
    "short drama full episode", "CEO contract wife drama",
    # 繁中通用 - 1个
    "总裁短剧",
]

DRAMA_KEYWORDS = {
    # 英文核心身份词（从蒸馏钩子提取）
    "ceo", "billionaire", "heiress", "mafia boss", "alpha",
    "prince", "princess", "tycoon", "mob boss", "vampire lord",
    "master chef", "assassin", "dragon king", "alpha king",
    # 英文核心关系词
    "husband", "wife", "ex-husband", "twin", "stepbrother", "stepsister",
    "fiance", "bodyguard", "fake girlfriend", "contract marriage",
    "arranged marriage", "flash marriage", "married stranger",
    # 英文核心冲突词
    "revenge", "betrayed", "abandoned", "reborn", "divorce",
    "cheated", "dumped", "kicked out", "framed", "humiliated",
    # 英文核心情绪词
    "obsessed", "spoiled", "possessive", "heartbroken", "jealous",
    # 英文核心反转词
    "turns out", "secretly", "revealed", "in disguise", "awakens",
    "unaware", "hidden identity", "only to learn",
    # 中文核心
    "总裁", "復仇", "重生", "逆襲", "甜寵", "豪門", "霸總", "逆袭",
    "短剧", "短劇", "微短剧", "爽剧", "穿越", "古装", "悬疑", "战神",
    "千金", "赘婿", "追妻", "灰姑娘", "虐恋", "修仙", "玄幻",
    # 通用标签
    "drama", "dramabox", "reelshort", "shortdrama", "minidrama",
    "sub indo", "full movie", "full episode", "series cortas",
    # 印尼语
    "suami", "istri", "kaya", "miliarder", "nikah", "hamil", "balas dendam",
    "cerita", "kisah",
    # 葡/西语
    "novela", "telenovela", "marido", "esposa", "bilionário", "vingança",
    "casamento", "grávida", "traición", "venganza", "casada", "embarazada",
    # 中文补充
    "复仇", "甜宠", "豪门", "霸总", "總裁",
}

# 非短剧频道指标（频道名/描述命中则直接排除）
NON_DRAMA_INDICATORS = {
    # 音乐
    "official music", "music video", "lyric video", "audio official",
    "records", "label", "singing", "cover by", "remix",
    # 金融
    "bank", "finance", "crypto", "trading", "forex", "fintech", "investment",
    # 游戏
    "gaming", "gameplay", "minecraft", "fortnite", "pubg", "mobile legends",
    # 生活/杂类
    "cooking", "recipe", "travel vlog", "daily vlog", "beauty", "makeup",
    "fitness", "workout", "yoga",
    # 知识/科技
    "news channel", "podcast", "tech review", "unboxing", "tutorial",
    "education", "documentary",
    # 体育
    "football", "soccer", "basketball", "cricket", "tennis", "ufc", "boxing",
    # 儿童
    "kids", "nursery", "cartoon", "animation",
}

# 已知短剧平台白名单（频道名命中直接通过）
KNOWN_DRAMA_PLATFORMS = {
    "reelshort", "dramabox", "shorttv", "shortmax", "flareflow", "vigloo",
    "dramalove", "flextv", "99shortdrama", "dramago", "moboReels",
    "shortsTV", "drama lovehouse", "dramawave", "mango short",
    "ubiti", "GoodShort", "Kalos TV", "MiniShort", "ReelSaga",
}


def _load_api_keys() -> list[str]:
    """加载所有API key（支持多key轮换）"""
    keys = []
    # 优先从 api_keys.json 加载（数组格式）
    if API_KEYS_FILE.exists():
        try:
            keys = json.loads(API_KEYS_FILE.read_text())
        except:
            pass
    # 兼容单key文件
    if not keys and API_KEY_FILE.exists():
        key = API_KEY_FILE.read_text().strip()
        if key:
            keys = [key]
    if not keys:
        raise RuntimeError(f"API Key not found: {API_KEYS_FILE} or {API_KEY_FILE}")
    return keys


# 全局key状态
_API_KEYS: list[str] = []
_API_KEY_INDEX: int = 0


def _get_current_key() -> str:
    global _API_KEYS, _API_KEY_INDEX
    if not _API_KEYS:
        _API_KEYS = _load_api_keys()
    return _API_KEYS[_API_KEY_INDEX % len(_API_KEYS)]


def _rotate_key():
    """切换到下一个key"""
    global _API_KEY_INDEX, _API_KEYS
    if not _API_KEYS:
        _API_KEYS = _load_api_keys()
    old_idx = _API_KEY_INDEX
    _API_KEY_INDEX = (_API_KEY_INDEX + 1) % len(_API_KEYS)
    print(f"  🔄 API Key轮换: #{old_idx} → #{_API_KEY_INDEX} (共{len(_API_KEYS)}个)")


def _yt_api(path: str, **params) -> dict:
    """YouTube API调用，自动轮换key（遇到403/429配额耗尽时）"""
    import urllib.parse, http.client
    global _API_KEYS
    if not _API_KEYS:
        _API_KEYS = _load_api_keys()
    max_retries = len(_API_KEYS)

    for attempt in range(max_retries):
        key = _get_current_key()
        conn = http.client.HTTPSConnection("www.googleapis.com")
        qs = "&".join(f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in {**params, "key": key}.items())
        conn.request("GET", f"/youtube/v3/{path}?{qs}")
        r = conn.getresponse()
        body = r.read().decode()

        if r.status == 200:
            return json.loads(body)

        if r.status in (403, 429) and "quota" in body.lower():
            print(f"  ⚠️ 配额耗尽 (key#{_API_KEY_INDEX})")
            conn.close()
            if attempt < max_retries - 1:
                _rotate_key()
                continue
            else:
                raise RuntimeError("所有API Key配额已耗尽")

        conn.close()
        raise RuntimeError(f"API {r.status}: {body[:200]}")

    raise RuntimeError("API调用失败")



def _fetch_subscribers(channel_ids: list) -> tuple:
    """批量获取频道订阅数+地区（channels.list API，1 unit/50频道）"""
    result = {}
    countries = {}
    for i in range(0, len(channel_ids), 50):
        batch = channel_ids[i:i+50]
        try:
            data = _yt_api("channels", part="statistics,snippet",
                          id=",".join(batch), maxResults=50)
            for item in data.get("items", []):
                cid = item["id"]
                subs = int(item.get("statistics", {}).get("subscriberCount", 0))
                country = item.get("snippet", {}).get("country", "")
                result[cid] = subs
                if country:
                    countries[cid] = country
            time.sleep(0.2)  # 控制频率
        except Exception as e:
            print(f"  ⚠️ 获取订阅数失败: {e}")
    return result, countries


def _load_seen() -> set:
    if SEEN_FILE.exists():
        return set(json.loads(SEEN_FILE.read_text()))
    return set()


def _save_seen(seen: set):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(list(seen), ensure_ascii=False))


def _is_drama_channel(title: str, description: str = "", video_titles: list = None) -> bool:
    """判断是否短剧频道 — 平台白名单 > 黑名单 > 关键词 > 视频标题"""
    text = (title + " " + description).lower()
    
    # 已知短剧平台白名单 → 直接通过
    if any(p.lower() in text for p in KNOWN_DRAMA_PLATFORMS):
        return True
    
    # 黑名单排除
    if any(kw in text for kw in NON_DRAMA_INDICATORS):
        return False
    
    # 频道名/描述命中短剧关键词
    if any(kw in text for kw in DRAMA_KEYWORDS):
        return True
    
    # 视频标题命中短剧关键词（至少2个标题命中）
    if video_titles:
        hits = sum(1 for t in video_titles if any(kw in t.lower() for kw in DRAMA_KEYWORDS))
        if hits >= 2:
            return True
    
    return False


def _is_drama_video(video: dict) -> bool:
    """判断是否短剧视频 — 优先用时长，无时长则用标题/标签"""
    title = video.get("title", "").lower()
    tags = [t.lower() for t in video.get("description_tags", [])]
    text = title + " " + " ".join(tags)

    # ── 反向排除（明确非短剧） ──
    non_drama_video_keywords = {
        "cover by", "music video", "official video", "sing off", "remix",
        "tiktok sing", "behind the scenes", "bloopers", "reaction video",
        "podcast", "vlog", "tutorial", "unboxing",
        "webinar", "seminar", "keynote",
        "video oficial", "video official", "making of", "documentary",
    }
    if any(kw in text for kw in non_drama_video_keywords):
        return False

    duration = video.get("duration", 0)

    # 有时长 → 用时长判断
    if duration:
        if duration < 600 or duration > 10800:
            return False
        return True

    # 无时长 → 用标题/标签判断
    # 正向：标题含短剧关键词
    if any(kw in text for kw in DRAMA_KEYWORDS):
        return True

    # 正向：标题含集数标记
    import re
    if re.search(r'ep\d+|episode|full\b|\bpart\d+', title):
        return True

    # 无法判断 → 排除
    return False


def discover_channels(limit: int = 10, months: int = 12) -> list[dict]:
    """
    搜索各地区有爆款短剧的频道。
    核心条件：14天内有 ≥ 1个破万播放的短剧视频。
    策略：yt-dlp搜索视频 → 反查频道 → 去重 → 验证是否短剧。
    """
    import urllib.parse
    seen = _load_seen()
    found = {}  # channel_id -> info

    print(f"🔍 Step 1: 发现新频道 (目标{limit}个)")

    # 策略：yt-dlp搜索视频，从视频反查频道（不消耗API配额）
    YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")
    COOKIES = os.path.expanduser("~/duanju/cookies.txt")
    
    for i, query in enumerate(SEARCH_QUERIES):
        if len(found) >= limit * 3:
            break
        try:
            # yt-dlp搜索视频（14天内破万播放）
            cmd = [
                YTDLP,
                f"ytsearch20:{query}",
                "--flat-playlist",
                "--dateafter", "today-2weeks",
                "--match-filters", "view_count>=10000 & view_count<=500000",
                "--print", "%(channel_id)s|||%(channel)s|||%(title)s|||%(view_count)s",
                "--cookies", COOKIES,
                "--no-download",
                "--ignore-errors",
            ]
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,
            )
            
            for line in result.stdout.strip().split("\n"):
                if not line or "|||" not in line:
                    continue
                
                parts = line.split("|||")
                if len(parts) < 4:
                    continue
                
                cid, ch_name, title, views = parts[0], parts[1], parts[2], parts[3]
                
                # 跳过无效ID
                if not cid or cid == "NA" or cid in seen or cid in found:
                    continue
                
                # 先用频道名快速过滤非短剧
                if not _is_drama_channel(ch_name, ""):
                    continue
                
                found[cid] = {
                    "channel_id": cid,
                    "name": ch_name,
                    "description": "",
                    "language": _detect_language(query),
                    "discovered_at": datetime.now().isoformat(),
                    "_source_video": title[:100] if title else "",
                }
            
            time.sleep(0.5)  # 控制搜索频率
            
        except Exception as e:
            print(f"  ⚠️ 搜索异常 ({query[:20]}): {e}")

    if not found:
        print("  ❌ 未找到新频道")
        return []

    # 批量获取订阅数
    channel_ids = list(found.keys())
    subscribers, countries = _fetch_subscribers(channel_ids)
    for cid, subs in subscribers.items():
        found[cid]["subscribers"] = subs
    for cid, country in countries.items():
        if cid in found:
            found[cid]["country"] = country

    # 验证：用yt-dlp获取频道最新10个视频，按播放量排序取前5个
    verified = []
    for cid, info in list(found.items())[:limit * 2]:
        try:
            # 用yt-dlp获取频道最新10个视频，按播放量排序取前5个
            videos = _fetch_channel_videos_ytdlp(cid, max_videos=10, top_n=5)

            if not videos:
                print(f"  ⏭️ {info['name'][:30]} — 无视频，跳过")
                continue

            # 二次验证：视频标题必须含短剧关键词
            video_titles = [v.get("title", "") for v in videos]
            if not _is_drama_channel(info["name"], info.get("description", ""), video_titles):
                print(f"  ⏭️ {info['name'][:30]} — 视频标题非短剧，跳过")
                continue

            # 用视频标题自动检测语种

            # 核心条件：播放量最高的5个视频中，有破万播放的短剧视频
            breakout = [v for v in videos
                       if v.get("view_count", 0) >= MIN_VIEWS_COMPETITOR
                       and _is_drama_video(v)]

            if len(breakout) >= 1:
                info["breakout_count"] = len(breakout)
                info["total_videos"] = len(videos)
                info["avg_views"] = sum(v.get("view_count", 0) for v in videos) // max(len(videos), 1)
                info["max_views"] = max(v.get("view_count", 0) for v in videos)
                verified.append(info)
                print(f"  ✅ {info['name'][:30]} — {len(breakout)}个爆款, 最高{info['max_views']:,}")
            else:
                print(f"  ⏭️ {info['name'][:30]} — 无破万视频，跳过")

        except Exception as e:
            print(f"  ⚠️ 验证失败: {e}")
        time.sleep(0.3)

    # 保存到 staging.json（待筛选库）
    verified = verified[:limit]
    if verified:
        # 更新注册表（只记录ID，避免重复搜索）
        seen.update(info["channel_id"] for info in verified)
        _save_seen(seen)
        
        # 写入 staging.json（而不是 latest.json）
        existing_staging = []
        if STAGING_FILE.exists():
            existing_staging = json.loads(STAGING_FILE.read_text())
        existing_ids = {ch["channel_id"] for ch in existing_staging}
        
        new_channels = [ch for ch in verified if ch["channel_id"] not in existing_ids]
        if new_channels:
            existing_staging.extend(new_channels)
            STAGING_FILE.write_text(json.dumps(existing_staging, ensure_ascii=False, indent=2))
            print(f"  📦 发现 {len(new_channels)} 个新频道 → staging.json")
        else:
            print(f"  ⚠️ 所有频道已在 staging.json 中")

    return verified


def _detect_language(query: str) -> str:
    """从搜索词推断语种"""
    if any(ord(c) > 0x4e00 for c in query):
        if "短劇" in query:
            return "繁中"
        return "zh-CN"
    if any(kw in query for kw in ["drama pendek", "drama singkat"]):
        return "印尼"
    if "ละคร" in query:
        return "泰语"
    if "drama ngắn" in query:
        return "越南"
    if "단편" in query:
        return "韩语"
    if "短編" in query:
        return "日语"
    if "drama corto" in query:
        return "西语"
    if any(kw in query for kw in ["drama curto", "drama romântico", "drama de amor"]):
        return "葡萄牙"
    if any(kw in query for kw in ["kısa dizi", "kısa dram", "türkçe"]):
        return "土耳其"
    if any(kw in query for kw in ["kurzdrama", "kurze drama"]):
        return "德语"
    return "英文"


def _is_recent(date_str: str, days: int = 30) -> bool:
    """判断日期是否在N天内"""
    if not date_str:
        return False
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        return dt > datetime.now(timezone.utc) - timedelta(days=days)
    except:
        try:
            dt = datetime.strptime(date_str[:10], "%Y%m%d")
            return dt > datetime.now() - timedelta(days=days)
        except:
            return False


def _parse_duration(iso_duration: str) -> int:
    """解析ISO 8601时长（PT1H2M3S → 秒数）"""
    import re
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', iso_duration)
    if not match:
        return 0
    h = int(match.group(1) or 0)
    m = int(match.group(2) or 0)
    s = int(match.group(3) or 0)
    return h * 3600 + m * 60 + s


def _fetch_channel_videos_ytdlp(channel_id: str, max_videos: int = 10, top_n: int = 0) -> list:
    """
    用yt-dlp快速获取频道视频基础数据（不消耗API）。
    flat-playlist返回: video_id, title, view_count, duration, upload_date
    如果 top_n > 0，返回播放量最高的 top_n 个视频
    """
    import subprocess
    import json as _json

    try:
        url = f"https://www.youtube.com/channel/{channel_id}/videos"
        cmd = [
            "yt-dlp",
            "--cookies-from-browser", "chrome",
            "--dump-json",
            "--flat-playlist",
            "--playlist-items", f"1:{max_videos}",
            "--ignore-errors",
            url
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            return []

        videos = []
        for line in result.stdout.strip().split('\n'):
            if not line:
                continue
            try:
                item = _json.loads(line)
                vid = item.get("id", "")
                if vid:
                    videos.append({
                        "video_id": vid,
                        "title": item.get("title", ""),
                        "view_count": int(item.get("view_count", 0) or 0),
                        "duration": int(item.get("duration", 0) or 0),
                        "published_at": item.get("upload_date", ""),
                    })
            except _json.JSONDecodeError:
                continue

        videos.sort(key=lambda x: x.get("view_count", 0), reverse=True)
        if top_n > 0:
            return videos[:top_n]
        return videos[:max_videos]

    except Exception as e:
        print(f"    ⚠️ yt-dlp异常: {e}")
        return []


def _fetch_channel_videos(channel_id: str, max_videos: int = 15, days: int = 14) -> list:
    """
    用yt-dlp获取频道视频ID+标题+标签，用YouTube API获取详情。
    两步走：yt-dlp拿videoId+title+tags → videos拿statistics+description。
    API失败时自动fallback到纯yt-dlp。
    """
    try:
        # Step 1: yt-dlp 获取频道视频ID、标题、标签（不消耗API）
        ytdlp_videos = _fetch_channel_videos_ytdlp(channel_id, max_videos=max_videos)
        if not ytdlp_videos:
            return []

        video_ids = [v["video_id"] for v in ytdlp_videos]
        ytdlp_map = {v["video_id"]: v for v in ytdlp_videos}

        # Step 2: YouTube API 获取详情（like_count, comment_count, description, thumbnail）
        videos = []
        for i in range(0, len(video_ids), 50):
            batch = video_ids[i:i+50]
            stats_data = _yt_api("videos",
                                part="snippet,statistics,contentDetails",
                                id=",".join(batch))
            if not stats_data:
                continue
            for item in stats_data.get("items", []):
                vid = item["id"]
                v_snip = item.get("snippet", {})
                stats = item.get("statistics", {})
                content = item.get("contentDetails", {})

                # 获取最佳封面URL
                thumbs = v_snip.get("thumbnails", {})
                thumbnail = (thumbs.get("maxres", {}).get("url", "")
                           or thumbs.get("high", {}).get("url", "")
                           or thumbs.get("medium", {}).get("url", ""))

                # 提取描述内容和 hashtag
                desc = v_snip.get("description", "")
                desc_tags = re.findall(r'#([\w]+)', desc) if desc else []

                # 合并yt-dlp数据和API数据
                ytdlp_info = ytdlp_map.get(vid, {})
                videos.append({
                    "video_id": vid,
                    "title": ytdlp_info.get("title", "") or v_snip.get("title", ""),
                    "published_at": ytdlp_info.get("published_at", "") or v_snip.get("publishedAt", ""),
                    "view_count": ytdlp_info.get("view_count", 0) or int(stats.get("viewCount", 0)),
                    "like_count": int(stats.get("likeCount", 0)),
                    "comment_count": int(stats.get("commentCount", 0)),
                    "duration": ytdlp_info.get("duration", 0) or _parse_duration(content.get("duration", "")),
                    "description": desc[:500],
                    "description_tags": desc_tags[:20],
                    "thumbnail": thumbnail or ytdlp_info.get("thumbnail", ""),
                    "tags": ytdlp_info.get("tags", []) or v_snip.get("tags", []),  # 优先用yt-dlp的标签
                })
            time.sleep(0.1)

        # 按播放量降序
        videos.sort(key=lambda x: x.get("view_count", 0), reverse=True)
        return videos[:max_videos]

    except Exception as e:
        print(f"    ⚠️ API采集异常: {e}")
        # API失败，fallback到纯yt-dlp
        return _fetch_channel_videos_ytdlp(channel_id, max_videos)


def _append_to_registry(channels: list):
    """追加新频道到注册表"""
    if REGISTRY_FILE.exists():
        registry = json.loads(REGISTRY_FILE.read_text())
    else:
        registry = {"channels": {}}

    for ch in channels:
        lang = ch.get("language", "未知")
        if lang not in registry["channels"]:
            registry["channels"][lang] = []
        # 去重
        existing_ids = {c["channel_id"] for c in registry["channels"][lang]}
        if ch["channel_id"] not in existing_ids:
            registry["channels"][lang].append({
                "channel_id": ch["channel_id"],
                "name": ch["name"],
                "language": lang,
                "country": ch.get("country", ""),
                "subscribers": 0,
                "tier": "new",
                "added_at": datetime.now().isoformat(),
            })

    registry["updated"] = datetime.now().strftime("%Y-%m-%d")
    REGISTRY_FILE.write_text(json.dumps(registry, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════
#  Step 2: 采集数据
# ═══════════════════════════════════════════════

def collect_data(lang_filter: str = None, collect_all: bool = False, new_only: bool = False) -> list[dict]:
    """
    从注册表中选择频道，采集视频数据。
    默认轮转（每天每语种2个），--all 全量，--new-only 只采新频道。
    """
    print(f"\n📥 Step 2: 采集数据")
    registry = _load_registry()
    channels_by_lang = registry.get("channels", {})
    
    # 把channels_filtered也加入采集范围
    channels_filtered = registry.get("channels_filtered", {})
    if channels_filtered:
        for cid, info in channels_filtered.items():
            lang = info.get("language", "未知")
            if lang not in channels_by_lang:
                channels_by_lang[lang] = []
            # 去重
            existing_ids = {c["channel_id"] for c in channels_by_lang[lang]}
            if cid not in existing_ids:
                channels_by_lang[lang].append({
                    "channel_id": cid,
                    "name": info.get("channel_name", ""),
                    "language": lang,
                    "subscribers": 0,
                    "tier": "new",
                    "discovered_at": info.get("discovered_at", ""),
                })

    if collect_all:
        selected = []
        langs = [lang_filter] if lang_filter else sorted(channels_by_lang.keys())
        for lang in langs:
            selected.extend(channels_by_lang.get(lang, []))
        print(f"  全量采集: {len(selected)} 个频道")
    elif new_only:
        # 只采集今天新发现的频道
        selected = []
        today = datetime.now().strftime("%Y-%m-%d")
        langs = [lang_filter] if lang_filter else sorted(channels_by_lang.keys())
        for lang in langs:
            ch_list = channels_by_lang.get(lang, [])
            for ch in ch_list:
                added_at = ch.get("added_at", "") or ch.get("discovered_at", "")
                if today in added_at:
                    selected.append(ch)
        print(f"  新频道采集: {len(selected)} 个频道")
    else:
        selected = []
        today_offset = int(datetime.now().strftime("%j"))
        langs = [lang_filter] if lang_filter else sorted(channels_by_lang.keys())
        per_lang = registry.get("daily_per_lang", 10)
        for lang in langs:
            ch_list = channels_by_lang.get(lang, [])
            if not ch_list:
                continue
            # 取per_lang和频道数量的最小值，避免重复采集
            actual_per_lang = min(per_lang, len(ch_list))
            start = (today_offset * actual_per_lang) % len(ch_list)
            for i in range(actual_per_lang):
                idx = (start + i) % len(ch_list)
                selected.append(ch_list[idx])
        print(f"  今日轮转: {len(selected)} 个频道")

    if not selected:
        print("  ❌ 没有频道")
        return []

    # 读取 staging.json（待筛选库）
    existing = {}
    if STAGING_FILE.exists():
        for ch in json.loads(STAGING_FILE.read_text()):
            existing[ch["channel_id"]] = ch

    # 批量获取频道地区（channels.list，1 unit/50频道）
    selected_ids = [ch["channel_id"] for ch in selected]
    _, countries = _fetch_subscribers(selected_ids)
    print(f"  📍 获取到{len(countries)}个频道的地区信息")

    for i, ch in enumerate(selected):
        cid = ch["channel_id"]
        name = ch.get("name", cid)
        lang = ch.get("language", "")
        print(f"\n  [{i+1}/{len(selected)}] {name[:35]} ({lang})")

        videos = _fetch_channel_videos(cid, max_videos=10)
        if not videos:
            print(f"    ⚠️ 无视频数据")
            continue

        views = [v["view_count"] for v in videos if v.get("view_count", 0) > 0]
        avg_views = sum(views) // max(len(views), 1)

        # 标记爆款
        breakout = [v for v in videos
                   if v.get("view_count", 0) >= BREAKOUT_VIEWS
                   or (avg_views > 0 and v.get("view_count", 0) >= avg_views * BREAKOUT_RATIO)]

        # 用视频标题重新检测语言（覆盖registry的初始标记）
        video_titles = [v.get("title", "") for v in videos]

        snapshot = {
            "channel_id": cid,
            "name": name,
            "language": lang,
            "country": countries.get(cid, ""),
            "subscribers": ch.get("subscribers", 0),
            "tier": ch.get("tier", ""),
            "collected_at": datetime.now().isoformat(),
            "video_count": len(videos),
            "avg_views": avg_views,
            "videos": videos,
        }
        existing[cid] = snapshot
        # 增量保存到 staging.json（待筛选库）
        STAGING_FILE.write_text(json.dumps(list(existing.values()), indent=2, ensure_ascii=False))
        print(f"    ✅ {len(videos)}视频, {len(breakout)}爆款, 均播{avg_views:,}")
        time.sleep(2)  # yt-dlp频率控制，避免被封

    snapshots = list(existing.values())
    print(f"\n  📦 采集完成: {len(snapshots)}个频道, {sum(s.get('video_count', len(s.get('videos', []))) for s in snapshots)}个视频")
    return snapshots


def _load_registry() -> dict:
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text())
    return {"channels": {}}


# ═══════════════════════════════════════════════
#  Step 3: 过滤非短剧 + 低播放量
# ═══════════════════════════════════════════════

def filter_data(snapshots: list[dict], min_views: int = MIN_VIEWS_COMPETITOR) -> list[dict]:
    """
    过滤：
    1. 非短剧频道（NON_DRAMA_INDICATORS + DRAMA_KEYWORDS）
    2. 非短剧视频（_is_drama_video: 时长 + 标题/标签）
    3. 低播放量视频（< min_views）
    4. 太短的视频（< 60秒，可能是shorts）
    5. 过滤后0视频的频道自动删除
    """
    print(f"\n🔍 Step 3: 过滤 (≥{min_views:,}播放, 排除非短剧)")

    filtered = []
    removed_channels = 0
    total_before = 0
    total_after = 0

    for snap in snapshots:
        name = snap.get("name", "")
        desc = snap.get("description", "")
        video_titles = [v.get("title", "") for v in snap.get("videos", [])]

        # 排除非短剧频道
        if not _is_drama_channel(name, desc, video_titles):
            print(f"  ⏭️ 排除频道: {name[:30]} (非短剧)")
            removed_channels += 1
            continue

        total_before += len(snap.get("videos", []))

        # 过滤视频（非短剧 + 低播放量 + shorts）
        filtered_videos = []
        for v in snap.get("videos", []):
            views = v.get("view_count", 0)
            duration = v.get("duration", 0)
            # 排除低播放量
            if views < min_views:
                continue
            # 排除shorts（< 60秒）
            if 0 < duration < 60:
                continue
            # 排除非短剧视频
            if not _is_drama_video(v):
                continue
            filtered_videos.append(v)

        snap["videos"] = filtered_videos
        snap["video_count"] = len(filtered_videos)
        total_after += len(filtered_videos)

        if filtered_videos:
            filtered.append(snap)
            print(f"  ✅ {snap['name'][:30]} — {len(filtered_videos)}/{len(snap.get('videos', []))}视频保留")
        else:
            print(f"  ⏭️ {snap['name'][:30]} — 过滤后无数据")

    print(f"  📊 过滤: {total_before} → {total_after} 视频 ({len(filtered)}频道保留, {removed_channels}频道排除)")
    return filtered


# ═══════════════════════════════════════════════
#  Step 3b: 规律打分（基于数据挖掘的多信号加权评分）
# ═══════════════════════════════════════════════

# 从 2006 条视频数据中挖掘的高频短剧标签
DRAMA_TAGS_HIGH = {
    'drama', 'shortdrama', 'chinesedrama', 'cdrama', 'cinderella', 'romance',
    'minidrama', 'kdrama', 'lovestory', 'revenge', 'urban', 'dramachina',
    'dramashorts', 'chinesedramaengsub', 'chinesefilm', 'billionaire',
    'dramapendek', 'shortdramas', 'sweetlove', 'chinesemovie', 'reborn',
    'romantic', 'engsub', '霸道總裁', 'filmdrama', 'dramapendekpopuler',
    'koreandrama', 'dramakoreasubindo', 'ceoandcinderellachinesedrama',
    'richceotwinssub', 'movie', 'tvshow', 'tvseries',
}

# 非短剧视频关键词（硬排除）
NON_DRAMA_VIDEO_EXCLUDE = {
    'cover by', 'music video', 'official video', 'sing off', 'remix',
    'tiktok sing', 'behind the scenes', 'bloopers', 'reaction video',
    'podcast', 'vlog', 'tutorial', 'unboxing', 'webinar', 'seminar',
    'keynote', 'video oficial', 'video official', 'making of', 'documentary',
    'karaoke', 'lyrics', 'audio official',
}


def _drama_score(video: dict, channel_name: str = "") -> int:
    """
    多信号加权评分：判断视频是否为短剧。
    分数越高越可能是短剧。>=2 分即通过。
    
    信号来源（从 2006 条视频数据挖掘）：
    - 频道名已知平台: +5（白名单直接通过）
    - 标签命中高频短剧标签: +3
    - 标题命中短剧关键词: +2
    - 时长 30min-3h: +2（短剧固定长度）
    - 标题含结构特征（emoji/|/《》/省略号）: +1
    """
    score = 0
    title = video.get("title", "").lower()
    tags = [t.lower() for t in video.get("description_tags", [])]
    duration = video.get("duration", 0)
    text = title + " " + " ".join(tags)

    # 硬排除：明确非短剧
    if any(kw in text for kw in NON_DRAMA_VIDEO_EXCLUDE):
        return -10

    # 硬排除：时长异常
    if 0 < duration < 600:  # < 10min
        return -10
    if duration > 10800:  # > 3h
        return -10

    # +5：频道名命中已知平台
    channel_lower = channel_name.lower()
    if any(p.lower() in channel_lower for p in KNOWN_DRAMA_PLATFORMS):
        score += 5

    # +3：标签命中高频短剧标签
    if any(t in DRAMA_TAGS_HIGH for t in tags):
        score += 3

    # +2：标题/标签命中短剧关键词
    if any(kw in text for kw in DRAMA_KEYWORDS):
        score += 2

    # +2：时长在短剧区间（30min-3h）
    if 1800 <= duration <= 10800:
        score += 2
    elif 600 <= duration < 1800:  # 10-30min 也可能是短剧/预告
        score += 1

    # +1：标题结构特征（短剧标题常用模式）
    import re
    if any(e in title for e in ['🔥', '💔', '😭', '😱', '❤️', '💜', '🧡', '🩸', '🐼']):
        score += 1
    if '|' in title:
        score += 1
    if '《' in title and '》' in title:
        score += 1
    if '…' in title or '...' in title:
        score += 1
    if re.search(r'ep\d+|episode|full\b|\bpart\d+', title):
        score += 1

    return score


def ai_validate_videos(snapshots: list[dict]) -> list[dict]:
    """
    规律打分：基于数据挖掘的多信号评分，替代 LLM 验证。
    每个视频独立打分，>=2 分通过。
    """
    print(f"\n📊 Step 3b: 规律打分（多信号加权）")

    total_before = 0
    total_after = 0
    passed = 0
    rejected = 0
    filtered = []

    for snap in snapshots:
        channel_name = snap.get("name", "")
        videos = snap.get("videos", [])
        total_before += len(videos)

        good_videos = []
        for v in videos:
            score = _drama_score(v, channel_name)
            if score >= 2:
                good_videos.append(v)
                passed += 1
            else:
                rejected += 1

        total_after += len(good_videos)
        snap["videos"] = good_videos
        snap["video_count"] = len(good_videos)

        if good_videos:
            filtered.append(snap)

    print(f"  📊 通过: {passed}, 拒绝: {rejected}")
    print(f"  📊 视频: {total_before} → {total_after} ({len(filtered)}频道)")

    return filtered


# ═══════════════════════════════════════════════
#  Step 4: 保存快照
# ═══════════════════════════════════════════════

def save_snapshots(snapshots: list[dict]) -> str:
    """保存到统一数据源 latest.json"""
    LATEST_FILE.write_text(json.dumps(snapshots, indent=2, ensure_ascii=False))
    size_kb = LATEST_FILE.stat().st_size / 1024
    print(f"\n💾 Step 4: 快照已保存 — latest.json ({size_kb:.0f}KB)")
    return str(LATEST_FILE)


# ═══════════════════════════════════════════════
#  Step 5a: 本地统计（6维JSON）
# ═══════════════════════════════════════════════

def distill_local_stats(snapshots: list[dict]):
    """
    从快照数据提取6个维度的本地统计，保存JSON：
    1. titles.json   — 标题 + 播放量
    2. timing.json   — 发布时间 + 播放量
    3. tags.json     — 标签 + 播放量
    4. emoji.json    — Emoji使用 + 播放量
    5. hashtag.json  — Hashtag使用 + 播放量
    6. length.json   — 标题长度 + 播放量
    """
    print(f"\n🧪 Step 5a: 本地统计（6维JSON）")

    by_lang = defaultdict(list)
    for snap in snapshots:
        lang = snap.get("language", "未知")
        by_lang[lang].append(snap)

    for lang, channels in by_lang.items():
        print(f"\n  🌍 {lang} ({len(channels)}频道)")

        # 收集所有视频
        all_videos = []
        for ch in channels:
            for v in ch.get("videos", []):
                v["_channel"] = ch.get("name", "")
                all_videos.append(v)

        if not all_videos:
            print(f"    ⚠️ 无数据")
            continue

        # 过滤非短剧内容
        before_count = len(all_videos)
        all_videos = [v for v in all_videos if _is_drama_video(v)]
        filtered = before_count - len(all_videos)
        if filtered:
            print(f"    🧹 过滤非短剧: {filtered}条（时长<10min 或 >4h）")

        # 按播放量降序
        all_videos.sort(key=lambda x: x.get("view_count", 0), reverse=True)

        lang_dir = EVIDENCE_DIR / lang
        lang_dir.mkdir(parents=True, exist_ok=True)

        # 1. titles.json (合并所有关键字段，单一数据源)
        titles_data = [{
            "title": v.get("title", ""),
            "views": v.get("view_count", 0),
            "channel": v.get("_channel", ""),
            "published_at": v.get("published_at", ""),
            "description": v.get("description", "")[:500],
            "description_tags": v.get("description_tags", []),
            "video_id": v.get("video_id", ""),
        } for v in all_videos]
        
        # 追加到现有titles.json，而不是覆盖
        titles_file = lang_dir / "titles.json"
        if titles_file.exists():
            try:
                existing_titles = json.loads(titles_file.read_text())
                # 按video_id去重
                existing_ids = {t.get("video_id") for t in existing_titles}
                new_titles = [t for t in titles_data if t.get("video_id") not in existing_ids]
                titles_data = existing_titles + new_titles
                print(f"    📊 追加 {len(new_titles)} 条新数据到titles.json")
            except:
                pass
        
        titles_file.write_text(json.dumps(titles_data, indent=2, ensure_ascii=False))

        # 2. timing.json
        timing_data = [{
            "title": v.get("title", ""),
            "views": v.get("view_count", 0),
            "published_at": v.get("published_at", ""),
            "channel": v.get("_channel", ""),
        } for v in all_videos]
        
        # 追加到现有timing.json
        timing_file = lang_dir / "timing.json"
        if timing_file.exists():
            try:
                existing_timing = json.loads(timing_file.read_text())
                existing_titles = {t.get("title") for t in existing_timing}
                new_timing = [t for t in timing_data if t.get("title") not in existing_titles]
                timing_data = existing_timing + new_timing
            except:
                pass
        timing_file.write_text(json.dumps(timing_data, indent=2, ensure_ascii=False))

        # 3. tags.json
        tags_data = [{
            "title": v.get("title", ""),
            "views": v.get("view_count", 0),
            "tags": v.get("tags", []),
        } for v in all_videos]
        
        # 追加到现有tags.json
        tags_file = lang_dir / "tags.json"
        if tags_file.exists():
            try:
                existing_tags = json.loads(tags_file.read_text())
                existing_titles = {t.get("title") for t in existing_tags}
                new_tags = [t for t in tags_data if t.get("title") not in existing_titles]
                tags_data = existing_tags + new_tags
            except:
                pass
        tags_file.write_text(json.dumps(tags_data, indent=2, ensure_ascii=False))

        # 4. emoji.json
        emoji_pattern = re.compile(
            r'[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF'
            r'\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF'
            r'\u2764\uFE0F⭐🌟❤️🔥💀👁️‍🗨️💯👑🎭🎬💕😱😭😡]'
        )
        emoji_data = []
        for v in all_videos:
            title = v.get("title", "")
            emojis = emoji_pattern.findall(title)
            if emojis:
                emoji_data.append({
                    "title": title,
                    "views": v.get("view_count", 0),
                    "emojis": emojis,
                    "emoji_count": len(emojis),
                })
        
        # 追加到现有emoji.json
        emoji_file = lang_dir / "emoji.json"
        if emoji_file.exists():
            try:
                existing_emoji = json.loads(emoji_file.read_text())
                existing_titles = {e.get("title") for e in existing_emoji}
                new_emoji = [e for e in emoji_data if e.get("title") not in existing_titles]
                emoji_data = existing_emoji + new_emoji
            except:
                pass
        emoji_file.write_text(json.dumps(emoji_data, indent=2, ensure_ascii=False))

        # 5. hashtag.json
        hashtag_pattern = re.compile(r'#\w+')
        hashtag_data = []
        for v in all_videos:
            title = v.get("title", "")
            hashtags = hashtag_pattern.findall(title)
            tags_in_desc = v.get("tags", [])
            if hashtags or tags_in_desc:
                hashtag_data.append({
                    "title": title,
                    "views": v.get("view_count", 0),
                    "hashtags_in_title": hashtags,
                    "tags": tags_in_desc[:10],
                })
        
        # 追加到现有hashtag.json
        hashtag_file = lang_dir / "hashtag.json"
        if hashtag_file.exists():
            try:
                existing_hashtag = json.loads(hashtag_file.read_text())
                existing_titles = {h.get("title") for h in existing_hashtag}
                new_hashtag = [h for h in hashtag_data if h.get("title") not in existing_titles]
                hashtag_data = existing_hashtag + new_hashtag
            except:
                pass
        hashtag_file.write_text(json.dumps(hashtag_data, indent=2, ensure_ascii=False))

        # 6. length.json
        length_data = [{
            "title": v.get("title", ""),
            "views": v.get("view_count", 0),
            "title_length": len(v.get("title", "")),
            "word_count": len(v.get("title", "").split()),
        } for v in all_videos]
        
        # 追加到现有length.json
        length_file = lang_dir / "length.json"
        if length_file.exists():
            try:
                existing_length = json.loads(length_file.read_text())
                existing_titles = {l.get("title") for l in existing_length}
                new_length = [l for l in length_data if l.get("title") not in existing_titles]
                length_data = existing_length + new_length
            except:
                pass
        length_file.write_text(json.dumps(length_data, indent=2, ensure_ascii=False))

        # 7. timing_stats.json（聚合统计，供 distill_rules_builder 使用）
        hour_views = defaultdict(list)
        weekday_views = defaultdict(list)
        for item in timing_data:
            pub = item.get("published_at", "")
            views = item.get("views", 0)
            if pub and len(pub) == 8:
                try:
                    dt = datetime.strptime(pub, "%Y%m%d")
                    hour_views[dt.hour].append(views)
                    weekday_views[dt.strftime("%A")].append(views)
                except:
                    pass
        timing_stats = {
            "best_hours": sorted(
                [{"hour": h, "avg_views": sum(v)//len(v), "count": len(v)}
                 for h, v in hour_views.items()],
                key=lambda x: x["avg_views"], reverse=True
            )[:5],
            "best_weekdays": sorted(
                [{"weekday": w, "avg_views": sum(v)//len(v), "count": len(v)}
                 for w, v in weekday_views.items()],
                key=lambda x: x["avg_views"], reverse=True
            )[:3],
        }
        (lang_dir / "timing_stats.json").write_text(
            json.dumps(timing_stats, indent=2, ensure_ascii=False))

        print(f"    📊 {len(all_videos)}视频 → 6维统计已保存")
        print(f"    📁 {lang_dir}")


# ═══════════════════════════════════════════════
#  Step 5b: MiMo结构提取（封面+标题骨架+钩子）
# ═══════════════════════════════════════════════

def analyze_covers_mimo(snapshots: list[dict]):
    """
    统一封面分析（从母本读取prompt）+ 标题骨架提取 + 钩子分类。
    每个语种一次调用，分析该地区全部标题（不是逐条调）。
    """
    print(f"\n🎨 Step 5b: MiMo结构提取（封面+标题骨架+钩子）")

    # 加载蒸馏prompt模板
    _prompt_path = ROOT / "references" / "cover-analysis-prompt.md"
    _prompt_template = None
    if _prompt_path.exists():
        raw = _prompt_path.read_text(encoding="utf-8")
        header_pos = raw.find("## 蒸馏prompt")
        s = raw.find("```", header_pos) if header_pos != -1 else raw.find("```")
        if s != -1:
            e = raw.find("```", s + 3)
            _prompt_template = raw[s + 3:e].strip() if e != -1 else raw[s + 3:].strip()

    import socket; socket.setdefaulttimeout(180)  # 3min global timeout for vision API
    # 加载MiMo API key
    import os, base64, urllib.request
    mimo_key = os.environ.get("XIAOMI_API_KEY", "")
    if not mimo_key:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if "XIAOMI_API_KEY" in line:
                    mimo_key = line.split("=", 1)[1].strip()
                    break
    if not mimo_key:
        print("  ⚠️ 未配置 XIAOMI_API_KEY，跳过封面分析")
        return

    evidence_dir = ROOT / "distill" / "evidence"

    # 按语种分组
    by_lang = defaultdict(list)
    for snap in snapshots:
        lang = snap.get("language", "未知")
        by_lang[lang].append(snap)

    total_ok = 0
    total_fail = 0

    for lang, channels in sorted(by_lang.items()):
        print(f"\n  🌍 {lang} ({len(channels)}频道)")

        # 收集该语种所有视频
        all_videos = []
        for ch in channels:
            for v in ch.get("videos", []):
                thumb = v.get("thumbnail", "")
                views = v.get("view_count", v.get("views", 0))
                if thumb and views >= 5000:
                    all_videos.append({
                        "title": v.get("title", "")[:80],
                        "views": views,
                        "thumbnail": thumb,
                        "channel": ch.get("name", ""),
                    })

        if not all_videos:
            print(f"    ⚠️ 无符合条件的视频")
            continue

        # 按播放量分层抽样：高/中/低各取1张代表
        by_channel = defaultdict(list)
        for v in all_videos:
            by_channel[v["channel"]].append(v)
        sampled = []
        for ch_name, ch_videos in by_channel.items():
            if not ch_videos:
                continue
            ch_videos.sort(key=lambda x: x["views"], reverse=True)
            # 分层：高播放(>=10万)、中播放(1-10万)、低播放(<1万)
            high = [v for v in ch_videos if v["views"] >= 100000]
            mid = [v for v in ch_videos if 10000 <= v["views"] < 100000]
            low = [v for v in ch_videos if v["views"] < 10000]
            # 每层取播放量最高的1张
            for tier in [high, mid, low]:
                if tier:
                    sampled.append(max(tier, key=lambda x: x["views"]))
        sampled.sort(key=lambda x: x["views"], reverse=True)
        top_covers = sampled
        print(f"    📊 {len(all_videos)}视频，{len(by_channel)}频道，取代表封面 {len(top_covers)}个")

        # 检查已有数据，跳过已完成的步骤
        lang_dir = evidence_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        covers_file = lang_dir / "covers.json"
        skeleton_file = lang_dir / "title_skeletons.json"
        tag_file = lang_dir / "tag_groups.json"

        existing_covers = []
        existing_titles = set()
        if covers_file.exists():
            try:
                existing_covers = json.loads(covers_file.read_text())
                existing_titles = {c.get("_meta", {}).get("title") for c in existing_covers if "_meta" in c}
            except:
                pass

        skeleton_ok = False
        if skeleton_file.exists():
            try:
                sk = json.loads(skeleton_file.read_text())
                skeleton_ok = "error" not in sk and sk.get("title_skeletons") and sk.get("key_words") and sk.get("title_packaging")
            except:
                pass

        tag_ok = False
        if tag_file.exists():
            try:
                tg = json.loads(tag_file.read_text())
                tag_ok = "tag_groups" in tg and tg.get("tag_groups")
            except:
                pass

        # 1. 封面分析（跳过已有）
        new_covers_needed = [v for v in top_covers if v["title"] not in existing_titles]
        if not new_covers_needed:
            print(f"    📸 封面已存在 {len(existing_covers)} 条，跳过")
            covers_results = existing_covers
        else:
            covers_results = list(existing_covers)
            print(f"    📸 已有 {len(existing_covers)} 条，新增 {len(new_covers_needed)} 条")
            for i, v in enumerate(new_covers_needed):
                print(f"    [{i+1}/{len(new_covers_needed)}] {v['title'][:30]}...", end="", flush=True)

                # 下载封面（requests + 重试）
                import requests as _req
                img_b64 = None
                thumb_url = v["thumbnail"]
                thumb_url = thumb_url.replace("/maxresdefault.jpg", "/hqdefault.jpg")
                thumb_url = thumb_url.replace("/sddefault.jpg", "/hqdefault.jpg")
                for attempt in range(3):
                    try:
                        r = _req.get(thumb_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                        r.raise_for_status()
                        img_data = r.content
                        if len(img_data) > 100000:
                            thumb_url2 = thumb_url.replace("/hqdefault.jpg", "/mqdefault.jpg")
                            r = _req.get(thumb_url2, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
                            r.raise_for_status()
                            img_data = r.content
                        img_b64 = base64.b64encode(img_data).decode()
                        print(" ✅")
                        break
                    except Exception as e:
                        if attempt < 2:
                            print(f" ⚠️", end="", flush=True)
                            time.sleep(1)
                        else:
                            print(f" ❌")
                            covers_results.append({"error": str(e)})
                            total_fail += 1
                if not img_b64:
                    continue

                # 统一prompt（从母本读取，fallback到旧11字段）
                if _prompt_template:
                    prompt = _prompt_template.replace("{title}", v['title']).replace("{views}", "{:,}".format(v['views']))
                else:
                    prompt = f"""分析这个YouTube短剧封面。返回JSON，每个字段2-3句话，总输出控制在500字以内。

标题：{v['title']}
播放量：{v['views']:,}

{{
  "人物": "数量、表情、服装差异、肢体语言、关系暗示",
  "道具": "关键道具及其象征意义",
  "色彩": "主色调、辅助色、饱和度、光影效果、情绪氛围",
  "构图": "布局类型、景别、视角高低、视线引导路径",
  "文字": "文字数量、内容、位置、字体风格、颜色、是否增强悬念",
  "视觉层级": "第一眼看什么、第二眼看什么、第三眼看什么",
  "题材元素": "该题材独有的视觉符号",
  "封面标题配合": "封面情绪与标题钩子是否一致、是否互补、是否增强悬念",
  "地区适配": "最适合哪个地区市场及原因",
  "整体风格": "风格+情绪基调+目标受众",
  "爆款因素": {{"评分": "0-10", "来源": "核心吸引力来源", "改进建议": "可优化的地方"}},
  "结构化": {{
    "person_count": 0,
    "color_type": "warm/cold/mixed",
    "composition": "contrast/center/collage/symmetry",
    "has_text": true,
    "emotion": "romance/tension/comedy/power/mystery",
    "identity_visible": true
  }}
}}"""

                try:
                    import http.client, ssl
                    ctx = ssl.create_default_context()
                    conn = http.client.HTTPSConnection("token-plan-cn.xiaomimimo.com", context=ctx, timeout=120)
                    body = json.dumps({
                        "model": "mimo-v2.5",
                        "messages": [{"role": "user", "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
                        ]}],
                        "temperature": 0.3,
                    })
                    conn.request("POST", "/v1/chat/completions", body=body, headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {mimo_key}"
                    })
                    resp = conn.getresponse()
                    resp_body = resp.read().decode()
                    conn.close()

                    if resp.status != 200:
                        print(f" ❌ API {resp.status}")
                        covers_results.append({"error": f"API {resp.status}"})
                        total_fail += 1
                        continue

                    resp_data = json.loads(resp_body)
                    content = resp_data["choices"][0]["message"]["content"]

                    # JSON解析（括号深度计数）
                    clean = re.sub(r'```(?:json)?\s*', '', content)
                    clean = re.sub(r'\s*```', '', clean).strip()
                    start = clean.find('{')
                    if start == -1:
                        print(f" ❌ 无JSON")
                        covers_results.append({"error": "no JSON"})
                        total_fail += 1
                        continue

                    depth = 0
                    end = -1
                    for ci in range(start, len(clean)):
                        if clean[ci] == '{': depth += 1
                        elif clean[ci] == '}':
                            depth -= 1
                            if depth == 0:
                                end = ci
                                break

                    if end == -1:
                        # 截断补全
                        partial = clean[start:]
                        analysis = None
                        for closes in range(10):
                            try:
                                analysis = json.loads(partial + '}' * (closes + 1))
                                break
                            except json.JSONDecodeError:
                                continue
                        if not analysis:
                            print(f" ❌ JSON截断")
                            covers_results.append({"error": "JSON truncated"})
                            total_fail += 1
                            continue
                    else:
                        analysis = json.loads(clean[start:end + 1])

                    tokens = resp_data.get("usage", {}).get("total_tokens", 0)
                    analysis["_meta"] = {"tokens": tokens, "title": v["title"], "views": v["views"]}
                    covers_results.append(analysis)
                    total_ok += 1
                    print(f" ✅ {tokens}tokens")

                except Exception as e:
                    print(f" ❌ {e}")
                    covers_results.append({"error": str(e)})
                    total_fail += 1

                time.sleep(1)

        # 2. 标题骨架提取（跳过已成功的）
        skeleton_data = {}
        if skeleton_ok:
            print(f"\n    📝 标题骨架已存在，跳过")
        else:
            print(f"\n    📝 提取标题骨架（全部{len(all_videos)}个标题）...", end="", flush=True)
            
            # 分批处理：每批≤100标题，避免API超时
            batch_size = 100
            all_skeletons = []
            all_hooks = {}
            all_formulas = []
            all_hook_tags = []
            all_genre_tags = []
            all_key_words = []
            all_emergent_hooks = []
            all_title_packaging = []
            
            for batch_start in range(0, len(all_videos), batch_size):
                batch_end = min(batch_start + batch_size, len(all_videos))
                batch_videos = all_videos[batch_start:batch_end]
                
                titles_text = "\n".join(f"[{v['views']:,}] {v['title']}" for v in batch_videos)
                
                skeleton_prompt = f"""分析以下{lang}市场YouTube短剧标题，提取以下7个维度：

一、标题叙事骨架（3-5种故事原型）
每种骨架包含：narrative_pattern（叙事路径）、psychological_hook（心理机制）、core_formula（可直接改编的完整句式模板）、sub_genre（适用题材）、examples（2个高播放标题）

二、钩子分类（6种，每种给出定义+3个示例标题）
- emotion：情绪共鸣（愤怒/心疼/甜蜜/感动）
- identity：身份落差（卑微→尊贵/隐藏→揭露）
- relationship：关系冲突（前妻/继母/闺蜜/兄弟反目）
- reversal：意外反转（没想到/原来/真相是）
- compensation：正义回报（后悔/打脸/跪求/被碾压）
- time：时间跨度（重生/多年后/回到过去）

三、逐条标题钩子标记（每条标题标记1-3个最强钩子类型）
四、逐条标题题材标记（每条标题标记1-2个题材类型）
题材类型参考：总裁/首富/霸总、战神/战王、重生/穿越、神医、逆袭、复仇、甜宠/爱情、豪门/家族、赘婿/弃婿、闪婚/契约婚姻、隐藏身份、保姆/佣人、千金/公主、保安/保镖、离婚/前妻、怀孕/带娃、其他
五、题材高频关键词（key_words）
从所有标题中提取15个最高频的题材关键词/短语（不是普通词汇，是有商业价值的类型标签如"总裁""复仇""重生"）
六、新兴钩子（emergent_hooks）
如果发现该市场存在高频且高播放的独特点击机制（跨多个高播放标题出现、不能与已有六类重复），归纳为emergent_hooks，输出名称+解释+代表标题

七、标题包装模式（title_packaging）— 怎么把故事写成标题
从标题中提取3-5种高频包装方式（不是故事内容，是表达方式）。
每种包含：name（模式名称）、pattern（结构描述）、example_titles（2个真实标题示例）。
关注以下维度：
- 句式结构：对白式("..."开头)、第一人称(I/My)、冒号分段(X: Y)、感叹/警告式、问句式、倒叙式、系统/设定式
- 标点策略：省略号...悬念、破折号—转折、感叹号！收尾、问号？悬念
- 视觉元素：ALL CAPS关键词、emoji嵌入位置（开头/中间/结尾）
- 递进手法：以为X没想到Y、不仅X还Y、从X到Y
- 数字/对比冲击：具体数字($6)、极端对比(1个→10个)

标题列表：
{titles_text}

返回JSON格式：
{{
  "title_skeletons": [
    {{
      "name": "骨架名称",
      "narrative_pattern": "A→B→C叙事路径",
      "psychological_hook": "为什么有效的心理机制",
      "core_formula": "可直接改编的完整句式模板，如：'当所有人都以为TA是[卑微身份]时，他们不知道TA的真实身份是[尊贵身份]'",
      "sub_genre": "适用题材",
      "examples": ["示例标题1", "示例标题2"]
    }}
  ],
  "hooks": {{
    "emotion": {{"definition": "定义", "examples": ["标题1", "标题2", "标题3"]}},
    "identity": {{"definition": "定义", "examples": ["标题1", "标题2", "标题3"]}},
    "relationship": {{"definition": "定义", "examples": ["标题1", "标题2", "标题3"]}},
    "reversal": {{"definition": "定义", "examples": ["标题1", "标题2", "标题3"]}},
    "compensation": {{"definition": "定义", "examples": ["标题1", "标题2", "标题3"]}},
    "time": {{"definition": "定义", "examples": ["标题1", "标题2", "标题3"]}}
  }},
  "hook_tags": [
    {{"title": "标题前60字", "views": 播放量, "hooks": ["emotion", "reversal"]}}
  ],
  "genre_tags": [
    {{"title": "标题前60字", "views": 播放量, "genres": ["总裁", "复仇"]}}
  ],
  "key_words": ["总裁", "复仇", "重生", "甜宠", "隐藏身份", "逆袭", "豪门", "闪婚", "离婚", "前妻", "霸总", "赘婿", "战神", "穿越", "怀孕"],
  "emergent_hooks": [
    {{"name": "钩子名称", "definition": "解释", "examples": ["代表标题1", "代表标题2"]}}
  ],
  "title_packaging": [
    {{"name": "模式名称", "pattern": "结构描述", "example_titles": ["标题1", "标题2"]}}
  ]
}}"""

                try:
                    import requests as _requests
                    
                    # 带重试的流式API调用
                    content = ""
                    for _attempt in range(3):
                        try:
                            _resp = _requests.post(
                                "https://token-plan-cn.xiaomimimo.com/v1/chat/completions",
                                headers={"Content-Type": "application/json", "Authorization": f"Bearer {mimo_key}"},
                                json={"model": "mimo-v2.5", "stream": True, "messages": [{"role": "user", "content": skeleton_prompt}], "temperature": 0.3},
                                stream=True, timeout=600
                            )
                            if _resp.status_code == 429:
                                print(f" ⏳限流", end="", flush=True)
                                time.sleep(10 * (_attempt + 1))
                                continue
                            _resp.raise_for_status()
                            for _line in _resp.iter_lines():
                                if _line:
                                    _decoded = _line.decode("utf-8")
                                    if _decoded.startswith("data: ") and _decoded != "data: [DONE]":
                                        try:
                                            _chunk = json.loads(_decoded[6:])
                                            content += _chunk.get("choices", [{}])[0].get("delta", {}).get("content") or ""
                                        except json.JSONDecodeError:
                                            pass
                            break
                        except Exception as _e:
                            print(f" ⚠️{_e}", end="", flush=True)
                            time.sleep(3)
                    
                    if content:
                        
                        # JSON解析
                        clean = re.sub(r'```(?:json)?\s*', '', content)
                        clean = re.sub(r'\s*```', '', clean).strip()
                        start = clean.find('{')
                        if start != -1:
                            depth = 0
                            end = -1
                            for ci in range(start, len(clean)):
                                if clean[ci] == '{': depth += 1
                                elif clean[ci] == '}':
                                    depth -= 1
                                    if depth == 0:
                                        end = ci
                                        break
                            
                            if end != -1:
                                batch_data = json.loads(clean[start:end + 1])
                                # 合并结果
                                all_skeletons.extend(batch_data.get("title_skeletons", []))
                                # hooks: 新格式是dict of dicts {type: {definition, examples}}
                                for hook_type, val in batch_data.get("hooks", {}).items():
                                    if hook_type not in all_hooks:
                                        all_hooks[hook_type] = {"definition": "", "examples": []}
                                    if isinstance(val, dict):
                                        if not all_hooks[hook_type].get("definition"):
                                            all_hooks[hook_type]["definition"] = val.get("definition", "")
                                        all_hooks[hook_type]["examples"].extend(val.get("examples", []))
                                    elif isinstance(val, list):
                                        all_hooks[hook_type]["examples"].extend(val)
                                all_formulas.extend(batch_data.get("title_formulas", []))
                                all_hook_tags.extend(batch_data.get("hook_tags", []))
                                all_genre_tags.extend(batch_data.get("genre_tags", []))
                                all_key_words.extend(batch_data.get("key_words", []))
                                all_emergent_hooks.extend(batch_data.get("emergent_hooks", []))
                                all_title_packaging.extend(batch_data.get("title_packaging", []))
                                print(f" ✅ 批次{batch_start//batch_size+1}")
                            else:
                                print(f" ⚠️ 批次{batch_start//batch_size+1} JSON截断")
                        else:
                            print(f" ⚠️ 批次{batch_start//batch_size+1} 无JSON")
                    else:
                        print(f" ❌ 批次{batch_start//batch_size+1} API重试失败")
                except Exception as e:
                    print(f" ❌ 批次{batch_start//batch_size+1} {e}")
            
            # 合并最终结果
            # key_words: Counter取Top15
            from collections import Counter as _Counter
            kw_counter = _Counter(all_key_words)
            merged_key_words = [k for k, _ in kw_counter.most_common(15)]

            skeleton_data = {
                "title_skeletons": all_skeletons,
                "hooks": all_hooks,
                "title_formulas": all_formulas,
                "hook_tags": all_hook_tags,
                "genre_tags": all_genre_tags,
                "key_words": merged_key_words,
                "emergent_hooks": all_emergent_hooks,
                "title_packaging": all_title_packaging
            }

        # 保存到 evidence 目录
        lang_dir = evidence_dir / lang
        lang_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存封面分析（追加模式）
        covers_file = lang_dir / "covers.json"
        if covers_file.exists():
            try:
                existing_covers = json.loads(covers_file.read_text())
                # 按标题去重
                existing_titles = {c.get("_meta", {}).get("title") for c in existing_covers}
                new_covers = [c for c in covers_results if c.get("_meta", {}).get("title") not in existing_titles]
                covers_results = existing_covers + new_covers
                print(f"    📊 追加 {len(new_covers)} 条新封面分析")
            except:
                pass
        covers_file.write_text(json.dumps(covers_results, indent=2, ensure_ascii=False))
        print(f"    📁 → {covers_file}")
        
        # 保存标题骨架（只在有新数据时写入，避免覆盖已有数据）
        skeleton_file = lang_dir / "title_skeletons.json"
        if skeleton_data.get("title_skeletons"):
            skeleton_file.write_text(json.dumps(skeleton_data, indent=2, ensure_ascii=False))
            print(f"    📁 → {skeleton_file}")
        else:
            print(f"    ⚠️ 无骨架数据，跳过写入")

        # 3. 标签语义分组（一次调用，分析该语种全部标签）
        # 从 evidence/titles.json 读取标签
        titles_file = lang_dir / "titles.json"
        all_tags = set()
        if titles_file.exists():
            try:
                titles_data = json.loads(titles_file.read_text())
                for t in titles_data:
                    for tag in t.get("description_tags", []):
                        all_tags.add(tag.lower())
            except:
                pass
        
        if all_tags:
            tags_list = sorted(all_tags)
            print(f"\n    🏷️ 标签语义分组（{len(tags_list)}个标签）...", end="", flush=True)
            
            # 使用Python规则脚本替代MiMo API调用
            try:
                import subprocess
                script_dir = Path(__file__).parent
                tag_script = script_dir / "tag_group_by_rules.py"
                
                # 读取titles.json作为输入
                titles_file = lang_dir / "titles.json"
                if not titles_file.exists():
                    # 如果titles.json不存在，从snapshots创建临时文件
                    import tempfile
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmp:
                        json.dump(snapshots, tmp, ensure_ascii=False, indent=2)
                        titles_file = Path(tmp.name)
                
                # 运行标签分组脚本
                result = subprocess.run(
                    ["python3", str(tag_script), str(titles_file), str(tag_file)],
                    capture_output=True, text=True, timeout=30
                )
                
                if result.returncode == 0:
                    print(f" ✅")
                    # 读取生成的tag_groups.json
                    if tag_file.exists():
                        tg = json.loads(tag_file.read_text())
                        tag_ok = True
                else:
                    print(f" ❌ 脚本错误: {result.stderr[:200]}")
                    
            except Exception as e:
                print(f" ❌ {e}")

    print(f"\n  ✅ MiMo分析完成: {total_ok}封面成功, {total_fail}失败")


# ═══════════════════════════════════════════════
#  Step 6: 三层蒸馏（直接输出 JSON）
# ═══════════════════════════════════════════════

def distill_three_layer(snapshots: list[dict]):
    """
    三层蒸馏：LLM 直接输出结构化 JSON → distilled-rules-{lang}.json
    MD 从 JSON 生成（给人看的）。
    """
    print(f"\n🧠 Step 6: 三层蒸馏")

    by_lang = defaultdict(list)
    for snap in snapshots:
        lang = snap.get("language", "未知")
        by_lang[lang].append(snap)

    for lang, channels in by_lang.items():
        lang_dir = EVIDENCE_DIR / lang
        if not lang_dir.exists():
            print(f"  ⏭️ {lang} — 无证据数据")
            continue

        # 加载所有证据
        evidence = {}
        titles_raw = lang_dir / "titles.json"
        all_titles = []
        if titles_raw.exists():
            all_titles = json.loads(titles_raw.read_text())
            print(f"  📊 全量标题: {len(all_titles)}条")
        for dim in ["timing", "tags", "emoji", "hashtag", "length"]:
            f = lang_dir / f"{dim}.json"
            if f.exists():
                evidence[dim] = json.loads(f.read_text())

        # 加载封面分析（必须存在，否则先跑 5b）
        covers_file = lang_dir / "covers.json"
        covers_data = []
        if covers_file.exists():
            covers_data = json.loads(covers_file.read_text())
        else:
            print(f"  ⚠️ {lang} — 缺少 covers.json，先跑 step 5b 补封面分析...")
            analyze_covers_mimo(channels)
            if covers_file.exists():
                covers_data = json.loads(covers_file.read_text())
            else:
                print(f"  ❌ {lang} — step 5b 跑完仍无 covers.json，跳过蒸馏")
                continue

        # 加载标题骨架（必须存在，否则先跑 5b）
        skeleton_file = lang_dir / "title_skeletons.json"
        skeleton_data = {}
        if skeleton_file.exists():
            skeleton_data = json.loads(skeleton_file.read_text())
        else:
            # 5b 已在上面触发，骨架应已生成
            if skeleton_file.exists():
                skeleton_data = json.loads(skeleton_file.read_text())
            else:
                print(f"  ⚠️ {lang} — 缺少 title_skeletons.json，蒸馏将缺少骨架维度")

        # 筛选标题：每频道Top3，优先有封面数据的
        if all_titles:
            evidence["titles"] = select_titles_for_distill(all_titles, covers_data, per_channel=3, max_total=150)
        else:
            print(f"  ⏭️ {lang} — 无标题数据")
            continue

        if not evidence.get("titles"):
            print(f"  ⏭️ {lang} — 筛选后无标题")
            continue

        # 构建蒸馏 prompt（要求输出 JSON）
        prompt = _build_three_layer_prompt(lang, evidence, channels, covers_data, skeleton_data)

        try:
            import os, http.client, ssl
            mimo_key = os.environ.get("XIAOMI_API_KEY", "")
            if not mimo_key:
                env_path = Path.home() / ".hermes" / ".env"
                if env_path.exists():
                    for line in env_path.read_text().split("\n"):
                        if "XIAOMI_API_KEY" in line:
                            mimo_key = line.split("=", 1)[1].strip()
                            break
            if not mimo_key:
                print(f"  ❌ {lang} — 未配置 XIAOMI_API_KEY")
                continue

            print(f"  🧠 蒸馏 {lang}...（mimo-v2.5-pro，流式）")
            print(f"  📏 prompt长度: {len(prompt):,}字符")
            
            # 流式请求
            import requests
            mimo_url = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {mimo_key}"
            }
            body = {
                "model": "mimo-v2.5-pro",
                "stream": True,
                "messages": [{"role": "user", "content": prompt}],
            }
            print(f"  📤 发送流式请求...")
            
            resp = requests.post(mimo_url, headers=headers, json=body, stream=True, timeout=600)
            resp.raise_for_status()
            
            result = ""
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode("utf-8")
                    if decoded.startswith("data: ") and decoded != "data: [DONE]":
                        try:
                            chunk = json.loads(decoded[6:])
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {}).get("content") or ""
                                if delta:
                                    result += delta
                                    print(delta, end="", flush=True)
                        except (json.JSONDecodeError, IndexError):
                            pass
            print()  # 换行
            
            if not result:
                print(f"  ❌ {lang} — 空响应")
                continue
            
            # 先保存原始响应，再解析（避免解析失败丢数据）
            raw_file = lang_dir / "distill_raw_response.txt"
            raw_file.write_text(result)
            print(f"  💾 原始响应已保存 → {raw_file}")
            print(f"  📊 输出长度: {len(result):,}字符")

            # 解析 JSON（重试一次）
            distill_data = _parse_distill_json(result)

            if not distill_data:
                print(f"  ⚠️ {lang} — JSON解析失败，重试...")
                time.sleep(5)
                try:
                    resp2 = requests.post(mimo_url, headers=headers, json=body, stream=True, timeout=600)
                    resp2.raise_for_status()
                    result2 = ""
                    for line in resp2.iter_lines():
                        if line:
                            decoded = line.decode("utf-8")
                            if decoded.startswith("data: ") and decoded != "data: [DONE]":
                                try:
                                    chunk = json.loads(decoded[6:])
                                    choices = chunk.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {}).get("content") or ""
                                        if delta:
                                            result2 += delta
                                except (json.JSONDecodeError, IndexError):
                                    pass
                    if result2:
                        raw_file.write_text(result2)
                        result = result2
                        distill_data = _parse_distill_json(result)
                except Exception as e2:
                    print(f"  ⚠️ 重试也失败: {e2}")

            if not distill_data:
                # 打印前500字符供调试
                print(f"  ❌ {lang} — JSON解析失败，跳过。LLM输出前500字:")
                print(f"    {result[:500]}")
                continue

            # Python计算stats（不让LLM填数字，会抄错）
            all_titles_for_stats = evidence.get("titles", [])
            if all_titles_for_stats:
                avg_len = sum(len(t.get("title","")) for t in all_titles_for_stats) / len(all_titles_for_stats)
                emoji_count = sum(1 for t in all_titles_for_stats if any(ord(c) > 0x1F000 for c in t.get("title","")))
                emoji_rate = emoji_count / len(all_titles_for_stats) * 100
                all_emojis = []
                for t in all_titles_for_stats:
                    all_emojis.extend(c for c in t.get("title","") if ord(c) > 0x1F000)
                top_emojis = [e for e, _ in Counter(all_emojis).most_common(10)]
                # 时间
                hour_counter = Counter()
                weekday_counter = Counter()
                for t in evidence.get("timing", []):
                    try:
                        dt = datetime.fromisoformat(t.get("published_at","").replace("Z","+00:00"))
                        hour_counter[dt.hour] += 1
                        weekday_counter[dt.strftime("%A")] += 1
                    except: pass
                best_hours = [h for h, _ in hour_counter.most_common(5)]
                best_weekdays = [w for w, _ in weekday_counter.most_common(3)]
                # 关键词：从genre_tags统计题材频率
                genre_tags = skeleton_data.get("genre_tags", []) if skeleton_data else []
                genre_counter = Counter()
                for gt in genre_tags:
                    for g in gt.get("genres", []):
                        genre_counter[g] += 1
                if genre_counter:
                    key_words = [g for g, _ in genre_counter.most_common(15)]
                else:
                    # fallback: Python词频
                    word_counter = Counter()
                    for t in all_titles_for_stats:
                        words = t.get("title","").lower().split()
                        word_counter.update(w for w in words if len(w) > 3)
                    key_words = [w for w, _ in word_counter.most_common(15)]

                distill_data["stats"] = {
                    "avg_title_length": round(avg_len),
                    "emoji_rate": round(emoji_rate, 1),
                    "top_emojis": top_emojis,
                    "best_hours": best_hours,
                    "best_weekdays": best_weekdays,
                    "key_words": key_words
                }

            # 保存 JSON（唯一真相源）
            json_path = OUTPUT_DIR / f"distilled-rules-{lang}.json"
            # 版本管理：从 history + 当前文件中取最新版本号
            history_dir = OUTPUT_DIR / "history"
            history_dir.mkdir(parents=True, exist_ok=True)
            max_version = "0.0.0"
            # 从当前文件读
            if json_path.exists():
                try:
                    old_rules = json.loads(json_path.read_text())
                    max_version = old_rules.get("meta", {}).get("version", "0.0.0")
                except:
                    pass
            # 从 history 文件读，取最大值
            import glob as _glob
            for hf in _glob.glob(str(history_dir / f"distilled-rules-{lang}-v*.json")):
                try:
                    hv = json.loads(Path(hf).read_text()).get("meta", {}).get("version", "0.0.0")
                    if _version_gt(hv, max_version):
                        max_version = hv
                except:
                    pass
            new_version = _bump_version(max_version)
            # 归档旧版本
            if json_path.exists():
                try:
                    old_v = json.loads(json_path.read_text()).get("meta", {}).get("version", "unknown")
                    archive_path = history_dir / f"distilled-rules-{lang}-v{old_v}.json"
                    archive_path.write_text(json_path.read_text())
                    print(f"  📦 归档旧版本 → {archive_path.name}")
                except Exception as e:
                    print(f"  ⚠️ 归档失败: {e}")

            distill_data["meta"] = {
                "platform": "youtube",
                "content_type": "short_drama",
                "version": new_version,
                "lang": lang,
                "generated_at": datetime.now().isoformat(),
                "sample_size": len(evidence.get("titles", [])),
            }

            json_path.write_text(json.dumps(distill_data, indent=2, ensure_ascii=False))
            print(f"  ✅ {lang} → {json_path.name} v{new_version}")

            # 生成 MD（给人看的）
            _generate_distill_md(lang, distill_data)

        except Exception as e:
            import traceback
            print(f"  ❌ {lang} 蒸馏失败: {e}")
            traceback.print_exc()


def _bump_version(version: str) -> str:
    parts = version.split(".")
    if len(parts) >= 3:
        parts[1] = str(int(parts[1]) + 1)
        parts[2] = "0"
    return ".".join(parts)


def _version_gt(a: str, b: str) -> bool:
    """比较两个 semver 版本号，a > b 返回 True"""
    try:
        a_parts = [int(x) for x in a.split(".")]
        b_parts = [int(x) for x in b.split(".")]
        return a_parts > b_parts
    except:
        return False


def _parse_distill_json(result: str) -> dict:
    """从 LLM 输出中解析 JSON"""
    import re
    
    # 尝试直接解析
    try:
        return json.loads(result)
    except:
        pass

    # 尝试从 markdown code block 中提取
    json_match = re.search(r'```(?:json)?\s*\n(.*?)\n```', result, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except:
            pass

    # 尝试找第一个 { 到最后一个 }
    start = result.find('{')
    end = result.rfind('}')
    if start >= 0 and end > start:
        raw = result[start:end + 1]
        try:
            return json.loads(raw)
        except:
            pass
        # 修复常见的JSON问题：尾部逗号
        try:
            fixed = re.sub(r',\s*([}\]])', r'\1', raw)
            return json.loads(fixed)
        except:
            pass
        # 修复单引号问题
        try:
            fixed = raw.replace("'", '"')
            fixed = re.sub(r',\s*([}\]])', r'\1', fixed)
            return json.loads(fixed)
        except:
            pass

    return {}


def _generate_distill_md(lang: str, data: dict):
    """从 JSON 生成可读 MD"""
    lines = ["# {}市场蒸馏规则\n".format(lang)]
    lines.append("核心理念：骨架可以复用，血肉必须创新。给渔不给鱼。\n")

    # Why 层（结构化原则）
    why = data.get("why", {})
    if isinstance(why, dict):
        lines.append("## WHY（为什么有效）\n")
        for dim, label in [("title", "标题原则"), ("thumbnail", "封面原则"), ("tags_and_distribution", "标签与分发原则")]:
            items = why.get(dim, [])
            if items:
                lines.append("### {}".format(label))
                for item in items:
                    if isinstance(item, dict):
                        lines.append("- **{}**".format(item.get("principle", "")))
                        lines.append("  - 心理机制: {}".format(item.get("psychology", "")))
                        lines.append("  - 应用: {}".format(item.get("application", "")))
                    else:
                        lines.append("- {}".format(item))
                lines.append("")
        mi = why.get("market_insights", {})
        if mi:
            lines.append("### 市场洞察")
            for key, label in [("gender_bias", "男女频差异"), ("emerging_trends", "新兴趋势"), ("content_quality_signals", "质量信号")]:
                val = mi.get(key, "")
                if val:
                    lines.append("- **{}**: {}".format(label, val))
            lines.append("")
    elif isinstance(why, str) and why:
        lines.append("## WHY（为什么有效）\n")
        lines.append(why)
        lines.append("")

    # What 层（故事模式模板）
    what = data.get("what", [])
    if isinstance(what, list) and what:
        lines.append("## WHAT（爆款故事模式）\n")
        for item in what:
            if isinstance(item, dict):
                lines.append("### {}".format(item.get("name", "模式")))
                lines.append("- 模板: {}".format(item.get("template", "")))
                if item.get("why_it_works"):
                    lines.append("- 为什么有效: {}".format(item["why_it_works"]))
                if item.get("sub_genre"):
                    lines.append("- 适用题材: {}".format(item["sub_genre"]))
                if item.get("examples"):
                    lines.append("- 示例: {}".format(", ".join(item["examples"][:3])))
                lines.append("")
    elif isinstance(what, str) and what:
        lines.append("## WHAT（爆款故事模式）\n")
        lines.append(what)
        lines.append("")

    # How 层
    how = data.get("how", {})
    if how:
        lines.append("## HOW（执行规则）\n")

        # 标题规则（兼容新旧结构）
        title_rules = how.get("title_rules", how)
        skels = title_rules.get("skeletons", title_rules.get("title_skeletons", []))
        if skels:
            lines.append("### 标题骨架")
            for s in skels:
                lines.append("- **{}**: {}".format(s.get("name", ""), s.get("core_formula", s.get("narrative_pattern", ""))))
                if s.get("sub_genre"):
                    lines.append("  - 题材: {}".format(s["sub_genre"]))
                if s.get("avg_views"):
                    lines.append("  - 均播: {:,}".format(s["avg_views"]))
                for e in s.get("examples", [])[:3]:
                    lines.append("  - 示例: {}".format(e))
            lines.append("")

        # 钩子组合
        hook = title_rules.get("hook_combination", how.get("hook_combination", {}))
        if hook:
            lines.append("### 钩子组合")
            if hook.get("golden_triangle"):
                lines.append("- 黄金三角: {}".format(hook["golden_triangle"]))
            for sp in hook.get("strongest_pairs", []):
                lines.append("- 最强配对: {}".format(sp))
            for r in hook.get("rules", []):
                lines.append("- {}".format(r))
            lines.append("")

        # 标题约束
        tc = title_rules.get("constraints", how.get("title_constraints", {}))
        if tc:
            lines.append("### 标题约束")
            for key, label in [("avg_length", "均长"), ("emoji_rate", "Emoji率")]:
                val = tc.get(key)
                if val is not None:
                    lines.append("- {}: {}".format(label, val))
            if tc.get("front_half"):
                lines.append("- 前半句: {}".format(tc["front_half"]))
            if tc.get("back_half"):
                lines.append("- 后半句: {}".format(tc["back_half"]))
            if tc.get("key_words"):
                lines.append("- 关键词: {}".format(", ".join(tc["key_words"])))
            lines.append("")

        # Emoji策略
        emoji = title_rules.get("emoji_strategy", how.get("emoji_strategy", {}))
        if emoji:
            lines.append("### Emoji策略")
            if emoji.get("best_position"):
                lines.append("- 最佳位置: {}".format(emoji["best_position"]))
            for r in emoji.get("rules", []):
                lines.append("- {}".format(r))
            lines.append("")

        # 标签策略
        tag = how.get("hashtag_strategy", {})
        if tag:
            lines.append("### 标签策略")
            if tag.get("combination_pattern"):
                lines.append("- 组合模式: {}".format(tag["combination_pattern"]))
            if tag.get("trend_hijacking"):
                lines.append("- 热点截流: {}".format(tag["trend_hijacking"]))
            for r in tag.get("rules", []):
                lines.append("- {}".format(r))
            lines.append("")

        # 描述模板
        desc = how.get("description_template", {})
        if desc:
            lines.append("### 描述模板")
            if desc.get("structure"):
                lines.append("- 结构: {}".format(desc["structure"]))
            for r in desc.get("rules", []):
                lines.append("- {}".format(r))
            lines.append("")

        # 封面指南
        thumb = how.get("thumbnail_guidelines", {})
        if thumb:
            lines.append("### 封面指南")
            for key, label in [("composition", "构图"), ("figures", "人物"), ("colors", "色彩"), ("emotion", "情绪基调"), ("visual_symbols", "视觉符号"), ("text", "文字")]:
                val = thumb.get(key, "")
                if val:
                    lines.append("- {}: {}".format(label, val))
            cover_types = thumb.get("cover_types", [])
            if cover_types:
                lines.append("- 封面类型:")
                for ct in cover_types:
                    lines.append("  - **{}**: {}（适用：{}）".format(ct.get("name",""), ct.get("description",""), ct.get("适用题材","")))
            lines.append("")

        # 发布时间
        pub = how.get("publish_time", {})
        if pub:
            lines.append("### 发布时间")
            if pub.get("best_hours"):
                lines.append("- 最佳小时: {}".format(", ".join("{}:00".format(h) for h in pub["best_hours"])))
            if pub.get("best_weekdays"):
                lines.append("- 最佳星期: {}".format(", ".join(pub["best_weekdays"])))
            for r in pub.get("rules", []):
                lines.append("- {}".format(r))
            lines.append("")

        # 增长策略
        growth = how.get("growth_strategy", [])
        if growth:
            lines.append("### 增长策略")
            for g in growth:
                lines.append("- {}".format(g))
            lines.append("")

    # 边界
    boundaries = data.get("boundaries", {})
    if boundaries:
        lines.append("## 边界与警告\n")
        if boundaries.get("sample_size_warning"):
            lines.append("- {}".format(boundaries["sample_size_warning"]))
        for f in boundaries.get("missing_fields", []):
            lines.append("- 缺失: {}".format(f))
        lines.append("")

    md_path = OUTPUT_DIR / "distill-{}-new.md".format(lang)
    md_path.write_text("\n".join(lines))
    print("  📄 {} → {} ({}行)".format(lang, md_path.name, len(lines)))


def select_titles_for_distill(titles: list, covers: list = None, per_channel: int = 3, max_total: int = 150) -> list:
    """
    筛选标题用于蒸馏：每频道取Top N，优先有封面数据的
    
    Args:
        titles: 全量标题列表
        covers: 封面分析数据（用于匹配有封面的标题）
        per_channel: 每频道取几条
        max_total: 总数上限
    """
    from collections import defaultdict
    
    # 构建封面标题集合
    cover_titles = set()
    if covers:
        for c in covers:
            meta_title = c.get("_meta", {}).get("title", "")
            if meta_title:
                cover_titles.add(meta_title)
    
    # 按频道分组
    by_channel = defaultdict(list)
    for t in titles:
        ch = t.get("channel", "unknown")
        by_channel[ch].append(t)
    
    selected = []
    for ch, ch_titles in by_channel.items():
        # 按播放量排序
        ch_sorted = sorted(ch_titles, key=lambda x: x.get("views", 0), reverse=True)
        
        # 分成有封面和无封面
        with_cover = [t for t in ch_sorted if t.get("title", "") in cover_titles]
        without_cover = [t for t in ch_sorted if t.get("title", "") not in cover_titles]
        
        # 优先取有封面的，不够再补无封面的
        picked = with_cover[:per_channel]
        if len(picked) < per_channel:
            picked.extend(without_cover[:per_channel - len(picked)])
        selected.extend(picked)
    
    # 按播放量全局排序，取max_total
    selected.sort(key=lambda x: x.get("views", 0), reverse=True)
    selected = selected[:max_total]
    
    print(f"  📊 标题筛选: {len(titles)}条 → {len(selected)}条（{len(by_channel)}频道×{per_channel}，有封面{sum(1 for t in selected if t.get('title','') in cover_titles)}条）")
    return selected


def _dedup_titles_by_pattern(titles: list) -> list:
    """按语义骨架去重标题：扩展词表 + 自适应保留（小组Top2，大组30%）"""
    import re as _re
    # 身份词（多语种，扩展版）
    IDENTITY_WORDS = {
        # 印尼
        'ceo', 'bos', 'presiden', 'konglomerat', 'pewaris', 'anak', 'putra', 'putri',
        'sopir', 'pembantu', 'pengemis', 'kuli', 'gelandangan', 'janda', 'duda',
        'prajurit', 'dewa', 'pangeran', 'ratu', 'raja', 'tuan', 'nyonya',
        'gadis', 'pria', 'wanita', 'istri', 'suami', 'pemuda', 'nenek', 'ibu', 'ayah',
        'miliarder', 'miskin', 'kaya', 'cantik', 'perang', 'srikandi', 'dewi',
        'mati', 'hidup', 'lumpuh', 'buta', 'tuli', 'jagoan', 'pendekar',
        'tukang', 'pedagang', 'guru', 'dokter', 'suster', 'model', 'artis', 'sultan',
        # 英文
        'boss', 'billionaire', 'heir', 'heiress', 'prince', 'princess',
        'maid', 'servant', 'beggar', 'driver', 'soldier', 'god', 'queen', 'king',
        'wife', 'husband', 'orphan', 'nanny', 'bodyguard', 'guard',
        'doctor', 'nurse', 'warrior', 'tycoon', 'mogul', 'mafia', 'gangster',
        'president', 'chairman', 'director', 'stepmother', 'stepfather',
        # 中文
        '总裁', '首富', '千金', '少爷', '战神', '神医', '保安', '保姆',
        '将军', '王爷', '公主', '皇子', '皇后', '妃子', '丫鬟', '乞丐',
        # 繁中
        '總裁', '千金', '少爺', '戰神', '保鑣', '傭人', '將軍', '王爺',
        # 西语
        'heredero', 'príncipe', 'princesa', 'sirvienta', 'chofer', 'empresario',
        'madrastra', 'padrastro', 'hermana', 'hermano', 'suegra',
        # 葡萄牙
        'bilionário', 'herdeiro', 'empregada', 'motorista', 'presidente',
        'madrasta', 'padrasto', 'sogra',
    }
    # 情节词（多语种，扩展版）
    PLOT_WORDS = {
        # 印尼
        'menikah', 'cerai', 'hamil', 'mengandung', 'balas', 'dendam', 'ditipu',
        'diremehkan', 'dihina', 'dikhianati', 'dicampakkan', 'disembunyikan',
        'palsu', 'sebenarnya', 'ternyata', 'rahasia', 'identitas', 'balas dendam',
        'dibuang', 'ditelantarkan', 'menikahi', 'selingkuh', 'khianat',
        'menyesal', 'kembali', 'pulang', 'turun', 'menyamar', 'misterius',
        'jatuh', 'cinta', 'sayang', 'dunia', 'seluruh',
        'preman', 'penjahat', 'jahat', 'diselamatkan', 'menyelamatkan',
        'disimpan', 'ditahan', 'diculik', 'dibunuh', 'selamat',
        'ditolong', 'menolong', 'menemukan', 'bertemu', 'berpisah',
        'dinikahi', 'diceraikan', 'ditinggalkan', 'diusir',
        # 英文
        'married', 'divorce', 'pregnant', 'revenge', 'betrayed', 'cheated',
        'abandoned', 'humiliated', 'fired', 'framed', 'secret', 'fake', 'real',
        'hidden', 'identity', 'revealed', 'contract', 'mistaken',
        'returns', 'saves', 'rescued', 'kidnapped', 'killed', 'dies',
        'regret', 'exposed', 'tricked', 'lied', 'steals', 'stolen',
        'comes back', 'falls', 'love', 'hate', 'jealous', 'rich', 'poor',
        'marries', 'baby', 'child', 'son', 'daughter',
        'father', 'mother', 'brother', 'sister', 'family', 'enemy',
        'weak', 'strong', 'power', 'powerful', 'truth', 'lies',
        # 中文
        '结婚', '离婚', '怀孕', '复仇', '背叛', '抛弃', '羞辱', '隐藏',
        '身份', '秘密', '假冒', '真相', '逆袭', '重生', '穿越', '退婚',
        # 繁中
        '結婚', '離婚', '復仇', '背叛', '拋棄', '羞辱', '隱藏',
        # 西语/葡萄牙
        'casar', 'divorciar', 'embarazada', 'venganza', 'traición', 'humillado',
        'abandonado', 'secuestrado', 'salvado', 'enamorado', 'arrepentido',
        'engañado', 'mentira', 'verdade', 'poder', 'familia', 'hijo', 'hija',
        'casamento', 'divórcio', 'gravida', 'vingança', 'traído', 'humilhado',
    }

    pattern_map = {}  # pattern_key -> [(views, title, original_item)]
    for t in titles:
        title = t.get('title', '')
        views = t.get('views', 0)
        # 清洗标题：去emoji/hashtag/数字/标点
        cleaned = _re.sub(r'[\[\]【】\d,\.!?❤️🔥😈💀👊😱💋💌🎬👊🏻✨💯]+', '', title)
        cleaned = _re.sub(r'#\S+', '', cleaned)
        cleaned = _re.sub(r'\s+', ' ', cleaned).strip().lower()

        # 提取身份词和情节词（CJK用子串匹配，Latin用词匹配）
        has_cjk = bool(_re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', cleaned))
        if has_cjk:
            identities = sorted(w for w in IDENTITY_WORDS if w in cleaned)[:3]
            plots = sorted(w for w in PLOT_WORDS if w in cleaned)[:3]
        else:
            words = set(cleaned.split())
            identities = sorted(words.intersection(IDENTITY_WORDS))[:3]
            plots = sorted(words.intersection(PLOT_WORDS))[:3]

        # 组合pattern key
        id_str = '+'.join(identities) if identities else '无身份'
        plot_str = '+'.join(plots) if plots else '无情节'
        pattern_key = '{}||{}'.format(id_str, plot_str)

        if pattern_key not in pattern_map:
            pattern_map[pattern_key] = []
        pattern_map[pattern_key].append((views, title, t))

    # 自适应保留：小组Top2，大组保留30%
    deduped = []
    for key, items in pattern_map.items():
        items.sort(key=lambda x: x[0], reverse=True)
        keep = max(2, int(len(items) * 0.3))
        for item in items[:keep]:
            deduped.append(item[2])

    # 按播放量排序
    deduped.sort(key=lambda x: x.get('views', 0), reverse=True)
    return deduped


def _build_three_layer_prompt(lang: str, evidence: dict, channels: list, 
                              covers_data: list, skeleton_data: dict) -> str:
    """构建三层蒸馏prompt — 语义去重后全量"""
    # 标题按播放量排序，语义去重后全量使用
    all_titles = sorted(evidence.get("titles", []), key=lambda x: x.get("views", 0), reverse=True)
    titles = _dedup_titles_by_pattern(all_titles)
    titles_text = "\n".join("  - [{:>10,}] {}".format(t['views'], t['title'][:100]) for t in titles)

    # 加载钩子标记数据（Step 5b LLM预处理）
    evidence_dir = ROOT / "distill" / "evidence" / lang
    hook_tags_data = []
    if skeleton_data and "hook_tags" in skeleton_data:
        hook_tags_data = skeleton_data["hook_tags"]
    # 统计钩子类型分布
    hook_stats = {}  # 动态收集，不预设类型
    hook_views = {}
    for h in hook_tags_data:
        views = h.get("views", 0)
        for hook_type in h.get("hooks", []):
            if hook_type not in hook_stats:
                hook_stats[hook_type] = 0
                hook_views[hook_type] = []
            hook_stats[hook_type] += 1
            hook_views[hook_type].append(views)
    hook_summary = ""
    if any(hook_stats.values()):
        hook_summary = "\n## 钩子类型分布（Python统计，{}个标题）\n".format(len(hook_tags_data))
        for htype, count in sorted(hook_stats.items(), key=lambda x: x[1], reverse=True):
            if count > 0:
                avg_v = sum(hook_views[htype]) / len(hook_views[htype]) if hook_views[htype] else 0
                hook_summary += "- {}: {}个标题({:.1f}%), 均播{:,.0f}\n".format(
                    htype, count, count/len(hook_tags_data)*100, avg_v)
        # 钩子共现
        pair_count = Counter()
        for h in hook_tags_data:
            hooks = h.get("hooks", [])
            for i in range(len(hooks)):
                for j in range(i+1, len(hooks)):
                    pair = tuple(sorted([hooks[i], hooks[j]]))
                    pair_count[pair] += 1
        if pair_count:
            hook_summary += "\n### 钩子共现Top5\n"
            for (a, b), c in pair_count.most_common(5):
                hook_summary += "- {}+{}: {}次\n".format(a, b, c)

    # 加载标签分组数据（Step 5b LLM预处理）
    tag_groups = {}
    tag_groups_file = evidence_dir / "tag_groups.json"
    if tag_groups_file.exists():
        try:
            tag_groups = json.loads(tag_groups_file.read_text()).get("tag_groups", {})
        except:
            pass
    tag_group_summary = ""
    if tag_groups:
        tag_group_summary = "\n## 标签语义分组（LLM预处理）\n"
        for group, tags in tag_groups.items():
            if tags:
                tag_group_summary += "- {}({}个): {}\n".format(group, len(tags), ", ".join(tags[:10]))
                if len(tags) > 10:
                    tag_group_summary += "  ...等{}个标签\n".format(len(tags))

    # 描述模板提炼（Python预处理：分类+统计+均播）
    desc_patterns = {
        "welcome": [],    # 欢迎语/频道定位
        "synopsis": [],   # 剧情简介/悬念句
        "subscribe": [],  # 订阅/通知引导
        "disclaimer": [], # 合规/免责声明
        "links": [],      # 外部链接/引流
    }
    desc_stats = {"total_with_desc": 0, "pattern_views": {}}
    for t in titles:
        desc = t.get("description", "")
        if not desc:
            continue
        desc_stats["total_with_desc"] += 1
        views = t.get("views", 0)
        lines = desc.strip().split("\n")
        first3 = " ".join(l.strip()[:80] for l in lines[:3]).lower()
        # 分类
        if any(kw in first3 for kw in ["welcome to", "💖", "welcome", "频道", "channel"]):
            desc_patterns["welcome"].append(views)
        if any(kw in first3 for kw in ["subscribe", "notification", "bell", "订阅", "关注"]):
            desc_patterns["subscribe"].append(views)
        if any(kw in first3 for kw in ["disclaimer", "compliance", "fictional", "声明", "fiction"]):
            desc_patterns["disclaimer"].append(views)
        if any(kw in first3 for kw in ["http", "www", "👉", "visit", "watch", "链接"]):
            desc_patterns["links"].append(views)
        if any(kw in first3 for kw in ["drama", "story", "love", "ceo", "billionaire", "revenge", "短剧", "故事"]):
            desc_patterns["synopsis"].append(views)
    
    desc_summary = "\n## 描述模板分析（Python预处理，{}条有描述）\n".format(desc_stats["total_with_desc"])
    for pattern_name, views_list in desc_patterns.items():
        if views_list:
            avg_v = sum(views_list) / len(views_list)
            rate = len(views_list) / max(desc_stats["total_with_desc"], 1) * 100
            desc_summary += "- {}: {}条({:.1f}%), 均播{:,.0f}\n".format(
                pattern_name, len(views_list), rate, avg_v)
    # Top3 高播描述样本
    desc_with_views = [(t.get("views",0), t.get("title","")[:40], 
                        " | ".join(l.strip()[:50] for l in t.get("description","").strip().split("\n")[:3] if l.strip()))
                       for t in titles if t.get("description")]
    desc_with_views.sort(key=lambda x: x[0], reverse=True)
    desc_summary += "\n### 高播放描述样本（Top5）\n"
    for views, title, preview in desc_with_views[:5]:
        desc_summary += "- [{:>10,}] {}\n  模板: {}\n".format(views, title, preview)

    # 标签统计（Python预处理：全量+均播+组合模式+效率对比）
    title_tag_counter = Counter()
    desc_tag_counter = Counter()
    title_tag_views = {}  # tag -> [views, ...]
    desc_tag_views = {}
    for t in titles:
        views = t.get("views", 0)
        # 从标题里提取 # 标签
        for word in t.get("title", "").split():
            if word.startswith("#"):
                title_tag_counter[word] += 1
                title_tag_views.setdefault(word, []).append(views)
        # 从 description_tags 里提取
        for tag in t.get("description_tags", []):
            desc_tag_counter[tag] += 1
            desc_tag_views.setdefault(tag, []).append(views)
    
    top_title_tags = [t for t, _ in title_tag_counter.most_common(15)]
    top_desc_tags = [t for t, _ in desc_tag_counter.most_common(20)]
    
    # 标签均播排名（Top15 高播标签）
    desc_tag_avg = [(tag, sum(vs)/len(vs), len(vs)) for tag, vs in desc_tag_views.items() if len(vs) >= 3]
    desc_tag_avg.sort(key=lambda x: x[1], reverse=True)
    top_high_views_tags = desc_tag_avg[:15]
    
    # 标签组合模式分析（描述标签共现）
    tag_pair_counter = Counter()
    for t in titles:
        tags = t.get("description_tags", [])
        if len(tags) >= 2:
            for i in range(min(len(tags), 5)):  # 只看前5个标签的组合
                for j in range(i+1, min(len(tags), 5)):
                    pair = tuple(sorted([tags[i].lower(), tags[j].lower()]))
                    tag_pair_counter[pair] += 1
    top_tag_pairs = tag_pair_counter.most_common(10)

    # Emoji统计（Python预处理：使用率+位置+播放量相关性）
    emoji_items = evidence.get("emoji", [])
    total_videos = len(evidence.get("titles", []))
    emoji_rate = len(emoji_items) / max(total_videos, 1) * 100
    all_emojis = []
    for item in emoji_items:
        all_emojis.extend(item.get("emojis", []))
    top_emojis = [e for e, _ in Counter(all_emojis).most_common(10)]
    # Emoji在标题中的位置分布
    emoji_in_title_start = 0
    emoji_in_title_mid = 0
    emoji_in_title_end = 0
    for t in titles:
        title = t.get("title", "")
        emojis_in_this = [c for c in title if ord(c) > 0x1F000]
        if not emojis_in_this:
            continue
        first_emoji_pos = title.index(emojis_in_this[0])
        if first_emoji_pos < len(title) * 0.2:
            emoji_in_title_start += 1
        elif first_emoji_pos > len(title) * 0.8:
            emoji_in_title_end += 1
        else:
            emoji_in_title_mid += 1
    # 有emoji vs 无emoji的播放量对比
    emoji_views = [t.get("views", 0) for t in titles if any(ord(c) > 0x1F000 for c in t.get("title", ""))]
    no_emoji_views = [t.get("views", 0) for t in titles if not any(ord(c) > 0x1F000 for c in t.get("title", ""))]
    emoji_avg = sum(emoji_views) / max(len(emoji_views), 1)
    no_emoji_avg = sum(no_emoji_views) / max(len(no_emoji_views), 1)

    # Hashtag统计
    hashtag_items = evidence.get("hashtag", [])
    all_hashtags = []
    for item in hashtag_items:
        all_hashtags.extend(item.get("hashtags_in_title", []))
    top_hashtags = [h for h, _ in Counter(all_hashtags).most_common(10)]

    # 标题长度统计
    lengths = evidence.get("length", [])
    avg_len = sum(l.get("title_length", 0) for l in lengths) / max(len(lengths), 1)

    # 时间分布
    timing = evidence.get("timing", [])
    hour_counter = Counter()
    weekday_counter = Counter()
    for t in timing:
        try:
            dt = datetime.fromisoformat(t.get("published_at", "").replace("Z", "+00:00"))
            hour_counter[dt.hour] += 1
            weekday_counter[dt.strftime("%A")] += 1
        except:
            pass
    best_hours = [h for h, _ in hour_counter.most_common(5)]
    best_weekdays = [w for w, _ in weekday_counter.most_common(3)]

    # 全部封面分析摘要（不限数量）+ 结构化统计
    covers_summary = ""
    if covers_data:
        valid_covers = [c for c in covers_data if "error" not in c]
        valid_covers.sort(key=lambda x: x.get("_meta", {}).get("views", 0), reverse=True)
        if valid_covers:
            # 结构化统计
            struct_stats = {
                "color_type": Counter(),
                "composition": Counter(),
                "has_text": Counter(),
                "emotion": Counter(),
                "identity_visible": Counter(),
                "person_count": Counter(),
            }
            struct_views = {k: {} for k in struct_stats}
            for c in valid_covers:
                s = c.get("结构化", {})
                if s:
                    for field in ["color_type", "composition", "has_text", "emotion", "identity_visible"]:
                        val = s.get(field)
                        if val is not None:
                            if isinstance(val, list):
                                val = ", ".join(str(v) for v in val)
                            struct_stats[field][val] += 1
                            if val not in struct_views[field]:
                                struct_views[field][val] = []
                            struct_views[field][val].append(c.get("_meta", {}).get("views", 0))
                    pc = s.get("person_count")
                    if pc is not None:
                        try:
                            struct_stats["person_count"][int(pc)] += 1
                        except (ValueError, TypeError):
                            struct_stats["person_count"][str(pc)] += 1
            
            covers_summary = "\n## 封面分析（{}个有效）\n".format(len(valid_covers))
            covers_summary += "\n### 封面结构化统计（Python预处理）\n"
            for field, label in [("color_type", "色彩类型"), ("composition", "构图类型"), 
                                  ("emotion", "情绪类型"), ("person_count", "人物数量")]:
                if struct_stats[field]:
                    covers_summary += "- {}: ".format(label)
                    items = struct_stats[field].most_common()
                    parts = []
                    for val, count in items:
                        avg_v = sum(struct_views[field].get(val, [0])) / max(len(struct_views[field].get(val, [0])), 1)
                        parts.append("{}({}个,均播{:,.0f})".format(val, count, avg_v))
                    covers_summary += ", ".join(parts) + "\n"
            
            # 封面详情（前10个，减少prompt长度避免超时）
            covers_summary += "\n### 封面详情样本（Top10）\n"
            synergy_samples = []
            for i, c in enumerate(valid_covers[:10], 1):
                meta = c.get("_meta", {})
                covers_summary += "\n#### 封面{}: {}\n".format(i, meta.get('title', '未知')[:60])
                covers_summary += "- 播放量: {:,}\n".format(meta.get('views', 0))
                covers_summary += "- 人物: {}\n".format(str(c.get('人物', '无'))[:150])
                covers_summary += "- 色彩: {}\n".format(str(c.get('色彩', '无'))[:150])
                covers_summary += "- 构图: {}\n".format(str(c.get('构图', '无'))[:150])
                covers_summary += "- 爆款因素: {}\n".format(str(c.get('爆款因素', {}).get('来源', '无'))[:150])
                s = c.get("结构化", {})
                if s:
                    covers_summary += "- 结构化: 色彩={},构图={},情绪={},人物={}\n".format(
                        s.get("color_type","?"), s.get("composition","?"),
                        s.get("emotion","?"), s.get("person_count","?"))
                # 封面×标题协同
                synergy = c.get("封面标题配合", "")
                if synergy:
                    covers_summary += "- 封面标题配合: {}\n".format(str(synergy)[:150])
                    synergy_samples.append(str(synergy)[:100])

    # 频道数据摘要（含增长指标）
    channels_summary = ""
    if channels:
        channels_summary = "\n## 竞品频道数据（含增长分析）\n"
        for ch in channels:
            ch_name = ch.get("channel_name", ch.get("name", "未知"))
            ch_views = ch.get("total_views", 0)
            ch_videos = ch.get("total_videos", 0)
            ch_avg = ch_views // max(ch_videos, 1)
            ch_subs = ch.get("subscribers", 0)
            # 计算爆款率
            hot_videos = ch.get("hot_videos", 0)
            hot_rate = hot_videos / max(ch_videos, 1) * 100
            channels_summary += "- {}: 总播{:,}, {}视频, 均播{:,}, 粉丝{:,}, 爆款率{:.1f}%\n".format(
                ch_name, ch_views, ch_videos, ch_avg, ch_subs, hot_rate)

    # 标题骨架摘要（强化格式，让LLM直接复用）
    skeletons_summary = ""
    if skeleton_data and "error" not in skeleton_data:
        skeletons_summary = "\n## 已提取的标题骨架（直接复用，不要重复分析）\n"
        for i, s in enumerate(skeleton_data.get("title_skeletons", []), 1):
            skeletons_summary += "{}. {} (频率: {})\n   示例: {}\n".format(
                i, s.get('structure', ''), s.get('frequency', ''), s.get('example', '')[:80])
        skeletons_summary += "\n## 已提取的钩子分类（直接复用，不要重复分析）\n"
        for hook_type, hook_val in skeleton_data.get("hooks", {}).items():
            if isinstance(hook_val, dict):
                examples = hook_val.get("examples", [])
                defn = hook_val.get("definition", "")
                skeletons_summary += "- {} ({}): {}\n".format(hook_type, defn, ', '.join(examples[:5]))
            elif isinstance(hook_val, list):
                skeletons_summary += "- {}: {}\n".format(hook_type, ', '.join(hook_val[:5]))
        # 新发现的钩子类型
        emergent = skeleton_data.get("emergent_hooks", [])
        if emergent:
            skeletons_summary += "\n## 新发现的钩子类型（emergent hooks，直接复用）\n"
            for eh in emergent:
                if isinstance(eh, dict):
                    skeletons_summary += "- {}: {}  示例: {}\n".format(
                        eh.get('name', ''), eh.get('definition', '')[:80],
                        ', '.join(eh.get('examples', [])[:2]))
        title_formulas = skeleton_data.get("title_formulas", [])
        if title_formulas:
            skeletons_summary += "\n## 已提取的标题公式\n"
            for f in title_formulas:
                if isinstance(f, dict):
                    skeletons_summary += "- {} (适用: {})\n".format(f.get('formula', ''), f.get('适用场景', ''))
        title_packaging = skeleton_data.get("title_packaging", [])
        if title_packaging:
            skeletons_summary += "\n## 已提取的标题包装模式（直接复用）\n"
            for tp in title_packaging:
                if isinstance(tp, dict):
                    skeletons_summary += "- {}: {}\n".format(tp.get('name', ''), tp.get('pattern', ''))

    return """══════════════════════════════════
作为短剧YouTube运营专家，你已深入分析以下{lang}市场的竞品数据。

核心理念：
骨架可以复用，血肉必须创新。
不要模仿具体标题，而要理解其背后的心理驱动力。
给渔不给鱼——教思维方式和工具，不是数据分析报告。
══════════════════════════════════

## 数据输入（Python已预处理，直接引用）

### 市场概况
- 样本: {sample_size}个视频, {channel_count}个频道
- 标题均长: {avg_len:.0f}字符
- Emoji使用率: {emoji_rate:.1f}%
- 最佳发布: {best_hours} UTC | {best_weekdays}

### 全部视频标题（按播放量排序）
{titles_text}

{desc_summary}

### 标签统计
- 标题内嵌标签Top15: {top_title_tags}
- 描述标签Top20: {top_desc_tags}
- 高播放标签Top15（均播）: {top_high_views_tags}
- 标签组合Top10（共现频率）: {top_tag_pairs}

### 标签语义分组
{tag_group_summary}

### Emoji
使用率: {emoji_rate:.1f}% | 常用: {top_emojis}
位置: 开头{emoji_start}个, 中间{emoji_mid}个, 末尾{emoji_end}个
播放对比: 有Emoji均播{emoji_avg:,.0f} vs 无Emoji均播{no_emoji_avg:,.0f}

{channels_summary}
{covers_summary}
{skeletons_summary}
{hook_summary}

### 封面×标题协同参考框架（跨语言通用规则，用本语言数据验证/修正/扩展）
核心原则：标题和封面围绕同一个"核心钩子"分工——标题说清身份反差/情节反转/情绪爆点，封面把最有张力的一瞬间视觉化。
参考模式：
1. 标题给反差，封面给证据
2. 封面定格冲突高潮，标题补全前因后果
3. 情绪反转视觉化
4. 男女主关系用肢体距离表达
5. 阶层符号强化爽感
6. 奇观元素服务战力
7. 标题负责信息密度，封面负责情绪密度
8. 互补优于重复
反模式：题材错位、只美不钩、标题有爆点封面无、信息过散、情绪不匹配、身份缺视觉锚点。
女频核心：关系张力+情绪反转+身份差。
男频核心：低位受辱+隐藏强者+瞬间打脸。

---

## 输出要求

直接输出 JSON 对象，不要有任何前言、总结、客套话，不要包裹在 code block 中。

JSON 结构如下：

{{
  "meta": {{
    "platform": "youtube",
    "content_type": "short_drama",
    "lang": "{lang}",
    "sample_size": 样本数
  }},

  "stats": {{
    "avg_title_length": 标题平均字符数,
    "emoji_rate": emoji使用率百分比,
    "top_emojis": ["emoji列表"],
    "best_hours": [最佳发布小时UTC列表],
    "best_weekdays": ["最佳发布星期"],
    "key_words": ["高频关键词1", "关键词2"]
  }},

  "why": {{
    "title": [
      {{
        "principle": "一句话原则（如：身份反转比身份本身更重要）",
        "psychology": "心理机制解释（为什么观众会点击）",
        "application": "怎么用（具体到标题/封面/标签怎么写）"
      }}
    ],
    "thumbnail": [
      {{
        "principle": "一句话原则",
        "psychology": "心理机制",
        "application": "怎么用"
      }}
    ],
    "tags_and_distribution": [
      {{
        "principle": "一句话原则",
        "psychology": "心理机制",
        "application": "怎么用"
      }}
    ],
    "market_insights": {{
      "gender_bias": "男频vs女频数据对比和建议",
      "emerging_trends": "近期新兴题材/格式趋势",
      "content_quality_signals": "内容质量信号词（如FULL/HD等）"
    }}
  }},

  "what": [
    {{
      "name": "模式名称（如：身份反转打脸）",
      "template": "完整句式模板，用【】标注可替换部分。必须是完整句子，不是公式碎片。",
      "why_it_works": "一句话解释为什么这个模式有效",
      "sub_genre": "适用题材",
      "examples": ["真实标题1", "真实标题2"]
    }}
  ],

  "how": {{
    "title_skeletons": [
      {{
        "name": "叙事原型名称（如：身份落差型、逆境考验型、契约误会型）",
        "narrative_pattern": "叙事原型描述：描述故事核的张力结构（不是填空模板）",
        "psychological_hook": "心理钩子（为什么观众会点击）",
        "sub_genre": "适用题材",
        "avg_views": 平均播放量,
        "count": 出现次数,
        "examples": ["真实标题1", "真实标题2", "真实标题3"],
        "rules": ["改编规则：什么能变、什么不能变", "反例：什么样的写法会失败"]
      }}
    ],

    "hook_combination": {{
      "核心发现": "从数据中发现的钩子组合规律",
      "最强配对": ["最强配对1", "最强配对2"],
      "低效组合": ["低效组合1"],
      "规则": ["组合规则1"],
      "hook_types": {{
        "钩子类型名": {{"definition": "钩子定义", "examples": ["标题1", "标题2"]}}
      }},
      "emergent_hooks": [{{"name": "新发现的钩子类型", "definition": "定义", "examples": ["标题1"]}}],
      "hook_stats": {{"从Python统计的钩子类型分布数据填入": 数量}}
    }},

    "title_constraints": {{
      "avg_length": 标题平均字符数,
      "emoji_rate": emoji使用率百分比,
      "top_emojis": ["emoji列表"],
      "title_structure": "标题结构规律（从数据中发现，如前半句/后半句的分工）",
      "key_words": ["高频关键词1", "关键词2"]
    }},

    "emoji_strategy": {{
      "best_position": "从数据中发现的emoji最佳位置",
      "rules": ["emoji使用规则"]
    }},

    "hashtag_strategy": {{
      "title_tags": ["#tag1"],
      "description_tags": ["tag1"],
      "combination_pattern": "从数据中发现的标签组合规律",
      "trend_hijacking": "热点截流策略",
      "rules": ["标签使用规则"]
    }},

    "description_template": {{
      "structure": "从数据中发现的描述结构规律",
      "template_types": [{{"name": "模板名", "pattern": "模式", "适用场景": "场景"}}],
      "rules": ["描述规则"]
    }},

    "thumbnail_guidelines": {{
      "composition": "构图建议",
      "figures": "人物建议",
      "colors": "配色建议",
      "emotion": "情绪基调",
      "visual_symbols": "视觉符号/道具",
      "text": "文字建议"
    }},

    "cover_title_synergy": {{
      "rule": "封面×标题协同的核心原则",
      "hook_cover_mapping": [
        {{
          "hook_type": "钩子类型（如emotion/identity/reversal/relationship等）",
          "title_pattern": "该钩子在标题中的典型表现",
          "cover_pattern": "该钩子对应的最佳封面视觉表现",
          "example_title": "真实标题",
          "example_cover": "封面描述"
        }}
      ],
      "patterns": [
        {{"name": "协同模式名称", "description": "描述", "example": "标题xxx+封面xxx"}}
      ],
      "anti_patterns": [
        {{"name": "反模式名称", "description": "描述"}}
      ],
      "female_freq": "女频协同策略",
      "male_freq": "男频协同策略"
    }},

    "publish_time": {{
      "best_hours": [小时列表],
      "best_weekdays": ["星期列表"],
      "rules": ["发布时间规则"]
    }},

    "growth_strategy": ["频道增长策略1", "策略2"],

    "rhetorical_patterns": {{
      "sentence_structures": [
        {{
          "name": "句式名称",
          "pattern": "句式模板，用{{}}标注可替换部分",
          "example": "真实标题示例",
          "avg_views": 该句式的平均播放量,
          "count": 出现次数,
          "when_to_use": "什么场景下用这个句式"
        }}
      ],
      "punctuation_strategy": {{
        "从数据中发现的标点使用规律": "描述"
      }},
      "visual_elements": {{
        "从数据中发现的视觉元素规律": "描述"
      }},
      "progression_techniques": [
        {{
          "name": "递进手法名称",
          "pattern": "手法模板",
          "example": "真实标题示例"
        }}
      ]
    }}
  }},

  "boundaries": {{
    "sample_size_warning": "数据量是否足够做判断",
    "missing_fields": ["缺失的数据字段"]
  }}
}}

要求：
- stats 由Python填写，不要自己编数字
- why 每个维度3-5条原则，每条必须包含principle+psychology+application三个字段
- why.market_insights 三个字段必须全部填写
- what 给3-5个可直接改编的故事模式，template必须是完整句子用【】标注可替换部分
- how.title_skeletons 3-5个叙事原型，narrative_pattern描述故事核结构（不是填空模板），每个必须有psychological_hook和rules
- how.title_constraints 所有数字字段必须填写，title_structure必须从数据中发现规律
- how.rhetorical_patterns 从数据中发现句式、标点、视觉元素、递进手法的规律，不限定数量
- 三重验证：每条规律必须满足以下至少两条才收录：(1)在多个骨架/模式中反复出现（不是孤例）(2)能解释为什么高播放标题有效（有预测力）(3)不是所有语种都一样的通用常识（有排他性）
- 整体风格：给渔不给鱼——讲原理和方法，不是堆数据""".format(
        lang=lang,
        titles_text=titles_text,
        sample_size=len(evidence.get("titles", [])),
        channel_count=len(channels),
        desc_summary=desc_summary,
        top_title_tags=", ".join(top_title_tags),
        top_desc_tags=", ".join(top_desc_tags),
        top_high_views_tags=", ".join("{}({:,.0f}播,{:.0f}条)".format(t, v, c) for t, v, c in top_high_views_tags),
        top_tag_pairs=", ".join("{}+{}({:.0f}次)".format(a, b, c) for (a, b), c in top_tag_pairs),
        emoji_rate=emoji_rate,
        top_emojis=" ".join(top_emojis),
        emoji_start=emoji_in_title_start,
        emoji_mid=emoji_in_title_mid,
        emoji_end=emoji_in_title_end,
        emoji_avg=emoji_avg,
        no_emoji_avg=no_emoji_avg,
        avg_len=avg_len,
        best_hours=", ".join("{}:00".format(h) for h in best_hours),
        best_weekdays=", ".join(best_weekdays),
        channels_summary=channels_summary,
        covers_summary=covers_summary,
        skeletons_summary=skeletons_summary,
        hook_summary=hook_summary,
        tag_group_summary=tag_group_summary
    )



def _parse_distill_result(result: str) -> dict:
    """解析三层蒸馏结果，分割成三个部分
    
    支持多种Markdown格式：
    - # 第一层 / ## 第一层 / ### 第一层（任意heading级别）
    - --- 分隔线
    - 第一层：xxx / 第二层：xxx / 第三层：xxx（带冒号）
    """
    parts = {"principles": "", "examples": "", "generation-rules": ""}
    
    # 策略1: 用heading分割（支持 #/##/### + 可选冒号）
    pattern = r'\n#{1,3}\s*第[一二三]层[：:]?'
    sections = re.split(pattern, result)
    
    if len(sections) >= 4:
        parts["principles"] = sections[1].strip()
        parts["examples"] = sections[2].strip()
        parts["generation-rules"] = sections[3].strip()
        return parts
    
    # 策略2: 用 --- 分割
    dash_sections = re.split(r'\n---\n', result)
    if len(dash_sections) >= 3:
        parts["principles"] = dash_sections[0].strip()
        parts["examples"] = dash_sections[1].strip()
        parts["generation-rules"] = dash_sections[2].strip()
        return parts
    
    # 策略3: heading在第一行（无前导换行）
    pattern2 = r'^#{1,3}\s*第[一二三]层[：:]?'
    sections2 = re.split(pattern2, result, flags=re.MULTILINE)
    if len(sections2) >= 4:
        parts["principles"] = sections2[1].strip()
        parts["examples"] = sections2[2].strip()
        parts["generation-rules"] = sections2[3].strip()
        return parts
    
    # 策略4: 按关键词提取
    for key, keywords in [
        ("principles", ["第一层", "Why", "原则"]),
        ("examples", ["第二层", "What", "示例"]),
        ("generation-rules", ["第三层", "How", "生成规则"]),
    ]:
        for kw in keywords:
            idx = result.find(kw)
            if idx >= 0:
                # 从关键词位置往后找heading开头
                start = result.rfind("\n", 0, idx)
                if start < 0:
                    start = 0
                # 找下一个heading或分割线作为结束
                end = len(result)
                for end_kw in ["第二层", "第三层", "---"]:
                    ei = result.find(end_kw, idx + len(kw))
                    if ei >= 0:
                        # 往前找到行首
                        line_start = result.rfind("\n", 0, ei)
                        end = min(end, line_start if line_start >= 0 else ei)
                content = result[start:end].strip()
                # 去掉heading行本身
                lines = content.split("\n")
                if lines and any(k in lines[0] for k in keywords):
                    content = "\n".join(lines[1:]).strip()
                if content and len(content) > 10:
                    parts[key] = content
                    break
    
    # 如果还是全空，整个结果放入principles
    if not any(parts.values()):
        parts["principles"] = result.strip()
    
    return parts


# ═══════════════════════════════════════════════
#  主入口
# ═══════════════════════════════════════════════

def main():
    import argparse
    parser = argparse.ArgumentParser(description="短剧竞品每日流水线")
    parser.add_argument("--step", type=str, help="只运行指定步骤 (1, 2, 2b, 3, 4, 5a, 5b, 6)")
    parser.add_argument("--lang", type=str, help="指定语种")
    parser.add_argument("--all", action="store_true", help="全量采集")
    parser.add_argument("--new-only", action="store_true", help="只采集新频道")
    parser.add_argument("--limit", type=int, default=10, help="发现频道数量")
    args = parser.parse_args()

    start = time.time()
    print(f"{'='*60}")
    print(f"🚀 短剧竞品每日流水线 — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    try:
        snapshots = []

        if args.step and args.step not in ["1", "5a"]:
            # 非第一步，需要加载已有快照
            # 5b/6 从 latest.json 加载（已筛选的短剧数据）
            if args.step in ["5b", "6"]:
                if LATEST_FILE.exists():
                    snapshots = json.loads(LATEST_FILE.read_text())
                    print(f"📂 加载 latest.json: {len(snapshots)}频道")
            elif STAGING_FILE.exists():
                snapshots = json.loads(STAGING_FILE.read_text())
                print(f"📂 加载 staging.json: {len(snapshots)}频道")

        # Step 1: 发现
        if not args.step or args.step == "1":
            new_channels = discover_channels(limit=args.limit)
            if new_channels and not args.step:
                print(f"\n  ℹ️ 新发现的频道已写入 staging.json，等待筛选后进入 latest.json")

        # Step 2: 采集
        if not args.step or args.step == "2":
            snapshots = collect_data(lang_filter=args.lang, collect_all=args.all, new_only=args.new_only)

        # Step 2b: 规则打分（移到采集后，过滤前）
        if not args.step or args.step == "2b":
            if not snapshots:
                if STAGING_FILE.exists():
                    snapshots = json.loads(STAGING_FILE.read_text())
            if snapshots:
                snapshots = ai_validate_videos(snapshots)

        # Step 3: 过滤
        if not args.step or args.step == "3":
            if not snapshots:
                if STAGING_FILE.exists():
                    snapshots = json.loads(STAGING_FILE.read_text())
            if snapshots:
                snapshots = filter_data(snapshots)

        # Step 4: 保存到 staging.json
        if not args.step or args.step == "4":
            if snapshots:
                STAGING_FILE.write_text(json.dumps(snapshots, ensure_ascii=False, indent=2))
                size_kb = STAGING_FILE.stat().st_size / 1024
                print(f"\n💾 Step 4: 快照已保存 — staging.json ({size_kb:.0f}KB)")
                print(f"  ℹ️ 数据已写入 staging.json，等待筛选后进入 latest.json")

        # Step 5a: 本地统计
        if not args.step or args.step == "5a":
            if not snapshots:
                if LATEST_FILE.exists():
                    snapshots = json.loads(LATEST_FILE.read_text())
            if snapshots:
                distill_local_stats(snapshots)
                time.sleep(2)  # 短暂休息，避免API过载

        # Step 5b: MiMo结构提取
        if not args.step or args.step == "5b":
            if not snapshots:
                if LATEST_FILE.exists():
                    snapshots = json.loads(LATEST_FILE.read_text())
            if snapshots:
                analyze_covers_mimo(snapshots)
                time.sleep(2)  # 短暂休息，避免API过载

        # Step 6: 三层蒸馏（临时启用，测试新 prompt）
        if not args.step or args.step == "6":
            if not snapshots:
                if LATEST_FILE.exists():
                    snapshots = json.loads(LATEST_FILE.read_text())
            if snapshots:
                if args.lang:
                    snapshots = [s for s in snapshots if s.get("language") == args.lang]
                distill_three_layer(snapshots)
                time.sleep(2)

        # Step 7: 增量蒸馏检查（已迁移至 run_competitor_pipeline.py）

        elapsed = time.time() - start
        print(f"\n{'='*60}")
        print(f"✅ 流水线完成 — {elapsed:.0f}秒")
        print(f"{'='*60}")

    except Exception as e:
        elapsed = time.time() - start
        print(f"\n{'='*60}")
        print(f"❌ 流水线失败 — {elapsed:.0f}秒")
        print(f"错误: {e}")
        print(f"{'='*60}")
        import traceback
        traceback.print_exc()
        raise


if __name__ == "__main__":
    main()
