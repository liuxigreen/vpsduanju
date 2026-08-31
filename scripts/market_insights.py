#!/usr/bin/env python3
"""
YouTube 短剧市场洞察（按语种/地区）

聚合同语种下所有频道的 LLM 分析结果，用 DeepSeek V4 Pro 蒸馏出
跨频道的市场规律：题材趋势、标题模式、竞争格局、内容空白点。

数据来源：data/competitor_insights/channel_{id}.json 中的 llm_analysis 字段
输出：data/market_insights_{lang}.json

用法：
    python3 scripts/market_insights.py                    # 全部语种
    python3 scripts/market_insights.py --language 印尼      # 只跑一个语种
    python3 scripts/market_insights.py --dry-run           # 只构建prompt不调LLM
"""

import json
import sys
import time
import argparse
import os
import requests
from datetime import datetime
from pathlib import Path
from collections import Counter, defaultdict
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
LATEST_FILE = DATA_DIR / "competitor_data" / "latest.json"  # 已断流(7/18)，仅作avg_views兜底
INSIGHT_DIR = DATA_DIR / "competitor_insights"
OUTPUT_DIR = DATA_DIR
TIERS_FILE = DATA_DIR / "competitor_tiers.json"
CHANNELS_ALL_FILE = DATA_DIR / "competitors_channels_all.json"  # 主数据源(velocity周一/四刷新)

sys.stdout.reconfigure(line_buffering=True)

from edgefn_models import call_for_task, parse_json_response, CALL_INTERVAL

MODEL = "DeepSeek-V4-Pro"  # 记录进meta用；实际调用走 call_for_task("market_insights")


def _load_all_insights() -> list:
    """加载所有有 LLM 分析的频道数据"""
    channels = []
    for f in sorted(INSIGHT_DIR.glob("channel_*.json")):
        if f.name.startswith("_"):
            continue
        try:
            data = json.loads(f.read_text())
            if data.get("llm_analysis", {}).get("distill"):
                channels.append(data)
        except:
            continue
    return channels


def _load_latest_stats() -> dict:
    """频道实时统计 — 主源 competitors_channels_all.json (velocity 周一/四刷新)
    兜底 competitor_data/latest.json 的 avg_views (已断流，仅历史参考)"""
    result = {}
    # 兜底: 旧latest.json的avg_views
    legacy = {}
    if LATEST_FILE.exists():
        try:
            for ch in json.loads(LATEST_FILE.read_text()):
                cid = ch.get("channel_id", "")
                videos = ch.get("videos", [])
                views = [v.get("view_count", v.get("views", 0)) for v in videos if v.get("view_count", v.get("views", 0)) > 0]
                legacy[cid] = {
                    "avg_views": round(sum(views) / len(views)) if views else 0,
                    "max_views": max(views) if views else 0,
                }
        except Exception:
            pass
    if CHANNELS_ALL_FILE.exists():
        data = json.loads(CHANNELS_ALL_FILE.read_text())
        for ch in data.get("channels", []):
            cid = ch.get("channel_id", "")
            if not cid:
                continue
            t = ch.get("tracking") or {}
            recent_titles = [v.get("title", "") for v in (t.get("momentum_videos_detail") or [])[:5] if v.get("title")]
            result[cid] = {
                "subscribers": ch.get("subscribers", 0),
                "video_count": ch.get("total_videos", 0),
                "avg_views": legacy.get(cid, {}).get("avg_views", 0),
                "max_views": legacy.get(cid, {}).get("max_views", 0),
                "country": ch.get("country", ""),
                "video_momentum": t.get("video_momentum", 0),          # 近30天视频日均播放
                "subs_velocity_weekly": t.get("subs_velocity_weekly", 0),
                "views_velocity_weekly": t.get("views_velocity_weekly", 0),
                "velocity_asof": t.get("velocity_asof", ""),
                "recent_titles": recent_titles,
                "content_tags": [x.strip() for x in (ch.get("content_tags") or []) if x and x.strip()],
            }
    else:
        result = legacy
    return result


