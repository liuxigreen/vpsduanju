#!/usr/bin/env python3
"""extract_subs_meta — 从字幕回传txt的头部行提取 video 元数据（title/channel/views/tier/lang）

字幕txt格式（本地agent产出）:
  ===== tier | 语种 | video_id | views=N | channel =====
  <下一行 = 视频标题>
  <对白...>

用法: python3 scripts/l1_calibration/extract_subs_meta.py <txt目录或文件...>
输出: data/subtitle_analysis/incoming/video_meta.jsonl （每行 {video_id,title,channel,views,tier,language,source}）
"""
import json, re, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
OUT = ROOT / "data/subtitle_analysis/incoming/video_meta.jsonl"

HDR = re.compile(r'^=====\s*(P\d)\s*\|\s*(.+?)\s*\|\s*(\S+)\s*\|\s*views=(\d+)\s*\|\s*(.+?)\s*=====\s*$')


def extract_one(fp, rows):
    seen = 0
    with open(fp, encoding="utf-8", errors="ignore") as f:
        prev_hdr = None
        for line in f:
            m = HDR.match(line.rstrip("\r\n"))
            if m:
                prev_hdr = m
                continue
            if prev_hdr is not None:
                tier, lang, vid, views, ch = prev_hdr.groups()
                title = line.strip("\r\n")
                # 标题行不应为空、不应是分隔注释；对白首行通常小写短句，但标题行紧跟header是产出约定
                if title and not title.startswith("#"):
                    rows.setdefault(vid, {
                        "video_id": vid, "title": title[:300], "channel": ch,
                        "views": int(views), "tier": tier, "language": lang,
                        "source": os.path.basename(fp),
                    })
                    seen += 1
                prev_hdr = None
    return seen


def main(paths):
    files = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            files += sorted(pp.glob("*.txt"))
        elif pp.is_file():
            files.append(pp)
    rows = {}
    for fp in files:
        if "collection_status" in fp.name:
            continue
        n = extract_one(fp, rows)
        print(f"  {fp.name}: {n}")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for r in rows.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"total unique videos: {len(rows)} -> {OUT}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["/zimu"])
