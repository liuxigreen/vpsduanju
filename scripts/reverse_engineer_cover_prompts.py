#!/usr/bin/env python3
"""
封面反推提示词脚本 — 从竞品封面逆向生成ChatGPT生图prompt

流程：
1. 从YouTube获取封面缩略图
2. 发送给vision模型（MiMo-v2.5）
3. Vision模型分析画面并反推ChatGPT生图prompt
4. 输出结构化JSON

用法：
    python scripts/reverse_engineer_cover_prompts.py --top 20
    python scripts/reverse_engineer_cover_prompts.py --video-id e1gbY6wrZy0
    python scripts/reverse_engineer_cover_prompts.py --lang id --top 10
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ============ 配置 ============
OUTPUT_DIR = ROOT / "data" / "reverse_engineered_covers"
COMPETITOR_DATA = ROOT / "data" / "competitor_data" / "latest.json"
DISTILL_DIR = ROOT / "distill" / "evidence"

LANG_MAP = {
    "id": "印尼", "en": "英文", "es": "西语", "jp": "日语",
    "pt": "葡萄牙", "tr": "土耳其", "zh-tw": "繁中",
}

API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
MODEL = "mimo-v2.5"

# ============ API Key ============
API_KEY = None

def load_config():
    global API_KEY
    API_KEY = os.environ.get("XIAOMICODING_API_KEY", "")
    if not API_KEY:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if "XIAOMICODING_API_KEY" in line:
                    API_KEY = line.split("=", 1)[1].strip()
                    break

# ============ 封面下载 ============
def fetch_thumbnail(video_id: str) -> str | None:
    """下载YouTube封面缩略图，返回base64"""
    # 尝试多种分辨率
    urls = [
        f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/sddefault.jpg",
        f"https://img.youtube.com/vi/{video_id}/hqdefault.jpg",
    ]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as r:
                data = r.read()
                if len(data) > 5000:  # 跳过空白占位图
                    return base64.b64encode(data).decode()
        except Exception:
            continue
    return None

# ============ Vision分析 ============

REVERSE_PROMPT = """你是一个专业的AI图像生成提示词工程师。分析这张YouTube短剧封面图片，然后写出一条能在ChatGPT（DALL-E 3）中复刻这张封面的英文提示词。

## 分析要求

先在脑中分析：
1. **场景**：什么环境？室内/室外？什么时代/风格？
2. **人物**：几个人？什么外貌/服装/表情/姿态？站位关系？
3. **色彩**：主色调？冷暖？对比方式？
4. **光影**：光源方向？戏剧性？逆光/侧光/顶光？
5. **道具**：有什么关键物品？象征什么？
6. **构图**：人物占画面比例？留白位置？视角高低？
7. **情绪**：传达什么情绪？紧张/甜蜜/愤怒/震撼？
8. **文字**：画面中有什么文字？位置和风格？

## 输出要求

输出严格JSON，两个字段：

```json
{{
  "analysis": {{
    "scene": "场景描述（2-3句）",
    "characters": "人物描述（2-3句）",
    "colors": "色彩描述（1-2句）",
    "lighting": "光影描述（1-2句）",
    "props": "道具描述（1-2句）",
    "composition": "构图描述（1-2句）",
    "emotion": "情绪描述（1句）",
    "text_overlay": "画面文字（如有）"
  }},
  "chatgpt_prompt": "完整的ChatGPT英文生图提示词（80-150词），可直接粘贴到ChatGPT生成类似封面。要求：\n1. 自然语言描述，不要关键词堆叠\n2. 包含场景+人物+服装+表情+姿态+色彩+光影+构图\n3. 指定16:9 landscape, 1280x720\n4. 末尾加 CONSTRAINTS: NO text, NO Chinese characters, NO gibberish in image\n5. 指定 photorealistic, cinematic, thumbnail-friendly"
}}
```

## ChatGPT提示词质量标准

