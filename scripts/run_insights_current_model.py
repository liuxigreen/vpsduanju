#!/usr/bin/env python3
"""用当前主模型(bai/qwen3.8-flash)亲自跑市场洞察。
复用 market_insights.py 的数据加载/prompt构建/落盘逻辑，只替换 call_llm 的模型层。
用法: python3 scripts/run_insights_current_model.py 日语 印尼 英文
"""
import json, sys, time
from pathlib import Path
from datetime import datetime

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "scripts"))

import yaml
cfg = yaml.safe_load(open(Path.home() / ".hermes/config.yaml"))
prov = (cfg.get("provider") or cfg["providers"])["bai"]
API_KEY, BASE_URL, MODEL = prov["api_key"], prov["base_url"].rstrip("/"), cfg["model"]["default"]

import market_insights as mi
from edgefn_models import parse_json_response

import requests

def call_llm_bai(prompt: str):
    r = requests.post(
        f"{BASE_URL}/chat/completions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"model": MODEL, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 16000, "temperature": 0.3},
        timeout=600,
    )
    r.raise_for_status()
    content = r.json()["choices"][0]["message"]["content"]
    usage = r.json().get("usage", {})
    print(f"    📊 tokens: in={usage.get('prompt_tokens',0):,} out={usage.get('completion_tokens',0):,}")
    if not content.strip():
        print("    ❌ 空响应")
        return None
    parsed = parse_json_response({"content": content})
    if "error" in parsed:
        Path(f"/tmp/insight_raw_{int(time.time())}.txt").write_text(content)
        print(f"    ❌ {parsed['error']}，原始文本存 /tmp/insight_raw_*.txt")
        return None
    return parsed

def main():
    langs = sys.argv[1:]
    if not langs:
        print("用法: run_insights_current_model.py 语种1 [语种2...]")
        sys.exit(1)

    all_insights = mi._load_all_insights()
    latest_stats = mi._load_latest_stats()
    filtered = [ch for ch in all_insights
                if latest_stats.get(ch.get("channel_id", ""), {}).get("video_momentum", 0) >= 10000
                or latest_stats.get(ch.get("channel_id", ""), {}).get("avg_views", 0) >= 10000]

    # monkeypatch：数据/落盘全走官方逻辑，只换模型层
    mi.call_llm = call_llm_bai
    mi.MODEL = f"bai/{MODEL}"

    ok = 0
    for lang in langs:
        channels = [ch for ch in filtered if ch.get("language") == lang]
        if len(channels) < 3:
            print(f"⏭️ {lang}: 只有{len(channels)}个频道(<3)，跳过")
            continue
        print(f"\n▶ {lang} 市场 ({len(channels)} 个频道) — 模型 bai/{MODEL}")
        out = mi.analyze_market(lang, channels, latest_stats)
        if out:
            li = out["llm_insights"]
            print(f"    热门: {', '.join(str(x) for x in (li.get('trending_genres') or [])[:5])}")
            print(f"    上升: {', '.join(str(x) for x in (li.get('rising_genres') or [])[:5])}")
            cs = li.get("cover_style") or ""
            print(f"    封面: {str(cs)[:90]}")
            ok += 1
        time.sleep(3)
    print(f"\n✅ 完成 {ok}/{len(langs)}")

if __name__ == "__main__":
    main()
