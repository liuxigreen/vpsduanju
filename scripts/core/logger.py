# -*- coding: utf-8 -*-
"""日志管理模块

统一管理 duanju 系统的日志，包括：
- 结构化日志
- trace_id 生成
- 日志文件写入
"""
import json
import logging
import uuid
from datetime import datetime
from pathlib import Path

from .config import ROOT

# 日志目录
LOGS_DIR = ROOT / "data" / "logs"

# 配置 logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)


def get_logger(name: str) -> logging.Logger:
    """获取 logger 实例
    
    Args:
        name: logger 名称（通常是模块名）
        
    Returns:
        logging.Logger 实例
    """
    return logging.getLogger(name)


def generate_trace_id() -> str:
    """生成 trace_id
    
    Returns:
        UUID 格式的 trace_id
    """
    return str(uuid.uuid4())


def log_structured(logger: logging.Logger, level: str, module: str, action: str,
                   status: str, data: dict = None, trace_id: str = None):
    """写入结构化日志
    
    Args:
        logger: logger 实例
        level: 日志级别（info, warning, error）
        module: 模块名
        action: 操作名
        status: 状态（success, error, warning）
        data: 附加数据
        trace_id: trace_id，如果为 None 则自动生成
    """
    if trace_id is None:
        trace_id = generate_trace_id()
    
    log_entry = {
        "timestamp": datetime.now().isoformat(),
        "trace_id": trace_id,
        "module": module,
        "action": action,
        "status": status,
        "data": data or {}
    }
    
    # 写入日志文件
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = LOGS_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
    
    # 同时输出到控制台
    msg = f"[{module}] {action} - {status}"
    if data:
        msg += f" | {json.dumps(data, ensure_ascii=False)}"
    
    if level == "info":
        logger.info(msg)
    elif level == "warning":
        logger.warning(msg)
    elif level == "error":
        logger.error(msg)
    else:
        logger.debug(msg)
    
    return trace_id


def log_api_call(logger: logging.Logger, api_name: str, endpoint: str,
                 status: str, duration_ms: int = None, error: str = None,
                 trace_id: str = None):
    """记录 API 调用日志
    
    Args:
        logger: logger 实例
        api_name: API 名称（如 "youtube", "edgefn"）
        endpoint: API 端点
        status: 状态（success, error）
        duration_ms: 耗时（毫秒）
        error: 错误信息
        trace_id: trace_id
    """
    data = {
        "api": api_name,
        "endpoint": endpoint,
    }
    if duration_ms is not None:
        data["duration_ms"] = duration_ms
    if error:
        data["error"] = error
    
    level = "info" if status == "success" else "error"
    return log_structured(logger, level, api_name, endpoint, status, data, trace_id)
