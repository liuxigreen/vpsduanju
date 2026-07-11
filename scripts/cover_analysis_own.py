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

# 统一封面分析prompt母本路径
COVER_PROMPT_PATH = ROOT / "references" / "cover-analysis-prompt.md"

DATA_DIR = ROOT / "data"
SNAPSHOT_DIR = DATA_DIR / "own" / "channel_snapshots"
DIAGNOSIS_DIR = DATA_DIR / "own" / "channel_diagnosis"


def _load_cover_prompt_template(mode: str = "diagnosis") -> str:
    """从统一母本加载封面分析prompt模板
    
    mode: "diagnosis" = 诊断prompt（自有频道打分）
          "distill" = 蒸馏prompt（竞品提取规律）
    """
    if not COVER_PROMPT_PATH.exists():
        # fallback
        return """分析这个YouTube短剧封面。按以下7个维度打分和分析，每个维度给出评分(0-10)和2-3句分析。

标题：{title}
播放量：{views}

1. **构图** — 布局类型、景别、视角、视线引导
2. **人物** — 数量、表情、服装、肢体语言、关系暗示
3. **色彩** — 主色调、辅助色、光影、情绪氛围
4. **情绪** — 核心情绪基调、第一眼能否看出冲突
5. **视觉符号** — 关键道具及象征意义
6. **文字** — 文字内容、位置、风格
7. **封面×标题协同** — 封面和标题是否围绕同一钩子分工

输出JSON：
{{"构图": {{"score": 7, "analysis": "..."}}, "人物": {{"score": 6, "analysis": "..."}}, "色彩": {{"score": 8, "analysis": "..."}}, "情绪": {{"score": 7, "analysis": "..."}}, "视觉符号": {{"score": 5, "analysis": "..."}}, "文字": {{"score": 3, "analysis": "..."}}, "封面×标题协同": {{"score": 6, "analysis": "..."}}, "总分": 6.0, "总评": "...", "改进建议": ["建议1", "建议2"]}}"""

    raw = COVER_PROMPT_PATH.read_text(encoding="utf-8")
    # 按行查找section header（必须是行首的## 标题）
    section_name = "蒸馏prompt" if mode == "distill" else "诊断prompt"
    header_pos = -1
    for i, line in enumerate(raw.split("\n")):
        if line.strip() == f"## {section_name}":
            header_pos = sum(len(l) + 1 for l in raw.split("\n")[:i])
            break
    
    if header_pos == -1:
        # 没找到，fallback到第一个code block
        start = raw.find("```")
    else:
        start = raw.find("```", header_pos)
    
    if start == -1:
        return raw
    end = raw.find("```", start + 3)
    if end == -1:
        return raw[start + 3:]
    return raw[start + 3:end].strip()


def _convert_to_diagnosis_format(unified: dict, title: str, views: int, image_url: str, tokens: int) -> dict:
    """将统一prompt输出转为diagnose_channel.py期望的诊断格式（向后兼容）
    
    兼容三种LLM输出格式：
    - 新格式: {"构图评分": {"score": 8, "analysis": "..."}, "结构化": {...}}
    - 旧嵌套: {"构图": {"score": 8, "analysis": "..."}, ...}
    - 旧扁平: {"person_score": 8, "person_detail": "...", ...}
    """
    dim_map = [
        ("构图评分", "构图", "composition_score"),
        ("人物评分", "人物", "person_score"),
        ("色彩评分", "色彩", "color_score"),
        ("情绪评分", "情绪", "emotion_score"),
        ("视觉符号评分", "视觉符号", "prop_score"),
        ("文字评分", "文字", "text_score"),
        ("封面标题协同评分", "封面×标题协同", "synergy_score"),
    ]
    entry = {
        "video_id": "",  # 由调用方填充
        "video_title": title[:80],
        "views": views,
        "image_url": image_url,
    }
    for src_key, nested_key, flat_key in dim_map:
        # 尝试从新格式读（"构图评分"）
        src = unified.get(src_key, {})
        # 如果没有，从旧嵌套格式读（"构图": {"score": ...}）
        if not src or not isinstance(src, dict):
            src = unified.get(nested_key, {})
        if isinstance(src, dict):
            score = src.get("score", 0)
            analysis_text = src.get("analysis", "")
        else:
            score = 0
            analysis_text = ""
        # 也检查旧扁平格式
        if not score and flat_key in unified:
            score = unified[flat_key]
        if not analysis_text and flat_key.replace("_score", "_detail") in unified:
            analysis_text = unified[flat_key.replace("_score", "_detail")]
        entry[nested_key] = {"score": score, "analysis": analysis_text}  # diagnose_channel读嵌套
        entry[flat_key] = score   # run_channel读扁平
        entry[flat_key.replace("_score", "_detail")] = analysis_text

    entry["总分"] = unified.get("总分", unified.get("overall_score", 0))
    entry["overall_score"] = unified.get("总分", unified.get("overall_score", 0))
    entry["总评"] = unified.get("总评", "")
    entry["改进建议"] = unified.get("改进建议", unified.get("suggestions", []))
    entry["suggestions"] = unified.get("改进建议", unified.get("suggestions", []))
    # 共享核心：结构化枚举
    entry["结构化"] = unified.get("结构化", {})
    # 中文描述字段（蒸馏也用）
    for cn_key in ["人物", "道具", "色彩", "构图", "文字", "视觉层级", "题材元素", "封面标题配合", "地区适配", "整体风格"]:
        entry[cn_key + "描述"] = unified.get(cn_key, "")
    entry["_meta"] = {"tokens": tokens, "title": title, "views": views, "image_url": image_url}
    return entry


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
    """统一封面分析：从母本读取prompt，输出诊断兼容格式"""
    img_b64 = encode_image(image_url)
    if not img_b64:
        return {"error": "下载失败"}

    # 从统一母本加载诊断prompt
    prompt_template = _load_cover_prompt_template(mode="diagnosis")
    prompt = prompt_template.replace("{title}", title[:80]).replace("{views}", "{:,}".format(views))

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

        # 解析JSON（兼容统一prompt输出和旧7维输出）
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

        tokens = usage.get("completion_tokens", 0)

        # 判断格式：新格式有"结构化"或"构图"(嵌套dict with score)
        has_structured = "结构化" in analysis
        has_nested_score = "构图" in analysis and isinstance(analysis.get("构图"), dict) and "score" in analysis.get("构图", {})
        has_flat_score = "person_score" in analysis
        
        if has_structured or has_nested_score:
            # 新格式或旧嵌套格式 → 统一转换
            return _convert_to_diagnosis_format(analysis, title, views, image_url, tokens)
        elif has_flat_score:
            # 已经是扁平格式 → 补结构化字段
            analysis.setdefault("结构化", {})
            analysis["_meta"] = {"image_url": image_url, "title": title[:80], "views": views, "tokens": tokens}
            return analysis
        else:
            # 其他格式 → 补空字段
            analysis.setdefault("结构化", {})
            analysis["_meta"] = {"image_url": image_url, "title": title[:80], "views": views, "tokens": tokens, "format": "unknown"}
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
