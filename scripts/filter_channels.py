#!/usr/bin/env python3
"""
初筛脚本 - 用频道名关键词过滤非短剧频道
"""
import json
import re
from collections import Counter

ROOT = "/Users/liuxi/duanju"
REGISTRY_FILE = f"{ROOT}/data/competitor_registry.json"

# 短剧关键词（各语种）
DRAMA_KEYWORDS = {
    "德语": ["drama", "kurzdrama", "kurze", "mini"],
    "土耳其": ["dizi", "drama", "mini", "kısa"],
    "日语": ["ドラマ", "劇場", "ショート", "ミニ"],
    "印尼": ["drama", "pendek", "teater", "mini"],
    "葡萄牙": ["drama", "filme", "novela", "série", "curto"],
    "西语": ["drama", "corto", "dramático", "novela", "mini"],
    "繁中": ["短劇", "劇場", "劇社", "短剧", "剧场"],
    "英文": ["drama", "short", "mini", "reel"],
}

# 排除关键词（非短剧）
EXCLUDE_KEYWORDS = {
    "德语": ["musik", "game", "news", "sport", "comedy", "film", "movie"],
    "土耳其": ["müzik", "oyun", "haber", "spor", "komedi", "film", "sinema"],
    "日语": ["アニメ", "ゲーム", "ニュース", "スポーツ", "映画", "音楽", "vtuber"],
    "印尼": ["musik", "game", "news", "olahraga", "komedi", "film", "movie"],
    "葡萄牙": ["música", "game", "news", "esporte", "comédia", "filme", "movie"],
    "西语": ["música", "game", "news", "deporte", "comedia", "película", "movie"],
    "繁中": ["音樂", "遊戲", "新聞", "運動", "喜劇", "電影", "电影"],
    "英文": ["music", "game", "news", "sport", "comedy", "movie", "film", "vlog"],
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def is_drama_channel(name, lang):
    """判断是否是短剧频道"""
    name_lower = name.lower()
    
    # 检查排除关键词
    for kw in EXCLUDE_KEYWORDS.get(lang, []):
        if kw.lower() in name_lower:
            return False
    
    # 检查短剧关键词
    for kw in DRAMA_KEYWORDS.get(lang, []):
        if kw.lower() in name_lower:
            return True
    
    # 如果没有明确关键词，默认保留（后续用视频数据验证）
    return True


def main():
    registry = load_json(REGISTRY_FILE)
    
    # 获取顶层channel条目
    channels = {}
    for k, v in registry.items():
        if k.startswith("UC") and isinstance(v, dict):
            channels[k] = v
    
    print(f"=== 初筛：频道名关键词过滤 ===")
    print(f"总频道: {len(channels)} 个\n")
    
    # 按语种统计
    lang_count = Counter()
    for ch in channels.values():
        lang_count[ch.get("language", "?")] += 1
    
    print("初筛前分布:")
    for lang, cnt in lang_count.most_common():
        print(f"  {lang}: {cnt}")
    
    # 初筛
    filtered = {}
    removed = []
    
    for cid, ch in channels.items():
        name = ch.get("channel_name", ch.get("name", ""))
        lang = ch.get("language", "?")
        
        if is_drama_channel(name, lang):
            filtered[cid] = ch
        else:
            removed.append((cid, name, lang))
    
    # 统计结果
    print(f"\n=== 初筛结果 ===")
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
    for cid, name, lang in removed[:20]:
        print(f"  [{lang}] {name}")
    
    # 保存筛选结果
    registry["channels_filtered"] = filtered
    save_json(REGISTRY_FILE, registry)
    print(f"\n已保存筛选结果到 registry.channels_filtered")
    
    return filtered, removed


if __name__ == "__main__":
    main()
