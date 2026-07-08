# -*- coding: utf-8 -*-
"""edgefn_models 适配器

为了保持向后兼容，原脚本可以继续 import edgefn_models，
实际功能已迁移到 core/llm_client.py。
"""
from core.llm_client import (
    CALL_INTERVAL,
    MODELS,
    TASK_MODEL,
    API_BASE,
    get_api_key,
    call_edgefn,
    call_for_task,
    parse_json_response,
)

# 保持原有接口不变
__all__ = [
    "CALL_INTERVAL",
    "MODELS",
    "TASK_MODEL",
    "API_BASE",
    "get_api_key",
    "call_edgefn",
    "call_for_task",
    "parse_json_response",
]
