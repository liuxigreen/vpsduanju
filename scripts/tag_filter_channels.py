#!/usr/bin/env python3
"""
标签筛选 - 用视频标签判断是否是短剧频道（比标题关键词更准）
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

# 短剧标签关键词
DRAMA_TAGS = [
    "drama", "dramas", "shortdrama", "minidrama", "short drama",
    "chinesedrama", "cdrama", "ceo", "revenge", "romance",
    "billionaire", "contractmarriage", "reborn", "rebornrevenge",
    "korean drama", "kdrama", "turkish drama", "telenovela",
    "kurzdrama", "kısa dizi", "ショートドラマ", "短劇", "短剧",
    "drama pendek", "drama corto", "drama curto",
]


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_video_tags(channel_id, max_videos=2):
    """用yt-dlp获取频道最近视频的标签"""
    try:
        # 先获取频道最新1个视频URL
        cmd_list = [
            YTDLP,
            f"https://www.youtube.com/channel/{channel_id}/videos",
            "--flat-playlist",
            "--print", "%(url)s",
            "--playlist-end", "1",
            "--cookies", COOKIES,
            "--no-download",
            "--ignore-errors",
        ]
        r = subprocess.run(cmd_list, capture_output=True, text=True, timeout=20)
        video_url = None
        for line in r.stdout.strip().split("\n"):
            line = line.strip()
            if line and line != "NA" and ("watch" in line or "shorts" in line):
                video_url = line if line.startswith("http") else f"https://www.youtube.com{line}"
                break
        
        if not video_url:
            return []
        
        # 获取该视频的标签
        cmd_tags = [
            YTDLP,
            video_url,
            "--print", "%(tags)s",
            "--cookies", COOKIES,
            "--no-download",
            "--ignore-errors",
        ]
        result = subprocess.run(cmd_tags, capture_output=True, text=True, timeout=30)
        
        all_tags = []
        for line in result.stdout.strip().split("\n"):
            if line and line != "NA":
                # 标签格式: ['tag1', 'tag2', 'tag3']
                try:
                    tags = eval(line)
                    if isinstance(tags, list):
                        all_tags.extend([t.lower() for t in tags])
                except:
                    # 可能是逗号分隔
                    tags = [t.strip().lower() for t in line.split(",")]
                    all_tags.extend(tags)
        
        return all_tags
    except Exception as e:
        return []


def is_drama_by_tags(tags):
    """用视频标签判断是否是短剧频道"""
    if not tags:
        return None  # 没有标签数据，无法判断
    
    tags_text = " ".join(tags)
    
    for kw in DRAMA_TAGS:
        if kw.lower() in tags_text:
            return True
    
    return False


def main():
    registry = load_json(REGISTRY_FILE)
    
    # 获取channels_smart_filtered（之前初筛保留的156个）
    channels = registry.get("channels_smart_filtered", {})
    if not channels:
        print("没有channels_smart_filtered，用channels_filtered")
        channels = registry.get("channels_filtered", {})
    
    # 也加上被初筛误杀的频道（重新检查）
    filtered_out = registry.get("channels_filtered", {})
    smart_filtered = registry.get("channels_smart_filtered", {})
    # 被初筛移除但不在smart_filtered里的
    for cid, ch in filtered_out.items():
        if cid not in smart_filtered and cid not in channels:
            channels[cid] = ch
    
    print(f"=== 标签筛选：用视频标签判断是否是短剧 ===")
    print(f"总频道: {len(channels)} 个\n")
    
    # 智能筛选
    filtered = {}
    removed = []
    uncertain = []
    checked = 0
    
    for cid, ch in channels.items():
        lang = ch.get("language", "?")
        name = ch.get("channel_name", ch.get("name", ""))
        
        # 获取视频标签
        tags = get_video_tags(cid)
        checked += 1
        
        result = is_drama_by_tags(tags)
        
        if result is True:
            filtered[cid] = ch
            tag_sample = ", ".join(tags[:5]) if tags else "无标签"
            print(f"  ✅ [{lang}] {name[:30]} — 标签: {tag_sample}")
        elif result is False:
            removed.append((cid, name, lang, tags))
            tag_sample = ", ".join(tags[:5]) if tags else "无标签"
            print(f"  ❌ [{lang}] {name[:30]} — 标签: {tag_sample}")
        else:
            uncertain.append((cid, name, lang))
            print(f"  ❓ [{lang}] {name[:30]} — 无标签数据")
        
        # 控制频率
        if checked % 10 == 0:
            print(f"  ... 已检查 {checked}/{len(channels)}")
            time.sleep(2)
    
    # 统计结果
    print(f"\n=== 标签筛选结果 ===")
    print(f"保留: {len(filtered)} 个")
    print(f"移除: {len(removed)} 个")
    print(f"不确定: {len(uncertain)} 个")
    
    # 按语种统计保留
    filtered_lang = Counter()
    for ch in filtered.values():
        filtered_lang[ch.get("language", "?")] += 1
    
    print(f"\n保留分布:")
    for lang, cnt in filtered_lang.most_common():
        print(f"  {lang}: {cnt}")
    
    # 显示被移除的频道
    print(f"\n被移除的频道:")
    for cid, name, lang, tags in removed:
        tag_sample = ", ".join(tags[:5]) if tags else "无标签"
        print(f"  [{lang}] {name[:25]} — {tag_sample}")
    
    # 保存筛选结果
    registry["channels_tag_filtered"] = filtered
    save_json(REGISTRY_FILE, registry)
    print(f"\n已保存筛选结果到 registry.channels_tag_filtered")
    
    return filtered, removed, uncertain


if __name__ == "__main__":
    main()
