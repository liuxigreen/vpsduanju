# -*- coding: utf-8 -*-
"""自有频道诊断模块

自有频道的诊断分析。
数据目录：data/own/diagnosis/
"""
import sys
from pathlib import Path

from core.config import ROOT

# 复用原有脚本
sys.path.insert(0, str(ROOT / "scripts"))


def diagnosis(channel: str = None, all_channels: bool = False, no_llm: bool = False):
    """诊断自有频道
    
    Args:
        channel: 指定频道名
        all_channels: 是否诊断所有频道
        no_llm: 是否禁用LLM
    """
    from diagnose_channel import main as diagnosis_main
    
    # 构建参数
    args = []
    if channel:
        args.extend(["--channel", channel])
    if all_channels:
        args.append("--all")
    if no_llm:
        args.append("--no-llm")
    
    # 调用原有脚本
    sys.argv = ["diagnose_channel.py"] + args
    diagnosis_main()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="自有频道诊断")
    parser.add_argument("--channel", type=str, help="指定频道名")
    parser.add_argument("--all", action="store_true", help="诊断所有频道")
    parser.add_argument("--no-llm", action="store_true", help="禁用LLM")
    args = parser.parse_args()
    
    diagnosis(args.channel, args.all, args.no_llm)
