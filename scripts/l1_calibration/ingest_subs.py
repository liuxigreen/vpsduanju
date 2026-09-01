#!/usr/bin/env python3
"""L1 字幕入库：把 fetch_subs.py 回传的原始字幕归一化为带时间轴的 JSONL。
产出 data/subs_norm.jsonl，每行:
  {video_id, source_lang, kind(auto/manual), duration_sec, cues:[[start,end,text],...],
   opening_0_3min, middle, ending_last_2min, full_text, quality}
quality: usable / too_short(<400字) / garbled(非文字占比>40%) / empty

用法:
    python3 scripts/l1_calibration/ingest_subs.py ~/incoming/subs_dump_0831/*.json
    # 兼容格式: 单文件=一条视频dict 或 多条list[{video_id, subtitles:[{lang,kind,body}]}]
    # 也兼容 .srt/.vtt 文件名即 video_id
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import SUBS_NORM, MANIFEST, hook_segments, parse_subs_text


def quality_of(cues, text):
    if not cues or len(text) < 400:
        return "too_short"
    nonword = len(re.findall(r"[^\w\s\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af.,!?;:'\"-]", text))
    if nonword / max(len(text), 1) > 0.4:
        return "garbled"
    return "usable"


def load_one(path):
    """返回 [(video_id, lang, kind, cues)]"""
    out = []
    if path.suffix in (".srt", ".vtt"):
        out.append((path.stem, "", "auto", parse_subs_text(path.read_text(encoding="utf-8", errors="ignore"))))
        return out
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    items = data if isinstance(data, list) else [data]
    for it in items:
        vid = str(it.get("video_id") or it.get("id") or "")
        subs = it.get("subtitles") or it.get("subs") or []
        if isinstance(subs, dict):
            subs = [dict(lang=k, body=v) if isinstance(v, str) else dict(lang=k, **v) for k, v in subs.items()]
        for s in subs:
            body = s.get("body") or s.get("text") or ""
            cues = parse_subs_text(body) if ("-->" in body) else [
                (i * 3.0, i * 3.0 + 3, ln.strip())
                for i, ln in enumerate(body.splitlines()) if ln.strip()]
            out.append((vid, s.get("lang", ""), s.get("kind", "auto"), cues))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("inputs", nargs="+", help="回传的字幕文件/目录")
    ap.add_argument("--prefer-lang", default="", help="多语言字幕时优先取哪个lang（如 id/en）")
    args = ap.parse_args()

    files = []
    for p in map(Path, args.inputs):
        files += sorted(p.glob("*")) if p.is_dir() else [p]
    files = [f for f in files if f.suffix in (".json", ".srt", ".vtt")]

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"videos": {}}

    existing = {}
    if SUBS_NORM.exists():
        for line in SUBS_NORM.read_text(encoding="utf-8").splitlines():
            d = json.loads(line)
            existing[d["video_id"]] = d

    n_new = 0
    for f in files:
        try:
            records = load_one(f)
        except Exception as e:
            print(f"❌ {f.name}: {e}")
            continue
        # 同一视频多语言字幕 → 取 prefer_lang，否则取第一条 cues 最多的
        by_vid = {}
        for vid, lang, kind, cues in records:
            by_vid.setdefault(vid, []).append((lang, kind, cues))
        for vid, variants in by_vid.items():
            variants.sort(key=lambda x: (x[0] != args.prefer_lang, -len(x[2])))
            lang, kind, cues = variants[0]
            segs = hook_segments(cues)
            text = segs.get("full", "")
            meta = manifest["videos"].get(vid, {})
            existing[vid] = {
                "video_id": vid, "source_lang": lang, "kind": kind,
                "title": meta.get("title", ""), "language": meta.get("language", ""),
                "channel": meta.get("channel", ""), "layer": meta.get("layer", "?"),
                "daily_views": meta.get("daily_views", 0),
                "duration_sec": segs.get("duration_sec", 0),
                "quality": quality_of(cues, text),
                "cues": [[s, e, t] for s, e, t in cues],
                "opening_0_3min": segs.get("opening_0_3min", ""),
                "middle": segs.get("middle", ""),
                "ending_last_2min": segs.get("ending_last_2min", ""),
                "full_text": text,
            }
            n_new += 1

    with SUBS_NORM.open("w", encoding="utf-8") as fh:
        for d in existing.values():
            fh.write(json.dumps(d, ensure_ascii=False) + "\n")

    from collections import Counter
    q = Counter(d["quality"] for d in existing.values())
    print(f"✅ 入库 {n_new} 条新字幕，总 {len(existing)} 条 → {SUBS_NORM}")
    print(f"   质量分布: {dict(q)}")
    cov = len(existing) / max(len(manifest['videos']), 1)
    print(f"   清单覆盖率: {len(existing)}/{len(manifest['videos'])} = {cov:.0%}（<100% 说明部分视频无字幕，fetch 时已跳过属正常）")


if __name__ == "__main__":
    main()
