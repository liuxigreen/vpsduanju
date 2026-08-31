#!/usr/bin/env python3
"""A/B 测试: 单频道分析 无字幕实证(base) vs 有字幕实证(injected)
同一频道、同一模型(bai)，仅 prompt 差异。产物存 data/subtitle_analysis/ab_test/
"""
import json, sys, os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import llm_analyze_channel as lac
import subtitle_evidence
import yaml

cfg = yaml.safe_load(open(Path.home() / ".hermes/config.yaml"))
prov = (cfg.get("provider") or cfg["providers"])["bai"]
API_KEY, BASE_URL, MODEL = prov["api_key"], prov["base_url"].rstrip("/"), cfg["model"]["default"]

CHANNEL_ID = "UCLyPyGXqFJbGT98dD_WzJSQ"   # 恋愛短編ドラマ
OUT = ROOT / "data/subtitle_analysis/ab_test"
OUT.mkdir(parents=True, exist_ok=True)

# --- 准备频道数据与 prompt ---
latest = json.load(open(ROOT / "data/competitor_data/latest.json"))
ch = next(c for c in latest if c.get("channel_id") == CHANNEL_ID)
data = lac.prepare_channel_data(ch)
base_prompt = lac.build_prompt(data)

block = subtitle_evidence.channel_subtitle_block(ch.get("name", ""), ch.get("language", ""))
assert block, "字幕实证 block 为空"
anchor = "\n\n## 分析要求"
assert anchor in base_prompt, "注入锚点缺失"
inj_prompt = base_prompt.replace(anchor, "\n\n" + block + anchor, 1)

(OUT / "prompt_base.txt").write_text(base_prompt, encoding="utf-8")
(OUT / "prompt_injected.txt").write_text(inj_prompt, encoding="utf-8")
print(f"prompt: base={len(base_prompt)} chars, injected={len(inj_prompt)} chars (+{len(inj_prompt)-len(base_prompt)})")

# --- 调 bai 两次 ---
import requests

def call_bai(prompt):
    import time
    fr, msg, last = None, "", None
    for attempt in range(5):
        try:
            r = requests.post(f"{BASE_URL}/chat/completions",
                              headers={"Authorization": f"Bearer {API_KEY}"},
                              json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
                                    "max_tokens": 16000, "temperature": 0.3},
                              timeout=600)
        except requests.RequestException as e:
            last = e
            print(f"  ⏳ 连接异常 {type(e).__name__}，等60s重试 ({attempt+1}/5)")
            time.sleep(60)
            continue
        if r.status_code == 429:
            wait = 45 * (attempt + 1)
            print(f"  ⏳ 429 限流，等 {wait}s 重试 ({attempt+1}/5)")
            time.sleep(wait)
            continue
        r.raise_for_status()
        j = r.json()
        msg = j["choices"][0]["message"]["content"] or ""
        fr = j["choices"][0].get("finish_reason")
        print(f"  finish_reason={fr}, out_chars={len(msg)}")
        if not msg.strip():
            print("  ⏳ 空响应，重试"); time.sleep(30); continue
        # JSON 完整性检查（截断则重试）
        if msg.count("{") > msg.count("}"):
            print(f"  ⏳ JSON 疑似截断 ({{={msg.count('{')} }}={msg.count('}')})，重试")
            time.sleep(20); continue
        return msg
    raise RuntimeError(f"bai 连续失败 (last finish_reason={fr}, chars={len(msg)}, last_exc={last})")

print("▶ base (纯标题+数据)...")
if (OUT / "out_base.json").exists() and (OUT / "out_base.json").stat().st_size > 500:
    print("  ✔ out_base.json 已存在，跳过")
    base_out = (OUT / "out_base.json").read_text(encoding="utf-8")
else:
    base_out = call_bai(base_prompt)
    (OUT / "out_base.json").write_text(base_out, encoding="utf-8")
print("▶ injected (标题+数据+字幕实证)...")
inj_out = call_bai(inj_prompt)
(OUT / "out_injected.json").write_text(inj_out, encoding="utf-8")

# --- 对比摘要 ---
def peek(fp):
    raw = Path(fp).read_text(encoding="utf-8")
    try:
        d = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    except Exception as e:
        return {"parse_error": str(e), "head": raw[:200]}
    what = d.get("what") or {}
    return {
        "content_strategy": what.get("content_strategy"),
        "top_themes": what.get("top_themes"),
        "hook_patterns": what.get("hook_patterns"),
    }

pb, pi = peek(OUT / "out_base.json"), peek(OUT / "out_injected.json")
print("\n===== BASE (无字幕实证) =====")
print(json.dumps(pb, ensure_ascii=False, indent=1)[:1500])
print("\n===== INJECTED (带字幕实证) =====")
print(json.dumps(pi, ensure_ascii=False, indent=1)[:1500])
