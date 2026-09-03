#!/usr/bin/env python3
"""L1 字幕→LLM抽取：对 data/subs_norm.jsonl 中 quality=usable 的视频跑维度1-3+5特征抽取。
产出 data/video_genres/{video_id}.json（含 _model 标注实际执行模型）。

用法:
    python3 scripts/l1_calibration/analyze_subs.py --limit 5      # 冒烟
    python3 scripts/l1_calibration/analyze_subs.py --all
    python3 scripts/l1_calibration/analyze_subs.py --retry-failed
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENRES_DIR, SUBS_NORM, call_bai, load_vocab, norm_genre

PROMPTS = Path(__file__).resolve().parent / "prompts.md"


def extract_prompt_template():
    text = PROMPTS.read_text(encoding="utf-8")
    # v2 优先（增量批：全中文+多维），回退 v1
    m = re.search(r"--- prompt:extract_v2 ---\n(.*)", text, re.S) or \
        re.search(r"--- prompt:extract ---\n(.*?)\n--- prompt:trace ---", text, re.S)
    if not m:
        raise RuntimeError("prompts.md 缺少 extract/trace 分隔标记")
    return m.group(1).rstrip() + "\n"


def middle_sample(text, max_chars=6000):
    """中段太长时均匀抽3块，控制token。"""
    if len(text) <= max_chars:
        return text
    step = len(text) // 3
    return "\n…\n".join(text[i:i + max_chars // 3] for i in (0, step, 2 * step))


def build_prompt(tpl, d):
    return (tpl.replace("{language}", d.get("language", ""))
            .replace("{title}", d.get("title", ""))
            .replace("{channel}", d.get("channel", ""))
            .replace("{duration_min}", str(round(d.get("duration_sec", 0) / 60, 1)))
            .replace("{opening}", d.get("opening_0_3min", "")[:4000])
            .replace("{middle}", middle_sample(d.get("middle", "")))
            .replace("{ending}", d.get("ending_last_2min", "")[:3000]))


def validate(parsed, d, vocab):
    """归一化题材 + evidence 回查（引用句必须真在字幕里，允许空白差异）。"""
    issues = []
    hay = re.sub(r"\s+", "", d.get("full_text", ""))
    for key in ("genre_l1", "genre_l2"):
        raw = parsed.get(key) or []
        emergent = parsed.get(f"{key}_emergent") or []
        normed = []
        for g in list(raw) + list(emergent):
            g = norm_genre(g if isinstance(g, str) else g.get("name", ""), vocab)
            if g and g not in normed:
                normed.append(g)
        parsed[key] = normed
        if not normed:
            issues.append(f"{key}为空")
    ev = parsed.get("evidence") or {}
    checked = {}
    for k, quote in ev.items():
        if isinstance(quote, str) and quote:
            q = re.sub(r"\s+", "", quote)
            ok = q in hay
            checked[k] = {"quote": quote, "in_subs": ok}
            if not ok:
                issues.append(f"evidence[{k}]引用不在字幕中")
    parsed["evidence_check"] = checked
    for hook_key in ("opening_hook",):
        h = parsed.get(hook_key) or {}
        q = re.sub(r"\s+", "", h.get("event", ""))
        # event 是描述句不强制回查；quote 类字段才回查
    dl, dlc = parsed.get("distinctive_lines") or [], parsed.get("distinctive_lines_cn") or []
    if dlc and len(dl) != len(dlc):
        issues.append(f"distinctive_lines({len(dl)})与_cn({len(dlc)})长度不一致")
        parsed.setdefault("_warnings", []).append("lines_cn_misaligned")
    cl = (parsed.get("ending_cliffhanger") or {}).get("quote", "")
    if cl and re.sub(r"\s+", "", cl) not in hay:
        issues.append("cliffhanger.quote不在字幕中(ASR容错降级为警告)")
        parsed.setdefault("_warnings", []).append("cliffhanger_quote_unmatched")
    return parsed, issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--retry-failed", action="store_true")
    args = ap.parse_args()

    vocab = load_vocab()
    tpl = extract_prompt_template()
    GENRES_DIR.mkdir(parents=True, exist_ok=True)

    videos = []
    for line in SUBS_NORM.read_text(encoding="utf-8").splitlines():
        d = json.loads(line)
        if d.get("quality") != "usable":
            continue
        out = GENRES_DIR / f"{d['video_id']}.json"
        if out.exists():
            old = json.loads(out.read_text(encoding="utf-8"))
            if old.get("_status") == "ok" and not args.retry_failed:
                continue
        videos.append(d)

    if not args.all:
        videos = videos[: args.limit or 5]
    print(f"待分析: {len(videos)} 条")

    ok = fail = 0
    for i, d in enumerate(videos, 1):
        print(f"[{i}/{len(videos)}] {d['video_id']} {d.get('title','')[:50]}")
        rec = {"video_id": d["video_id"], "title": d.get("title"), "language": d.get("language"),
               "channel": d.get("channel"), "layer": d.get("layer"),
               "daily_views": d.get("daily_views"), "duration_sec": d.get("duration_sec"),
               "source_lang": d.get("source_lang"), "sub_kind": d.get("kind")}
        try:
            parsed, raw, model = call_bai(build_prompt(tpl, d))
            rec["_model"] = model
            if parsed is None:
                rec["_status"] = "parse_failed"
                (GENRES_DIR / f"{d['video_id']}.raw.txt").write_text(raw, encoding="utf-8")
                fail += 1
            else:
                parsed, issues = validate(parsed, d, vocab)
                rec.update(parsed)
                rec["_status"] = "ok" if not issues else "ok_with_issues"
                rec["_issues"] = issues
                if issues:
                    print(f"    ⚠️ {issues}")
                ok += 1
        except Exception as e:
            print(f"    ❌ {e}")
            rec["_status"] = f"error: {e}"
            fail += 1
        (GENRES_DIR / f"{d['video_id']}.json").write_text(
            json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✅ ok={ok} ❌ fail={fail} → {GENRES_DIR}/")


if __name__ == "__main__":
    main()