# ═══════════════════════════════════════════════
#  数据准备（Python层）
# ═══════════════════════════════════════════════

def prepare_market_data(lang: str, channels: list, latest_stats: dict) -> dict:
    """聚合同语种所有频道数据，准备给 LLM"""

    # 按 tier 分组
    by_tier = defaultdict(list)
    for ch in channels:
        tier = ch.get("tier", "unknown")
        by_tier[tier].append(ch)

    # 每个频道的摘要
    channel_summaries = []
    for ch in channels:
        cid = ch.get("channel_id", "")
        name = ch.get("name", cid[:12])
        distill = ch.get("llm_analysis", {}).get("distill", {})
        stats = ch.get("llm_analysis", {}).get("stats", {})
        raw_stats = latest_stats.get(cid, {})

        why = distill.get("why", {})
        what = distill.get("what", {})

        summary = f"### {name}"
        summary += f"\n- 订阅: {raw_stats.get('subscribers', ch.get('subscribers', 0)):,}"
        summary += f" | 均播: {raw_stats.get('avg_views', stats.get('avg_views', 0)):,}"
        summary += f" | 视频: {raw_stats.get('video_count', ch.get('total_videos', 0))}"
        summary += f" | 地区: {raw_stats.get('country', ch.get('country', ''))}"
        summary += f" | 层级: {ch.get('tier', '?')}"
        if raw_stats.get("video_momentum"):
            summary += f"\n- 📈 动量(近30天视频日均播放): {raw_stats['video_momentum']:,} | 周订阅涨速: {raw_stats.get('subs_velocity_weekly', 0):+,} | 数据日期: {raw_stats.get('velocity_asof', '?')}"
        if raw_stats.get("recent_titles"):
            summary += f"\n- 近期热视频标题: " + " ‖ ".join(t[:70] for t in raw_stats["recent_titles"][:3])

        if why.get("growth_drivers"):
            summary += f"\n- 增长原因: {'; '.join(why['growth_drivers'][:3])}"
        if why.get("audience_fit"):
            summary += f"\n- 受众: {why['audience_fit'][:100]}"
        if why.get("trajectory"):
            summary += f"\n- 阶段: {why['trajectory'][:80]}"
        if what.get("top_themes"):
            summary += f"\n- 题材: {', '.join(what['top_themes'])}"
        if what.get("title_formulas"):
            summary += f"\n- 标题公式: {'; '.join(what['title_formulas'][:3])}"
        if what.get("hook_patterns"):
            summary += f"\n- 钩子: {'; '.join(what['hook_patterns'][:2])}"
        if what.get("engagement_insight"):
            summary += f"\n- 互动: {what['engagement_insight'][:80]}"

        # 封面数据
        covers = ch.get("top_covers", [])
        if covers:
            cover_lines = []
            for c in covers[:3]:
                cover_lines.append(f"  - [{c.get('views',0):,}播放] {c.get('title','')[:60]}")
            summary += f"\n- 封面Top3:\n" + "\n".join(cover_lines)
        if what.get("cover_strategy"):
            summary += f"\n- 封面策略: {what['cover_strategy'][:100]}"

        # 时长信息
        if stats.get("avg_duration_sec"):
            dur = stats["avg_duration_sec"]
            summary += f"\n- 平均时长: {dur//60}分{dur%60}秒"

        channel_summaries.append(summary)

    # 统计汇总
    all_themes = []
    all_hooks = []
    all_formulas = []
    all_cover_strategies = []
    for ch in channels:
        distill = ch.get("llm_analysis", {}).get("distill", {})
        what = distill.get("what", {})
        all_themes.extend(what.get("top_themes", []))
        all_hooks.extend(what.get("hook_patterns", []))
        all_formulas.extend(what.get("title_formulas", []))
        if what.get("cover_strategy"):
            all_cover_strategies.append(what["cover_strategy"])

    theme_freq = Counter(all_themes).most_common(15)
    hook_freq = Counter(all_hooks).most_common(10)

    stats_text = f"## 跨频道统计（Python计算）\n"
    stats_text += f"- 频道数: {len(channels)}\n"
    stats_text += f"- 层级分布: {', '.join(f'{t}×{len(cs)}' for t, cs in by_tier.items())}\n"
    stats_text += f"- 题材频率: {', '.join(f'{t}({c})' for t, c in theme_freq)}\n"
    stats_text += f"- 钩子频率: {', '.join(f'{h[:30]}({c})' for h, c in hook_freq)}\n"

    # 题材动量聚合（基于velocity实时数据，多题材频道均摊）— rising/declining 的真实依据
    # 注意: 聚合所有有动量数据的频道（入场门槛是"动量或均播≥1万"，低动量频道的动量同样有信号价值）
    # 题材归一化：别名合并 + 非题材噪声过滤（频道名/泛化词/纯语言标签）
    GENRE_ALIAS = {
        "Cinderella": "灰姑娘", "cinderela": "灰姑娘", "灰姑娘": "灰姑娘",
        "CEO": "霸总", "ceolovestory": "霸总", "浪漫爱情": "爱情", "amor": "爱情",
        "drama de amor": "爱情", "Romansa": "爱情", "kiss": "爱情", "sweet": "甜宠",
        "ação": "动作", "假身份": "秘密身份", "隐藏身份": "秘密身份",
    }
    NON_GENRE = {"剧情", "film cina", "Sinetron pendek", "Web drama", "Gado-Gado Clips",
                 "filme completo", "中文短剧", "女频", "男频"}
    genre_momentum = defaultdict(int)
    genre_channels = defaultdict(list)
    for ch in channels:
        cid = ch.get("channel_id", "")
        rs = latest_stats.get(cid, {})
        mom = rs.get("video_momentum", 0)
        raw_tags = [t.strip() for t in (rs.get("content_tags") or []) if t and t.strip()]
        tags = []
        for t in raw_tags:
            if t in NON_GENRE:
                continue
            g = GENRE_ALIAS.get(t, GENRE_ALIAS.get(t.lower(), t))
            if g not in tags:
                tags.append(g)
        if mom > 0 and tags:
            share = mom / len(tags)
            for tg in tags:
                genre_momentum[tg] += share
                genre_channels[tg].append(ch.get("name", cid[:10]))
    if genre_momentum:
        gm_sorted = sorted(genre_momentum.items(), key=lambda x: -x[1])
        stats_text += f"\n## 题材动量榜（近30天日均播放聚合，Python计算）\n"
        for tg, m in gm_sorted[:10]:
            stats_text += f"- {tg}: {int(m):,}（{len(genre_channels[tg])}个频道）\n"

    # 封面策略汇总
    if all_cover_strategies:
        stats_text += f"\n## 各频道封面策略\n"
        for i, cs in enumerate(all_cover_strategies):
            stats_text += f"- {cs[:120]}\n"

    # 订阅分布
    subs_list = [latest_stats.get(ch.get("channel_id",{}), {}).get("subscribers", ch.get("subscribers", 0)) for ch in channels]
    subs_list = [s for s in subs_list if s > 0]
    if subs_list:
        stats_text += f"- 订阅范围: {min(subs_list):,} ~ {max(subs_list):,}\n"
        stats_text += f"- 中位数订阅: {sorted(subs_list)[len(subs_list)//2]:,}\n"

    return {
        "language": lang,
        "channel_count": len(channels),
        "channel_summaries": "\n\n".join(channel_summaries),
        "stats_text": stats_text,
        "theme_freq": theme_freq,
        "hook_freq": hook_freq,
        "genre_momentum": {tg: int(m) for tg, m in sorted(genre_momentum.items(), key=lambda x: -x[1])},
    }


