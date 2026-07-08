#!/usr/bin/env python3
"""
MiMo 蒸馏测试：用 GPT55 同样的筛选样本量
测试 MiMo 在小样本下的质量
"""

import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

# 导入 daily_pipeline 的蒸馏函数
from daily_pipeline import _build_three_layer_prompt

OUTPUT_DIR = ROOT / "distill" / "outputs"
EVIDENCE_DIR = ROOT / "distill" / "evidence"


def load_filtered_evidence(lang: str, max_titles: int = 60) -> dict:
    """加载筛选后的证据数据（与 GPT55 相同的筛选逻辑）"""
    lang_dir = EVIDENCE_DIR / lang
    
    # 加载标题
    titles_file = lang_dir / "titles.json"
    if not titles_file.exists():
        print(f"❌ {lang} — 无 titles.json")
        return None
    
    all_titles = json.loads(titles_file.read_text())
    print(f"📊 原始标题: {len(all_titles)} 个")
    
    # 筛选：按播放量排序取 Top N
    titles_sorted = sorted(all_titles, key=lambda x: x.get("views", 0), reverse=True)
    filtered_titles = titles_sorted[:max_titles]
    print(f"📊 筛选后: {len(filtered_titles)} 个（Top {max_titles} by views）")
    
    # 加载其他维度
    evidence = {"titles": filtered_titles}
    for dim in ["timing", "tags", "emoji", "hashtag", "length"]:
        f = lang_dir / f"{dim}.json"
        if f.exists():
            evidence[dim] = json.loads(f.read_text())
    
    return evidence


def call_mimo(prompt: str, max_tokens: int = 32768) -> str:
    """调用 MiMo API"""
    import http.client
    import ssl
    
    mimo_key = os.environ.get("XIAOMI_API_KEY", "")
    if not mimo_key:
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            for line in env_path.read_text().split("\n"):
                if "XIAOMI_API_KEY" in line:
                    mimo_key = line.split("=", 1)[1].strip()
                    break
    if not mimo_key:
        raise RuntimeError("未配置 XIAOMI_API_KEY")
    
    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection("token-plan-cn.xiaomimimo.com", context=ctx, timeout=600)
    body = json.dumps({
        "model": "mimo-v2.5-pro",
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    })
    conn.request("POST", "/v1/chat/completions", body=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {mimo_key}"
    })
    resp = conn.getresponse()
    resp_body = resp.read().decode()
    conn.close()
    
    if resp.status != 200:
        raise RuntimeError(f"API {resp.status}: {resp_body[:200]}")
    
    resp_data = json.loads(resp_body)
    usage = resp_data.get("usage", {})
    print(f"  📊 Token: {usage.get('prompt_tokens',0)}+{usage.get('completion_tokens',0)}={usage.get('total_tokens',0)}")
    
    return resp_data["choices"][0]["message"]["content"]


def main():
    lang = "印尼"
    max_titles = 60
    
    print(f"🧪 MiMo 蒸馏测试: {lang}（Top {max_titles} 样本）")
    print("=" * 60)
    
    # 加载筛选后的证据
    evidence = load_filtered_evidence(lang, max_titles)
    if not evidence:
        return
    
    # 加载封面和骨架
    lang_dir = EVIDENCE_DIR / lang
    
    covers_data = []
    covers_file = lang_dir / "covers.json"
    if covers_file.exists():
        covers_data = json.loads(covers_file.read_text())
        print(f"📸 封面: {len(covers_data)} 个")
    
    skeleton_data = {}
    skeleton_file = lang_dir / "title_skeletons.json"
    if skeleton_file.exists():
        skeleton_data = json.loads(skeleton_file.read_text())
        print(f"🦴 骨架: 已加载")
    
    # 构建 prompt
    print(f"\n📝 构建 prompt...")
    prompt = _build_three_layer_prompt(lang, evidence, [], covers_data, skeleton_data)
    print(f"  Prompt 长度: {len(prompt)} 字符")
    
    # 调用 MiMo
    print(f"\n🧠 调用 MiMo...")
    start = time.time()
    
    try:
        result = call_mimo(prompt)
        elapsed = time.time() - start
        print(f"  ✅ 完成 ({elapsed:.0f}s)")
        
        # 解析 JSON
        try:
            # 提取 JSON 部分
            if "```json" in result:
                json_str = result.split("```json")[1].split("```")[0].strip()
            elif "```" in result:
                json_str = result.split("```")[1].split("```")[0].strip()
            else:
                json_str = result
            
            parsed = json.loads(json_str)
            
            # 保存
            output_file = OUTPUT_DIR / f"distilled-rules-{lang}-mimo-filtered-v1.json"
            output_file.write_text(json.dumps(parsed, ensure_ascii=False, indent=2))
            print(f"  💾 保存: {output_file}")
            
            # 统计
            print(f"\n📊 输出统计:")
            for key in parsed:
                if key == "meta":
                    continue
                if isinstance(parsed[key], dict):
                    for subkey, val in parsed[key].items():
                        if isinstance(val, list):
                            print(f"  {key}.{subkey}: {len(val)} 条")
                        elif isinstance(val, dict):
                            for subsub, subval in val.items():
                                if isinstance(subval, list):
                                    print(f"  {key}.{subkey}.{subsub}: {len(subval)} 条")
            
        except json.JSONDecodeError as e:
            print(f"  ❌ JSON 解析失败: {e}")
            print(f"  原始输出前 500 字: {result[:500]}")
            
    except Exception as e:
        elapsed = time.time() - start
        print(f"  ❌ 失败 ({elapsed:.0f}s): {e}")


if __name__ == "__main__":
    main()
