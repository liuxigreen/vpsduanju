#!/usr/bin/env python3
"""L1 抽样清单生成：A层=每语种动量TOP N，B层=中腰部按动量分3档随机抽30%，C层不跑。
产出 data/l1_manifest.json（video_id → 元数据 + layer），fetch_subs.py 读 ids 列表拉字幕。

用法:
    python3 scripts/l1_calibration/select_batch.py                 # 生成清单
    python3 scripts/l1_calibration/select_batch.py --emit-ids x.txt  # 另存 video_id 列表
"""
import argparse
import json
import random
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import MANIFEST, load_momentum_videos, load_vocab


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--emit-ids", help="把入选 video_id 写到该文件（每行一个，供 fetch_subs.py）")
    args = ap.parse_args()

    vocab = load_vocab()
    lang_cfg = vocab["languages"]
    pool = load_momentum_videos()
    print(f"动量视频池: {len(pool)} 条")

    by_lang = defaultdict(list)
    for v in pool:
        by_lang[v["language"]].append(v)

    rng = random.Random(args.seed)
    manifest = {"generated_at": datetime.now().isoformat(timespec="seconds"),
                "note": "A层=语种动量TOP；B层=中腰部3档随机30%；C层未入选",
                "videos": {}}
    stats = defaultdict(lambda: {"pool": 0, "A": 0, "B": 0})

    for lang, vids in by_lang.items():
        cfg = lang_cfg.get(lang)
        if not cfg:
            print(f"  ⚠️ 语种[{lang}]无配额配置（{len(vids)}条），跳过。需要时在 genre_vocab.yaml languages 补充")
            continue
        vids.sort(key=lambda x: -x["daily_views"])
        n_a = cfg["layer_a"]
        layer_a = vids[:n_a]
        rest = vids[n_a:]
        # B层：中腰部按动量分3档，各档随机抽 ratio
        ratio = cfg["layer_b_ratio"]
        b_max = cfg.get("layer_b_max", 30)
        layer_b = []
        if rest:
            tiers = [rest[: len(rest) // 3], rest[len(rest) // 3: 2 * len(rest) // 3], rest[2 * len(rest) // 3:]]
            for t in tiers:
                k = round(len(t) * ratio)
                layer_b += rng.sample(t, min(k, len(t)))
            if len(layer_b) > b_max:  # 超封顶则各档等比缩，保持分层随机
                layer_b = rng.sample(layer_b, b_max)
        for v in layer_a:
            manifest["videos"][v["id"]] = {**v, "layer": "A"}
        for v in layer_b:
            manifest["videos"][v["id"]] = {**v, "layer": "B"}
        stats[lang]["pool"] = len(vids)
        stats[lang]["A"] = len(layer_a)
        stats[lang]["B"] = len(layer_b)

    total = len(manifest["videos"])
    print(f"\n{'语种':<6}{'池':>6}{'A层':>5}{'B层':>5}")
    for lang in sorted(stats):
        s = stats[lang]
        print(f"{lang:<6}{s['pool']:>6}{s['A']:>5}{s['B']:>5}")
    print(f"\n总计入选: {total} 条（预期 ~300/语种轮次，多语种全跑约 {total}）")

    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"✅ 清单: {MANIFEST}")

    if args.emit_ids:
        Path(args.emit_ids).write_text("\n".join(manifest["videos"].keys()), encoding="utf-8")
        print(f"✅ id列表: {args.emit_ids}")


if __name__ == "__main__":
    main()
