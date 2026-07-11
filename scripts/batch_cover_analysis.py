#!/usr/bin/env python3
"""
批量封面分析 — 11字段版，存入蒸馏证据库

用法：
  python3 scripts/batch_cover_analysis.py              # 全量
  python3 scripts/batch_cover_analysis.py --lang 英文   # 指定语种
  python3 scripts/batch_cover_analysis.py --max 5       # 每地区最多5个
"""

import json
import sys
import time
import re
import base64
import urllib.request
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# 统一封面分析prompt母本路径
COVER_PROMPT_PATH = ROOT / "references" / "cover-analysis-prompt.md"

DATA_DIR = ROOT / "data"
EVIDENCE_DIR = ROOT / "distill" / "evidence"
OUTPUT_DIR = ROOT / "output" / "cover_analysis"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ─── MiMo API ───
MIMO_API_KEY = None

def load_config():
    global MIMO_API_KEY
    import os
    MIMO_API_KEY = os.environ.get("XIAOMI_API_KEY", "") or os.environ.get("XIAOMICODING_API_KEY", "")
    if not MIMO_API_KEY:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if "XIAOMI_API_KEY" in line or "XIAOMICODING_API_KEY" in line:
                    MIMO_API_KEY = line.split("=", 1)[1].strip()
                    break

def encode_image(url: str):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return base64.b64encode(r.read()).decode()
    except Exception as e:
        print(f"    ⚠️ 下载封面失败: {e}")
        return None

