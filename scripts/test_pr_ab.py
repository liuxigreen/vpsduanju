#!/usr/bin/env python3
"""PR(市场洞察)注入 AB 测试 — 沙箱运行，不覆盖线上 market_insights_*.json
用法: python3 scripts/test_pr_ab.py [日语]
产物: data/subtitle_analysis/ab_test/pr_out_{base|inj}_{lang}.json
"""
import json, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import market_insights as mi
import subtitle_evidence
import yaml, requests

LANG_CN = {'日语': 'ja', '印尼': 'id', '英文': 'en', '西语': 'es',
           '葡萄牙': 'pt', '土耳其': 'tr', '繁中': 'zh-Hant'}

cfg = yaml.safe_load(open(Path.home() / ".hermes/config.yaml"))
prov = (cfg.get("provider") or cfg["providers"])["bai"]
API_KEY, BASE_URL = prov["api_key"], prov["base_url"].rstrip("/")
# 生产洞察(run_insights_current_model.py 7/7成功)用 qwen3.8-flash；config 默认 glm-5.3-flash
# 在 bai 上对长分析任务思考模式退化(27K think无正文,9min零输出)，故测试对齐生产模型
MODEL = "qwen3.8-flash"

OUT = ROOT / "data/subtitle_analysis/ab_test"
OUT.mkdir(parents=True, exist_ok=True)
LANG = sys.argv[1] if len(sys.argv) > 1 else "日语"
LC = LANG_CN[LANG]

# ---- 数据层（与 run_insights_current_model.py 同门槛）----
all_ins = mi._load_all_insights()
latest_stats = mi._load_latest_stats()
filtered = [ch for ch in all_ins
            if latest_stats.get(ch.get("channel_id", ""), {}).get("video_momentum", 0) >= 10000
            or latest_stats.get(ch.get("channel_id", ""), {}).get("avg_views", 0) >= 10000]
channels = [ch for ch in filtered if ch.get("language") == LANG]
print(f"{LANG}: {len(channels)} 个频道过门槛(动量或均播≥1万)")
assert len(channels) >= 3, "频道数不足"

data = mi.prepare_market_data(LANG, channels, latest_stats)
base_prompt = mi.build_prompt(data)

block = subtitle_evidence.market_subtitle_block(LC)
assert block, "market subtitle block 为空"
anchor = "短剧市场的整体洞察。\n\n"
assert anchor in base_prompt, f"注入锚点缺失"
inj_prompt = base_prompt.replace(anchor, anchor + block + "\n\n", 1)
print(f"prompt: base={len(base_prompt)} chars / injected={len(inj_prompt)} chars (+{len(inj_prompt)-len(base_prompt)})")
(OUT / f"pr_prompt_base_{LC}.txt").write_text(base_prompt, encoding="utf-8")
(OUT / f"pr_prompt_inj_{LC}.txt").write_text(inj_prompt, encoding="utf-8")


def call_bai(prompt):
    fr, msg, last = None, "", None
    for attempt in range(5):
        try:
            r = requests.post(f"{BASE_URL}/chat/completions",
                              headers={"Authorization": f"Bearer {API_KEY}"},
                              json={"model": MODEL, "messages": [{"role": "user", "content": prompt + "\n/no_think"}],
                                    "max_tokens": 32000, "temperature": 0.3},
                              timeout=600)
        except requests.RequestException as e:
            last = e
            print(f"  ⏳ 连接异常 {type(e).__name__}，等60s重试 ({attempt+1}/5)")
            time.sleep(60)
            continue
        if r.status_code == 429:
            wait = 45 * (attempt + 1)
            print(f"  ⏳ 429，等 {wait}s ({attempt+1}/5)")
            time.sleep(wait)
            continue
        r.raise_for_status()
        j = r.json()
        msg = j["choices"][0]["message"]["content"] or ""
        fr = j["choices"][0].get("finish_reason")
        print(f"  finish_reason={fr}, out_chars={len(msg)}")
        if not msg.strip():
            time.sleep(30); continue
        if msg.count("{") > msg.count("}"):
            print(f"  ⏳ JSON截断 ({{={msg.count('{')} }}={msg.count('}')})，重试")
            time.sleep(20); continue
        return msg
    raise RuntimeError(f"bai 连续失败: fr={fr} chars={len(msg)} exc={last}")


for tag, p in (("base", base_prompt), ("inj", inj_prompt)):
    fp = OUT / f"pr_out_{tag}_{LC}.json"
    if fp.exists() and fp.stat().st_size > 500:
        print(f"✔ {tag} 已存在，跳过")
        continue
    print(f"▶ {tag}...")
    out = call_bai(p)
    fp.write_text(json.dumps({"meta": {"language": LANG, "model": f"bai/{MODEL}",
                                       "variant": tag, "subtitle_evidence": tag == "inj"},
                               "raw": out}, ensure_ascii=False), encoding="utf-8")
    print(f"✅ {tag} → {fp.name}")

print("\n完成。跑 scripts/ab_compare_pr.py 看对比。")
