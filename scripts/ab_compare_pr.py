#!/usr/bin/env python3
"""PR 注入 AB 对比 → 控制台 + ab_test/pr_verdict.md"""
import json, re, sys
from pathlib import Path

OUT = Path.home() / "duanju/data/subtitle_analysis/ab_test"
LC = sys.argv[1] if len(sys.argv) > 1 else "ja"


def load(tag):
    fp = OUT / f"pr_out_{tag}_{LC}.json"
    if not fp.exists():
        return None
    wrap = json.loads(fp.read_text(encoding="utf-8"))
    raw = wrap.get("raw", "")
    try:
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception:
        return {"_unparsed_head": raw[:300]}


base, inj = load("base"), load("inj")
if not base or not inj:
    raise SystemExit(f"产物未就绪: base={bool(base)} inj={bool(inj)}")

report = [f"# PR注入AB对比 ({LC})", ""]


def section(name, obj, keys=None):
    report.append(f"## {name}")
    if keys:
        for k in keys:
            v = obj.get(k)
            report.append(f"### {k}\n```json\n{json.dumps(v, ensure_ascii=False, indent=1)[:1200]}\n```")
    else:
        report.append("```json\n" + json.dumps(obj, ensure_ascii=False, indent=1)[:2500] + "\n```")
    report.append("")


wtb, wti = base.get("what_they_watch") or {}, inj.get("what_they_watch") or {}
tahb, tahi = base.get("titles_and_hooks") or {}, inj.get("titles_and_hooks") or {}
fob, foi = inj.get("future_opportunities") or {}, base.get("future_opportunities") or {}

report.append("## what_they_watch.top_genres")
report.append("**BASE:**\n```json\n" + json.dumps(wtb.get("top_genres"), ensure_ascii=False, indent=1)[:1000] + "\n```")
report.append("**INJ:**\n```json\n" + json.dumps(wti.get("top_genres"), ensure_ascii=False, indent=1)[:1000] + "\n```")
report.append("")

report.append("## titles_and_hooks")
report.append("**BASE:**\n```json\n" + json.dumps(tahb, ensure_ascii=False, indent=1)[:1200] + "\n```")
report.append("**INJ:**\n```json\n" + json.dumps(tahi, ensure_ascii=False, indent=1)[:1200] + "\n```")
report.append("")

report.append("## future_opportunities.content_gaps")
report.append("**BASE:**\n```json\n" + json.dumps((base.get('future_opportunities') or {}).get('content_gaps'), ensure_ascii=False, indent=1) + "\n```")
report.append("**INJ:**\n```json\n" + json.dumps((inj.get('future_opportunities') or {}).get('content_gaps'), ensure_ascii=False, indent=1) + "\n```")
report.append("")

# 锚点核对
CHECKS = [
    ("引用字幕实证数字(如 翻译剧率/中位时长/钩子%)", r"(翻译剧率|字幕实证|中位时长|身份反差\s*\d+%|53%|100%)"),
    ("标题通胀/标题与内容偏差提示", r"(标题通胀|标题与内容|标题主打.*内容实|标题层.*内容层)"),
    ("钩子按内容8类表述(身份反差/关系背叛/时间改命/系统异能)", r"(身份反差|时间改命|系统异能|关系背叛)"),
    ("内容级空白点(悬念结尾率/萌宝占比/翻译剧垄断)", r"(悬念|结尾|萌宝|翻译剧|空白)"),
]
allb, alli = json.dumps(base, ensure_ascii=False), json.dumps(inj, ensure_ascii=False)
report.append("## 锚点核对")
for name, pat in CHECKS:
    b, i = bool(re.search(pat, allb)), bool(re.search(pat, alli))
    arrow = "✅新增" if (not b and i) else ("保留" if (b and i) else ("—" if not b and not i else "⚠️丢失"))
    report.append(f"- {arrow} | {name}: base={'有' if b else '无'} → inj={'有' if i else '无'}")

md = "\n".join(report)
(OUT / f"pr_verdict_{LC}.md").write_text(md, encoding="utf-8")
print(md)
