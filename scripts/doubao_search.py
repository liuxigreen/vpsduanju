#!/usr/bin/env python3
"""豆包联网搜索 — 单任务：搜《以千金之名》热门标题和投放素材

只做一件事：调用豆包 ChatCompletions + web_search: true
查询 "以千金之名 抖音 热门标题 短剧投放素材"
返回原始文本，不做解析。
"""

import os, json, requests, base64
from pathlib import Path
from typing import Optional

# 自动加载 .env
_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
if _ENV_PATH.exists():
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v)

# 配置
ENDPOINT = "https://ark.cn-beijing.volces.com/api/v3/chat/completions"
MODEL = os.getenv("DOUBAO_SEARCH_MODEL", "YOUR_DOUBAO_SEARCH_MODEL_ID")

def doubao_web_search(
    query: str,
    model: str = MODEL,
    api_key: Optional[str] = None,
    max_tokens: int = 1500
) -> str:
    """
    调用豆包联网搜索
    """
    api_key = api_key or os.getenv("ARK_API_KEY")
    if not api_key:
        raise ValueError("ARK_API_KEY 未设置。请在 ~/duanju/.env 添加 ARK_API_KEY=your_key")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": query}
        ],
        "max_output_tokens": max_tokens,
        "extra_body": {
            "web_search": True  # 🔑 开启联网搜索
        }
    }
    
    resp = requests.post(ENDPOINT, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
    
    data = resp.json()
    return data["choices"][0]["message"]["content"]

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--query", default="以千金之名 抖音 热门标题 短剧投放素材", help="搜索查询")
    ap.add_argument("--model", default=MODEL, help="豆包模型 endpoint ID")
    ap.add_argument("--api-key", help="ARK_API_KEY（如未设置环境变量）")
    ap.add_argument("--out", default="data/douyin_titles/以千金之名_搜索结果.json", help="输出路径")
    args = ap.parse_args()

    # 确保输出目录
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    
    print(f"🔍 豆包联网搜索: {args.query}")
    print(f"   模型: {args.model}")
    
    try:
        result = doubao_web_search(args.query, model=args.model, api_key=args.api_key)
        print(f"\n✅ 搜索成功，返回 {len(result)} 字")
        print("─" * 60)
        print(result[:1000])  # 预览前1000字
        print("─" * 60)
        print(f"全文共 {len(result)} 字")
        
        # 保存原始结果
        with open(args.out, 'w', encoding='utf-8') as f:
            json.dump({
                "query": args.query,
                "model": args.model,
                "raw_result": result,
                "length": len(result)
            }, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 已保存原始搜索结果: {args.out}")
        
    except Exception as e:
        print(f"❌ 搜索失败: {e}")
        print("\n排查建议:")
        print("1. 检查 ARK_API_KEY 是否正确（从控制台复制）")
        print("2. 确认模型 endpoint 支持 web_search")
        print("3. 网络是否通畅")

if __name__ == "__main__":
    main()
