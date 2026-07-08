#!/usr/bin/env python3
"""
智能筛选 - 用视频标题关键词判断是否是短剧频道
"""
import json
import subprocess
import os
import time
from collections import Counter

ROOT = "/Users/liuxi/duanju"
REGISTRY_FILE = f"{ROOT}/data/competitor_registry.json"
YTDLP = os.path.expanduser("~/.pyenv/shims/yt-dlp")
COOKIES = os.path.expanduser("~/duanju/cookies.txt")

# 短剧视频标题关键词（各语种）
DRAMA_TITLE_KEYWORDS = {
    "德语": ["kurzdrama", "drama", "serie", "mini", "kurze", "liebe", "romantik", "rache", "betrug", "geheimnis"],
    "土耳其": ["dizi", "drama", "mini", "kısa", "aşk", "intikam", "ihanet", "sır", "evlilik"],
    "日语": ["ドラマ", "短編", "恋愛", "復讐", "秘密", "結婚", "社長", "CEO", "花嫁", "嘘"],
    "印尼": ["drama", "pendek", "mini", "cinta", "balas dendam", "rahasia", "nikah", "CEO"],
    "葡萄牙": ["drama", "curto", "mini", "amor", "vingança", "segredo", "casamento", "CEO", "milionário"],
    "西语": ["drama", "corto", "mini", "amor", "venganza", "secreto", "matrimonio", "CEO", "millonario"],
    "繁中": ["短劇", "短剧", "總裁", "总裁", "復仇", "复仇", "重生", "甜寵", "甜宠", "虐戀", "虐恋"],
    "英文": ["drama", "short", "mini", "ceo", "revenge", "secret", "marriage", "billionaire", "romance"],
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_recent_video_titles(channel_id, max_videos=3):
    """用yt-dlp获取频道最近3个视频标题"""
    try:
        cmd = [
            YTDLP,
            f"https://www.youtube.com/channel/{channel_id}/videos",
            "--flat-playlist",
            "--print", "%(title)s",
            "--playlist-end", str(max_videos),
            "--cookies", COOKIES,
            "--no-download",
            "--ignore-errors",
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        titles = []
        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and line != "NA":
                titles.append(line)
        
        return titles[:max_videos]
    except Exception as e:
        return []


def is_drama_by_titles(titles, lang):
    """用视频标题判断是否是短剧频道"""
    if not titles:
        return False  # 没有视频数据，跳过
    
    # 合并所有标题
    all_text = " ".join(titles).lower()
    
    # 检查短剧关键词
    keywords = DRAMA_TITLE_KEYWORDS.get(lang, [])
    for kw in keywords:
        if kw.lower() in all_text:
            return True
    
    return False


def main():
    registry = load_json(REGISTRY_FILE)
    
    # 获取channels_filtered
    channels = registry.get("channels_filtered", {})
    if not channels:
        # 如果没有filtered，用顶层条目
        for k, v in registry.items():
            if k.startswith("UC") and isinstance(v, dict):
                channels[k] = v
    
    print(f"=== 智能筛选：视频标题关键词判断 ===")
    print(f"总频道: {len(channels)} 个\n")
    
    # 按语种统计
    lang_count = Counter()
    for ch in channels.values():
        lang_count[ch.get("language", "?")] += 1
    
    print("筛选前分布:")
    for lang, cnt in lang_count.most_common():
        print(f"  {lang}: {cnt}")
    
    # 每个语种只检查前30个（按订阅数排序，包含小号）
    lang_channels = {}
    for cid, ch in channels.items():
        lang = ch.get("language", "?")
        if lang not in lang_channels:
            lang_channels[lang] = []
        lang_channels[lang].append((cid, ch))
    
    # 每个语种取前30个
    selected = {}
    for lang, ch_list in lang_channels.items():
        # 按订阅数排序（降序）
        ch_list.sort(key=lambda x: x[1].get("subscribers", 0), reverse=True)
        for cid, ch in ch_list[:30]:
            selected[cid] = ch
    
    print(f"\n每语种前30: {len(selected)} 个")
    channels = selected
    
    # 智能筛选
    filtered = {}
    removed = []
    checked = 0
    
    for cid, ch in channels.items():
        lang = ch.get("language", "?")
        name = ch.get("channel_name", ch.get("name", ""))
        
        # 获取最近视频标题
        titles = get_recent_video_titles(cid)
        checked += 1
        
        if is_drama_by_titles(titles, lang):
            filtered[cid] = ch
            print(f"  ✅ [{lang}] {name[:30]} — {titles[0][:40] if titles else '无视频'}")
        else:
            removed.append((cid, name, lang, titles))
            print(f"  ❌ [{lang}] {name[:30]} — {titles[0][:40] if titles else '无视频'}")
        
        # 控制频率
        if checked % 10 == 0:
            print(f"  ... 已检查 {checked}/{len(channels)}")
            time.sleep(1)
    
    # 统计结果
    print(f"\n=== 智能筛选结果 ===")
    print(f"保留: {len(filtered)} 个")
    print(f"移除: {len(removed)} 个")
    
    # 按语种统计保留
    filtered_lang = Counter()
    for ch in filtered.values():
        filtered_lang[ch.get("language", "?")] += 1
    
    print(f"\n保留分布:")
    for lang, cnt in filtered_lang.most_common():
        print(f"  {lang}: {cnt}")
    
    # 显示被移除的频道
    print(f"\n被移除的频道 (前20个):")
    for cid, name, lang, titles in removed[:20]:
        title_sample = titles[0][:40] if titles else "无视频"
        print(f"  [{lang}] {name[:25]} — {title_sample}")
    
    # 保存筛选结果
    registry["channels_smart_filtered"] = filtered
    save_json(REGISTRY_FILE, registry)
    print(f"\n已保存筛选结果到 registry.channels_smart_filtered")
    
    return filtered, removed


if __name__ == "__main__":
    main()
