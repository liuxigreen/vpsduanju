#!/usr/bin/env python3
"""
短剧上架前完整方案生成 Pipeline — V3 (nuwa-style)

流程（2次API调用）：
1. 豆包搜索国内素材（剧情+热门标题+冲突+人物关系）
2. 注入 overseas-drama-director 完整认知 → 1次生成完整方案

用法：
    python scripts/pre_upload_pipeline.py --drama "以千金之名" --region hk --video raw/1.mp4
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# 添加项目根目录到路径
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.skill_router import build_prompt_with_skill
from scripts.doubao_api import doubao_search
from scripts.nuwa_api import nuwa_chat

# 加载 youtube-short-drama-distribution.skill
SKILL_FILE = ROOT / "skills" / "youtube-short-drama-distribution.skill.md"

# ============ 配置 ============
DATA_DIR = ROOT / "data" / "ad_materials"
OUTPUT_DIR = ROOT / "output"
PANEL_RUNS_DIR = ROOT / "panel" / "web_runs"


# ============ 第一阶段：搜索国内素材 ============

def search_drama_materials(drama_name: str) -> dict:
    """
    用豆包联网搜索国内素材。
    合并为 1 个 query：完整剧情 + 热门标题 + 冲突点 + 人物关系 + 投放素材
    """
    print(f"\n🔍 正在搜索《{drama_name}》国内素材...")
    
    query = f"""请搜索短剧《{drama_name}》的完整信息，按以下格式分条输出，内容越详细越好：

1. 【剧情概述】完整剧情介绍（包含起承转合、主要转折点、结局，尽量详细）
2. 【核心冲突】至少7个主要冲突点，每个包含：冲突类型、涉及人物、激烈程度(1-5)、视觉元素、发生在哪一集/哪个片段
3. 【热门标题】国内抖音/快手/小红书投放的热门标题和关键词（至少15个）
4. 【人物关系】主要角色及关系、性格特征、身份背景
5. 【经典台词/钩子】爆款开场钩子、经典台词、催泪/爽点台词（至少10句）
6. 【投放素材】国内常用的剪辑方向、高点击率片段描述、名场面时间戳