def analyze_cover(image_url: str, title: str, views: int) -> dict:
    """统一封面分析（从母本读取prompt）"""
    img_b64 = encode_image(image_url)
    if not img_b64:
        return {"error": "下载失败"}

    # 从统一母本加载prompt模板
    _prompt_template = None
    if COVER_PROMPT_PATH.exists():
        raw = COVER_PROMPT_PATH.read_text(encoding="utf-8")
        s = raw.find("```")
        if s != -1:
            e = raw.find("```", s + 3)
            _prompt_template = raw[s + 3:e].strip() if e != -1 else raw[s + 3:].strip()

    if _prompt_template:
        prompt = _prompt_template.replace("{title}", title[:80]).replace("{views}", "{:,}".format(views))
    else:
        prompt = f"""分析这个YouTube短剧封面。返回JSON，每个字段2-3句话，总输出控制在500字以内。

标题：{title[:80]}
播放量：{views:,}

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
  "爆款因素": {{"评分": "0-10", "来源": "核心吸引力来源", "改进建议": "可优化的地方"}}
}}"""

    data = {
        "model": "mimo-v2.5",
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"}}
        ]}],
        "max_tokens": 4000,
        "temperature": 0.3
    }

    try:
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {MIMO_API_KEY}"}
        url = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"
        req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read().decode())

        content = result["choices"][0]["message"]["content"]
        finish = result["choices"][0].get("finish_reason", "unknown")
        usage = result.get("usage", {})

        # 解析JSON
        clean = re.sub(r'```(?:json)?\s*', '', content)
        clean = re.sub(r'\s*```', '', clean).strip()
        start = clean.find('{')
        if start == -1:
            return {"error": "无JSON", "raw": content[:200]}

        depth = 0
        end = -1
        for i in range(start, len(clean)):
            if clean[i] == '{': depth += 1
            elif clean[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end == -1:
            # 截断补全
            partial = clean[start:]
            for closes in range(1, 10):
                try:
                    analysis = json.loads(partial + '}' * closes)
                    break
                except json.JSONDecodeError:
                    continue
            else:
                return {"error": "JSON截断", "raw": content[:300]}
        else:
            analysis = json.loads(clean[start:end + 1])

        analysis["_meta"] = {
            "image_url": image_url,
            "title": title[:80],
            "views": views,
            "finish_reason": finish,
            "tokens": usage.get("completion_tokens", 0),
        }
        return analysis

    except Exception as e:
        return {"error": f"API异常: {e}"}


def load_videos(min_views: int = 10000) -> dict:
    """从 latest.json 加载视频，按地区分组"""
    data_file = DATA_DIR / "competitor_data" / "latest.json"
    if not data_file.exists():
        print("❌ latest.json 不存在")
        return {}

    data = json.load(open(data_file))
    channels = data if isinstance(data, list) else data.get("channels", [])

    by_lang = defaultdict(list)
    for ch in channels:
        lang = ch.get("language", "未知")
        if lang == "zh-CN":
            continue  # 跳过 zh-CN
        vids = ch.get("videos", [])
        for v in vids:
            views = v.get("views", v.get("view_count", 0))
            thumb = v.get("thumbnail", "")
            if views >= min_views and thumb:
                by_lang[lang].append({
                    "title": v.get("title", ""),
                    "views": views,
                    "thumbnail": thumb,
                    "channel": ch.get("name", ""),
                })

    # 按播放量排序
    for lang in by_lang:
        by_lang[lang].sort(key=lambda x: x["views"], reverse=True)

    return dict(by_lang)


def run(lang_filter: str = None, max_per_region: int = 20):
    load_config()
    if not MIMO_API_KEY:
        print("❌ 未配置 XIAOMI_API_KEY")
        return

    videos_by_lang = load_videos(min_views=10000)
    if not videos_by_lang:
        print("❌ 无数据")
        return

    langs = [lang_filter] if lang_filter else sorted(videos_by_lang.keys())
    print(f"🎬 批量封面分析 — {len(langs)}个地区, 每地区最多{max_per_region}个")
    print(f"{'='*60}")

    total_tokens = 0
    total_success = 0
    total_error = 0

    for lang in langs:
        videos = videos_by_lang.get(lang, [])[:max_per_region]
        if not videos:
            print(f"\n⏭️ {lang} — 无数据")
            continue

        print(f"\n🌍 {lang} ({len(videos)}个封面)")
        lang_dir = EVIDENCE_DIR / lang
        lang_dir.mkdir(parents=True, exist_ok=True)

        results = []
        for i, v in enumerate(videos):
            print(f"  [{i+1}/{len(videos)}] {v['title'][:40]} ({v['views']:,}播放)...", end="", flush=True)

            analysis = analyze_cover(v["thumbnail"], v["title"], v["views"])

            if "error" in analysis:
                print(f" ❌ {analysis['error']}")
                total_error += 1
            else:
                tokens = analysis.get("_meta", {}).get("tokens", 0)
                total_tokens += tokens
                total_success += 1
                print(f" ✅ {tokens}tokens")

            results.append(analysis)
            time.sleep(1)  # 限速

        # 保存到蒸馏证据库
        covers_file = lang_dir / "covers.json"
        covers_file.write_text(json.dumps(results, indent=2, ensure_ascii=False))
        print(f"  📁 → {covers_file}")

        # 保存到 output（带模式统计）
        patterns = extract_patterns(results)
        output_file = OUTPUT_DIR / f"cover_patterns_{lang}.json"
        output_file.write_text(json.dumps({
            "samples": len(results),
            "patterns": patterns,
            "analyses": results,
        }, indent=2, ensure_ascii=False))

    print(f"\n{'='*60}")
    print(f"✅ 完成: {total_success}成功, {total_error}失败, {total_tokens:,}tokens")


def extract_patterns(results: list) -> dict:
    """从分析结果提取模式统计"""
    valid = [r for r in results if "error" not in r]
    if not valid:
        return {}

    # 人物分布
    person_types = defaultdict(int)
    for r in valid:
        p = r.get("人物", "")
        if isinstance(p, str):
            if "双人" in p or "一男一女" in p:
                person_types["双人"] += 1
            elif "单人" in p:
                person_types["单人"] += 1
            elif "多人" in p:
                person_types["多人"] += 1
            else:
                person_types["其他"] += 1

    # 色彩情绪
    color_mood = defaultdict(int)
    for r in valid:
        c = r.get("色彩", "")
        if isinstance(c, str):
            if "暖" in c:
                color_mood["暖色调"] += 1
            elif "冷" in c:
                color_mood["冷色调"] += 1
            else:
                color_mood["中性"] += 1

    # 爆款评分
    scores = []
    for r in valid:
        f = r.get("爆款因素", {})
        if isinstance(f, dict):
            try:
                scores.append(int(f.get("评分", 0)))
            except:
                pass

    return {
        "样本数": len(valid),
        "人物分布": dict(person_types),
        "色彩情绪": dict(color_mood),
        "平均爆款评分": round(sum(scores) / len(scores), 1) if scores else 0,
        "评分分布": {str(s): scores.count(s) for s in sorted(set(scores))} if scores else {},
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", type=str)
    parser.add_argument("--max", type=int, default=20)
    args = parser.parse_args()
    run(lang_filter=args.lang, max_per_region=args.max)
