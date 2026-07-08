#!/usr/bin/env python3
"""
自有频道封面分析 — 按skill封面指南维度分析，存入channel_diagnosis

用法：
  python3 scripts/cover_analysis_own.py --channel Apocalyptic_Films
  python3 scripts/cover_analysis_own.py --all
"""
import json
import os
import re
import sys
import time
import base64
import urllib.request
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

DATA_DIR = ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "own" / "channel_snapshots"
DIAGNOSIS_DIR = DATA_DIR / "own" / "channel_diagnosis"


def _atomic_write_json(path: Path, data: dict, indent: int = 2, ensure_ascii: bool = False) -> None:
    """原子写 JSON：写 .tmp → fsync → os.replace。避免 panel 读到截断 JSON。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    payload = json.dumps(data, ensure_ascii=ensure_ascii, indent=indent)
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(payload)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    os.replace(tmp, path)

# 豆包ARK视觉模型（走 Hermes 主用的 custom:doubao 通道：plan/v3 + ark-code-latest auto路由）
MIMO_API_URL = "https://token-plan-cn.xiaomimimo.com/v1/chat/completions"  # 保留旧配置
DOUBARK_API_URL = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
DOUBARK_MODEL = "ark-code-latest"
DOUBARK_API_KEY = ""
USE_VISION_MODEL = "doubao"  # "mimo" or "doubao"


def _read_key_from_hermes_config():
    """从 ~/.hermes/config.yaml 的 custom_providers[doubao].api_key 读 key"""
    cfg = Path.home() / ".hermes" / "config.yaml"
    if not cfg.exists():
        return ""
    # 轻量正则解析，避免依赖 yaml
    in_doubao_block = False
    for line in cfg.read_text(encoding="utf-8").splitlines():
        s = line.rstrip()
        if s == "- name: doubao":
            in_doubao_block = True
            continue
        if in_doubao_block:
            if s.startswith("- name:"):  # 进入下一个 provider 了
                break
            m = re.match(r"\s+api_key:\s*(\S+)", s)
            if m:
                return m.group(1).strip().strip('"').strip("'")
    return ""


def load_config():
    global MIMO_API_KEY
    global DOUBARK_API_KEY
    MIMO_API_KEY = os.environ.get("XIAOMI_API_KEY", "")
    if not MIMO_API_KEY:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if "XIAOMI_API_KEY" in line and "=" in line:
                    MIMO_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    # Load Doubao ARK key — 走 Hermes custom_providers[doubao] 通道
    # 优先 env var，然后 hermes config.yaml，最后 ARKCODE_API_KEY 兜底
    DOUBARK_API_KEY = os.environ.get("DOUBAO_API_KEY", "") or os.environ.get("ARK_INFERENCE_KEY", "")
    if not DOUBARK_API_KEY:
        DOUBARK_API_KEY = _read_key_from_hermes_config()
    if not DOUBARK_API_KEY:
        # 兜底：~/.hermes/.env 的 ARKCODE_API_KEY（同一把 key，但更容易过期，最不优先）
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if "ARKCODE_API_KEY" in line and "=" in line:
                    DOUBARK_API_KEY = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break


def encode_image(url):
    # type: (str) -> Optional[str]
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return base64.b64encode(r.read()).decode()
    except Exception as e:
        print("    ⚠️ 下载封面失败: {}".format(e))
        return None


def analyze_cover(image_url, title, views):
    # type: (str, str, int) -> dict
    """按skill封面指南的6个维度分析"""
    img_b64 = encode_image(image_url)
    if not img_b64:
        return {"error": "下载失败"}

    prompt = """分析这个YouTube短剧封面。按以下7个维度打分和分析，每个维度给出评分(0-10)和2-3句分析。

标题：%s
播放量：%d