请尽量详细，信息越全越好，1000-2000字都没问题。"""
    
    try:
        result = doubao_search(query, max_tokens=4000)
        if result and len(result) > 200:
            print(f"  ✅ 搜索成功，返回 {len(result)} 字")
            results = {"合并搜索": result}
            search_success = True
        else:
            print(f"  ⚠️ 搜索结果为空")
            results = {}
            search_success = False
    except Exception as e:
        print(f"  ⚠️ 搜索失败: {e}")
        results = {}
        search_success = False
    
    # 保存原始搜索
    drama_dir = DATA_DIR / drama_name
    drama_dir.mkdir(parents=True, exist_ok=True)
    
    raw_file = drama_dir / "search_raw.json"
    raw_file.write_text(json.dumps({
        "drama_name": drama_name,
        "searched_at": datetime.utcnow().isoformat() + "Z",
        "search_success": search_success,
        "results": results
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"  ✅ 原始搜索已保存: {raw_file}")
    return results


# ============ 第二阶段：注入 overseas-drama-director，1次生成完整方案 ============

def generate_proposal(drama_name: str, region: str, search_results: dict) -> dict:
    """
    用 overseas-drama-director 的完整认知，基于搜索素材 + 三层蒸馏数据，1次生成完整上架方案。
    """
    print(f"\n🧠 注入 overseas-drama-director 认知框架，生成 {region} 地区完整方案...")

    # 加载三层蒸馏数据
    region_map = {
        "hk": "繁中", "tw": "繁中", "sg": "繁中", "mo": "繁中",
        "en": "英文", "us": "英文", "gb": "英文",
        "id": "印尼", "pt": "葡萄牙", "br": "葡萄牙",
        "es": "西语", "mx": "西语",
        "zh-CN": "zh-CN", "zh": "zh-CN",
    }
    lang = region_map.get(region, region)
    distill_context = ""

    # 优先读 JSON（How 层）
    json_file = ROOT / "distill" / "outputs" / f"distilled-rules-{lang}.json"
    if json_file.exists():
        rules = json.loads(json_file.read_text(encoding="utf-8"))
        how = rules.get("how", {})
        # 提取 How 层关键内容作为上下文
        how_summary = json.dumps(how, ensure_ascii=False, indent=2)[:3000]
        distill_context = f"\n\n## 蒸馏规则（{lang}市场 How 层）\n```json\n{how_summary}\n```\n"
        print(f"  ✅ 加载蒸馏规则: {lang}")
    else:
        # fallback: 读 MD
        md_file = ROOT / "distill" / "outputs" / f"distill-{lang}.md"
        if md_file.exists():
            distill_context = f"\n\n## 三层蒸馏数据（{lang}市场）\n{md_file.read_text()[:2000]}\n"
            print(f"  ✅ 加载蒸馏数据（MD fallback）: {lang}")

    # 加载通用 SKILL（Why 层）
    skill_file = Path.home() / ".hermes" / "skills" / "short-drama-youtube" / "SKILL.md"
    if skill_file.exists():
        skill_content = skill_file.read_text(encoding="utf-8")
        distill_context = f"\n\n## 通用原则（Why 层）\n{skill_content}\n" + distill_context
        print(f"  ✅ 加载通用 SKILL")

    # 检查是否有有效搜索结果
    has_search = any(v for v in search_results.values() if len(v) > 50)
    
    if has_search:
        search_text = "\n\n".join([f"【搜索】{k}\n{v[:2000]}" for k, v in search_results.items() if v])
        search_context = f"## 搜索到的国内素材\n{search_text}\n\n请基于以上素材进行分析。"
    else:
        search_context = f"未搜索到《{drama_name}》的国内素材。请基于你对该剧的了解，或基于常见短剧套路进行合理推断。"
    
    # 构建 base prompt（JSON模板部分用普通字符串，避免f-string转义冲突）
    json_template = '''{
  "content_analysis": {
    "plot_summary": "100字剧情概述",
    "matched_model": "匹配的爆款模型名称（如：重生复仇模型、霸总甜宠模型等）",
    "model_confidence": 0.85,
    "episodes": 80,
    "conflicts": [
      {
        "id": "cf_001",
        "episode": 1,
        "type": "冲突类型（如：identity_misunderstanding/revenge/contract_marriage等）",
        "description": "具体冲突描述（30字内）",
        "hook_intensity": 5,
        "viral_score": 0.92,
        "key_phrases": ["跪下", "赶出去"],
        "visual_elements": ["暴雨", "行李箱", "跪地"],
        "is_opening_hook": true,
        "is_climax": false
      }
    ],
    "characters": {
      "protagonist": "女主名字/特征",
      "antagonist": "反派名字/特征",
      "love_interest": "男主名字/特征",
      "supporting": ["配角1", "配角2"]
    },
    "hooks": {
      "opening": "开场3秒钩子",
      "mid_twist": "中段转折",
      "climax": "高潮",
      "ending": "结尾悬念"
    },
    "hot_title_patterns": ["热门标题模式1", "模式2", "模式3"]
  },
  
  "titles": [
    {
      "text": "标题文本（符合REGION地区风格）",
      "formula": "使用的标题公式（如：冲突前置+人名+疑问）",
      "score": {"hook": 90, "conflict": 85, "curiosity": 80, "region_fit": 95, "total": 87.5},
      "conflicts_used": ["cf_001", "cf_002"]
    }
  ],
  
  "covers": [
    {
      "style": "bright_hk|warm_romantic|fresh_modern|sweet_romantic",
      "style_name": "风格中文名（港式明亮/暖色唯美/清爽现代/甜蜜浪漫）",
      "brief": "给用户的封面说明（中文，明亮风格，包含剧名位置、冲突布局、主角描述）",
      "prompt": "给AI生图工具的完整prompt（16:9，明亮高饱和暖色调，大字居中，融合2-3个核心冲突）",
      "conflicts_used": ["cf_001", "cf_002"],
      "target_regions": ["REGION"]
    }
  ],
  
  "distribution": {
    "schedule": {
      "best_time": "20:00",
      "timezone": "HKT/TST/SGT",
      "reason": "选择理由"
    },
    "tags": ["tag1", "tag2", "tag3"],
    "description": "YouTube描述（格式：第1行放15-20个SEO关键词逗号分隔，空一行后写【簡介】+剧名+100-150字剧情简介涵盖前3幕核心冲突人物关系，再空一行写订阅引导+更新频率）"
  }
}'''.replace("REGION", region)

    base_prompt = f"""你是「海外市场短剧运营总监」。请为短剧《{drama_name}》生成面向 {region.upper()} 地区的完整 YouTube 上架方案。

{search_context}
{distill_context}

## 目标地区
{region.upper()}

