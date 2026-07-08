#!/usr/bin/env python3
"""豆包大模型 HTTP API 调用（火山引擎 Ark）

不需要 volcengine-sdk，直接 requests 调用，更轻。
模型 endpoint 格式：ark.cn-beijing.volcengine.com
"""

from __future__ import annotations
import argparse, json, os, requests
from typing import Optional

ENDPOINT_BASE = "https://ark.cn-beijing.volcengine.com/api/v3/chat/completions"

def doubao_chat(messages: list, model: str = None, temperature: float = 0.7, max_tokens: int = 500) -> str:
    api_key = os.getenv("VOLC_ACCESSKEY_ID")
    secret = os.getenv("VOLC_ACCESSKEY_SECRET")
    model = model or os.getenv("DOUBAO_ENDPOINT_ID") or "ep-20240605123456-abcdef"

    if not api_key or not secret:
        raise ValueError("请设置 VOLC_ACCESSKEY_ID 和 VOLC_ACCESSKEY_SECRET")

    # 火山引擎用 Bearer Token（AK:SK base64）
    import base64
    token = base64.b64encode(f"{api_key}:{secret}".encode()).decode()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    resp = requests.post(ENDPOINT_BASE, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"{resp.status_code}: {resp.text[:200]}")
    data = resp.json()
    return data["choices"][0]["message"]["content"]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prompt", help="提问内容")
    ap.add_argument("--titles", help="热门标题JSON文件路径（用于衍生）")
    ap.add_argument("--count", type=int, default=10, help="衍生标题数量")
    ap.add_argument("--style", default="youtube", help="平台风格")
    ap.add_argument("--out", default="", help="输出文件")
    args = ap.parse_args()

    if args.titles:
        # 读取热门标题 → 衍生
        with open(args.titles) as f:
            data = json.load(f)
        base_titles = data.get("热门标题", [])
        print(f"✅ 加载 {len(base_titles)} 个热门标题")
        # 构造 prompt
        p = f"""
        你是女频短剧标题专家。基于以下热门标题，生成{args.count}个新标题（风格：{args.style}）：

        热门标题样本：
        {chr(10).join([f"- {t}" for t in base_titles[:5]])}

        要求：
        1. 保留核心关键词（豪门/甜宠/重生/契约/千金）
        2. 加入emoji（💎💕🔥✨）
        3. 长度30-60字
        4. 输出纯标题列表，每行一个，不要编号
        """
        result = doubao_chat([{"role": "user", "content": p}])
        titles = [l.strip() for l in result.split("\n") if l.strip()]
        print(f"✅ 衍生 {len(titles)} 个标题:")
        for t in titles:
            print(f"  - {t}")
        out = args.out or f"output/titles/衍生_{data.get('剧名','unknown')}.json"
        os.makedirs(os.path.dirname(out), exist_ok=True)
        with open(out, 'w', encoding='utf-8') as f:
            json.dump({"source": args.titles, "derived_titles": titles}, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已保存: {out}")

    elif args.prompt:
        result = doubao_chat([{"role": "user", "content": args.prompt}])
        print(result)
        if args.out:
            with open(args.out, 'w', encoding='utf-8') as f:
                f.write(result)
            print(f"✅ 保存: {args.out}")

if __name__ == "__main__":
    main()
