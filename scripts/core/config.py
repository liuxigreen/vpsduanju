# -*- coding: utf-8 -*-
"""配置管理模块

统一管理 duanju 系统的配置，包括：
- 路径配置
- API Key 配置
- 数据目录配置
"""
import os
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent.parent

# 数据目录
DATA_DIR = ROOT / "data"
COMPETITOR_DATA_DIR = DATA_DIR / "competitor_data"
OWN_DATA_DIR = DATA_DIR / "own"
DISTILL_DIR = DATA_DIR / "distill"
COMPETITOR_INSIGHTS_DIR = DATA_DIR / "competitor_insights"
COMPETITOR_TRACKING_DIR = DATA_DIR / "competitor_tracking"

# 脚本目录
SCRIPTS_DIR = ROOT / "scripts"

# 知识库目录（duanju profile）
KNOWLEDGE_DIR = Path.home() / ".hermes" / "profiles" / "duanju" / "knowledge"

# API Key 文件路径
API_KEY_FILE = Path.home() / ".hermes" / "duanju" / "api_key.txt"
API_KEYS_FILE = Path.home() / ".hermes" / "duanju" / "api_keys.json"

# 面板数据文件
PANEL_DATA_FILE = DATA_DIR / "competitors_channels_all.json"

# 定时任务相关
TIERS_FILE = DATA_DIR / "competitor_tiers.json"
STAGING_FILE = COMPETITOR_DATA_DIR / "staging.json"
LATEST_FILE = COMPETITOR_DATA_DIR / "latest.json"


def get_youtube_api_key(index: int = 0) -> str:
    """获取 YouTube API Key
    
    Args:
        index: key索引
        - 0: api_key.txt (pUaE) - 竞品采集专用
        - 1: api_keys.json[0] (19Nc) - 竞品采集专用
        - 2: api_keys.json[1] (mtt0) - 自有频道专用
    
    Returns:
        API key 字符串
    """
    if index == 0:
        # 读取 api_key.txt
        if API_KEY_FILE.exists():
            return API_KEY_FILE.read_text().strip()
    else:
        # 读取 api_keys.json
        if API_KEYS_FILE.exists():
            import json
            try:
                keys = json.loads(API_KEYS_FILE.read_text())
                if index - 1 < len(keys):
                    return keys[index - 1]
            except:
                pass
    return ""


def get_competitor_api_keys() -> list:
    """获取竞品采集专用的 API keys
    
    Returns:
        [pUaE, 19Nc] 两个 key
    """
    keys = []
    key1 = get_youtube_api_key(0)  # pUaE
    if key1:
        keys.append(key1)
    key2 = get_youtube_api_key(1)  # 19Nc
    if key2:
        keys.append(key2)
    return keys


def get_own_channel_api_key() -> str:
    """获取自有频道专用的 API key
    
    Returns:
        mtt0 key
    """
    return get_youtube_api_key(2)  # mtt0


def ensure_dirs():
    """确保所有必要的数据目录存在"""
    dirs = [
        DATA_DIR,
        COMPETITOR_DATA_DIR,
        OWN_DATA_DIR,
        DISTILL_DIR,
        COMPETITOR_INSIGHTS_DIR,
        COMPETITOR_TRACKING_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
