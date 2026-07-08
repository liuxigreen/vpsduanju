# -*- coding: utf-8 -*-
"""市场洞察模块

用LLM对竞品数据做聚合分析，生成市场洞察报告。
数据流：competitor_insights/ → LLM聚合 → market_insights_{lang}.json
"""
import sys
from pathlib import Path

from core.config import ROOT

# 复用原有脚本
sys.path.insert(0, str(ROOT / "scripts"))

# 导入原有脚本的核心函数
from market_insights import (
    _load_all_insights,
    _load_latest_stats,
    prepare_market_data,
    build_prompt,
    call_llm,
    analyze_market,
)


def market_insights(language: str = None):
    """生成市场洞察报告
    
    Args:
        language: 指定语种，None表示全部
    """
    from market_insights import main as market_main
    
    # 构建参数
    args = []
    if language:
        args.extend(["--language", language])
    
    # 调用原有脚本
    sys.argv = ["market_insights.py"] + args
    market_main()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="市场洞察分析")
    parser.add_argument("--language", type=str, help="指定语种")
    args = parser.parse_args()
    
    market_insights(args.language)
