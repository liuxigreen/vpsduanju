#!/usr/bin/env python3
"""豆包 API 统一封装（Agent Plan 模型 + 火山联网搜索API）"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests

# 自动加载 .env
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

# 模型 API（Agent Plan）
MODEL_ENDPOINT = "https://ark.cn-beijing.volces.com/api/plan/v3/chat/completions"
MODEL = os.getenv("DOUBAO_MODEL", "doubao-seed-2-0-pro-260215")
API_KEY = os.getenv("ARK_API_KEY", "")

# 联网搜索 API（独立服务）
SEARCH_ENDPOINT = "https://open.feedcoopapi.com/search_api/web_search"
SEARCH_API_KEY = os.getenv("VOLC_SEARCH_API_KEY", "")


def _web_search(query: str, count: int = 5) -> str:
    """调用火山联网搜索API，返回格式化文本"""
    if not SEARCH_API_KEY:
        return ""

    headers = {
        "Authorization": f"Bearer {SEARCH_API_KEY}",
        "Content-Type": "application/json"
    }
    payload = {
        "Query": query[:100],
        "SearchType": "web",
        "Count": count,
        "NeedSummary": True,
    }
    try:
        resp = requests.post(SEARCH_ENDPOINT, headers=headers, json=payload, timeout=30)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        results = data.get("Result", {}).get("WebResults", [])
        if not results:
            return ""
        # 格式化搜索结果
        lines = []
        for i, r in enumerate(results):
            title = r.get("Title", "")
            url = r.get("Url", "")
            summary = r.get("Summary") or r.get("Snippet") or r.get("Content", "")
            lines.append(f"[{i+1}] {title}\n    URL: {url}\n    摘要: {summary[:300]}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"搜索失败: {e}"


def call_doubao(
    messages: list[dict],
    model: str = MODEL,
    api_key: Optional[str] = None,
    max_tokens: int = 2000,
    enable_search: bool = False,
) -> str:
    """
    调用豆包 API

    Args:
        messages: [{"role": "user", "content": "..."}]
        enable_search: True时先用联网搜索API获取信息，再让模型基于搜索结果回答
    """
    api_key = api_key or API_KEY
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    if enable_search:
        # 从最后一条用户消息提取搜索query
        user_msg = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                user_msg = m.get("content", "")
                break
        if user_msg:
            search_results = _web_search(user_msg)
            if search_results:
                # 把搜索结果注入到消息中
                enhanced_messages = list(messages)
                enhanced_messages.append({
                    "role": "system",
                    "content": f"以下是联网搜索结果，请基于这些信息回答用户问题：\n\n{search_results}"
                })
                messages = enhanced_messages

    payload = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
    }

    resp = requests.post(MODEL_ENDPOINT, headers=headers, json=payload, timeout=300)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")

    data = resp.json()
    choices = data.get("choices", [])
    if choices:
        return choices[0].get("message", {}).get("content", "")
    return ""


def doubao_search(query: str, **kwargs) -> str:
    """便捷搜索：联网搜索 + 模型回答"""
    return call_doubao([{"role": "user", "content": query}], enable_search=True, **kwargs)


def doubao_chat(messages: list[dict], **kwargs) -> str:
    """便捷聊天（不带搜索）"""
    return call_doubao(messages, enable_search=False, **kwargs)


if __name__ == "__main__":
    result = call_doubao(
        [{"role": "user", "content": "搜索短剧《离开不必回头》的主演和剧情"}],
        max_tokens=500,
        enable_search=True,
    )
    print(result[:500])
