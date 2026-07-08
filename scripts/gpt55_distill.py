#!/usr/bin/env python3
"""
GPT-5.5 三层蒸馏脚本

用法:
  python3 scripts/gpt55_distill.py --lang 印尼
  python3 scripts/gpt55_distill.py --lang all

输出:
  distill/outputs/distilled-rules-{lang}-gpt55-v5.json
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# 导入 daily_pipeline 的蒸馏函数和筛选函数
from daily_pipeline import _build_three_layer_prompt, select_titles_for_distill

# 路径常量
OUTPUT_DIR = ROOT / "distill" / "outputs"


def _load_evidence(lang: str, use_filtered: bool = True) -> dict:
    """加载蒸馏证据数据"""
    evidence_dir = ROOT / "distill" / "evidence" / lang
    result = {}
    
    # 优先使用筛选后的标题
    if use_filtered:
        filtered_file = evidence_dir / "titles_filtered.json"
        if filtered_file.exists():
            result["titles"] = json.loads(filtered_file.read_text())
            print(f"  📊 使用筛选后标题: {len(result['titles'])} 个")
        else:
            # 回退到原始标题
            titles_file = evidence_dir / "titles.json"
            if titles_file.exists():
                result["titles"] = json.loads(titles_file.read_text())
    else:
        titles_file = evidence_dir / "titles.json"
        if titles_file.exists():
            result["titles"] = json.loads(titles_file.read_text())
    
    # 加载其他维度
    for dim in ["timing", "tags", "emoji", "hashtag", "length"]:
        f = evidence_dir / f"{dim}.json"
        if f.exists():
            result[dim] = json.loads(f.read_text())
    return result


def _load_covers(lang: str) -> list:
    """加载封面分析数据"""
    covers_file = ROOT / "distill" / "evidence" / lang / "covers.json"
    if covers_file.exists():
        return json.loads(covers_file.read_text())
    return []


def _load_skeleton(lang: str) -> dict:
    """加载骨架数据"""
    skeleton_file = ROOT / "distill" / "evidence" / lang / "title_skeletons.json"
    if skeleton_file.exists():
        return json.loads(skeleton_file.read_text())
    return {}


def filter_evidence(evidence: dict, max_titles: int = 200) -> dict:
    """
    筛选证据数据，减少 prompt 长度但保留蒸馏质量
    
    策略：
    1. 标题：按播放量取 Top N，保留高播放量代表作
    2. 标签/Emoji/Hashtag：保留全部（数据量小）
    3. 时间：保留全部（数据量小）
    """
    filtered = dict(evidence)
    
    # 标题筛选：按播放量排序取 Top N
    if "titles" in filtered:
        titles = filtered["titles"]
        # 按播放量降序排序
        titles_sorted = sorted(titles, key=lambda x: x.get("views", 0), reverse=True)
        # 取 Top N
        filtered["titles"] = titles_sorted[:max_titles]
        print(f"  📊 标题筛选: {len(titles)} → {len(filtered['titles'])}（Top {max_titles} by views）")
    
    return filtered

# GPT-5.5 API 配置
API_KEY_FILE = ROOT / "config" / "gpt55_api_key.txt"
API_KEY_FALLBACK = os.path.expanduser("~/.hermes/duanju/gpt55_api_key.txt")
def _load_derouter_config():
    """从hermes config加载derouter配置"""
    try:
        import yaml
        config_path = Path.home() / ".hermes" / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            providers = config.get("providers", {})
            if "derouter" in providers:
                p = providers["derouter"]
                base_url = p.get("base_url", "https://api.derouter.ai/openai/v1")
                models = p.get("models", ["gpt-5.5"])
                return base_url, models[0] if models else "gpt-5.5"
    except Exception:
        pass
    return "https://api.derouter.ai/openai/v1", "gpt-5.5"

DEROUTER_BASE, DEFAULT_MODEL = _load_derouter_config()
ENDPOINT = f"{DEROUTER_BASE}/chat/completions"
MODEL = DEFAULT_MODEL

ALL_LANGS = ["印尼", "繁中", "英文", "葡萄牙", "西语", "土耳其", "日语"]


def load_api_key():
    """加载 API key - 优先从hermes config读取"""
    # 1. 从hermes config读取
    try:
        import yaml
        config_path = Path.home() / ".hermes" / "config.yaml"
        if config_path.exists():
            with open(config_path) as f:
                config = yaml.safe_load(f)
            providers = config.get("providers", {})
            # 优先derouter
            if "derouter" in providers:
                key = providers["derouter"].get("api_key", "")
                if key:
                    print(f"  ✅ 从hermes config读取derouter key")
                    return key
            # 回退edgefn
            if "edgefn" in providers:
                key = providers["edgefn"].get("api_key", "")
                if key:
                    print(f"  ✅ 从hermes config读取edgefn key")
                    return key
    except Exception as e:
        print(f"  ⚠️ 读取hermes config失败: {e}")
    
    # 2. 回退到文件
    for path in [API_KEY_FILE, Path(API_KEY_FALLBACK)]:
        if path.exists():
            return path.read_text().strip()
    raise RuntimeError(f"找不到 API key，请创建 {API_KEY_FILE}")


def call_gpt55(prompt: str, max_tokens: int = 32768) -> dict:
    """调用 GPT-5.5 API (OpenAI 兼容格式，流式请求)"""
    import requests

    key = load_api_key()
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }

    data = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "stream": True,
        "messages": [{
            "role": "user",
            "content": prompt
        }]
    }

    for attempt in range(3):
        try:
            resp = requests.post(ENDPOINT, headers=headers, json=data, 
                               stream=True, timeout=600)
            resp.raise_for_status()
            
            # 流式读取完整响应
            full_content = ""
            for line in resp.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: ") and decoded != "data: [DONE]":
                        try:
                            chunk = json.loads(decoded[6:])
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {}).get("content") or ""
                                if delta:
                                    full_content += delta
                                    print(delta, end="", flush=True)
                        except (json.JSONDecodeError, IndexError):
                            pass
            
            print()  # 换行
            
            if not full_content:
                raise ValueError("空响应")
            
            # 保存原始响应（避免解析失败丢数据）
            raw_file = ROOT / "distill" / "evidence" / "gpt_raw_response.txt"
            raw_file.parent.mkdir(parents=True, exist_ok=True)
            raw_file.write_text(full_content)
            print(f"  💾 原始响应已保存 → {raw_file}")
            
            # 提取 JSON
            if "```json" in full_content:
                full_content = full_content.split("```json")[1].split("```")[0]
            elif "```" in full_content:
                full_content = full_content.split("```")[1].split("```")[0]
            
            return json.loads(full_content.strip())
        except Exception as e:
            print(f"  ⚠️ 尝试 {attempt+1}/3 失败: {e}")
            if attempt < 2:
                time.sleep(5 * (attempt + 1))
            else:
                raise


def distill_lang(lang: str, max_titles: int = 200) -> dict:
    """对单个语言进行 GPT-5.5 蒸馏"""
    print(f"\n🌍 {lang}")

    # 加载数据
    evidence_raw = _load_evidence(lang, use_filtered=False)  # 加载全量
    covers = _load_covers(lang)
    skeleton = _load_skeleton(lang)

    if not evidence_raw.get("titles"):
        print(f"  ❌ 无数据，跳过")
        return None

    # 筛选标题：每频道Top3，优先有封面数据的
    evidence = dict(evidence_raw)
    evidence["titles"] = select_titles_for_distill(evidence_raw["titles"], covers, per_channel=3, max_total=150)

    # 构建 prompt
    channels = []  # 从 evidence 中提取
    prompt = _build_three_layer_prompt(lang, evidence, channels, covers, skeleton)
    print(f"  📝 Prompt: {len(prompt)} 字符")

    # 调用 GPT-5.5
    start = time.time()
    result = call_gpt55(prompt)
    elapsed = time.time() - start
    print(f"  ✅ 完成 ({elapsed:.1f}s)")

    # 添加 meta
    result["meta"] = {
        "platform": "youtube",
        "content_type": "short_drama",
        "lang": lang,
        "model": "GPT-5.5",
        "generated_at": datetime.now().isoformat(),
        "sample_size": len(evidence.get("titles", []))
    }

    return result


def main():
    parser = argparse.ArgumentParser(description="GPT-5.5 三层蒸馏")
    parser.add_argument("--lang", required=True, help="语言（印尼/繁中/英文/葡萄牙/西语/土耳其/日语/all）")
    parser.add_argument("--max-titles", type=int, default=200, help="每个语言最多保留的标题数（默认200）")
    args = parser.parse_args()

    if args.lang == "all":
        langs = ALL_LANGS
    else:
        langs = [args.lang]

    # 备份
    backup_dir = OUTPUT_DIR / f"backup_{datetime.now().strftime('%Y%m%d_%H%M')}"
    backup_dir.mkdir(exist_ok=True)
    for f in OUTPUT_DIR.glob("distilled-rules-*-gpt55-v5.json"):
        (backup_dir / f.name).write_bytes(f.read_bytes())
    print(f"📦 已备份到 {backup_dir}")

    # 蒸馏
    results = {}
    for lang in langs:
        result = distill_lang(lang, max_titles=args.max_titles)
        if result:
            output_file = OUTPUT_DIR / f"distilled-rules-{lang}-gpt55-v5.json"
            output_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
            print(f"  💾 已保存: {output_file.name}")
            results[lang] = result

    # 汇总
    print(f"\n{'='*50}")
    print(f"✅ 完成 {len(results)}/{len(langs)} 个语言")
    for lang, r in results.items():
        ver = r.get("meta", {}).get("version", "?")
        n = r.get("meta", {}).get("sample_size", "?")
        print(f"  {lang}: v{ver} | {n}样本")


if __name__ == "__main__":
    main()
