#!/usr/bin/env python3
"""
多信号综合筛选 - 频道名+视频标题+标签 综合打分
"""
import json
import subprocess
import os
import time
import re
from collections import Counter

ROOT = "/Users/liuxi/duanju"
REGISTRY_FILE = f"{ROOT}/data/competitor_registry.json"
YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")
COOKIES = os.path.expanduser("~/duanju/cookies.txt")

# 短剧关键词（各语种，用于频道名+标题）
DRAMA_NAME_KEYWORDS = {
    "德语": ["drama", "kurzdrama", "kurze", "mini", "serie"],
    "土耳其": ["dizi", "drama", "mini", "kısa"],
    "日语": ["ドラマ", "劇場", "ショート", "ミニ"],
    "印尼": ["drama", "pendek", "teater", "mini"],
    "葡萄牙": ["drama", "filme", "novela", "série", "curto", "corto"],
    "西语": ["drama", "corto", "dramático", "novela", "mini"],
    "繁中": ["短劇", "短剧", "劇場", "剧场", "劇社", "短片"],
    "英文": ["drama", "short", "mini", "reel", "dramas"],
}

# 短剧标签关键词
DRAMA_TAGS = [
    "drama", "dramas", "shortdrama", "minidrama", "short drama",
    "chinesedrama", "cdrama", "ceo", "revenge", "romance",
    "billionaire", "contractmarriage", "reborn", "rebornrevenge",
    "kurzdrama", "kısa dizi", "ショートドラマ", "短劇", "短剧",
    "drama pendek", "drama corto", "drama curto", "telenovela",
]

# 排除关键词（非短剧内容）
EXCLUDE_KEYWORDS = [
    "music", "musik", "müzik", "音楽", "音樂", "音乐",
    "game", "spiel", "oyun", "ゲーム", "遊戲", "游戏",
    "news", "nachrichten", "haber", "ニュース", "新聞", "新闻",
    "movie", "film", "filme", " película", "映画", "電影", "电影",
    "comedy", "komedi", "コメディ", "喜劇", "喜剧",
    "vlog", "tutorial", "howto", "review", "unboxing",
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_video_info(channel_id):
    """获取频道最新视频的标题+标签"""
    try:
        # 获取最新1个视频URL
        cmd_list = [
            YTDLP,
            f"https://www.youtube.com/channel/{channel_id}/videos",
            "--flat-playlist",
            "--print", "%(url)s|||%(title)s",
            "--playlist-end", "1",
            "--cookies", COOKIES,
            "--no-download",
            "--ignore-errors",
        ]
        r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=20)
        
        video_url = None
        video_title = ""
        for line in r.stdout.strip().split("\n"):
            if "|||" in line:
                parts = line.split("|||", 1)
                url_part = parts[0].strip()
                title_part = parts[1].strip() if len(parts) > 1 else ""
                if url_part and url_part != "NA":
                    video_url = url_part if url_part.startswith("http") else f"https://www.youtube.com{url_part}"
                    video_title = title_part
                    break
        
        if not video_url:
            return {"title": "", "tags": []}
        
        # 获取视频标签
        cmd_tags = [
            YTDLP,
            video_url,
            "--print", "%(tags)s",
            "--cookies", COOKIES,
            "--no-download",
            "--ignore-errors",
        ]
        result = subprocess.run(cmd_tags, capture_output=True, text=True, timeout=30)
        
        tags = []
        for line in result.stdout.strip().split("\n"):
            if line and line != "NA":
                try:
                    t = eval(line)
                    if isinstance(t, list):
                        tags = [x.lower() for x in t]
                        break
                except:
                    pass
        
        return {"title": video_title, "tags": tags}
    except Exception as e:
        return {"title": "", "tags": []}


