#!/usr/bin/env python3
"""
短剧剧情库构建器
联网搜索 + 模型总结，存入本地 JSON 数据库。

用法：
    python3 drama_db_builder.py -f data/drama_names.txt
    python3 drama_db_builder.py -f data/drama_names.txt --skip-existing
    python3 drama_db_builder.py -n "剧名1" "剧名2"
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nuwa_api import PROVIDERS

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "drama_db.json"
INTERVAL = 3

# 联网搜索配置
SEARCH_ENDPOINT = "https://open.feedcoopapi.com/search_api/web_search"
SEARCH_API_KEY = "dK2EDDItDgc5Uhjw2sF0qg7b76Nrz0LY"

SUMMARY_PROMPT = """以下是联网搜索到的短剧《{name}》的相关信息，请基于这些搜索结果整理出详细剧情资料：

{search_results}

请按以下格式输出，内容越详细越好：
1. 【剧情概述】完整剧情介绍（包含起承转合、主要转折点、结局）
2. 【核心冲突】至少5个主要冲突点
3. 【热门标题】国内抖音/快手投放的热门标题和关键词（至少10个）
4. 【人物关系】主要角色及关系、性格特征
5. 【经典台词/钩子】爆款开场钩子、经典台词（至少5句）

1000-2000字，尽量详细。"""


def load_db() -> dict:
    if DB_PATH.exists():
        return json.loads(DB_PATH.read_text(encoding="utf-8"))
    return {}


def save_db(db: dict):
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2), encoding="utf-8")


def web_search(query: str, count: int = 5) -> str:
    """调用火山联网搜索API"""
    headers = {"Authorization": f"Bearer {SEARCH_API_KEY}", "Content-Type": "application/json"}
    payload = {"Query": query[:100], "SearchType": "web", "Count": count, "NeedSummary": True}
    try:
        resp = requests.post(SEARCH_ENDPOINT, headers=headers, json=payload, timeout=15)
        if resp.status_code != 200:
            return ""
        data = resp.json()
        results = data.get("Result", {}).get("WebResults", [])
        if not results:
            return ""
        lines = []
        for i, r in enumerate(results):
            title = r.get("Title", "")
            summary = r.get("Summary") or r.get("Snippet") or r.get("Content", "")
            lines.append(f"[{i+1}] {title}\n{summary[:500]}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"搜索失败: {e}"
    finally:
        time.sleep(0.3)  # QPS 5 限速保护


def call_model(prompt: str) -> str:
    """调用模型总结 — 优先用 m3（快），fallback 到其他"""
    # 重排序：m3 最快，放在第一位
    ordered = sorted(PROVIDERS, key=lambda p: 0 if "m3" in p["name"] else 1)
    for provider in ordered:
        try:
            resp = requests.post(
                f"{provider['base_url']}/chat/completions",
                headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
                json={"model": provider["model"], "messages": [{"role": "user", "content": prompt}], "max_tokens": 3000},
                timeout=120,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
        except Exception:
            continue
    return ""


def search_drama(name: str) -> dict:
    """联网搜索剧情（只用搜索API，不调模型）"""
    print(f"  🔍 联网搜索...", end="", flush=True)
    search_results = web_search(f"短剧《{name}》剧情 角色 冲突")
    if search_results:
        print(f" ✅ ({len(search_results)}字)")
        return {
            "name": name,
            "plot": search_results,
            "searched_at": datetime.now().isoformat(),
        }
    else:
        print(f" ⚠️ 无搜索结果")
        return {"name": name, "plot": "", "error": "no_search_result", "searched_at": datetime.now().isoformat()}


def parse_names(text: str) -> list[str]:
    names = re.split(r'[\n,，、;；]+', text)
    return [n.strip().strip("《》").strip() for n in names if n.strip().strip("《》").strip()]


def main():
    parser = argparse.ArgumentParser(description="短剧剧情库构建器")
    parser.add_argument("-f", "--file", help="剧名列表文件")
    parser.add_argument("-n", "--names", nargs="+", help="直接传剧名")
    parser.add_argument("-i", "--interval", type=int, default=INTERVAL)
    parser.add_argument("--skip-existing", action="store_true")
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    db = load_db()

    names = []
    if args.names:
        names = args.names
    elif args.file:
        names = parse_names(Path(args.file).read_text(encoding="utf-8"))
    else:
        print("📺 短剧剧情库构建器")
        print("输入剧名（每行一个，空行结束）：")
        while True:
            line = input("> ").strip()
            if not line:
                break
            names.extend(parse_names(line))

    if not names:
        print("没有输入任何剧名")
        return

    # 去重
    seen = set()
    unique = []
    for n in names:
        if n not in seen:
            seen.add(n)
            unique.append(n)
    names = unique

    if args.skip_existing:
        before = len(names)
        names = [n for n in names if n not in db or not db[n].get("plot")]
        if before - len(names):
            print(f"⏭️  跳过 {before - len(names)} 部已有剧情的剧")

    if args.test:
        names = names[:1]

    print(f"\n📋 共 {len(names)} 部剧待搜索，间隔 {args.interval}秒")
    print(f"📁 数据库: {DB_PATH}\n")

    success = 0
    for i, name in enumerate(names, 1):
        print(f"[{i}/{len(names)}] 《{name}》")
        if name in db and db[name].get("plot") and not args.skip_existing:
            overwrite = input(f"  ⚠️  已有剧情，覆盖？(y/N) ").strip().lower()
            if overwrite != "y":
                print(f"  ⏭️  跳过")
                continue

        result = search_drama(name)
        db[name] = result
        save_db(db)
        if result.get("plot"):
            success += 1

        if i < len(names):
            print(f"  ⏳ 等待 {args.interval}秒...")
            time.sleep(args.interval)

    print(f"\n✅ 完成！成功 {success}/{len(names)} 部")
    print(f"📁 数据库: {DB_PATH}")


if __name__ == "__main__":
    main()
