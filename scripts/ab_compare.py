#!/usr/bin/env python3
"""AB 对比报告: out_base.json vs out_injected.json → ab_verdict.md"""
import json
from pathlib import Path

OUT = Path.home() / "duanju/data/subtitle_analysis/ab_test"


def load(fp):
    raw = (OUT / fp).read_text(encoding="utf-8")
    try:
        return json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception:
        return None


base, inj = load("out_base.json"), load("out_injected.json")
if not inj:
    raise SystemExit("injected 输出尚未就绪或解析失败")


def digest(d, tag):
    what = d.get("what") or {}
    w = d.get("why") or {}
    print(f"===== {tag} =====")
    print("[content_strategy]", what.get("content_strategy"))
    print("[top_themes]")
    for t in what.get("top_themes", []):
        print("  -", t)
    print("[hook_patterns]")
    for h in what.get("hook_patterns", []):
        print("  -", str(h)[:100])
    print("[audience_fit]", str(w.get("audience_fit"))[:160])
    print()


digest(base, "BASE (纯标题+播放数据)")
digest(inj, "INJECTED (标题+数据+字幕实证)")

# 字幕实证锚点核对表
CHECKS = [
    ("萌宝要素", "萌宝", "字幕实证: 萌宝 40% (6/15)，爆款组 3/3"),
    ("钩子主导型", "关系背叛", "字幕实证: 关系背叛 53% 主导"),
    ("爆款钩子", "身份反差", "字幕实证: 爆款组钩子=身份反差/情绪爆点"),
    ("翻译剧定位", "翻译\|搬运\|中国", "字幕实证: 翻译剧率 100%"),
]
import re
for name, pat, evidence in CHECKS:
    b_hit = any(re.search(pat, json.dumps(x, ensure_ascii=False)) for x in [base.get("what", {})])
    i_hit = any(re.search(pat, json.dumps(x, ensure_ascii=False)) for x in [inj.get("what", {})])
    print(f"{'✅' if i_hit else '❌'} {name}: base={'有' if b_hit else '无'} → injected={'有' if i_hit else '无'}   ({evidence})")

md = ["# AB测试: 字幕实证注入效果", "",
      f"- base prompt {len((OUT/'prompt_base.txt').read_text())} chars / injected +584 chars (字幕实证块)",
      "- 频道: 恋愛短編ドラマ (ja, 15条字幕) · 模型: bai · temperature 0.3",
      "", "见上方控制台输出", ""]
(OUT / "ab_verdict.md").write_text("\n".join(md), encoding="utf-8")
print("\nsaved → ab_verdict.md")