- ✅ 用自然语言描述一个具体画面，不是关键词列表
- ✅ 人物描述要具体：外貌特征、服装细节、表情、肢体语言、站位
- ✅ 色彩用具体描述（warm golden light, cold blue shadows）不用HEX
- ✅ 光影要有方向感（rim light from behind, side lighting）
- ✅ 构图要说明人物在画面中的位置（center, left third, lower half）
- ❌ 不要写"60% center-low"这种像素级指令，ChatGPT不认
- ❌ 不要超过150词，太长ChatGPT会忽略后面的内容
- ❌ 不要用电影术语（chiaroscuro, mise-en-scène），用 plain English"""


def reverse_engineer_prompt(image_b64: str, title: str = "", views: int = 0) -> dict:
    """用vision模型反推ChatGPT生图prompt"""
    context = ""
    if title:
        context = f"\n\n视频标题：{title}"
    if views:
        context += f"\n播放量：{views:,}"

    full_prompt = REVERSE_PROMPT + context

    data = {
        "model": MODEL,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": full_prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]}],
        "max_tokens": 3000,
        "temperature": 0.3,
    }

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {API_KEY}"}
    req = urllib.request.Request(API_URL, data=json.dumps(data).encode(), headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read().decode())

        content = result["choices"][0]["message"]["content"]
        usage = result.get("usage", {})

        # 解析JSON
        clean = re.sub(r'```(?:json)?\s*', '', content)
        clean = re.sub(r'\s*```', '', clean).strip()
        start = clean.find('{')
        if start == -1:
            return {"error": "无JSON", "raw": content[:500]}

        # 找到匹配的闭合括号
        depth = 0
        end = start
        for i, c in enumerate(clean[start:], start):
            if c == '{': depth += 1
            elif c == '}': depth -= 1
            if depth == 0:
                end = i + 1
                break

        parsed = json.loads(clean[start:end])
        parsed["_usage"] = usage
        return parsed

    except Exception as e:
        return {"error": str(e)}


# ============ 数据源 ============

def get_videos_from_competitor_data(lang: str = None, top_n: int = 20) -> list[dict]:
    """从竞品数据中获取高播放视频"""
    if not COMPETITOR_DATA.exists():
        return []

    with open(COMPETITOR_DATA) as f:
        data = json.load(f)

    videos = []
    for ch in data:
        ch_lang = ch.get("language", "")
        if lang and ch_lang != lang:
            continue
        for v in ch.get("videos", []):
            vid_id = v.get("video_id", v.get("id", ""))
            if vid_id:
                videos.append({
                    "video_id": vid_id,
                    "title": v.get("title", ""),
                    "views": v.get("view_count", 0),
                    "channel": ch.get("name", ""),
                    "language": ch_lang,
                })

    # 按播放量排序，取top
    videos.sort(key=lambda x: x["views"], reverse=True)
    return videos[:top_n]


def get_videos_from_distill(lang: str, top_n: int = 20) -> list[dict]:
    """从蒸馏数据中获取高播放视频（有封面分析的）"""
    lang_dir = LANG_MAP.get(lang, lang)
    covers_file = DISTILL_DIR / lang_dir / "covers.json"
    if not covers_file.exists():
        return []

    with open(covers_file) as f:
        covers = json.load(f)

    videos = []
    for c in covers:
        meta = c.get("_meta", {})
        title = meta.get("title", "")
        views = meta.get("views", 0)
        # 从标题推断video_id（蒸馏数据可能不含ID）
        videos.append({
            "video_id": "",  # 蒸馏数据没有video_id
            "title": title,
            "views": views,
            "channel": "",
            "language": lang,
            "_has_analysis": True,
            "_analysis": c,
        })

    videos.sort(key=lambda x: x["views"], reverse=True)
    return videos[:top_n]


# ============ 主流程 ============

def main():
    parser = argparse.ArgumentParser(description="封面反推ChatGPT生图prompt")
    parser.add_argument("--video-id", help="单个视频ID")
    parser.add_argument("--lang", help="语言: id/en/es/jp/pt/tr/zh-tw")
    parser.add_argument("--top", type=int, default=20, help="处理前N个高播放视频")
    parser.add_argument("--dry-run", action="store_true", help="只列出视频，不调API")
    args = parser.parse_args()

    load_config()
    if not API_KEY:
        print("❌ 未找到 XIAOMICODING_API_KEY")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 确定视频列表
    if args.video_id:
        videos = [{"video_id": args.video_id, "title": "", "views": 0, "channel": "", "language": ""}]
    else:
        videos = get_videos_from_competitor_data(lang=args.lang, top_n=args.top)
        if not videos:
            print("⚠️ 竞品数据中无视频，尝试蒸馏数据...")
            if args.lang:
                videos = get_videos_from_distill(args.lang, top_n=args.top)
            if not videos:
                print("❌ 无可用视频数据")
                sys.exit(1)

    print(f"📋 待处理: {len(videos)} 个视频")

    if args.dry_run:
        for i, v in enumerate(videos):
            print(f"  {i+1}. [{v['views']:>10,}] {v['video_id'] or '(无ID)'} | {v['title'][:60]}")
        return

    # 逐个处理
    results = []
    for i, v in enumerate(videos):
        vid_id = v["video_id"]
        title = v["title"]
        views = v["views"]

        print(f"\n{'='*60}")
        print(f"[{i+1}/{len(videos)}] {title[:60]}")
        print(f"  播放: {views:,} | ID: {vid_id or '(无)'}")

        if not vid_id:
            print("  ⚠️ 无视频ID，跳过（蒸馏数据需要先补充video_id）")
            continue

        # 下载封面
        print("  📥 下载封面...")
        img_b64 = fetch_thumbnail(vid_id)
        if not img_b64:
            print("  ❌ 下载失败")
            continue

        # 反推prompt
        print("  🧠 Vision分析+反推prompt...")
        result = reverse_engineer_prompt(img_b64, title=title, views=views)

        if "error" in result:
            print(f"  ❌ 分析失败: {result['error']}")
            results.append({"video_id": vid_id, "title": title, "views": views, "error": result["error"]})
        else:
            prompt = result.get("chatgpt_prompt", "")
            print(f"  ✅ 反推完成 ({len(prompt)} 字符)")
            print(f"  📝 Prompt预览: {prompt[:100]}...")
            results.append({
                "video_id": vid_id,
                "title": title,
                "views": views,
                "channel": v.get("channel", ""),
                "language": v.get("language", ""),
                "reverse_engineered": result,
            })

        # 保存中间结果（每条都存）
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        lang_suffix = f"_{args.lang}" if args.lang else ""
        output_file = OUTPUT_DIR / f"covers_reversed{lang_suffix}_{timestamp}.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

        # 速率控制
        if i < len(videos) - 1:
            print("  ⏳ 等待5秒...")
            time.sleep(5)

    # 最终输出
    print(f"\n{'='*60}")
    print(f"✅ 完成! {len(results)} 条结果")
    print(f"📁 输出: {output_file}")

    # 统计
    success = [r for r in results if "chatgpt_prompt" in r.get("reverse_engineered", {})]
    print(f"📊 成功: {len(success)}/{len(results)}")

    if success:
        print(f"\n🎯 Top 3 反推prompt:")
        for r in sorted(success, key=lambda x: x["views"], reverse=True)[:3]:
            prompt = r["reverse_engineered"]["chatgpt_prompt"]
            print(f"\n  [{r['views']:,}] {r['title'][:50]}")
            print(f"  {prompt[:200]}...")


if __name__ == "__main__":
    main()