# ═══════════════════════════════════════════════
#  Prompt 构建
# ═══════════════════════════════════════════════

def build_prompt(data: dict) -> str:
    # 字幕实证注入（开关: settings.yaml subtitle_injection.enabled；无数据自动降级）
    subtitle_block = ""
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import subtitle_evidence as _se
        if _se.injection_enabled():
            _code = _se.cn_to_code(data["language"])
            _b = _se.market_subtitle_block(_code) if _code else ""
            if _b:
                subtitle_block = _b + "\n\n"
    except Exception:
        pass

    return f"""你是YouTube短剧市场分析师。以下是{data['language']}市场中{data['channel_count']}个竞品频道的深度分析数据。
其中「题材动量榜」和每个频道的「📈动量/周订阅涨速」是近30天实时计算的数据，「均播」是历史快照数据。
请基于这些数据，产出{data['language']}短剧市场的整体洞察。

{subtitle_block}{data['stats_text']}

# 各频道详细分析

{data['channel_summaries']}

## 分析要求

1. 一切结论必须有数据锚点：判断题材涨/退时，对比「题材频率」（历史存量）与「题材动量榜」（近30天实时），动量占比高于存量占比的才算在涨，反之在退。
2. 只引用上面出现过的频道名和标题，禁止编造数据中不存在的频道、视频或数字。
3. future_opportunities 必须从本市场数据中推导（如：高动量题材×低频道供给=空白点），不要套用通用爆款题材清单；如果数据不足以支撑某个机会，宁可少写。
4. 每个数组字段最多5项，宁缺毋滥；没有依据的字段填空数组，不要凑数。

请输出纯JSON（不要markdown代码块、不要其他文字）：

{{
  "what_they_watch": {{
    "top_genres": [
      {{"genre": "题材名", "popularity": "热度描述（引用动量榜数字）", "examples": ["代表频道/视频"]}},
    ],
    "rising_genres": [
      {{"genre": "题材名", "trend": "为什么在涨（必须引用动量vs存量的对比）"}}
    ],
    "declining_genres": ["在退的题材（同样需数据对比支撑）"],
    "audience_notes": "这个地区的观众偏好特点（年龄/性别/观看习惯/付费意愿）"
  }},
  "titles_and_hooks": {{
    "winning_formulas": ["最有效的标题公式1", "公式2"],
    "top_hook_words": ["高频钩子词1", "钩子词2", "钩子词3"],
    "language_mix": "标题语言使用特点（纯本地语/混英文/中文比例，基于近期热视频标题观察）",
    "hook_analysis": "什么类型的钩子在这个市场最有效"
  }},
  "covers_and_visuals": {{
    "cover_styles": ["封面风格1", "风格2"],
    "what_works": "什么封面在这个市场点击率高",
    "common_elements": ["封面常用元素1", "元素2"]
  }},
  "competition": {{
    "top_channels": [
      {{"name": "频道名", "why_top": "为什么是头部（引用订阅/动量数字）", "what_we_can_learn": "能学到什么"}}
    ],
    "emerging_channels": [
      {{"name": "频道名", "why_watch": "为什么值得关注（必须引用周订阅涨速或动量数据）"}}
    ],
    "content_gaps": ["还没人做的内容机会1", "机会2", "机会3"]
  }},
  "future_opportunities": {{
    "localization_potential": ["适合该地区的本土化题材方向1", "方向2"],
    "cultural_fusion": ["文化融合题材机会（基于该地区文化特征）", "机会2"],
    "emerging_themes": ["数据中已冒头的新题材信号（动量榜新面孔）", "方向2"],
    "subculture_narratives": ["亚文化叙事机会（须有本市场数据支撑）", "机会2"],
    "why_these_work": "为什么这些方向在该地区有潜力（逐条对应数据证据）"
  }},
  "takeaways": {{
    "if_entering_now": ["如果现在入场应该做的1", "2", "3"],
    "avoid": ["应该避开的1", "2"]
  }}
}}"""


