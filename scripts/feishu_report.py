#!/usr/bin/env python3
"""
feishu_report.py — 将频道分析数据写入飞书文档

用法:
    python3 scripts/feishu_report.py  # 读取最新分析数据，创建飞书文档

输出:
    飞书文档链接，可通过消息发送
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(os.path.expanduser("~/.hermes/.env"))

try:
    import lark_oapi as lark
    from lark_oapi.api.docx.v1 import *
    from lark_oapi.api.im.v1 import *
except ImportError:
    print("❌ 需要安装 lark_oapi: pip install lark_oapi")
    sys.exit(1)

app_id = os.environ.get("FEISHU_APP_ID", "")
app_secret = os.environ.get("FEISHU_APP_SECRET", "")


def create_feishu_doc(title: str) -> str:
    """Create a new Feishu document, return doc_id."""
    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
    resp = client.docx.v1.document.create(
        CreateDocumentRequest.builder().request_body(
            CreateDocumentRequestBody.builder().title(title).build()
        ).build()
    )
    return resp.data.document.document_id


def write_blocks_to_doc(doc_id: str, blocks: list):
    """Write blocks to document in batches."""
    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()

    # Get root block
    blocks_resp = client.docx.v1.document_block.list(
        ListDocumentBlockRequest.builder()
        .document_id(doc_id).page_size(500).build()
    )
    root_block_id = blocks_resp.data.items[0].block_id

    BATCH = 50
    for i in range(0, len(blocks), BATCH):
        batch = blocks[i:i+BATCH]
        req = CreateDocumentBlockChildrenRequest.builder() \
            .document_id(doc_id).block_id(root_block_id) \
            .request_body(
                CreateDocumentBlockChildrenRequestBody.builder()
                .children(batch).index(-1).build()
            ).build()
        resp = client.docx.v1.document_block_children.create(req)
        if resp.code != 0:
            print(f"  ⚠️ Batch {i//BATCH+1} 写入失败: {resp.msg}")


def text(content: str, bold: bool = False) -> dict:
    style = {"bold": True} if bold else {}
    return {
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": content, "text_element_style": style}}]}
    }


def heading(content: str, level: int = 2) -> dict:
    return {
        "block_type": 2 + level,
        f"heading{level}": {"elements": [{"text_run": {"content": content}}]}
    }


def divider() -> dict:
    return {"block_type": 22, "divider": {}}


def build_channel_section(ch: dict, details: dict, diagnosis: dict | None = None) -> list:
    """Build blocks for one channel's analysis section (panel-style)."""
    blocks = []
    name = ch['name']
    lang = ch.get('language', '-')
    niche = ch.get('niche', '-')
    days = ch.get('days', 0)
    subs = ch.get('subscribers', 0)
    views = ch.get('total_views', 0)
    vids = ch.get('videos', 0)
    daily_subs = ch.get('daily_subs', 0)
    lr = ch.get('like_rate', 0)
    vsr = ch.get('view_sub_ratio', 0)
    avg10 = ch.get('avg_views_10', 0)

    # Health indicator
    sev_counts = {"critical": 0, "major": 0, "info": 0}
    for iss in details.get("issues", []):
        sev_counts[iss.get("severity", "info")] += 1
    if diagnosis and diagnosis.get("diagnostics"):
        for iss in diagnosis["diagnostics"]:
            sev_counts[iss.get("severity", "info")] += 1

    if sev_counts["critical"] > 0:
        health = "🔴 需紧急处理"
    elif sev_counts["major"] > 0:
        health = "🟡 有改进空间"
    else:
        health = "🟢 健康"

    # Header
    blocks.append(heading(f"{name} — {health}", level=2))
    blocks.append(text(f"👤 {ch.get('operator', '-')} | 🌐 {lang} | 🎯 {niche} | 📅 {days}天"))
    blocks.append(text(""))

    # === 关键指标 ===
    blocks.append(heading("📊 关键指标", level=3))
    blocks.append(text(f"订阅: {subs:,} | 总播放: {views:,} | 视频: {vids} | 日增: {daily_subs}"))
    blocks.append(text(f"播放/订阅比: {vsr}x | 近10均播放: {avg10:,} | 点赞率: {lr}%"))

    # Benchmark comparison
    if lr > 2.0:
        blocks.append(text(f"  ✅ 点赞率 {lr}% 超过行业基准(1.5-2%)"))
    elif lr < 1.0:
        blocks.append(text(f"  ⚠️ 点赞率 {lr}% 低于行业基准(1.5-2%)，需优化互动引导"))

    if vsr > 100:
        blocks.append(text(f"  ✅ 播放/订阅比 {vsr}x，内容有传播力"))
    elif vsr < 50:
        blocks.append(text(f"  ⚠️ 播放/订阅比 {vsr}x 偏低，内容差异化不足"))

    # === 周增长 ===
    growth = details.get("growth", {})
    blocks.append(text(""))
    blocks.append(heading("📈 周增长", level=3))
    if growth.get("has_prev"):
        sub_ch = growth.get("subscribers_change", 0)
        view_ch = growth.get("views_change", 0)
        sub_icon = "📈" if sub_ch > 0 else "📉" if sub_ch < 0 else "➡️"
        view_icon = "📈" if view_ch > 0 else "📉" if view_ch < 0 else "➡️"
        blocks.append(text(f"{sub_icon} 订阅: {sub_ch:+d} (日均 {growth.get('daily_sub_growth', 0):+.1f})"))
        blocks.append(text(f"{view_icon} 播放: {view_ch:+,} (日均 {growth.get('daily_view_growth', 0):+,.0f})"))
        blocks.append(text(f"视频: {growth.get('videos_change', 0):+d}"))
    else:
        blocks.append(text("首次采集，无历史对比"))

    # === 诊断引擎分析 ===
    if diagnosis:
        vd = diagnosis.get("view_distribution", {})
        ef = diagnosis.get("engagement_funnel", {})
        tp = diagnosis.get("title_patterns", {})
        cc = diagnosis.get("content_consistency", {})
        seo = diagnosis.get("seo_analysis", {})

        # 播放分布
        if vd:
            blocks.append(text(""))
            blocks.append(heading("📊 播放分布", level=3))
            blocks.append(text(f"Top3占比: {vd.get('top3_ratio', 0):.1f}% | 头部(20%): {vd.get('head_ratio', 0):.1f}% | 长尾(50%): {vd.get('tail_ratio', 0):.1f}%"))
            if vd.get("cliff"):
                blocks.append(text(f"🔴 流量断崖: 最近播放仅为之前的 {vd.get('cliff_ratio', 0):.0%}"))

        # 标题分析
        if tp:
            blocks.append(text(""))
            blocks.append(heading("📝 标题分析", level=3))
            blocks.append(text(f"平均长度: {tp.get('avg_length', 0):.0f}字符 | Emoji率: {tp.get('emoji_rate', 0):.0f}%"))
            hw = tp.get("hook_words", {})
            if hw:
                top_hooks = sorted(hw.items(), key=lambda x: -x[1])[:5]
                hooks_str = ", ".join(f"{w}({c})" for w, c in top_hooks)
                blocks.append(text(f"高频钩子词: {hooks_str}"))

        # 互动漏斗
        if ef:
            blocks.append(text(""))
            blocks.append(heading("💬 互动漏斗", level=3))
            blocks.append(text(f"整体点赞率: {ef.get('overall_like_rate', 0):.2f}%"))
            blocks.append(text(f"零点赞视频: {ef.get('zero_like_count', 0)}条 ({ef.get('zero_like_ratio', 0):.0%})"))
            blocks.append(text(f"高互动视频(>2%): {ef.get('high_engagement_count', 0)}条"))

        # 内容一致性
        if cc:
            score = cc.get("consistency_score", 0)
            primary = cc.get("primary_type", "?")
            ratio = cc.get("primary_ratio", 0)
            blocks.append(text(""))
            blocks.append(heading("🎯 内容一致性", level=3))
            blocks.append(text(f"一致性评分: {score}/100 | 主类型: {primary} ({ratio:.0%})"))
            if score < 50:
                blocks.append(text("⚠️ 内容定位混杂，建议统一赛道"))

    # === 标题分析（原版） ===
    title = details.get("title_analysis", {})
    if title and not diagnosis:
        blocks.append(text(""))
        blocks.append(heading("📝 标题分析", level=3))
        blocks.append(text(f"平均标题长度: {title.get('avg_length', 0):.0f} 字符"))
        blocks.append(text(f"Emoji使用率: {title.get('emoji_ratio', 0):.0%}"))
        lp = title.get("length_performance", {})
        for bucket, data in lp.items():
            if data.get("count", 0) > 0:
                blocks.append(text(f"  {bucket}: {data['count']}条, 平均点赞率 {data['avg_like_rate']}%"))

    # === 时长分析 ===
    duration = details.get("duration_impact", {})
    if duration:
        blocks.append(text(""))
        blocks.append(heading("⏱️ 时长分析", level=3))
        for label, data in duration.items():
            blocks.append(text(f"  {label}: {data['count']}条, 平均播放 {data['avg_views']:,}, 点赞率 {data['avg_like_rate']}%"))

    # === 诊断问题 ===
    all_issues = list(details.get("issues", []))
    if diagnosis and diagnosis.get("diagnostics"):
        all_issues.extend(diagnosis["diagnostics"])

    if all_issues:
        blocks.append(text(""))
        blocks.append(heading("⚠️ 诊断问题", level=3))
        for iss in all_issues:
            sev_icon = {"critical": "🔴", "major": "🟡", "info": "🟢"}.get(iss.get("severity", "info"), "⚪")
            cat = f"[{iss.get('category', '')}] " if iss.get("category") else ""
            blocks.append(text(f"{sev_icon} {cat}{iss.get('issue', '')}"))
            if iss.get("detail"):
                blocks.append(text(f"    {iss['detail']}"))
            if iss.get("action"):
                # Only first line of action in summary
                first_line = iss["action"].split("\n")[0]
                blocks.append(text(f"    → {first_line}"))

    # === 热门视频 ===
    top_vids = details.get("top_videos", [])
    if top_vids:
        blocks.append(text(""))
        blocks.append(heading("📺 近期热门视频", level=3))
        for v in top_vids[:5]:
            vlr = v.get("likes", 0) / v["views"] * 100 if v["views"] > 0 else 0
            blocks.append(text(f"  • {v['title'][:50]} | {v['views']:,}播放 | {v['likes']:,}赞 | {vlr:.1f}%"))

    blocks.append(divider())
    return blocks