## 输出要求（绝对重要）
1. **只输出纯 JSON，不要任何 markdown 格式（不要 ```json 包裹）**
2. **不要输出分析说明、不要输出标题、不要输出 emoji**
3. **直接输出可解析的 JSON 对象**
4. 字段必须完整，不要省略任何字段

## JSON 格式模板（严格照此结构）

{json_template}

## 内容要求
- 生成3个标题候选，都符合 {region} 地区风格
- 生成3版封面指令（明亮港风、暖色唯美、清爽现代），每版融合2-3个核心冲突
- 封面风格必须明亮、高饱和、暖色调，禁止暗黑/赛博朋克/低键光
- 标签至少15个，包含核心标签+长尾标签+热点标签
- 描述用 {region} 地区的语言风格
- 描述必须包含：第1行SEO关键词（15-20个，逗号分隔，含剧名核心词+类型词+情绪词），空一行后写【簡介】+剧名+剧情简介（100-150字，涵盖前3幕核心冲突和人物关系，要有具体人物名和情节转折），再空一行写订阅引导

## 封面风格定义（严格照此4选3）
- 港式明亮：高对比、情绪夸张、红金主调、暖光、粗体白色标题、明亮背景
- 暖色唯美：柔和暖光、粉橘主调、逆光光晕、手写体白色标题、温暖氛围
- 清爽现代：干净虚化背景、人物特写、蓝白主调、极简白色标题、清新明亮
- 甜蜜浪漫：粉紫主调、柔光、lens flare、双人亲密动作、梦幻氛围
"""
    
    # 注入 youtube-short-drama-distribution.skill
    skill_context = ""
    if SKILL_FILE.exists():
        skill_context = f"\n\n## YouTube短剧分发规则（来自蒸馏数据）\n{SKILL_FILE.read_text()[:3000]}\n"
        print(f"  ✅ 加载 skill: youtube-short-drama-distribution")
    
    full_prompt = f"""你是「海外市场短剧运营总监」。请为短剧《{drama_name}》生成面向 {region.upper()} 地区的完整 YouTube 上架方案。

{search_context}
{distill_context}
{skill_context}

## 目标地区
{region.upper()}
"""
    
    # 调用 LLM
    try:
        response = nuwa_chat(full_prompt, max_tokens=4000)
        
        if not response or len(response) < 100:
            print(f"  ⚠️ LLM 返回为空")
            raise ValueError("Empty response")
        
        # 提取 JSON
        json_match = re.search(r'```json\s*(.*?)\s*```', response, re.DOTALL)
        if json_match:
            proposal = json.loads(json_match.group(1))
        else:
            response = response.strip()
            if response.startswith('{'):
                proposal = json.loads(response)
            else:
                raise ValueError("No JSON found in response")
        
        print(f"  ✅ 方案生成完成")
        print(f"  📊 冲突点: {len(proposal.get('content_analysis', {}).get('conflicts', []))} 个")
        print(f"  ✍️ 标题候选: {len(proposal.get('titles', []))} 个")
        print(f"  🎨 封面指令: {len(proposal.get('covers', []))} 版")
        
        # 保存分析结果
        analysis_file = DATA_DIR / drama_name / "proposal_generated.json"
        analysis_file.parent.mkdir(parents=True, exist_ok=True)
        analysis_file.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ✅ 方案JSON已保存: {analysis_file}")
        
        return proposal
        
    except Exception as e:
        print(f"  ❌ 生成失败: {e}")
        import traceback
        traceback.print_exc()
        # 返回最小结构
        return {
            "content_analysis": {
                "plot_summary": "生成失败",
                "conflicts": [],
                "characters": {},
                "hooks": {},
            },
            "titles": [],
            "covers": [],
            "distribution": {"schedule": {}, "tags": [], "description": ""}
        }


# ============ 第三阶段：构建 YAML 方案文件 ============

def build_proposal_yaml(
    drama_name: str,
    region: str,
    proposal: dict,
    video_file: Optional[str] = None
) -> Path:
    """
    将生成的 proposal 包装成最终 YAML 文件
    """
    print(f"\n📋 构建最终上架方案文件...")
    
    content = proposal.get("content_analysis", {})
    distribution = proposal.get("distribution", {})
    
    final = {
        "proposal": {
            "drama_name": drama_name,
            "region": region,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "version": "3.0-nuwa",
            
            "content_analysis": {
                "plot_summary": content.get("plot_summary", ""),
                "matched_model": content.get("matched_model", "未知"),
                "model_confidence": content.get("model_confidence", 0),
                "episodes": content.get("episodes", 0),
                "total_conflicts": len(content.get("conflicts", [])),
                "characters": content.get("characters", {}),
                "hooks": content.get("hooks", {}),
            },
            
            "titles": {
                "candidates": proposal.get("titles", []),
                "recommended": proposal.get("titles", [{}])[0].get("text", "") if proposal.get("titles") else "",
            },
            
            "covers": {
                "count": len(proposal.get("covers", [])),
                "styles": [c.get("style_name", "") for c in proposal.get("covers", [])],
                "recommended_style": "bright_hk",
                "prompts": [
                    {
                        "style": c.get("style", ""),
                        "name": c.get("style_name", ""),
                        "brief": c.get("brief", ""),
                        "prompt": c.get("prompt", ""),
                    }
                    for c in proposal.get("covers", [])
                ],
            },
            
            "distribution": {
                "schedule": distribution.get("schedule", {}),
                "tags": distribution.get("tags", []),
                "description": distribution.get("description", ""),
            },
            
            "video": {
                "source_file": video_file or "待提供",
                "subtitle_status": "待生成",
                "edit_guide": {
                    "priority_clips": [
                        {
                            "conflict_id": c.get("id"),
                            "episode": c.get("episode"),
                            "description": c.get("description"),
                            "priority": i + 1,
                        }
                        for i, c in enumerate(content.get("conflicts", [])[:5])
                    ],
                },
            },
            
            "next_steps": [
                "1. 用封面AI指令去生图工具生成封面（推荐影视海报风）",
                "2. 按推荐标题上传视频",
                "3. 生成多语言字幕（zh-hk/zh-tw）",
                "4. 按推荐时间定时发布",
                "5. 发布后48h监控CTR数据",
            ],
            
            "upload_ready": video_file is not None,
        }
    }
    
    # 保存
    proposal_file = PANEL_RUNS_DIR / f"{drama_name}_{region}_proposal.yaml"
    PANEL_RUNS_DIR.mkdir(parents=True, exist_ok=True)
    
    try:
        import yaml
        proposal_file.write_text(yaml.dump(final, allow_unicode=True, sort_keys=False), encoding="utf-8")
    except ImportError:
        proposal_file = proposal_file.with_suffix(".json")
        proposal_file.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    
    print(f"  ✅ 方案已保存: {proposal_file}")
    print(f"\n{'='*60}")
    print(f"📦 完整方案生成完毕！")
    print(f"   剧名: {drama_name}")
    print(f"   地区: {region}")
    print(f"   冲突点: {len(content.get('conflicts', []))} 个")
    print(f"   封面指令: {len(proposal.get('covers', []))} 版")
    print(f"   标题候选: {len(proposal.get('titles', []))} 个")
    print(f"{'='*60}")
    
    return proposal_file


# ============ 主流程 ============

def run_pipeline(
    drama_name: str,
    region: str,
    video_file: Optional[str] = None,
    skip_search: bool = False
) -> Path:
    """
    运行完整 pipeline (2次API调用)
    """
    print(f"\n{'='*60}")
    print(f"🚀 开始生成《{drama_name}》{region} 地区上架方案 [V3 nuwa]")
    print(f"{'='*60}")
    
    # Step 1: 搜索国内素材
    if not skip_search:
        search_results = search_drama_materials(drama_name)
    else:
        raw_file = DATA_DIR / drama_name / "search_raw.json"
        if raw_file.exists():
            search_results = json.loads(raw_file.read_text(encoding="utf-8")).get("results", {})
            print(f"\n📂 使用已有搜索: {raw_file}")
        else:
            search_results = search_drama_materials(drama_name)
    
    # Step 2: 注入 overseas-drama-director，1次生成完整方案
    proposal = generate_proposal(drama_name, region, search_results)
    
    # Step 3: 构建最终 YAML
    proposal_file = build_proposal_yaml(drama_name, region, proposal, video_file)
    
    return proposal_file


def main():
    ap = argparse.ArgumentParser(description="短剧上架前方案生成 — V3 nuwa")
    ap.add_argument("--drama", required=True, help="短剧名称，如：以千金之名")
    ap.add_argument("--region", default="hk", choices=["hk", "tw", "sg", "en", "mo", "my"],
                    help="目标地区 (默认: hk)")
    ap.add_argument("--video", help="原始视频文件路径")
    ap.add_argument("--skip-search", action="store_true",
                    help="跳过搜索，使用已有素材")
    args = ap.parse_args()
    
    proposal_file = run_pipeline(
        drama_name=args.drama,
        region=args.region,
        video_file=args.video,
        skip_search=args.skip_search
    )
    
    print(f"\n✅ 方案文件: {proposal_file}")
    print(f"   可打开 Panel v2 查看: python main.py panel-v2")


if __name__ == "__main__":
    main()
