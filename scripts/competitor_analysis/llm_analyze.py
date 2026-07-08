# -*- coding: utf-8 -*-
"""竞品LLM分析模块

用LLM对竞品频道做深度分析。
数据流：latest.json → LLM分析 → competitor_insights/channel_{id}.json 的 llm_analysis 字段
"""
import sys
from pathlib import Path

from core.config import ROOT

# 复用原有脚本
sys.path.insert(0, str(ROOT / "scripts"))

# 导入原有脚本的核心函数
from llm_analyze_channel import (
    prepare_channel_data,
    build_prompt,
    call_llm,
    analyze_channel,
)


def llm_analyze_channel(channel_id: str = None, language: str = None, limit: int = None):
    """LLM分析竞品频道
    
    Args:
        channel_id: 指定频道ID
        language: 指定语种
        limit: 最大分析数量
    """
    from llm_analyze_channel import main as llm_main
    
    # 构建参数
    args = []
    if channel_id:
        args.extend(["--channel", channel_id])
    if language:
        args.extend(["--language", language])
    if limit:
        args.extend(["--limit", str(limit)])
    
    # 调用原有脚本
    sys.argv = ["llm_analyze_channel.py"] + args
    llm_main()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="竞品LLM分析")
    parser.add_argument("--channel", type=str, help="指定频道ID")
    parser.add_argument("--language", type=str, help="指定语种")
    parser.add_argument("--limit", type=int, help="最大分析数量")
    args = parser.parse_args()
    
    llm_analyze_channel(args.channel, args.language, args.limit)
