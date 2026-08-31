#!/usr/bin/env python3
"""subtitle_evidence — 字幕实证注入模块（零LLM，纯确定性聚合）

数据源: ~/duanju/data/subtitle_analysis/*_normalized.jsonl（subtitle_aggregate_v1.py 产出）
用法:
    from subtitle_evidence import channel_subtitle_block, market_subtitle_block
    block = channel_subtitle_block("恋愛短編ドラマ", "日语")   # 单频道prompt注入
    block = market_subtitle_block("ja")                        # 市场洞察prompt注入
"""
import json, re, glob, os, statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POOL_DIR = ROOT / "data" / "subtitle_analysis"

_CACHE = {"loaded": False, "by_channel": defaultdict(list), "rows": []}


def _load():
    if _CACHE["loaded"]:
        return
    files = sorted(glob.glob(str(POOL_DIR / "*_normalized.jsonl")))
    # 兼容: 聚合脚本还没产出normalized时直接读原始回传
    if not files:
        files = sorted(glob.glob(str(ROOT / "output/subtitle_task/results_*.jsonl")))
    for fp in files:
        for line in open(fp, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if not (d.get("analysis") or {}).get("genre_l1"):
                continue
            _CACHE["rows"].append(d)
            name = (d.get("channel") or "").strip()
            if name:
                _CACHE["by_channel"][name].append(d)
    _CACHE["loaded"] = True


def _med(xs):
    xs = [x for x in xs if x is not None]
    return round(statistics.median(xs), 1) if xs else None


def _pct(n, total):
    return f"{n / total * 100:.0f}%" if total else "-"


def channel_subtitle_block(channel_name: str, lang_cn: str = "", max_lines: int = 26) -> str:
    """单频道字幕实证 block。无数据返回空串（prompt自动降级为纯标题分析）。"""
    _load()
    rows = _CACHE["by_channel"].get((channel_name or "").strip(), [])
    if not rows:
        # 容错: 名称带空格/大小写差异
        key = re.sub(r"\s+", "", (channel_name or "")).lower()
        for k, v in _CACHE["by_channel"].items():
            if re.sub(r"\s+", "", k).lower() == key:
                rows = v
                break
    if not rows:
        return ""

    n = len(rows)
    l1, l2, hook, pay = Counter(), Counter(), Counter(), Counter()
    translated = comp = cliff = 0
    durs, hook_secs, revs = [], [], []
    for d in rows:
        a = d["analysis"]
        for g in a.get("genre_l1", []):
            l1[g] += 1
        for g in a.get("genre_l2", [])[:3]:
            l2[g] += 1
        h = a.get("opening_hook") or {}
        if h.get("type"):
            hook[h["type"]] += 1
            if h.get("appears_at_sec") is not None:
                hook_secs.append(h["appears_at_sec"])
        for p in a.get("payoffs", []):
            pay[p] += 1
        os_ = a.get("origin_signals") or {}
        translated += int(bool(os_.get("feels_translated")))
        comp += int(bool(d.get("is_compilation")))
        cliff += int(bool((a.get("ending_cliffhanger") or {}).get("present")))
        durs.append(d.get("duration_sec") or 0)
        if a.get("reversal_density") is not None:
            revs.append(a["reversal_density"])

    # 爆款组 vs 普通组 对照（阈值 = 组内中位播放×2）
    views_list = [d.get("views", 0) for d in rows]
    med_v = statistics.median(views_list) if views_list else 0
    hot = [d for d in rows if d.get("views", 0) >= med_v * 2]
    norm = [d for d in rows if d.get("views", 0) < med_v * 2]

    def _profile(subset):
        if not subset:
            return "样本不足"
        c1 = Counter(g for d in subset for g in d["analysis"].get("genre_l1", [])).most_common(3)
        ck = Counter(((d["analysis"].get("opening_hook") or {}).get("type") or "其他") for d in subset).most_common(2)
        cp = Counter(p for d in subset for p in d["analysis"].get("payoffs", [])).most_common(3)
        return (f"L1={';'.join(f'{g}×{c}' for g, c in c1)} | "
                f"钩子={'/'.join(g for g, _ in ck)} | payoff={'/'.join(g for g, _ in cp)}")

    med_dur = _med(durs)
    dur_min = round(med_dur / 60) if med_dur is not None else "-"
    lines = [
        "## 字幕内容实证（内容级LLM分析，直接看过了视频对白字幕）",
        f"- 覆盖: 该频道 {n} 条视频已有字幕级分析（标题之外的真实内容证据，优先级高于标题推断）",
        f"- L1题材: {'; '.join(f'{g} {_pct(c, n)}' for g, c in l1.most_common(6))}",
        f"- L2细分: {'; '.join(f'{g}×{c}' for g, c in l2.most_common(6))}",
        f"- 开场钩子: {'; '.join(f'{g} {_pct(c, n)}' for g, c in hook.most_common(4))}"
        f"（钩子出现中位 {_med(hook_secs)}s）",
        f"- Payoff: {'; '.join(f'{g}×{c}' for g, c in pay.most_common(6))}",
        f"- 结构: 翻译剧率 {_pct(translated, n)} | 合辑率 {_pct(comp, n)} | 结尾悬念率 {_pct(cliff, n)}"
        f" | 中位时长 {dur_min}min | 反转密度中位 {_med(revs)}/10min",
        f"- 爆款组(n={len(hot)}, ≥2×中位播放): {_profile(hot)}",
        f"- 普通组(n={len(norm)}): {_profile(norm)}",
        "- 分析要求: 用以上实证校正你从标题得出的判断；冲突时以字幕实证为准并明确指出（如'标题主打X但内容实为Y'）",
    ]
    return "\n".join(lines[:max_lines])


def market_subtitle_block(lang_code: str) -> str:
    """市场层字幕实证 block（来自 p0_report.json 聚合）。"""
    fp = POOL_DIR / "p0_report.json"
    if not fp.exists():
        return ""
    rep = json.loads(fp.read_text())
    ls = (rep.get("lang_stats") or {}).get(lang_code)
    if not ls:
        return ""
    # 该语种 payoff/l2 由 rows 现算（report里只有全局）
    _load()
    rows = [d for d in _CACHE["rows"] if d.get("lang_code") == lang_code]
    pay, l2, hooks = Counter(), Counter(), Counter()
    for d in rows:
        for p in d["analysis"].get("payoffs", []):
            pay[p] += 1
        for g in d["analysis"].get("genre_l2", []):
            l2[g] += 1
        h = (d["analysis"].get("opening_hook") or {}).get("type")
        if h:
            hooks[h] += 1
    n = ls["n"]
    lines = [
        "## 字幕内容实证（本语种 P0 样本的内容级分析）",
        f"- 样本: {n} 条完整视频的字幕级分析",
        f"- 题材格局(L1): {'; '.join(f'{g} {_pct(c, n)}' for g, c in ls['top_l1'].items())}",
        f"- L2细分: {'; '.join(f'{g}×{c}' for g, c in l2.most_common(8))}",
        f"- 开场钩子: {'; '.join(f'{g} {_pct(c, n)}' for g, c in hooks.most_common(5))}",
        f"- Payoff: {'; '.join(f'{g}×{c}' for g, c in pay.most_common(8))}",
        f"- 结构: 翻译剧率 {ls['translated_ratio']:.0%} | 合辑率 {ls['compilation_ratio']:.0%} | "
        f"结尾悬念率 {ls['cliffhanger_ratio']:.0%} | 中位时长 {ls['median_duration_min']}min | "
        f"钩子中位 {ls['median_hook_at_sec']}s | 反转密度中位 {ls['median_reversal_per10min']}/10min",
        "- 分析要求: 题材/钩子判断需与上述内容级证据一致；标题层信号与内容层冲突时，指出'标题通胀'现象",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    name = sys.argv[1] if len(sys.argv) > 1 else "恋愛短編ドラマ"
    lang = sys.argv[2] if len(sys.argv) > 2 else ""
    b = channel_subtitle_block(name, lang)
    print(b or f"(无字幕数据: {name})")
