#!/usr/bin/env python3
"""
从蒸馏数据的267条封面 → 下载图片 → vision反推ChatGPT prompt

流程：
1. 读 distill/evidence/*/covers.json（267条，有详细分析但没图片）
2. 按标题匹配 competitor_data/latest.json（有video_id）
3. 下载YouTube缩略图
4. Vision模型反推ChatGPT生图prompt
5. 输出到 data/reverse_engineered_covers/from_distill.json
"""
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import reverse_engineer_cover_prompts as rec

DISTILL_DIR = ROOT / "distill" / "evidence"
COMPETITOR_DATA = ROOT / "data" / "competitor_data" / "latest.json"
OUTPUT_DIR = ROOT / "data" / "reverse_engineered_covers"
OUTPUT_FILE = OUTPUT_DIR / "from_distill.json"

LANG_MAP = {
    "印尼": "id", "英文": "en", "西语": "es", "日语": "jp",
    "葡萄牙": "pt", "土耳其": "tr", "繁中": "zh-tw",
}

DELAY = 6


def normalize(s: str) -> str:
    """标题归一化，用于模糊匹配"""
    s = s.lower().strip()
    s = re.sub(r'[\[\]【】🔥💕❤️💖💗💘😍😱💔💋]', '', s)
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[^a-z0-9\u4e00-\u9fff\s]', '', s)
    return s.strip()[:80]


def build_competitor_index():
    """建立 标题→(video_id, views, channel) 的索引"""
    with open(COMPETITOR_DATA) as f:
        data = json.load(f)

    index = {}  # normalized_title -> {video_id, views, channel, language}
    for ch in data:
        ch_name = ch.get("name", "")
        lang = ch.get("language", "")
        for v in ch.get("videos", []):
            vid = v.get("video_id", v.get("id", ""))
            title = v.get("title", "")
            views = v.get("view_count", 0)
            if vid and title:
                key = normalize(title)
                # 保留播放量更高的
                if key not in index or views > index[key]["views"]:
                    index[key] = {
                        "video_id": vid,
                        "views": views,
                        "channel": ch_name,
                        "language": lang,
                        "title": title,
                    }
    return index


def match_title(title: str, comp_index: dict) -> dict | None:
    """在竞品索引中匹配标题"""
    key = normalize(title)
    # 精确匹配
    if key in comp_index:
        return comp_index[key]
    # 前60字符匹配
    for k, v in comp_index.items():
        if key[:60] == k[:60]:
            return v
    # 前40字符匹配
    for k, v in comp_index.items():
        if key[:40] == k[:40]:
            return v
    return None


def main():
    rec.load_config()
    if not rec.API_KEY:
        print("❌ 未找到 API Key")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 加载竞品索引
    print("📊 加载竞品索引...")
    comp_index = build_competitor_index()
    print(f"   索引: {len(comp_index)} 条\n")

    # 加载蒸馏封面
    all_covers = []
    for lang_dir in DISTILL_DIR.iterdir():
        if not lang_dir.is_dir():
            continue
        covers_file = lang_dir / "covers.json"
        if not covers_file.exists():
            continue
        with open(covers_file) as f:
            covers = json.load(f)
        lang_name = lang_dir.name
        for c in covers:
            c["_distill_lang"] = lang_name
        all_covers.extend(covers)
        print(f"  {lang_name}: {len(covers)} 条")

    print(f"\n📋 蒸馏封面总计: {len(all_covers)} 条")

    # 匹配video_id
    matched = []
    unmatched = 0
    for c in all_covers:
        title = c.get("_meta", {}).get("title", "")
        hit = match_title(title, comp_index)
        if hit:
            matched.append({
                "distill": c,
                "video_id": hit["video_id"],
                "title": title,
                "views": c.get("_meta", {}).get("views", 0),
                "language": c.get("_distill_lang", hit.get("language", "")),
                "channel": hit.get("channel", ""),
            })
        else:
            unmatched += 1

    print(f"✅ 匹配成功: {len(matched)}")
    print(f"❌ 未匹配: {unmatched}")

    # 按播放量排序
    matched.sort(key=lambda x: x["views"], reverse=True)

    # 断点续跑
    done_ids = set()
    existing = []
    if OUTPUT_FILE.exists():
        with open(OUTPUT_FILE) as f:
            existing = json.load(f)
        done_ids = {r["video_id"] for r in existing if "chatgpt_prompt" in r.get("reverse_engineered", {})}
        print(f"\n📌 已完成: {len(done_ids)} 条")

    results = list(existing)
    todo = [m for m in matched if m["video_id"] not in done_ids]
    print(f"🔄 本次待处理: {len(todo)} 条")
    print(f"⏱️  预计: {len(todo) * (DELAY + 12) // 60} 分钟\n")

    for i, m in enumerate(todo):
        vid_id = m["video_id"]
        title = m["title"]
        views = m["views"]
        lang = m["language"]

        print(f"[{i+1}/{len(todo)}] [{lang}] {title[:55]} ({views:,})")

        img_b64 = rec.fetch_thumbnail(vid_id)
        if not img_b64:
            print("  ❌ 下载失败")
            results.append({**m, "error": "下载失败"})
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            continue

        result = rec.reverse_engineer_prompt(img_b64, title=title, views=views)

        if "error" in result:
            print(f"  ❌ {result['error'][:60]}")
            results.append({**m, "error": result["error"]})
        else:
            prompt = result.get("chatgpt_prompt", "")
            print(f"  ✅ {len(prompt)}字 | {prompt[:80]}...")
            results.append({
                "video_id": vid_id,
                "title": title,
                "views": views,
                "language": lang,
                "channel": m.get("channel", ""),
                "reverse_engineered": result,
                "_distill_analysis": {
                    "人物": m["distill"].get("人物", "")[:100],
                    "色彩": m["distill"].get("色彩", "")[:60],
                },
            })

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        if i < len(todo) - 1:
            time.sleep(DELAY)

    # 统计
    success = [r for r in results if "chatgpt_prompt" in r.get("reverse_engineered", {})]
    print(f"\n{'='*60}")
    print(f"✅ 完成! 总{len(results)} | 成功{len(success)} | 失败{len(results)-len(success)}")
    print(f"📁 {OUTPUT_FILE}")

    lang_stats = {}
    for r in success:
        l = r.get("language", "?")
        lang_stats[l] = lang_stats.get(l, 0) + 1
    print("\n📊 按语言:")
    for l, c in sorted(lang_stats.items(), key=lambda x: -x[1]):
        print(f"  {l}: {c}")


if __name__ == "__main__":
    main()