def score_channel(name, lang, title, tags):
    """综合打分：0-10分"""
    score = 0
    reasons = []
    
    name_lower = name.lower()
    title_lower = title.lower()
    tags_text = " ".join(tags).lower()
    all_text = f"{name_lower} {title_lower} {tags_text}"
    
    # 排除检查（-5分）
    for kw in EXCLUDE_KEYWORDS:
        if kw.lower() in name_lower:
            score -= 5
            reasons.append(f"排除词:{kw}")
            break
    
    # 频道名匹配（+2分）
    for kw in DRAMA_NAME_KEYWORDS.get(lang, []):
        if kw.lower() in name_lower:
            score += 2
            reasons.append(f"频道名:{kw}")
            break
    
    # 标题匹配（+2分）
    for kw in DRAMA_NAME_KEYWORDS.get(lang, []):
        if kw.lower() in title_lower:
            score += 2
            reasons.append(f"标题:{kw}")
            break
    
    # 标签匹配（+4分，最准）
    for kw in DRAMA_TAGS:
        if kw.lower() in tags_text:
            score += 4
            reasons.append(f"标签:{kw}")
            break
    
    # 无标签数据时降权
    if not tags:
        score -= 1
        reasons.append("无标签")
    
    return score, reasons


def main():
    registry = load_json(REGISTRY_FILE)
    
    # 获取channels_smart_filtered
    channels = registry.get("channels_smart_filtered", {})
    if not channels:
        channels = registry.get("channels_filtered", {})
    
    # 加上被smart_filter移除的
    filtered_out = registry.get("channels_filtered", {})
    for cid, ch in filtered_out.items():
        if cid not in channels:
            channels[cid] = ch
    
    print(f"=== 多信号综合筛选 ===")
    print(f"总频道: {len(channels)} 个\n")
    
    # 综合筛选
    results = []
    checked = 0
    
    for cid, ch in channels.items():
        lang = ch.get("language", "?")
        name = ch.get("channel_name", ch.get("name", ""))
        
        # 获取视频信息
        info = get_video_info(cid)
        title = info["title"]
        tags = info["tags"]
        checked += 1
        
        # 综合打分
        score, reasons = score_channel(name, lang, title, tags)
        
        results.append({
            "cid": cid,
            "name": name,
            "lang": lang,
            "score": score,
            "reasons": reasons,
            "title": title[:60],
            "tags": tags[:5],
        })
        
        status = "✅" if score >= 4 else "❌"
        tag_sample = ", ".join(tags[:3]) if tags else "无标签"
        print(f"  {status} [{lang}] {name[:25]} — 分:{score} | {tag_sample}")
        
        if checked % 10 == 0:
            print(f"  ... 已检查 {checked}/{len(channels)}")
            time.sleep(2)
    
    # 统计
    results.sort(key=lambda x: x["score"], reverse=True)
    
    print(f"\n=== 综合筛选结果 ===")
    
    # 按分数分布
    score_dist = Counter()
    for r in results:
        if r["score"] >= 4:
            score_dist["✅保留"] += 1
        elif r["score"] >= 2:
            score_dist["❓不确定"] += 1
        else:
            score_dist["❌移除"] += 1
    
    print(f"✅保留(≥4分): {score_dist['✅保留']}")
    print(f"❓不确定(2-3分): {score_dist['❓不确定']}")
    print(f"❌移除(<2分): {score_dist['❌移除']}")
    
    # 保留频道按语种分布
    kept = [r for r in results if r["score"] >= 4]
    kept_lang = Counter(r["lang"] for r in kept)
    print(f"\n保留分布:")
    for lang, cnt in kept_lang.most_common():
        print(f"  {lang}: {cnt}")
    
    # 保存
    kept_ids = {r["cid"] for r in kept}
    filtered = {cid: ch for cid, ch in channels.items() if cid in kept_ids}
    registry["channels_multi_filtered"] = filtered
    save_json(REGISTRY_FILE, registry)
    print(f"\n已保存到 registry.channels_multi_filtered ({len(filtered)} 个)")


if __name__ == "__main__":
    main()
