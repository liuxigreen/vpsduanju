#!/usr/bin/env python3
"""L2 校准闭环：L1字幕题材 × L0标题法标签 混淆矩阵 → 逐标签准确率系数。
输入: data/video_genres/*.json (_status ok) + L0标签（现场用 extract_content_tags 对单视频标题重算，
     避免频道级历史污染——这正是审计发现的"时间窗错位"）。
产出: data/l1_calibration_report.json（系数表 + 错位分型 + emergent题材清单）

用法: python3 scripts/l1_calibration/confusion_matrix.py
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENRES_DIR, load_vocab, norm_genre
from distill_competitors import extract_content_tags

MIN_SAMPLES = 8  # 样本<8的标签不出系数，只出计数


def main():
    vocab = load_vocab()
    # L0 关键词表（与 extract_content_tags 同源，取其 label→kw 反查）
    import inspect, re
    src = inspect.getsource(extract_content_tags)
    kw_map = defaultdict(set)
    for kw, label in re.findall(r"'([^']+)':\s*'([^']+)'", src):
        kw_map[label].add(kw.lower())

    cm = defaultdict(lambda: defaultdict(int))  # l0_label -> l1_label -> count
    l0_total = defaultdict(int)
    l0_hit = defaultdict(int)   # L0标签且L1同题材存在 = 真
    emergent = defaultdict(list)
    mismatch_examples = []
    underpromise = []  # 标题保守内容更狠
    n = 0

    for f in sorted(GENRES_DIR.glob("*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("_status") not in ("ok", "ok_with_issues"):
            continue
        l1 = set(d.get("genre_l1") or [])
        if not l1:
            continue
        title = d.get("title") or ""
        l0 = set()
        for label, kws in kw_map.items():
            if label in vocab.get("non_genre", []):
                continue
            if any(k in title.lower() for k in kws):
                l0.add(label)
        n += 1
        for a in l0:
            l0_total[a] += 1
            for b in l1:
                cm[a][b] += 1
            if l0 & l1:
                l0_hit[a] += 1
            else:
                mismatch_examples.append({"video_id": d["video_id"], "title": title[:70],
                                          "l0": sorted(l0), "l1": sorted(l1)})
        for b in l1 - l0:
            if not l0:
                underpromise.append({"video_id": d["video_id"], "title": title[:70], "l1_only": sorted(l1)})
        for key in ("genre_l1_emergent", "genre_l2_emergent"):
            for g in d.get(key) or []:
                known = set(vocab["genre_l1"]) | set(vocab["genre_l2"])
                ng = norm_genre(g, vocab)
                if ng is None or ng not in known:
                    emergent[g].append(d["video_id"])

    rates = {}
    for a, tot in sorted(l0_total.items(), key=lambda x: -x[1]):
        r = l0_hit[a] / tot if tot else 0
        rates[a] = {"l0_count": tot, "precision": round(r, 3),
                    "reliable": tot >= MIN_SAMPLES,
                    "top_confusions": sorted(cm[a].items(), key=lambda x: -x[1])[:3]}

    report = {
        "n_videos": n,
        "note": "precision=L0标签在单视频标题命中时L1字幕同题材存在的比例；样本<8不出系数(reliable=false)",
        "l0_precision": rates,
        "mismatch_count": len(mismatch_examples),
        "mismatch_examples": mismatch_examples[:40],
        "under_promise_count": len(underpromise),
        "under_promise_examples": underpromise[:40],
        "emergent_genres": {g: {"count": len(vs), "video_ids": vs[:5]} for g, vs in sorted(emergent.items(), key=lambda x: -len(x[1]))},
    }
    out = Path("data/l1_calibration_report.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"样本 {n} 条视频")
    print(f"\n{'L0标签':<8}{'命中':>5}{'precision':>10}  可靠")
    for a, r in rates.items():
        print(f"{a:<8}{r['l0_count']:>5}{r['precision']:>10.1%}  {'✅' if r['reliable'] else '样本少'}")
    print(f"\n错位(标题挂A演B): {len(mismatch_examples)} 条 | 标题保守(under-promise): {len(underpromise)} 条")
    print(f"emergent新题材: {len(emergent)} 个")
    print(f"✅ {out}")


if __name__ == "__main__":
    main()
