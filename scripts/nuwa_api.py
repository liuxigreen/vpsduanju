#!/usr/bin/env python3
"""nuwa 分析层 — 调用 Bank of AI（非豆包），专用于运营决策"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

import requests

# ============ 加载 .env ============
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

# ============ Agent Plan 配置 ============
_ARK_API_KEY = os.environ.get("DOUBAO_API_KEY", "")
PROVIDERS = [
    {
        "name": "agent-plan-pro",
        "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "api_key": _ARK_API_KEY,
        "model": "doubao-seed-2.0-pro",
    },
    {
        "name": "agent-plan-m3",
        "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "api_key": _ARK_API_KEY,
        "model": "minimax-m3",
    },
    {
        "name": "agent-plan-kimi",
        "base_url": "https://ark.cn-beijing.volces.com/api/plan/v3",
        "api_key": _ARK_API_KEY,
        "model": "kimi-k2.6",
    },
]

# 模型别名映射（面板选择用）
MODEL_ALIASES = {
    "pro": "doubao-seed-2.0-pro",
    "m3": "minimax-m3",
    "kimi": "kimi-k2.6",
    "ark-code-latest": "ark-code-latest",
}

# 过滤掉没有 key 的 provider
PROVIDERS = [p for p in PROVIDERS if p["api_key"]]
if not PROVIDERS:
    raise RuntimeError("Agent Plan API Key 未设置")

# 轮询计数器
_provider_idx = 0


def _get_provider(rotate: bool = False):
    """获取 provider。rotate=True 时轮流切换，False 时固定用第一个可用的。"""
    global _provider_idx
    if rotate:
        idx = _provider_idx % len(PROVIDERS)
        _provider_idx += 1
        return PROVIDERS[idx]
    return PROVIDERS[0]


def nuwa_chat(
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    rotate: bool = False,
    json_mode: bool = False,
    timeout: int = 120,
) -> str:
    """
    nuwa 分析接口 — 三 provider 轮询 + 指数退避重试。
    rotate=True: 每次调用轮流切换 provider。
    json_mode=True: 强制模型输出 JSON（减少解析失败）。
    返回 (content, meta) 元组，meta 包含实际使用的 provider。
    """
    global _provider_idx
    providers_to_try = []
    if rotate:
        start = _provider_idx % len(PROVIDERS)
        providers_to_try = PROVIDERS[start:] + PROVIDERS[:start]
        _provider_idx += 1
    else:
        providers_to_try = PROVIDERS

    last_error = ""
    for attempt in range(3):  # 每个 provider 最多重试3次
        for p in providers_to_try:
            headers = {
                "Authorization": f"Bearer {p['api_key']}",
                "Content-Type": "application/json",
            }
            payload = {
                "model": model or p["model"],
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
            if json_mode:
                payload["response_format"] = {"type": "json_object"}

            try:
                resp = requests.post(
                    f"{p['base_url']}/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    content = (
                        data.get("choices", [{}])[0]
                        .get("message", {})
                        .get("content", "")
                    )
                    if content and len(content) > 1:
                        # 记录成功 provider
                        _last_provider = p["name"]
                        return content
                elif resp.status_code == 429:
                    last_error = f"{p['name']} rate limited"
                    continue
                else:
                    last_error = f"{p['name']} HTTP {resp.status_code}"
            except requests.exceptions.Timeout:
                last_error = f"{p['name']} timeout"
            except Exception as e:
                last_error = f"{p['name']} {type(e).__name__}: {str(e)[:50]}"

        # 指数退避
        import time
        time.sleep(2 ** attempt)

    return ""


def nuwa_chat_structured(
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 4000,
    temperature: float = 0.7,
    rotate: bool = False,
) -> dict:
    """强制 JSON 输出并解析，失败返回 {"error": ..., "raw": ...}"""
    raw = nuwa_chat(
        prompt,
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        rotate=rotate,
        json_mode=True,
    )
    if not raw:
        return {"error": "all_providers_failed", "raw": ""}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"error": "json_parse_failed", "raw": raw[:500]}


def nuwa_chat_stream(
    prompt: str,
    model: Optional[str] = None,
    max_tokens: int = 4000,
    rotate: bool = False,
) -> str:
    """流式版本 — 适合长输出。"""
    providers_to_try = []
    if rotate:
        start = _provider_idx % len(PROVIDERS)
        providers_to_try = PROVIDERS[start:] + PROVIDERS[:start]
    else:
        providers_to_try = PROVIDERS

    for p in providers_to_try:
        headers = {
            "Authorization": f"Bearer {p['api_key']}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": model or p["model"],
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
            "stream": True,
        }
        try:
            chunks = []
            resp = requests.post(
                f"{p['base_url']}/chat/completions",
                headers=headers,
                json=payload,
                timeout=90,
                stream=True,
            )
            for line in resp.iter_lines():
                if not line:
                    continue
                line = line.decode("utf-8")
                if line.startswith("data: "):
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                        delta = (
                            chunk.get("choices", [{}])[0]
                            .get("delta", {})
                            .get("content", "")
                        )
                        chunks.append(delta)
                    except (json.JSONDecodeError, KeyError):
                        continue
            result = "".join(chunks)
            if result and len(result) > 10:
                if rotate:
                    _provider_idx += 1
                return result
        except Exception:
            pass

    return ""


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        prompt = "你是短剧运营总监。短剧《以千金之名》，真假千金重生复仇，给3个HK风格标题。"

    # 测试双 provider 轮询
    for i, _ in enumerate(PROVIDERS):
        p = PROVIDERS[i]
        print(f"Provider: {p['name']} | Model: {p['model']}")
    print(f"Prompt: {prompt[:50]}...")
    print("-" * 40)

    result = nuwa_chat(prompt, rotate=True)
    print(result)
