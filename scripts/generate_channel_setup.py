#!/usr/bin/env python3
"""
generate_channel_setup.py — 真正调用 nuwa 专家的频道配置生成器

流程：
1. 读取 manifest（地区 + 题材 + 风格偏好）
2. 通过 skill_router 读取 distribution-expert + hk-traditional-market-expert 规则
3. 调用 nuwa_api 生成频道配置（name / description / schedule / branding）
4. 用规则检查（DST + HKT）
5. 输出合规配置

用法：
    python3 scripts/generate_channel_setup.py --region hk --genre 甜寵 --style 品牌化
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from nuwa_api import nuwa_chat
from skill_router import build_prompt_with_skill

BASE_DIR = Path(__file__).parent.parent
OUTPUT_DIR = BASE_DIR / "panel" / "channel_setup"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def _check_channel_compliance(cfg: dict, region: str, subscriber_count: int = 0) -> list[dict]:
    """频道配置规则检查"""
    failures = []
    name = cfg.get("name", "")
    desc = cfg.get("description", "")
    tags = cfg.get("tags", [])
    schedule = cfg.get("upload_schedule", {})
    genre_focus = cfg.get("genre_focus", [])

    # DST-018: 禁用纯英文通用词
    generic_words = ["short drama", "channel", "tv", "video"]
    if all("\u4e00" <= c <= "\u9fff" for c in name.replace(" ", "")) is False:
        # 有英文，检查是否太通用
        name_lower = name.lower()
        if any(w in name_lower for w in generic_words) and not any(
            w in name for w in ["劇場", "劇社", "影院", "大全", "DramaBox", "ShortTV"]
        ):
            failures.append(
                {
                    "rule": "DST-018",
                    "level": "WARN",
                    "reason": f"频道名'{name}'含通用英文词且无品牌化后缀，辨识度低",
                }
            )

    # HKT-007: 频道名后缀偏好
    suffixes = ["劇場", "劇社", "影院", "大全", "泡泡", "小館"]
    if not any(s in name for s in suffixes):
        failures.append(
            {
                "rule": "HKT-007",
                "level": "INFO",
                "reason": f"频道名'{name}'无常见后缀（劇場/劇社/影院/大全），建议品牌化",
            }
        )

    # HKT-008: 简介必须含搜索关键词
    seo_keywords = ["短劇", "全集", "一口氣看完", "總裁", "甜寵", "重生", "逆襲"]
    hits = sum(1 for k in seo_keywords if k in desc)
    if hits < 3:
        failures.append(
            {
                "rule": "HKT-008",
                "level": "WARN",
                "reason": f"简介仅含{hits}个搜索关键词（建议≥3个）",
            }
        )

    # HKT-009: 标签必须含平台词
    platform_words = ["DramaBox", "ShortTV", "MoboReels", "FlexTV", "TopShort", "ReelShort"]
    if not any(p in tags for p in platform_words):
        failures.append(
            {
                "rule": "HKT-009",
                "level": "INFO",
                "reason": "标签未含平台词（DramaBox/ShortTV等），建议添加引流",
            }
        )

    # DST-010: 题材单一性（新频道<10000订阅只做1-2个题材）
    if subscriber_count < 10000 and len(genre_focus) > 2:
        failures.append(
            {
                "rule": "DST-010",
                "level": "WARN",
                "reason": f"新频道建议只做1-2个题材，当前{len(genre_focus)}个",
            }
        )

    # DST-014: 搜索流量占比40%必须优化标题SEO
    if hits < 2:
        failures.append(
            {
                "rule": "DST-014",
                "level": "WARN",
                "reason": "SEO关键词不足，搜索流量可能偏低",
            }
        )

    # DST-004/013: 黄金时段检查
    times = schedule.get("times", [])
    region_hours = {
        "hk": (20, 22),
        "tw": (20, 22),
        "sg": (20, 22),
        "mo": (20, 22),
        "id": (19, 21),
        "br": (19, 21),
    }
    if region in region_hours:
        start, end = region_hours[region]
        for t in times:
            try:
                h = int(t.split(":")[0])
                if not (start <= h <= end):
                    failures.append(
                        {
                            "rule": "DST-004",
                            "level": "WARN",
                            "reason": f"发布时间{t}不在黄金时段{start}:00-{end}:00",
                        }
                    )
                    break
            except ValueError:
                pass

    return failures


def _score_channel(cfg: dict, region: str) -> dict:
    """基于规则的频道评分"""
    name = cfg.get("name", "")
    desc = cfg.get("description", "")
    tags = cfg.get("tags", [])

    # 品牌化 30%
    has_brand = any(s in name for s in ["劇場", "劇社", "影院", "泡泡", "小館", "DramaBox"])
    has_chinese = any("\u4e00" <= c <= "\u9fff" for c in name)
    branding = 100 if (has_brand and has_chinese) else 60 if has_chinese else 30

    # SEO完整度 25%
    seo_words = ["短劇", "全集", "總裁", "甜寵", "重生", "逆襲", "一口氣看完"]
    seo_hits = sum(1 for w in seo_words if w in desc or w in tags)
    seo = min(30 + seo_hits * 10, 100)

    # 标签质量 20%
    platform_hits = sum(
        1 for p in ["DramaBox", "ShortTV", "MoboReels", "FlexTV"] if p in tags
    )
    tags_score = min(40 + platform_hits * 15 + len(tags) * 2, 100)

    # 简介信息量 15%
    desc_len = len(desc)
    info = 100 if desc_len > 200 else 70 if desc_len > 100 else 40

    # 地区适配 10%
    region_match = 100
    if region in ("hk", "mo") and "點知" not in desc and "即刻" not in desc:
        region_match = 80
    if region == "tw" and "沒想到" not in desc and "竟然" not in desc:
        region_match = 80

    total = round(branding * 0.30 + seo * 0.25 + tags_score * 0.20 + info * 0.15 + region_match * 0.10, 1)
    return {
        "branding": branding,
        "seo": seo,
        "tags": tags_score,
        "info": info,
        "region_match": region_match,
        "total": total,
    }


def _build_nuwa_prompt(region: str, genre: str, style: str, subscriber_count: int = 0) -> str:
    """构建 nuwa prompt"""
    skill_ctx = build_prompt_with_skill(
        task="channel setup",
        base_prompt="",
        force_skills=["distribution-expert", "hk-traditional-market-expert"],
    )

    # 地区风格词
    style_words = {
        "hk": "港式口语（點知/即刻/全城），粤语感强",
        "tw": "台式书面（沒想到/竟然/原來），描述细",
        "sg": "新马双语，繁体中文+英文标签",
        "mo": "同香港，粤语优先",
    }

    prompt = f"""你是 distribution-expert + hk-traditional-market-expert 的合体。