# ═══════════════════════════════════════════════
#  LLM 调用
# ═══════════════════════════════════════════════

def call_llm(prompt: str) -> Optional[dict]:
    """走 edgefn 统一路由（AGENTS.md: 模型选择经 model/edgefn，不硬编码）"""
    result = call_for_task(
        "market_insights",
        prompt,
        max_tokens=16000,
        temperature=0.3,
    )
    if result.get("error"):
        print(f"    ❌ LLM调用失败: {result['error']}")
        return None
    usage = result.get("usage", {})
    if usage:
        print(f"    📊 tokens: in={usage.get('prompt_tokens',0):,} out={usage.get('completion_tokens',0):,}")
    parsed = parse_json_response(result)
    if parsed.get("error"):
        print(f"    ❌ JSON解析失败: {parsed['error']}")
        return None
    return parsed


# ═══════════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════════

def analyze_market(lang: str, channels: list, latest_stats: dict, dry_run: bool = False) -> Optional[dict]:
    """对一个语种做市场洞察"""
    data = prepare_market_data(lang, channels, latest_stats)
    prompt = build_prompt(data)

    if dry_run:
        print(f"    [dry-run] prompt长度: {len(prompt)} 字符, 频道数: {data['channel_count']}")
        return None

    insights = call_llm(prompt)
    if not insights:
        return None

    # 保存
    output = {
        "meta": {
            "language": lang,
            "model": MODEL,
            "generated_at": datetime.now().isoformat(),
            "channel_count": data["channel_count"],
        },
        "python_stats": {
            "theme_frequency": dict(data["theme_freq"]),
            "hook_frequency": dict(data["hook_freq"]),
            "genre_momentum": data.get("genre_momentum", {}),
        },
        "llm_insights": insights,
    }

    output_file = OUTPUT_DIR / f"market_insights_{lang}.json"
    output_file.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"    ✅ 保存 → {output_file.name}")

    return output


