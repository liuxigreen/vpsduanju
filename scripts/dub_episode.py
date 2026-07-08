#!/usr/bin/env python3
"""短剧配音脚本 - MiMo TTS 分角色配音。

用法:
    python3 scripts/dub_episode.py --analysis analysis_en.json --voice-map voice_map_en.json --output dub_en/

功能:
    1. 读取翻译分析文件（含角色、情绪、翻译文本）
    2. 通过名字归一化匹配角色音色
    3. 用 MiMo TTS 逐句配音
    4. 输出 WAV 文件列表供后续合并
"""

import argparse
import base64
import json
import os
import re
import sys
import time
from pathlib import Path

import requests
import yaml


# ── 名字归一化 ──────────────────────────────────────────────

# 同义角色名 → 标准名
NAME_ALIASES = {
    # 林子遥
    "林子遥": "林子遥",
    "lin ziyao": "林子遥",
    "linziyao": "林子遥",
    # 花子
    "花子": "花子",
    "huazi": "花子",
    "hua zi": "花子",
    # 乘务员
    "乘务员": "乘务员",
    "attendant": "乘务员",
    "conductor": "乘务员",
    # 旁白
    "旁白": "旁白",
    "narrator": "旁白",
}


def normalize_char(raw: str) -> str:
    """将各种角色名变体归一化为标准名。"""
    if not raw:
        return "旁白"

    # 去掉前缀: "1. 林子遥" → "林子遥", "Tag: 花子" → "花子"
    cleaned = re.sub(r"^[\d]+\.\s*", "", raw)
    cleaned = re.sub(r"^Tag:\s*", "", cleaned)
    cleaned = re.sub(r"^\*\*Tag:\s*", "", cleaned)
    cleaned = cleaned.strip()

    # 直接匹配
    lower = cleaned.lower()
    if lower in NAME_ALIASES:
        return NAME_ALIASES[lower]

    # 模糊匹配（包含关系）
    for alias, standard in NAME_ALIASES.items():
        if alias in lower or lower in alias:
            return standard

    # 未匹配 → 旁白
    return "旁白"


# ── 情绪标签 ──────────────────────────────────────────────

EMOTION_MAP = {
    "angry": "愤怒",
    "sad": "悲伤",
    "happy": "开心",
    "tender": "温柔",
    "scared": "恐惧",
    "surprised": "惊喜",
    "cold": "冷漠",
    "anxious": "紧张",
    "normal": "",
}


# ── 主逻辑 ──────────────────────────────────────────────

def load_config():
    with open(os.path.expanduser("~/.hermes/config.yaml")) as f:
        cfg = yaml.safe_load(f)
    return cfg["model"]["api_key"], cfg["model"]["base_url"]


def main():
    parser = argparse.ArgumentParser(description="MiMo TTS 分角色配音")
    parser.add_argument("--analysis", required=True, help="翻译分析 JSON 文件")
    parser.add_argument("--voice-map", required=True, help="角色音色映射 JSON 文件")
    parser.add_argument("--output", required=True, help="输出目录")
    parser.add_argument("--start", type=int, default=0, help="起始字幕索引")
    parser.add_argument("--limit", type=int, default=0, help="最多处理条数 (0=全部)")
    args = parser.parse_args()

    # 加载数据
    with open(args.analysis) as f:
        analysis = json.load(f)
    with open(args.voice_map) as f:
        voice_map = json.load(f)

    subs = analysis["subtitles"]
    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    api_key, base_url = load_config()
    tts_url = f"{base_url}/chat/completions"

    # 处理范围
    start = args.start
    end = min(start + args.limit, len(subs)) if args.limit > 0 else len(subs)
    target_subs = subs[start:end]

    print(f"🎙️ 配音: {len(target_subs)} 条 (索引 {start}~{end-1})")

    files = []
    stats = {}
    errors = 0

    for i, s in enumerate(target_subs):
        idx = start + i
        text = s.get("tr", "")
        if not text.strip():
            continue

        raw_char = s.get("char", "")
        char = normalize_char(raw_char)
        emotion = s.get("emotion", "normal")

        stats[char] = stats.get(char, 0) + 1

        # 构建情绪标签
        emo_tag = ""
        if emotion and emotion != "normal":
            zh = EMOTION_MAP.get(emotion, "")
            if zh:
                emo_tag = f"<style>{zh}</style>"

        content = f"{emo_tag}{text}"

        # 获取音色
        vd = voice_map.get(char)
        if vd and isinstance(vd, dict) and "data" in vd:
            msgs = [
                {"role": "user", "content": f"Say this: {text}"},
                {"role": "assistant", "content": content, "audio": vd},
            ]
        else:
            # fallback: 用预置音色 Dean（男声叙述）
            msgs = [
                {"role": "user", "content": text},
                {"role": "assistant", "content": content, "audio": {"voice": "Dean"}},
            ]

        try:
            resp = requests.post(
                tts_url,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "mimo-v2.5-tts",
                    "messages": msgs,
                    "stream": False,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                msg = resp.json()["choices"][0]["message"]
                if "audio" in msg and isinstance(msg["audio"], dict) and "data" in msg["audio"]:
                    audio = base64.b64decode(msg["audio"]["data"])
                    af = out_dir / f"dub_{idx:05d}.wav"
                    af.write_bytes(audio)
                    files.append({
                        "idx": idx,
                        "file": str(af),
                        "start": s["start"],
                        "end": s["end"],
                        "char": char,
                        "raw_char": raw_char,
                        "emotion": emotion,
                    })
                else:
                    errors += 1
                    print(f"  ⚠️ [{idx}] 无音频数据")
            elif resp.status_code == 429:
                print(f"  ⏳ [{idx}] 限速，等 10 秒...")
                time.sleep(10)
                # 重试一次
                resp2 = requests.post(
                    tts_url,
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={"model": "mimo-v2.5-tts", "messages": msgs, "stream": False},
                    timeout=30,
                )
                if resp2.status_code == 200:
                    msg = resp2.json()["choices"][0]["message"]
                    if "audio" in msg and isinstance(msg["audio"], dict) and "data" in msg["audio"]:
                        audio = base64.b64decode(msg["audio"]["data"])
                        af = out_dir / f"dub_{idx:05d}.wav"
                        af.write_bytes(audio)
                        files.append({"idx": idx, "file": str(af), "start": s["start"], "end": s["end"], "char": char, "raw_char": raw_char, "emotion": emotion})
                    else:
                        errors += 1
                else:
                    errors += 1
                    print(f"  ❌ [{idx}] 重试失败: {resp2.status_code}")
            else:
                errors += 1
                if errors <= 3:
                    print(f"  ❌ [{idx}] HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            errors += 1
            if errors <= 3:
                print(f"  ❌ [{idx}] {e}")

        # 进度报告
        if (i + 1) % 100 == 0:
            print(f"  进度: {i+1}/{len(target_subs)} 成功:{len(files)} 失败:{errors}")

        # 防限速: 每 5 个请求间隔 1 秒
        if (i + 1) % 5 == 0:
            time.sleep(1)

    # 保存结果
    manifest = out_dir / "dub_files.json"
    manifest.write_text(json.dumps(files, ensure_ascii=False, indent=2))

    print(f"\n✅ 配音完成: {len(files)} 段, {errors} 失败")
    print(f"   结果: {manifest}")

    # 角色统计（归一化后）
    print("\n角色分布:")
    for c, n in sorted(stats.items(), key=lambda x: -x[1]):
        print(f"  {c}: {n}句")


if __name__ == "__main__":
    main()