【任务】为一个面向{region.upper()}市场的短剧YouTube频道生成完整配置。

【要求】
- 地区：{region.upper()}（{style_words.get(region, '繁体中文')}）
- 主题材：{genre}
- 风格偏好：{style}（品牌化/个人IP/官方感）
- 当前订阅数：{subscriber_count}

【必须遵守的规则】
1. 频道名必须含繁体中文，禁用纯英文通用词如"Short Drama Channel"（DST-018）
2. 频道名建议用品牌化后缀：劇場/劇社/影院/大全/小館（HKT-007）
3. 简介必须含≥3个搜索关键词：短劇/全集/總裁/甜寵/重生/逆襲（HKT-008）
4. 标签必须含至少1个平台词：DramaBox/ShortTV/MoboReels/FlexTV/TopShort（HKT-009）
5. 如订阅<1000，每天发布2部；1000-10000每天1部（DST-001/002）
6. 发布时间必须在黄金时段：HK/TW/SG为20:00-22:00（DST-004/013）
7. 新频道<10000订阅只做1-2个题材（DST-010）
8. 简介第一行放搜索关键词组合（HKT-010）

【输出格式】
只输出JSON，不要解释：
{{
  "name": "频道名（繁体中文，可含英文副名）",
  "name_en": "英文副名（可选）",
  "description": "频道简介（多行，含SEO关键词、更新时间、合作邮箱）",
  "tags": ["标签1", "标签2", ...],
  "genre_focus": ["主题材1", "主题材2"],
  "upload_schedule": {{
    "frequency": "daily",
    "times": ["20:00"],
    "timezone": "Asia/Hong_Kong",
    "quota_per_day": 1
  }},
  "branding": {{
    "primary_color": "#ff8fab",
    "secondary_color": "#ffe5ec",
    "avatar_style": "描述",
    "banner_text": "文字"
  }},
  "target_audience": {{
    "gender": "female",
    "age_range": [18, 35],
    "regions": ["HK"]
  }}
}}
"""
    return prompt


def _parse_nuwa_response(raw: str) -> dict:
    m = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if m:
        raw_json = m.group(1)
    else:
        m = re.search(r"(\{.*\})", raw, re.DOTALL)
        raw_json = m.group(1) if m else raw
    try:
        return json.loads(raw_json)
    except json.JSONDecodeError:
        return {}


def _fallback_setup(region: str, genre: str, style: str) -> dict:
    """fallback 模板"""
    region_name = {"hk": "香港", "tw": "台灣", "sg": "新加坡", "mo": "澳門"}.get(region, "繁体")
    genre_map = {"甜寵": "Sweet", "總裁": "CEO", "重生": "Rebirth", "逆襲": "Rise", "復仇": "Revenge"}
    g = genre_map.get(genre, "Drama")

    if style == "品牌化":
        name = f"劇糖{region_name}"
    elif style == "个人IP":
        name = f"小糖追劇{region_name}"
    else:
        name = f"{g}劇場{region_name}"

    return {
        "name": name,
        "name_en": f"{g} Drama {region.upper()}",
        "description": f"💖 {name} — 專注「{genre}」女頻短劇\n💖 每日更新，精選爆款\n💖 全網最齊全書庫，高清完整版\n\n⏰ 更新時間：20:00 (GMT+8)\n📩 商務合作：business@dramabox.hk",
        "tags": [genre, "短劇", "全集", "女頻", "DramaBox", "ShortTV"],
        "genre_focus": [genre],
        "upload_schedule": {
            "frequency": "daily",
            "times": ["20:00"],
            "timezone": "Asia/Hong_Kong",
            "quota_per_day": 1,
        },
        "branding": {
            "primary_color": "#ff8fab",
            "secondary_color": "#ffe5ec",
            "avatar_style": "cute_brand_logo",
            "banner_text": name,
        },
        "target_audience": {
            "gender": "female",
            "age_range": [18, 35],
            "regions": [region.upper()],
        },
    }


def run(region: str, genre: str, style: str, subscriber_count: int = 0) -> Path:
    print(f"📺 生成频道配置: {region.upper()} | 题材: {genre} | 风格: {style}")

    # 1. 构建 prompt
    prompt = _build_nuwa_prompt(region, genre, style, subscriber_count)
    print("🤖 调用 nuwa 专家生成...")

    # 2. 调用 nuwa
    raw = nuwa_chat(prompt, max_tokens=4000, temperature=0.7, rotate=True)
    if raw:
        cfg = _parse_nuwa_response(raw)
    else:
        cfg = {}

    if not cfg or not cfg.get("name"):
        print("⚠️ nuwa 未返回有效配置，fallback 到模板")
        cfg = _fallback_setup(region, genre, style)

    # 3. 规则检查
    failures = _check_channel_compliance(cfg, region, subscriber_count)
    reject_reasons = [f"{f['rule']}: {f['reason']}" for f in failures if f["level"] == "REJECT"]
    warn_reasons = [f"{f['rule']}: {f['reason']}" for f in failures if f["level"] in ("WARN", "INFO")]

    score = _score_channel(cfg, region)

    if reject_reasons:
        print(f"  ❌ REJECT: {', '.join(reject_reasons)}")
        # 不保存，fallback
        cfg = _fallback_setup(region, genre, style)
        failures = _check_channel_compliance(cfg, region, subscriber_count)
        warn_reasons = [f"{f['rule']}: {f['reason']}" for f in failures if f["level"] in ("WARN", "INFO")]
        score = _score_channel(cfg, region)
        print(f"  🔄 fallback 模板生成 | 总分{score['total']}")
    else:
        status = "✅ PASS"
        if warn_reasons:
            status = f"⚠️ PASS(warn: {len(warn_reasons)}个)"
        print(f"  {status}: {cfg['name']} | 总分{score['total']}")

    # 4. 组装输出
    output = {
        "region": region,
        "genre": genre,
        "style": style,
        "subscriber_count": subscriber_count,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "provider": "nuwa(DeepSeek/BankOfAI)",
        "config": cfg,
        "score": score,
        "warnings": warn_reasons,
    }

    safe_name = re.sub(r"[^\w]", "_", cfg["name"])[:30]
    out_path = OUTPUT_DIR / f"channel_{region}_{safe_name}.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n📁 输出: {out_path}")
    print(f"   频道: {cfg['name']}")
    print(f"   更新: {cfg['upload_schedule']['quota_per_day']}部/天 @ {cfg['upload_schedule']['times']}")
    print(f"   标签: {', '.join(cfg['tags'][:6])}")
    return out_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="hk", choices=["hk", "tw", "sg", "mo", "id", "br"])
    p.add_argument("--genre", default="甜寵", help="主题材")
    p.add_argument("--style", default="品牌化", choices=["品牌化", "个人IP", "官方感"])
    p.add_argument("--subscribers", type=int, default=0, help="当前订阅数")
    args = p.parse_args()
    run(args.region, args.genre, args.style, args.subscribers)


if __name__ == "__main__":
    main()
