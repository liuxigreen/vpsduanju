#!/usr/bin/env python3
"""
竞品频道统一管线

串联：筛选 → 追踪 → LLM分析 → 再筛选 → 市场洞察 → 面板刷新

用法：
    python3 scripts/run_competitor_pipeline.py           # 标准运行（增量）
    python3 scripts/run_competitor_pipeline.py --full     # 全量重跑
    python3 scripts/run_competitor_pipeline.py --filter-only  # 只筛选+追踪
    python3 scripts/run_competitor_pipeline.py --status    # 查看状态
"""

import json
import sys
import argparse
import os
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter, defaultdict

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.stdout.reconfigure(line_buffering=True)

from distill_competitors import filter_by_tier, track_daily, update_panel_data

DATA_DIR = ROOT / "data"
INSIGHT_DIR = DATA_DIR / "competitor_insights"
PIPELINE_STATE_FILE = DATA_DIR / "_pipeline_state.json"


def _load_state() -> dict:
    if PIPELINE_STATE_FILE.exists():
        try:
            return json.loads(PIPELINE_STATE_FILE.read_text())
        except:
            pass
    return {
        "last_run": "",
        "last_market_insights": {},
        "llm_analyzed_count": {},
    }


def _save_state(state: dict):
    state["last_run"] = datetime.now().isoformat()
    PIPELINE_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def _count_llm_analyzed() -> dict:
    """统计每个语种的LLM分析数量"""
    tracker_file = INSIGHT_DIR / "_llm_analyzed.json"
    if not tracker_file.exists():
        return {}
    tracker = json.loads(tracker_file.read_text())
    by_lang = Counter()
    for info in tracker.get("analyzed", {}).values():
        by_lang[info.get("language", "未知")] += 1
    return dict(by_lang)


def _count_new_since(state: dict) -> dict:
    """统计每个语种新增的LLM分析数量"""
    current = _count_llm_analyzed()
    prev = state.get("llm_analyzed_count", {})
    delta = {}
    for lang, count in current.items():
        prev_count = prev.get(lang, 0)
        if count > prev_count:
            delta[lang] = count - prev_count
    return delta


def _should_run_market_insights(state: dict, min_new: int = 5, max_days: int = 7) -> list:
    """判断哪些语种需要跑市场洞察"""
    current = _count_llm_analyzed()
    prev = state.get("llm_analyzed_count", {})
    last_runs = state.get("last_market_insights", {})

    langs_to_run = []
    for lang, count in current.items():
        if count < 3:  # 至少3个频道才跑
            continue
        prev_count = prev.get(lang, 0)
        new_count = count - prev_count

        # 条件1：新增≥5个
        if new_count >= min_new:
            langs_to_run.append(lang)
            continue

        # 条件2：距上次≥7天
        last_str = last_runs.get(lang, "")
        if last_str:
            try:
                last_dt = datetime.fromisoformat(last_str)
                if datetime.now() - last_dt > timedelta(days=max_days):
                    langs_to_run.append(lang)
            except:
                langs_to_run.append(lang)
        else:
            # 从未跑过
            langs_to_run.append(lang)

    return langs_to_run


def step1_filter():
    """第一步：筛选（题材去重）"""
    print(f"\n{'='*60}")
    print(f"📋 Step 1: 筛选（tier + 题材去重）")
    print(f"{'='*60}")
    selected = filter_by_tier()
    return selected


def step2_track(selected):
    """第二步：每日追踪（订阅+播放量）"""
    print(f"\n{'='*60}")
    print(f"📊 Step 2: 每日追踪")
    print(f"{'='*60}")
    track_daily(selected)


def step3_llm_analyze(limit: int = 0, force: bool = False):
    """第三步：LLM深度分析（只分析未分析过的）"""
    print(f"\n{'='*60}")
    print(f"🧠 Step 3: LLM频道分析")
    print(f"{'='*60}")

    cmd = f"cd {ROOT} && python3 scripts/llm_analyze_channel.py"
    if force:
        cmd += " --all"
    if limit:
        cmd += f" --limit {limit}"
    print(f"  执行: {cmd}")
    exit_code = os.system(cmd)
    return exit_code == 0


def step4_refilter():
    """第四步：用LLM题材再筛选（补充新题材频道）"""
    print(f"\n{'='*60}")
    print(f"🔄 Step 4: 精筛（LLM题材去重）")
    print(f"{'='*60}")
    selected = filter_by_tier()
    return selected


def step5_market_insights(langs: list):
    """第五步：市场洞察（按语种）"""
    if not langs:
        print(f"\n⏭️ Step 5: 市场洞察 — 无需更新")
        return True

    print(f"\n{'='*60}")
    print(f"🌏 Step 5: 市场洞察 ({', '.join(langs)})")
    print(f"{'='*60}")

    for lang in langs:
        cmd = f"cd {ROOT} && python3 scripts/market_insights.py --language '{lang}'"
        print(f"  执行: {cmd}")
        os.system(cmd)

    return True


def step6_panel():
    """第六步：刷新面板数据"""
    print(f"\n{'='*60}")
    print(f"🖥️ Step 6: 刷新面板数据")
    print(f"{'='*60}")
    update_panel_data()


def show_status():
    """显示管线状态"""
    state = _load_state()
    llm_counts = _count_llm_analyzed()

    print(f"竞品频道管线状态")
    print(f"{'='*50}")
    print(f"上次运行: {state.get('last_run', '从未')}")
    print(f"\nLLM已分析频道:")
    total = 0
    for lang, count in sorted(llm_counts.items()):
        print(f"  {lang}: {count}")
        total += count
    print(f"  合计: {total}")

    print(f"\n市场洞察上次更新:")
    for lang, ts in state.get("last_market_insights", {}).items():
        print(f"  {lang}: {ts}")

    # 面板数据
    panel_file = DATA_DIR / "competitors_channels_all.json"
    if panel_file.exists():
        data = json.loads(panel_file.read_text())
        channels = data.get("channels", [])
        has_llm = sum(1 for c in channels if c.get("llm_distill"))
        print(f"\n面板: {len(channels)} 频道, {has_llm} 有LLM洞察")


def main():
    parser = argparse.ArgumentParser(description="竞品频道统一管线")
    parser.add_argument("--full", action="store_true", help="全量重跑")
    parser.add_argument("--filter-only", action="store_true", help="只筛选+追踪")
    parser.add_argument("--status", action="store_true", help="查看状态")
    parser.add_argument("--llm-limit", type=int, default=0, help="LLM分析数量限制")
    args = parser.parse_args()

    if args.status:
        show_status()
        return

    state = _load_state()

    # Step 1: 筛选
    selected = step1_filter()
    if not selected:
        print("❌ 筛选结果为空")
        return

    # Step 2: 每日追踪
    step2_track(selected)

    if args.filter_only:
        step6_panel()
        _save_state(state)
        return

    # Step 3: LLM分析
    step3_llm_analyze(limit=args.llm_limit, force=args.full)

    # Step 4: 精筛
    selected = step4_refilter()
    step2_track(selected)  # 新频道也追踪

    # Step 5: 市场洞察（增量判断）
    langs = _should_run_market_insights(state)
    step5_market_insights(langs)

    # 更新市场洞察时间
    for lang in langs:
        state.setdefault("last_market_insights", {})[lang] = datetime.now().isoformat()

    # Step 6: 面板
    step6_panel()

    # 保存状态
    state["llm_analyzed_count"] = _count_llm_analyzed()
    _save_state(state)

    print(f"\n{'='*60}")
    print(f"✅ 管线完成")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
