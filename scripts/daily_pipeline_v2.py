#!/usr/bin/env python3
"""
duanju 主流水线（重构版）

调度各模块完成竞品采集、分析、蒸馏等任务。
模块结构：
  core/ - 公共模块
  competitor/ - 竞品采集模块
  competitor_analysis/ - 竞品分析模块
  distill/ - 蒸馏数据模块
  own_channel/ - 自有频道模块

用法：
    python3 scripts/daily_pipeline.py                    # 完整流水线
    python3 scripts/daily_pipeline.py --step 1           # 只跑搜索
    python3 scripts/daily_pipeline.py --step 2           # 只跑采集
    python3 scripts/daily_pipeline.py --step 3           # 只跑筛选
    python3 scripts/daily_pipeline.py --step 4           # 只跑竞品分析
    python3 scripts/daily_pipeline.py --step 5a          # 只跑本地统计
    python3 scripts/daily_pipeline.py --step 6           # 只跑蒸馏
    python3 scripts/daily_pipeline.py --new-only         # 只采集新频道
    python3 scripts/daily_pipeline.py --language 英文     # 指定语种
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def step_1_discover(language: str = None, limit: int = 10):
    """Step 1: 搜索新频道"""
    from competitor.search import discover_channels
    return discover_channels(limit=limit, language=language)


def step_2_collect(language: str = None, new_only: bool = False, collect_all: bool = False):
    """Step 2: 采集数据"""
    from competitor.collect import collect_data
    return collect_data(language=language, new_only=new_only, collect_all=collect_all)


def step_3_screen():
    """Step 3: 筛选 staging → latest"""
    from competitor.screen import screen_staging, show_result, promote_to_latest
    passed, rejected = screen_staging()
    show_result(passed, rejected)
    if passed:
        promote_to_latest(passed)


def step_4_distill_competitors(language: str = None, per_lang: int = 1):
    """Step 4: 竞品频道分析"""
    from competitor_analysis.distill import distill_competitors
    distill_competitors(language=language, per_lang=per_lang)


def step_5a_evidence(language: str = None):
    """Step 5a: 本地统计"""
    from distill.evidence import evidence
    evidence(language=language)


def step_6_distill(language: str = None):
    """Step 6: 三层蒸馏"""
    from distill.evidence import rules
    rules(language=language)


def step_7_own_channel_snapshot():
    """Step 7: 自有频道快照"""
    from own_channel.snapshot import snapshot
    snapshot()


def step_8_own_channel_diagnosis():
    """Step 8: 自有频道诊断"""
    from own_channel.diagnosis import diagnosis
    diagnosis(all_channels=True)


def main():
    parser = argparse.ArgumentParser(description="duanju 主流水线")
    parser.add_argument("--step", type=str, help="指定步骤（1, 2, 3, 4, 5a, 6, 7, 8）")
    parser.add_argument("--new-only", action="store_true", help="只采集新频道")
    parser.add_argument("--all", action="store_true", help="全量采集/分析")
    parser.add_argument("--language", type=str, help="指定语种")
    parser.add_argument("--limit", type=int, default=10, help="搜索频道数量限制")
    parser.add_argument("--per-lang", type=int, default=1, help="每语种分析数量")
    args = parser.parse_args()
    
    print("=" * 50)
    print("🚀 duanju 主流水线")
    print("=" * 50)
    
    if args.step:
        # 只跑指定步骤
        if args.step == "1":
            step_1_discover(args.language, args.limit)
        elif args.step == "2":
            step_2_collect(args.language, args.new_only, args.all)
        elif args.step == "3":
            step_3_screen()
        elif args.step == "4":
            step_4_distill_competitors(args.language, args.per_lang)
        elif args.step == "5a":
            step_5a_evidence(args.language)
        elif args.step == "6":
            step_6_distill(args.language)
        elif args.step == "7":
            step_7_own_channel_snapshot()
        elif args.step == "8":
            step_8_own_channel_diagnosis()
        else:
            print(f"❌ 未知步骤: {args.step}")
            return
    else:
        # 完整流水线
        print("\n📋 Step 1: 搜索新频道")
        step_1_discover(args.language, args.limit)
        
        print("\n📋 Step 2: 采集数据")
        step_2_collect(args.language, args.new_only, args.all)
        
        print("\n📋 Step 3: 筛选 staging → latest")
        step_3_screen()
        
        print("\n📋 Step 4: 竞品频道分析")
        step_4_distill_competitors(args.language, args.per_lang)
        
        print("\n📋 Step 5a: 本地统计")
        step_5a_evidence(args.language)
        
        print("\n📋 Step 6: 三层蒸馏")
        step_6_distill(args.language)
        
        print("\n📋 Step 7: 自有频道快照")
        step_7_own_channel_snapshot()
        
        print("\n📋 Step 8: 自有频道诊断")
        step_8_own_channel_diagnosis()
    
    print("\n" + "=" * 50)
    print("✅ 流水线完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