def build_full_report(panel_data: dict) -> list:
    """Build the complete Feishu document blocks with diagnosis integration."""
    blocks = []

    # Load diagnosis data (latest available)
    import glob
    diag_files = sorted(glob.glob(str(ROOT / "data" / "diagnosis_report_*.json")), reverse=True)
    diagnosis_data = {}
    if diag_files:
        try:
            diagnosis_data = json.loads(open(diag_files[0]).read())
            print(f"  📊 加载诊断数据: {Path(diag_files[0]).name}")
        except Exception:
            pass

    # Title
    blocks.append(heading("📺 短剧频道周度诊断报告", level=1))
    blocks.append(text(f"报告日期: {panel_data['report_date']}"))
    blocks.append(text(f"频道数: {len(panel_data['channels'])}"))
    blocks.append(text(""))

    # === 运营团队概览 ===
    operators = {}
    for ch in panel_data["channels"]:
        op = ch.get("operator", "未知")
        if op not in operators:
            operators[op] = []
        operators[op].append(ch)

    if len(operators) > 1:
        blocks.append(heading("👥 运营团队", level=2))
        for op, channels in operators.items():
            ch_names = ", ".join(c["name"] for c in channels)
            total_subs = sum(c.get("subscribers", 0) for c in channels)
            blocks.append(text(f"• {op}: {len(channels)}个频道 ({ch_names}) | 合计 {total_subs:,} 订阅"))
        blocks.append(text(""))

    # Summary table
    blocks.append(heading("📊 总览", level=2))
    for ch in panel_data["channels"]:
        details = panel_data.get("channel_details", {}).get(ch["name"], {})
        diag = diagnosis_data.get(ch["name"], {})

        # Health indicator
        sev_counts = {"critical": 0, "major": 0, "info": 0}
        for iss in details.get("issues", []):
            sev_counts[iss.get("severity", "info")] += 1
        if diag and diag.get("diagnostics"):
            for iss in diag["diagnostics"]:
                sev_counts[iss.get("severity", "info")] += 1

        if sev_counts["critical"] > 0:
            health = "🔴"
        elif sev_counts["major"] > 0:
            health = "🟡"
        else:
            health = "🟢"

        growth_info = ""
        growth = details.get("growth", {})
        if growth.get("has_prev"):
            sub_ch = growth.get("subscribers_change", 0)
            growth_info = f" | 周增{sub_ch:+d}"

        blocks.append(text(
            f"{health} {ch['name']} | {ch.get('language','')} {ch.get('niche','')} | {ch['subscribers']:,}订阅 | {ch['total_views']:,}播放 | {ch['like_rate']}%赞率{growth_info}"
        ))

    blocks.append(text(""))
    blocks.append(divider())

    # Per-channel detail
    blocks.append(heading("📋 自有账号分析", level=2))
    for ch in panel_data["channels"]:
        details = panel_data.get("channel_details", {}).get(ch["name"], {})
        diag = diagnosis_data.get(ch["name"], None)
        blocks.extend(build_channel_section(ch, details, diag))

    # Recommendations
    blocks.append(heading("🎯 行动建议", level=2))
    all_issues = []
    for ch in panel_data["channels"]:
        name = ch["name"]
        details = panel_data.get("channel_details", {}).get(name, {})
        diag = diagnosis_data.get(name, {})
        for iss in details.get("issues", []):
            all_issues.append({**iss, "channel": name})
        if diag and diag.get("diagnostics"):
            for iss in diag["diagnostics"]:
                all_issues.append({**iss, "channel": name})

    criticals = [i for i in all_issues if i.get("severity") == "critical"]
    majors = [i for i in all_issues if i.get("severity") == "major"]

    if criticals:
        blocks.append(text("🔴 紧急问题:", bold=True))
        for iss in criticals:
            cat = f"[{iss.get('category', '')}] " if iss.get("category") else ""
            blocks.append(text(f"  [{iss['channel']}] {cat}{iss.get('issue', '')}"))
            if iss.get("action"):
                blocks.append(text(f"    → {iss['action'].split(chr(10))[0]}"))

    if majors:
        blocks.append(text(""))
        blocks.append(text("🟡 重要改进:", bold=True))
        for iss in majors:
            cat = f"[{iss.get('category', '')}] " if iss.get("category") else ""
            blocks.append(text(f"  [{iss['channel']}] {cat}{iss.get('issue', '')}"))
            if iss.get("action"):
                blocks.append(text(f"    → {iss['action'].split(chr(10))[0]}"))

    blocks.append(text(""))
    blocks.append(divider())
    blocks.append(text(f"数据采集: {panel_data['report_date']} | 来源: YouTube Data API v3 + 诊断引擎 | 面板: https://duanju.opspilot.me"))

    return blocks


