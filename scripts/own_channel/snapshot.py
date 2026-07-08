# -*- coding: utf-8 -*-
"""自有频道快照模块

自有频道的快照采集。
数据目录：data/own/
API Key：mtt0 (api_keys.json[1])
"""
import sys
from pathlib import Path

from core.config import ROOT

# 复用原有脚本
sys.path.insert(0, str(ROOT / "scripts"))


def snapshot():
    """采集自有频道快照"""
    from channel_weekly_snapshot import main as snapshot_main
    snapshot_main()


if __name__ == "__main__":
    snapshot()
