#!/usr/bin/env python3
"""频道诊断PDF报告生成器

用法:
  python3 scripts/gen_diagnosis_pdf.py --channel "Beer Anime"
  python3 scripts/gen_diagnosis_pdf.py --all
  python3 scripts/gen_diagnosis_pdf.py --channel "Beer Anime" --output /tmp/report.pdf
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
DIAG_DIR = ROOT / "data" / "own" / "channel_diagnosis"
OUTPUT_DIR = ROOT / "data" / "own" / "reports"


def load_diagnosis(channel_name: str) -> dict | None:
    slug = channel_name.replace(" ", "_")
    path = DIAG_DIR / f"{slug}_latest.json"
    if not path.exists():
        print(f"❌ 无诊断数据: {path}")
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def severity_color(sev: str) -> str:
    return {"critical": "#ef4444", "major": "#f59e0b", "info": "#3b82f6"}.get(sev, "#6b7280")


def severity_label(sev: str) -> str:
    return {"critical": "严重", "major": "重要", "info": "提示"}.get(sev, sev)


def score_color(score: float) -> str:
    if score >= 7: return "#22c55e"
    if score >= 5: return "#f59e0b"
    return "#ef4444"


def grade_bg(grade: str) -> str:
    return {"A": "#22c55e", "B": "#3b82f6", "C": "#f59e0b", "D": "#ef4444", "F": "#ef4444"}.get(grade, "#6b7280")


def build_html(data: dict) -> str:
    llm = data.get("channel_llm", {})
    name = data.get("channel_name", "未知频道")
    health = llm.get("health_score", 0)
    grade = llm.get("health_grade", "?")
    summary = llm.get("summary", "")
    strengths = llm.get("strengths", [])
    problems = llm.get("problems", [])
    actions = llm.get("actions", [])
    discoveries = llm.get("ai_discoveries", [])
    bottleneck = llm.get("bottleneck", {})
    vs = data.get("video_scores", [])
    analyzed_at = data.get("analyzed_at", datetime.now().strftime("%Y-%m-%d %H:%M"))

    # Video table rows
    video_rows = ""
    sorted_vs = sorted(vs, key=lambda x: x.get("views", 0), reverse=True)
    for i, v in enumerate(sorted_vs[:20], 1):
        title = v.get("title", "?")[:60]
        views = v.get("views", 0)
        likes = v.get("likes", 0)
        lr = v.get("like_rate", 0)
        score = v.get("score", 0)
        hooks = v.get("title_analysis", {}).get("hooks", {})
        active = [k for k, val in hooks.items() if val is True]
        other = hooks.get("other", [])
        hook_count = len(active) + len(other)
        hook_badge = f'<span class="badge badge-{"good" if hook_count >= 3 else "warn" if hook_count >= 2 else "bad"}">{hook_count}钩</span>'
        cs = v.get("cover_synergy", {}).get("score")
        cs_badge = f'<span class="badge badge-{"good" if cs and cs >= 7 else "warn" if cs and cs >= 5 else "bad"}">{cs or "-"}</span>' if cs else '<span class="badge">-</span>'
        
        video_rows += f"""
        <tr>
          <td>{i}</td>
          <td class="title-cell">{title}</td>
          <td class="num">{views:,}</td>
          <td class="num">{lr:.1f}%</td>
          <td class="num"><span style="color:{score_color(score)};font-weight:700">{score:.1f}</span></td>
          <td>{hook_badge}</td>
          <td>{cs_badge}</td>
        </tr>"""

    # Strengths HTML
    strengths_html = ""
    for s in strengths:
        area = s.get("area", "") if isinstance(s, dict) else ""
        detail = s.get("detail", "") if isinstance(s, dict) else str(s)
        strengths_html += f'<div class="item"><b>{area}</b>：{detail}</div>\n'

    # Problems HTML
    problems_html = ""
    for p in problems:
        if isinstance(p, dict):
            sev = p.get("severity", "info")
            area = p.get("area", "")
            detail = p.get("detail", "")
            evidence = p.get("evidence", "")
            problems_html += f"""
            <div class="problem-item">
              <div class="problem-header">
                <span class="sev-badge" style="background:{severity_color(sev)}">{severity_label(sev)}</span>
                <b>{area}</b>
              </div>
              <div class="problem-detail">{detail}</div>
              {f'<div class="evidence">📊 {evidence}</div>' if evidence else ''}
            </div>"""

    # Actions HTML
    actions_html = ""
    for a in actions:
        if isinstance(a, dict):
            pri = a.get("priority", "?")
            act = a.get("action", "")
            based = a.get("based_on", "")
            steps = a.get("concrete_steps", "")
            impact = a.get("expected_impact", "")
            actions_html += f"""
            <div class="action-item">
              <div class="action-header"><span class="pri-badge">P{pri}</span> <b>{act}</b></div>
              {f'<div class="action-detail">📌 {based}</div>' if based else ''}
              {f'<div class="action-detail">📋 {steps}</div>' if steps else ''}
              {f'<div class="action-detail" style="color:#22c55e">📈 {impact}</div>' if impact else ''}
            </div>"""

    # AI Discoveries HTML
    disc_html = ""
    for d in discoveries:
        if isinstance(d, dict):
            pattern = d.get("pattern", "")
            insight = d.get("insight", "")
            disc_html += f'<div class="item"><b>🔮 {pattern}</b><br><span class="muted">{insight}</span></div>\n'

    # Bottleneck HTML
    bn_html = ""
    if bottleneck:
        primary = bottleneck.get("primary", "")
        evidence = bottleneck.get("evidence", "")
        next_lever = bottleneck.get("next_lever", "")
        bn_html = f"""
        <div class="bottleneck-box">
          <div class="section-title">🎯 当前瓶颈</div>
          <div style="font-size:15px;font-weight:700;margin:6px 0">{primary}</div>
          {f'<div class="muted">📊 {evidence}</div>' if evidence else ''}
          {f'<div style="margin-top:6px;color:#8b5cf6">🔧 下一步：{next_lever}</div>' if next_lever else ''}
        </div>"""

    return f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  @page {{
    size: A4;
    margin: 20mm 18mm;
    @bottom-center {{
      content: counter(page) " / " counter(pages);
      font-size: 9px;
      color: #9ca3af;
    }}
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: "Helvetica Neue", Arial, "PingFang SC", "Microsoft YaHei", sans-serif;
    font-size: 11px;
    line-height: 1.5;
    color: #1f2937;
    background: #fff;
  }}

  /* Header */
  .header {{
    display: flex;
    align-items: center;
    gap: 20px;
    padding: 24px;
    background: linear-gradient(135deg, #1e1b4b, #312e81);
    color: white;
    border-radius: 12px;
    margin-bottom: 20px;
  }}
  .health-circle {{
    width: 80px;
    height: 80px;
    border-radius: 50%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    border: 4px solid rgba(255,255,255,0.3);
    flex-shrink: 0;
  }}
  .health-score {{
    font-size: 28px;
    font-weight: 800;
    line-height: 1;
  }}
  .health-grade {{
    font-size: 11px;
    opacity: 0.8;
    margin-top: 2px;
  }}
  .header-info {{
    flex: 1;
  }}
  .header-info h1 {{
    font-size: 22px;
    font-weight: 700;
    margin-bottom: 4px;
  }}
  .header-info .meta {{
    font-size: 10px;
    opacity: 0.7;
  }}
  .summary {{
    font-size: 13px;
    line-height: 1.6;
    margin-top: 8px;
    opacity: 0.9;
  }}

  /* Sections */
  .section {{
    margin-bottom: 16px;
    page-break-inside: avoid;
  }}
  .section-title {{
    font-size: 13px;
    font-weight: 700;
    color: #4338ca;
    margin-bottom: 8px;
    padding-bottom: 4px;
    border-bottom: 2px solid #e0e7ff;
  }}

  /* Items */
  .item {{
    padding: 6px 0;
    font-size: 11px;
    border-bottom: 1px solid #f3f4f6;
  }}
  .item:last-child {{ border-bottom: none; }}
  .muted {{ color: #6b7280; font-size: 10px; }}

  /* Problems */
  .problem-item {{
    padding: 10px 12px;
    margin-bottom: 8px;
    border-radius: 8px;
    background: #fef2f2;
    border-left: 4px solid #ef4444;
  }}
  .problem-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }}
  .sev-badge {{
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    color: white;
    font-size: 9px;
    font-weight: 600;
  }}
  .problem-detail {{
    font-size: 11px;
    color: #374151;
    line-height: 1.5;
  }}
  .evidence {{
    font-size: 10px;
    color: #6b7280;
    margin-top: 4px;
    padding: 4px 8px;
    background: #f9fafb;
    border-radius: 4px;
  }}

  /* Actions */
  .action-item {{
    padding: 10px 12px;
    margin-bottom: 8px;
    border-radius: 8px;
    background: #f0fdf4;
    border-left: 4px solid #22c55e;
  }}
  .action-header {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 4px;
  }}
  .pri-badge {{
    display: inline-block;
    padding: 1px 8px;
    border-radius: 10px;
    background: #4338ca;
    color: white;
    font-size: 9px;
    font-weight: 700;
  }}
  .action-detail {{
    font-size: 10px;
    color: #374151;
    margin-top: 3px;
    line-height: 1.4;
  }}

  /* Bottleneck */
  .bottleneck-box {{
    padding: 14px 16px;
    background: linear-gradient(90deg, #fffbeb, #fef3c7);
    border-left: 4px solid #f59e0b;
    border-radius: 8px;
    margin-bottom: 16px;
  }}

  /* Table */
  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 10px;
  }}
  th {{
    background: #f1f5f9;
    padding: 6px 8px;
    text-align: left;
    font-weight: 600;
    color: #475569;
    border-bottom: 2px solid #e2e8f0;
  }}
  td {{
    padding: 5px 8px;
    border-bottom: 1px solid #f1f5f9;
    vertical-align: top;
  }}
  tr:nth-child(even) {{ background: #f8fafc; }}
  .title-cell {{ max-width: 280px; word-break: break-all; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .badge {{
    display: inline-block;
    padding: 1px 6px;
    border-radius: 8px;
    font-size: 9px;
    font-weight: 600;
  }}
  .badge-good {{ background: #dcfce7; color: #166534; }}
  .badge-warn {{ background: #fef3c7; color: #92400e; }}
  .badge-bad {{ background: #fef2f2; color: #991b1b; }}

  /* Two columns */
  .two-col {{
    display: flex;
    gap: 16px;
  }}
  .two-col > div {{
    flex: 1;
  }}

  /* Footer */
  .footer {{
    margin-top: 20px;
    padding-top: 10px;
    border-top: 1px solid #e5e7eb;
    font-size: 9px;
    color: #9ca3af;
    text-align: center;
  }}
</style>
</head>
<body>

<!-- Header -->
<div class="header">
  <div class="health-circle">
    <div class="health-score">{health:.1f}</div>
    <div class="health-grade">{grade}</div>
  </div>
  <div class="header-info">
    <h1>{name}</h1>
    <div class="meta">生成时间: {analyzed_at} | 视频数: {len(vs)}</div>
    <div class="summary">{summary}</div>
  </div>
</div>

<!-- Bottleneck -->
{bn_html}

<!-- Strengths & Problems -->
<div class="two-col">
  <div class="section">
    <div class="section-title">✅ 核心优势</div>
    {strengths_html}
  </div>
  <div class="section">
    <div class="section-title">🚨 核心问题</div>
    {problems_html}
  </div>
</div>

<!-- Actions -->
<div class="section">
  <div class="section-title">📋 行动清单</div>
  {actions_html}
</div>

<!-- AI Discoveries -->
{f'''<div class="section">
  <div class="section-title">🔮 AI发现规律</div>
  {disc_html}
</div>''' if disc_html else ''}

<!-- Video Table -->
<div class="section">
  <div class="section-title">📹 视频诊断明细（按播放量排序 Top 20）</div>
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>标题</th>
        <th>播放</th>
        <th>赞率</th>
        <th>评分</th>
        <th>钩子</th>
        <th>协同</th>
      </tr>
    </thead>
    <tbody>
      {video_rows}
    </tbody>
  </table>
</div>

<!-- Footer -->
<div class="footer">
  短剧YouTube频道诊断报告 · 自动生成 · {datetime.now().strftime("%Y-%m-%d")}
</div>

</body>
</html>"""


def generate_pdf(channel_name: str, output_path: str | None = None) -> str | None:
    data = load_diagnosis(channel_name)
    if not data:
        return None

    html = build_html(data)

    if not output_path:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = channel_name.replace(" ", "_")
        date = datetime.now().strftime("%Y%m%d")
        output_path = str(OUTPUT_DIR / f"{slug}_diagnosis_{date}.pdf")

    from weasyprint import HTML
    HTML(string=html).write_pdf(output_path)
    size_kb = Path(output_path).stat().st_size / 1024
    print(f"✅ PDF生成: {output_path} ({size_kb:.0f}KB)")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="频道诊断PDF报告")
    parser.add_argument("--channel", help="频道名")
    parser.add_argument("--all", action="store_true", help="所有频道")
    parser.add_argument("--output", help="输出路径")
    args = parser.parse_args()

    if not args.channel and not args.all:
        parser.print_help()
        return

    if args.all:
        registry = json.loads((ROOT / "data" / "own" / "our_channels.json").read_text())
        for ch in registry["channels"]:
            name = ch["name"]
            try:
                generate_pdf(name)
            except Exception as e:
                print(f"⚠️ {name}: {e}")
    else:
        generate_pdf(args.channel, args.output)


if __name__ == "__main__":
    main()