维度说明（来自短剧封面指南）：
1. **构图** — 布局类型（中心/对比/三角/拼贴）、景别、视角高低、视线引导路径
2. **人物** — 数量、表情、服装符号（西装=CEO/权力、女仆装=低位、礼服=逆袭后）、肢体语言、关系暗示
3. **色彩** — 主色调、辅助色、饱和度、光影效果、情绪氛围（暖金=甜宠豪门、冷蓝=虐恋悬疑、红黑=复仇打脸）
4. **情绪** — 核心情绪基调（tension/romance/power/mystery）、第一眼能否看出冲突/关系/悬念
5. **视觉符号** — 关键道具及其象征意义（戒指/结婚证/豪车/病床/孕肚/离婚协议等）
6. **文字** — 封面文字数量、内容、位置、字体风格、颜色、是否增强悬念（短剧封面文字控制在3-6个词）
7. **封面×标题协同** — 封面和标题是否围绕同一个核心钩子分工协作。判断标准：标题说清身份反差/情节反转/情绪爆点，封面把最有张力的一瞬间视觉化。协同模式：标题给反差封面给证据 / 封面定格高潮标题补前因 / 情绪反转视觉化 / 肢体距离表达关系 / 阶层符号强化爽感。反模式：题材错位 / 只美不钩 / 标题有爆点封面无 / 信息过散 / 情绪不匹配。

