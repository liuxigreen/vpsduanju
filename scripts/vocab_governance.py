#!/usr/bin/env python3
"""vocab_governance — 词表治理报告（确定性，无LLM）

跑在 subtitle_aggregate_v2 之后。统计归一化后的题材分布，识别长尾与待评审标签，
产出 data/vocab_governance.json 供面板"词表健康"卡与人工评审使用。

判定:
  - vocab_target: l1_rules 全部 target + channel_tag_to_l1 值（词表靶）
  - pending: 出现≥3次但不在词表靶的标签（升词表候选，按频次降序）
  - longtail: 出现≤2次的标签（量太小暂不处理）
"""
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/subtitle_analysis/full_normalized.jsonl"
VOCAB = ROOT / "data/subtitle_analysis/genre_vocab_map.json"
OUT = ROOT / "data/vocab_governance.json"


def vocab_targets(v):
    rules = [(r["pattern"], r["target"]) for r in v.get("l1_rules", [])]
    tag2l1 = v.get("channel_tag_to_l1", {})
    return {t for _, t in rules} | set(tag2l1.values()), rules, tag2l1


def build():
    v = json.load(open(VOCAB, encoding="utf-8"))
    targets, rules, tag2l1 = vocab_targets(v)
    drop = set(v.get("drop", []))
    t2s = str.maketrans(v.get("t2s", {}))

    dist = Counter()
    sample = {}
    for line in open(SRC, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        for g in (d.get("analysis") or {}).get("genre_l1", []):
            if not isinstance(g, str) or not g.strip():
                continue
            g = g.strip()
            dist[g] += 1
            sample.setdefault(g, (d.get("title") or "")[:50])

    known = {g: c for g, c in dist.items() if g in targets}
    pending = [
        {"label": g, "n": c, "sample": sample.get(g, "")}
        for g, c in dist.most_common()
        if g not in targets and c >= 3
    ]
    longtail = {g: c for g, c in dist.items() if c <= 2}

    # 待评审标签的规则建议：若某 target 规则的 pattern 是该标签的前缀，建议归并
    for p in pending:
        p["suggest"] = next((tgt for pat, tgt in rules if p["label"] in pat or pat in p["label"]), None)

    report = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "vocab_version": v.get("version"),
        "rows_scanned": sum(dist.values()),
        "distinct_labels": len(dist),
        "vocab_targets": len(targets),
        "known_total": sum(known.values()),
        "known_share": round(sum(known.values()) / max(sum(dist.values()), 1), 3),
        "pending": pending[:30],
        "pending_total": len(pending),
        "longtail_count": len(longtail),
        "longtail_rows": sum(longtail.values()),
        "top_known": dict(Counter(known).most_common(15)),
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"distinct={report['distinct_labels']} targets={report['vocab_targets']} "
          f"known_share={report['known_share']:.0%} pending={report['pending_total']} "
          f"longtail={report['longtail_count']}({report['longtail_rows']}条)")
    for p in pending[:8]:
        print(f"  待评审: {p['label']} ×{p['n']}  suggest={p['suggest']}")


if __name__ == "__main__":
    build()