def main():
    parser = argparse.ArgumentParser(description="YouTube短剧市场洞察")
    parser.add_argument("--language", help="只分析某语种")
    parser.add_argument("--dry-run", action="store_true", help="只构建prompt不调LLM")
    args = parser.parse_args()

    all_insights = _load_all_insights()
    if not all_insights:
        print("❌ 没有 LLM 分析数据，请先运行 llm_analyze_channel.py")
        sys.exit(1)

    latest_stats = _load_latest_stats()

    # 市场洞察门槛：近30天动量≥1万 或 历史均播≥1万（有真实热度的才代表市场）
    filtered = []
    for ch in all_insights:
        stat = latest_stats.get(ch.get("channel_id", ""), {})
        if stat.get("video_momentum", 0) >= 10000 or stat.get("avg_views", 0) >= 10000:
            filtered.append(ch)
    print(f"📊 市场洞察门槛：{len(all_insights)}个LLM频道 → {len(filtered)}个有真实热度(动量或均播≥1万)")

    # 按语种分组
    by_lang = defaultdict(list)
    for ch in filtered:
        lang = ch.get("language", "未知")
        by_lang[lang].append(ch)

    # 只分析有 ≥3 个频道的语种
    langs = {}
    for lang, channels in by_lang.items():
        if args.language and lang != args.language:
            continue
        if len(channels) >= 3:
            langs[lang] = channels
        else:
            print(f"⏭️ {lang}: 只有 {len(channels)} 个频道（<3），跳过")

    if not langs:
        print("❌ 没有符合条件的语种（需要 ≥3 个已分析频道）")
        sys.exit(1)

    print(f"📋 市场洞察: {len(langs)} 个语种")
    print(f"{'='*50}")

    for i, (lang, channels) in enumerate(langs.items(), 1):
        print(f"\n[{i}/{len(langs)}] 🌏 {lang} 市场 ({len(channels)} 个频道)")

        result = analyze_market(lang, channels, latest_stats, dry_run=args.dry_run)

        if result:
            llm = result.get("llm_insights", {})
            watch = llm.get("what_they_watch", {})
            covers = llm.get("covers_and_visuals", {})
            print(f"    热门题材: {', '.join(g.get('genre','') for g in watch.get('top_genres',[])[:3])}")
            print(f"    上升题材: {', '.join(g.get('genre','') for g in watch.get('rising_genres',[])[:3])}")
            print(f"    封面风格: {covers.get('what_works','')[:60]}")

        if i < len(langs) and not args.dry_run:
            print(f"    ⏳ 等待 {CALL_INTERVAL:.0f}秒...")
            time.sleep(CALL_INTERVAL)

    print(f"\n{'='*50}")
    print(f"✅ 完成")


if __name__ == "__main__":
    main()