输出JSON：
{"构图": {"score": 7, "type": "中心构图", "analysis": "..."},
  "人物": {"score": 6, "count": 2, "clothing": "西装+便装", "emotion": "对峙", "analysis": "..."},
  "色彩": {"score": 8, "main": "冷蓝", "accent": "红色", "mood": "悬疑紧张", "analysis": "..."},
  "情绪": {"score": 7, "base": "tension", "first_impression": "能看出冲突", "analysis": "..."},
  "视觉符号": {"score": 5, "symbols": ["武器", "废墟"], "meaning": "末世生存", "analysis": "..."},
  "文字": {"score": 3, "has_text": false, "count": 0, "analysis": "无封面文字，错失悬念增强机会"},
  "封面×标题协同": {"score": 6, "synergy_pattern": "标题给反差封面给证据", "anti_pattern": "无", "assessment": "封面和标题的协同分析", "improvement": "改进建议"},
  "总分": 6.0,
  "总评": "一句话总评",
  "改进建议": ["建议1", "建议2"]}""" % (title[:80], views)

    if USE_VISION_MODEL == "doubao":
        model = DOUBARK_MODEL
        api_url = DOUBARK_API_URL
        api_key = DOUBARK_API_KEY
    else:  # mimo
        model = "mimo-v2.5"
        api_url = MIMO_API_URL
        api_key = MIMO_API_KEY

    data = {
        "model": model,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,{}".format(img_b64)}}
            ]
        }],
        "max_tokens": 3000,
        "temperature": 0.3
    }

    try:
        headers = {"Content-Type": "application/json", "Authorization": "Bearer {}".format(api_key)}
        req = urllib.request.Request(api_url, data=json.dumps(data).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=120) as r:
            result = json.loads(r.read().decode())

        content = result["choices"][0]["message"]["content"]
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
            if clean[i] == '{':
                depth += 1
            elif clean[i] == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break

        if end == -1:
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
            "tokens": usage.get("completion_tokens", 0),
        }
        return analysis
    except Exception as e:
        return {"error": "API异常: {}".format(e)}


def run_channel(channel_name, max_videos=0):
    # type: (str, int) -> Optional[dict]
    """分析一个频道的封面"""
    slug = channel_name.replace(" ", "_")
    snap_path = SNAPSHOT_DIR / "{}_latest.json".format(slug)
    if not snap_path.exists():
        print("❌ 无快照: {}".format(channel_name))
        return None

    snap = json.loads(snap_path.read_text())
    videos = snap.get("videos", [])
    if not videos:
        print("❌ 无视频: {}".format(channel_name))
        return None

    # 按播放量排序，取top N（0=全部）
    sorted_vids = sorted(videos, key=lambda x: x.get("views", 0), reverse=True)
    if max_videos > 0:
        sorted_vids = sorted_vids[:max_videos]
    print("\n" + "=" * 50)
    print("🎨 封面分析: {} ({}条视频)".format(channel_name, len(sorted_vids)))
    print("=" * 50)

    results = []
    total_tokens = 0
    for i, v in enumerate(sorted_vids):
        thumb = v.get("thumbnail", "")
        title = v.get("title", "")
        views = v.get("views", 0)
        vid = v.get("video_id", "")

        if not thumb:
            print("  [{}] {}... ❌ 无封面URL".format(i + 1, title[:40]))
            results.append({"video_id": vid, "error": "无封面URL"})
            continue

        print("  [{}/{}] {}... ({}播放)".format(i + 1, len(sorted_vids), title[:40], views), end="", flush=True)
        analysis = analyze_cover(thumb, title, views)

        if "error" in analysis:
            print(" ❌ {}".format(analysis["error"]))
            results.append({"video_id": vid, "video_title": title[:80], "views": views, "error": analysis["error"]})
        else:
            tokens = analysis.get("_meta", {}).get("tokens", 0)
            total_tokens += tokens
            score = analysis.get("总分", 0)
            print(" ✅ {}/10 ({}tokens)".format(score, tokens))

            # 转换为diagnose_channel期望的格式
            entry = {
                "video_id": vid,
                "video_title": title[:80],
                "views": views,
                "image_url": thumb,
                "person_score": analysis.get("人物", {}).get("score", 0),
                "person_detail": analysis.get("人物", {}).get("analysis", ""),
                "emotion_score": analysis.get("情绪", {}).get("score", 0),
                "emotion_detail": analysis.get("情绪", {}).get("analysis", ""),
                "prop_score": analysis.get("视觉符号", {}).get("score", 0),
                "prop_detail": analysis.get("视觉符号", {}).get("analysis", ""),
                "color_score": analysis.get("色彩", {}).get("score", 0),
                "color_detail": analysis.get("色彩", {}).get("analysis", ""),
                "text_score": analysis.get("文字", {}).get("score", 0),
                "text_detail": analysis.get("文字", {}).get("analysis", ""),
                "composition_score": analysis.get("构图", {}).get("score", 0),
                "composition_detail": analysis.get("构图", {}).get("analysis", ""),
                "overall_score": analysis.get("总分", 0),
                "suggestions": analysis.get("改进建议", []),
                "封面×标题协同": analysis.get("封面×标题协同", {}),
            }
            results.append(entry)
        time.sleep(2)  # 限速

    # 计算平均分
    valid = [r for r in results if "overall_score" in r and "error" not in r]
    def _avg(key):
        vals = [r[key] for r in valid if r.get(key)]
        return round(sum(vals) / len(vals), 1) if vals else 0

    output = {
        "channel_name": channel_name,
        "analyzed_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "model": DOUBARK_MODEL if USE_VISION_MODEL == "doubao" else "mimo-v2.5",  # P3-8: 动态反映实际调用模型
        "total_videos": len(sorted_vids),
        "analyzed_videos": len(valid),
        "avg_scores": {
            "avg_person_score": _avg("person_score"),
            "avg_emotion_score": _avg("emotion_score"),
            "avg_prop_score": _avg("prop_score"),
            "avg_color_score": _avg("color_score"),
            "avg_text_score": _avg("text_score"),
            "avg_composition_score": _avg("composition_score"),
            "avg_overall_score": _avg("overall_score"),
        },
        "top_suggestions": [],
        "details": results,
    }

    # 汇总建议
    all_suggestions = []
    for r in valid:
        for s in r.get("suggestions", []):
            if s and s not in all_suggestions:
                all_suggestions.append(s)
    output["top_suggestions"] = all_suggestions[:5]

    # 保存到channel_diagnosis
    out_path = DIAGNOSIS_DIR / "{}_covers.json".format(slug)
    # P1-3: 原子写，避免 panel 读到截断 JSON
    _atomic_write_json(out_path, output)
    print("\n  📁 → {}".format(out_path))
    print("  📊 平均封面分: {}/10 | 总tokens: {}".format(output["avg_scores"]["avg_overall_score"], total_tokens))

    return output


def main():
    import argparse
    parser = argparse.ArgumentParser(description="自有频道封面分析")
    parser.add_argument("--channel", help="频道名称")
    parser.add_argument("--all", action="store_true", help="所有频道")
    parser.add_argument("--max", type=int, default=0, help="每频道最多分析几条(0=全部)")
    args = parser.parse_args()

    load_config()
    if USE_VISION_MODEL == "doubao":
        if not DOUBARK_API_KEY:
            print("❌ 未配置 ARKCODE_API_KEY (doubao)")
            sys.exit(1)
    else:
        if not MIMO_API_KEY:
            print("❌ 未配置 XIAOMI_API_KEY (mimo)")
            sys.exit(1)

    if args.channel:
        run_channel(args.channel.replace("_", " "), args.max)
    elif args.all:
        registry_path = DATA_DIR / "our_channels.json"
        if registry_path.exists():
            reg = json.loads(registry_path.read_text())
            for ch in reg.get("channels", []):
                name = ch.get("name", "")
                if name:
                    run_channel(name, args.max)
                    time.sleep(3)
    else:
        print("用法: --channel 频道名 或 --all")


if __name__ == "__main__":
    main()
