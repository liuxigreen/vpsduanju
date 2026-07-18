#!/usr/bin/env python3
"""
批量反推封面prompt — 按语言分批，合并输出

输出：data/reverse_engineered_covers/all_reversed_prompts.json
格式：每个prompt可直接作为few-shot example给封面生产agent用
"""
import json
import sys
import time
from datetime import datetime
from pathlib import Path

# 复用单条脚本的功能
sys.path.insert(0, str(Path(__file__).parent))
import reverse_engineer_cover_prompts as rec
from reverse_engineer_cover_prompts import (
    fetch_thumbnail, reverse_engineer_prompt,
    get_videos_from_competitor_data, OUTPUT_DIR
)

TOP_PER_LANG = 30
LANGUAGES = ["印尼", "英文", "西语", "日语", "葡萄牙", "土耳其", "繁中"]
DELAY = 6  # 秒

def main():
    rec.load_config()
    if not rec.API_KEY:
        print("❌ 未找到 API Key")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 收集所有语言的视频
    all_videos = []
    for lang in LANGUAGES:
        videos = get_videos_from_competitor_data(lang=lang, top_n=TOP_PER_LANG)
        print(f"  {lang}: {len(videos)} 条")
        all_videos.extend(videos)

    print(f"\n📋 总计: {len(all_videos)} 条待处理")
    print(f"⏱️  预计耗时: {len(all_videos) * (DELAY + 10) // 60} 分钟\n")

    # 检查已有结果（断点续跑）
    merged_file = OUTPUT_DIR / "all_reversed_prompts.json"
    done_ids = set()
    existing = []
    if merged_file.exists():
        with open(merged_file) as f:
            existing = json.load(f)
        done_ids = {r["video_id"] for r in existing if "chatgpt_prompt" in r.get("reverse_engineered", {})}
        print(f"📌 已完成: {len(done_ids)} 条，跳过\n")

    results = list(existing)
    todo = [v for v in all_videos if v["video_id"] not in done_ids]
    print(f"🔄 本次待处理: {len(todo)} 条\n")

    for i, v in enumerate(todo):
        vid_id = v["video_id"]
        title = v["title"]
        views = v["views"]
        lang = v.get("language", "")

        print(f"[{i+1}/{len(todo)}] [{lang}] {title[:55]} ({views:,})")

        # 下载封面
        img_b64 = fetch_thumbnail(vid_id)
        if not img_b64:
            print("  ❌ 下载失败")
            results.append({"video_id": vid_id, "title": title, "views": views, "language": lang, "error": "下载失败"})
            continue

        # 反推
        result = reverse_engineer_prompt(img_b64, title=title, views=views)

        if "error" in result:
            print(f"  ❌ {result['error'][:50]}")
            results.append({"video_id": vid_id, "title": title, "views": views, "language": lang, "error": result["error"]})
        else:
            prompt = result.get("chatgpt_prompt", "")
            print(f"  ✅ {len(prompt)}字符 | {prompt[:80]}...")
            results.append({
                "video_id": vid_id,
                "title": title,
                "views": views,
                "language": lang,
                "channel": v.get("channel", ""),
                "reverse_engineered": result,
            })

        # 每条都存（防中断丢失）
        with open(merged_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        if i < len(todo) - 1:
            time.sleep(DELAY)

    # 统计
    success = [r for r in results if "chatgpt_prompt" in r.get("reverse_engineered", {})]
    failed = [r for r in results if "error" in r]

    print(f"\n{'='*60}")
    print(f"✅ 完成! 总{len(results)}条 | 成功{len(success)} | 失败{len(failed)}")
    print(f"📁 {merged_file}")

    # 按语言统计
    lang_stats = {}
    for r in success:
        l = r.get("language", "?")
        lang_stats[l] = lang_stats.get(l, 0) + 1
    print(f"\n📊 按语言:")
    for l, c in sorted(lang_stats.items(), key=lambda x: -x[1]):
        print(f"  {l}: {c}")

    # 输出精选prompt（每语言top3）
    print(f"\n🎯 每语言Top3 Prompt预览:")
    for lang in LANGUAGES:
        lang_items = sorted(
            [r for r in success if r.get("language") == lang],
            key=lambda x: x["views"], reverse=True
        )[:3]
        if lang_items:
            print(f"\n  === {lang} ===")
            for r in lang_items:
                p = r["reverse_engineered"]["chatgpt_prompt"]
                print(f"  [{r['views']:>8,}] {p[:120]}...")


if __name__ == "__main__":
    main()