def send_doc_link(doc_id: str, title: str):
    """Send document link via Feishu IM."""
    client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
    url = f"https://bytedance.larkoffice.com/docx/{doc_id}"

    # Get chat_id from accounts or use default
    accounts_path = ROOT / "data" / "feishu_accounts.json"
    chat_id = ""
    if accounts_path.exists():
        try:
            accts = json.loads(accounts_path.read_text())
            chat_id = accts.get("default_chat_id", "")
        except Exception:
            pass

    if not chat_id:
        print(f"  ℹ️ 文档链接: {url}")
        return url

    msg_content = json.dumps({"text": f"📋 {title}\n\n{url}"})
    req = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(
            CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("text")
            .content(msg_content).build()
        ).build()
    resp = client.im.v1.message.create(req)
    if resp.code == 0:
        print(f"  ✅ 链接已发送到飞书")
    else:
        print(f"  ⚠️ 发送失败: {resp.msg}")

    return url


def main():
    # Load latest panel data
    panel_path = ROOT / "data" / "own" / "channel_analysis_latest.json"
    if not panel_path.exists():
        print("❌ 没有分析数据，先运行: python3 scripts/channel_weekly_snapshot.py")
        sys.exit(1)

    panel_data = json.loads(panel_path.read_text())
    print(f"📊 加载 {len(panel_data['channels'])} 个频道数据")

    # Create Feishu document
    title = f"短剧频道周度诊断报告 {panel_data['report_date']}"
    print(f"📝 创建飞书文档: {title}")
    doc_id = create_feishu_doc(title)
    print(f"  文档ID: {doc_id}")

    # Write content
    blocks = build_full_report(panel_data)
    print(f"  ✍️ 写入 {len(blocks)} 个内容块...")
    write_blocks_to_doc(doc_id, blocks)

    # Send link
    url = send_doc_link(doc_id, title)
    print(f"\n✅ 飞书文档: https://bytedance.larkoffice.com/docx/{doc_id}")

    # Save doc_id for future reference
    ref_path = ROOT / "data" / "feishu_doc_refs.json"
    refs = {}
    if ref_path.exists():
        try:
            refs = json.loads(ref_path.read_text())
        except Exception:
            pass
    refs[panel_data["report_date"]] = {
        "doc_id": doc_id,
        "title": title,
        "url": f"https://bytedance.larkoffice.com/docx/{doc_id}",
        "channels": len(panel_data["channels"]),
        "created_at": datetime.now().isoformat(),
    }
    ref_path.write_text(json.dumps(refs, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    from datetime import datetime
    main()
