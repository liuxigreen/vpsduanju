#!/usr/bin/env python3
"""L1 校准层共享工具：词表加载、动量视频源、字幕解析、bai 主模型调用。"""
import json
import re
import sys
import time
from pathlib import Path

import requests
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent  # ~/duanju
sys.path.insert(0, str(ROOT / "scripts"))

VOCAB_PATH = Path(__file__).resolve().parent / "genre_vocab.yaml"
GENRES_DIR = ROOT / "data" / "video_genres"
SUBS_RAW_DIR = ROOT / "data" / "subs_raw"
SUBS_NORM = ROOT / "data" / "subs_norm.json"
MANIFEST = ROOT / "data" / "l1_manifest.json"
PANEL = ROOT / "data" / "competitors_channels_all.json"


def load_vocab():
    return yaml.safe_load(VOCAB_PATH.read_text(encoding="utf-8"))


def norm_genre(label, vocab):
    """别名归一化；非题材词返回 None。"""
    if not label:
        return None
    s = label.strip()
    alias = vocab.get("alias", {})
    s = alias.get(s, alias.get(s.lower(), s))
    if s in vocab.get("non_genre", []) or s.lower() in [x.lower() for x in vocab.get("non_genre", [])]:
        return None
    return s


def all_vocab_labels(vocab):
    return set(vocab["genre_l1"]) | set(vocab["genre_l2"])


def load_momentum_videos():
    """全语种动量视频池: [{id,title,channel_id,channel,language,views,published_at,daily_views}]"""
    from datetime import datetime
    panel = json.loads(PANEL.read_text(encoding="utf-8"))
    channels = panel["channels"] if isinstance(panel, dict) else panel
    pool = {}
    today = datetime(2026, 8, 30)  # 与 collect_video_daily 口径一致，重跑时更新或用 now
    for ch in channels:
        lang = ch.get("language") or ""
        for v in (ch.get("tracking") or {}).get("momentum_videos_detail") or []:
            vid = v.get("id")
            if not vid or vid in pool:
                continue
            pub = v.get("published_at")
            try:
                days = max((today - datetime.strptime(pub, "%Y-%m-%d")).days, 1)
            except (TypeError, ValueError):
                days = 30
            views = v.get("views") or 0
            pool[vid] = {
                "id": vid, "title": v.get("title", ""),
                "channel_id": ch.get("channel_id", ""), "channel": ch.get("name", ""),
                "language": lang, "views": views, "published_at": pub,
                "daily_views": round(views / days),
            }
    return list(pool.values())


# ---------- 字幕解析（SRT / WebVTT 通用） ----------

_TS = re.compile(r"(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{1,3})")


def parse_subs_text(text):
    """返回 [(start_sec, end_sec, line)]，已去 HTML 标签/重复行/水印行。"""
    cues = []
    cur_start = cur_end = None
    for raw in text.splitlines():
        line = raw.strip()
        m = _TS.search(line)
        if m:
            g = list(map(int, m.groups()))
            cur_start = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000
            cur_end = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000
            continue
        if not line or line == "WEBVTT" or line.isdigit() or line.startswith(("NOTE ", "Kind:", "Language:", "STYLE")):
            continue
        line = re.sub(r"<[^>]+>", "", line).strip()  # 去 vtt 内联标签
        line = re.sub(r"\{\{[^}]*\}\}", "", line).strip()
        if not line:
            continue
        if cues and cues[-1][2] == line:  # auto-subs 滚动重复行
            continue
        if cur_start is not None:
            cues.append((round(cur_start, 1), round(cur_end or cur_start, 1), line))
    return cues


def cues_duration(cues):
    return cues[-1][1] if cues else 0.0


def seg(cues, t0, t1):
    """取 [t0,t1) 区间文本。"""
    return " ".join(t for s, e, t in cues if t0 <= s < t1)


def hook_segments(cues):
    """按审计维度拆段：前3分钟(开场钩子) / 中段 / 尾2分钟(cliffhanger)。
    短素材（单条<10分钟，短剧常按合集发布则更长）自适应缩放。"""
    dur = cues_duration(cues)
    if dur <= 0:
        return {}
    head_end = min(180, dur * 0.2)
    tail_start = max(dur - 120, head_end)
    return {
        "duration_sec": round(dur),
        "opening_0_3min": seg(cues, 0, head_end),
        "middle": seg(cues, head_end, tail_start),
        "ending_last_2min": seg(cues, tail_start, dur + 1),
        "full": " ".join(t for _, _, t in cues),
    }


# ---------- bai 主模型（与 run_insights_current_model.py 同源） ----------

def bai_config():
    cfg = yaml.safe_load((Path.home() / ".hermes/config.yaml").read_text(encoding="utf-8"))
    prov = (cfg.get("provider") or cfg["providers"])["bai"]
    return prov["api_key"], prov["base_url"].rstrip("/"), cfg["model"]["default"]


_BAI = None


def call_bai(prompt, max_tokens=8000, temperature=0.2, retries=2):
    """返回 (parsed_dict_or_None, raw_text, model_name)。"""
    global _BAI
    if _BAI is None:
        _BAI = bai_config()
    api_key, base_url, model = _BAI
    from edgefn_models import parse_json_response
    for attempt in range(retries + 1):
        try:
            r = requests.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={"model": model, "messages": [{"role": "user", "content": prompt}],
                      "max_tokens": max_tokens, "temperature": temperature},
                timeout=600,
            )
            r.raise_for_status()
            j = r.json()
            content = j["choices"][0]["message"]["content"]
            usage = j.get("usage", {})
            print(f"    📊 model={model} in={usage.get('prompt_tokens', 0):,} out={usage.get('completion_tokens', 0):,}")
            if not content.strip():
                raise RuntimeError("空响应")
            parsed = parse_json_response({"content": content})
            if "error" not in parsed:
                return parsed, content, model
            if attempt < retries:
                print(f"    ⚠️ JSON解析失败，重试 {attempt + 1}")
                time.sleep(3)
            else:
                return None, content, model
        except Exception as e:
            if attempt < retries:
                print(f"    ⚠️ {e}，重试 {attempt + 1}")
                time.sleep(5)
            else:
                raise
    return None, "", model
