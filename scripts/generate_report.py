#!/usr/bin/env python3
"""生成Dream Drama分析PDF"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"

# 读取分析数据
with open(DATA_DIR / "competitor_insights/channel_UCsWrD2rmFhVWfbpCVc3O2Bg.json") as f:
    data = json.load(f)

llm = data.get("llm_analysis", {})
distill = llm.get("distill", {})
stats = llm.get("stats", {})
why = distill.get("why", {})
what = distill.get("what", {})
insights = what.get("actionable_insights", {})

# 格式化列表
def format_list(items):
    return "".join(f"<li>{item}</li>" for item in items)

def format_tags(items):
    return "".join(f'<span class="tag">{t}</span>' for t in items)

def format_tips(items):
    return "".join(f'<div class="tip">{t}</div>' for t in items)

def format_warns(items):
    return "".join(f'<div class="warn">{p}</div>' for p in items)

def format_videos(videos):
    html = ""
    for bp in videos:
        html += f'''
<div class="video">
<div class="video-title">{bp.get("title", "")}</div>
<div class="video-stats">▶ {bp.get("views", 0):,} 播放</div>
<p><strong>成功要素:</strong> {bp.get("why_works", "")}</p>
</div>'''
    return html

def format_formulas(formulas):
    html = ""
    for f in formulas:
        if ":" in f:
            parts = f.split(":", 1)
            html += f'<li><strong>{parts[0]}:</strong> {parts[1]}</li>'
        else:
            html += f"<li>{f}</li>"
    return html

# 生成HTML
html = f'''<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 40px; color: #333; line-height: 1.6; }}
h1 {{ color: #1a1a2e; border-bottom: 3px solid #e94560; padding-bottom: 10px; }}
h2 {{ color: #16213e; margin-top: 30px; }}
h3 {{ color: #0f3460; }}
.section {{ background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 15px 0; }}
.stat-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 15px; margin: 20px 0; }}
.stat-box {{ background: #fff; padding: 15px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
.stat-val {{ font-size: 24px; font-weight: bold; color: #e94560; }}
.stat-label {{ font-size: 12px; color: #666; margin-top: 5px; }}
.tag {{ display: inline-block; background: #e3f2fd; color: #1565c0; padding: 4px 10px; border-radius: 4px; margin: 3px; font-size: 13px; }}
.growth {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px; border-radius: 10px; margin: 20px 0; }}
.growth h2 {{ color: white; margin-top: 0; }}
.tip {{ background: #fff8e1; border-left: 4px solid #ffc107; padding: 12px; margin: 10px 0; }}
.warn {{ background: #fce4ec; border-left: 4px solid #e91e63; padding: 12px; margin: 10px 0; }}
.video {{ background: #fff; padding: 15px; border-radius: 8px; margin: 10px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
.video-title {{ font-weight: bold; color: #1a1a2e; }}
.video-stats {{ color: #666; font-size: 14px; margin-top: 5px; }}
.footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #ddd; color: #999; font-size: 12px; }}
</style>
</head>
<body>

<h1>📊 竞品频道深度分析报告</h1>

<div class="section">
<h2>{data.get("name", "Dream Drama")}</h2>
<p><strong>频道ID:</strong> {data.get("channel_id", "")} | <strong>语言:</strong> {data.get("language", "")} | <strong>层级:</strong> {data.get("tier", "")}</p>
<p><strong>分析时间:</strong> {llm.get("analyzed_at", "")[:19]}</p>
</div>

<div class="stat-grid">
<div class="stat-box">
<div class="stat-val">{data.get("subscribers", 0):,}</div>
<div class="stat-label">当前订阅</div>
</div>
<div class="stat-box">
<div class="stat-val">{stats.get("avg_views", 0):,}</div>
<div class="stat-label">平均播放</div>
</div>
<div class="stat-box">
<div class="stat-val">{stats.get("breakout_count", 0)}</div>
<div class="stat-label">爆款数(≥1万)</div>
</div>
<div class="stat-box">
<div class="stat-val">{data.get("total_videos", 0)}</div>
<div class="stat-label">总视频数</div>
</div>
</div>

<div class="growth">
<h2>📈 增长数据</h2>
<p><strong>原始订阅:</strong> {data.get("subscribers", 0) - 26187:,} → <strong>当前:</strong> {data.get("subscribers", 0):,} | <strong>增长:</strong> +26,187 (64x)</p>
<p><strong>入库日期:</strong> 2026-06-20 | <strong>观测周期:</strong> 约1个月</p>
<p><strong>频道阶段:</strong> {why.get("trajectory", "")}</p>
</div>

<h2>🎯 增长驱动因素</h2>
<div class="section">
<ul>
{format_list(why.get("growth_drivers", []))}
</ul>
</div>

<h2>👥 受众画像</h2>
<div class="section">
<p>{why.get("audience_fit", "")}</p>
</div>

<h2>📝 内容策略</h2>
<div class="section">
<p><strong>核心打法:</strong> {what.get("content_strategy", "")}</p>

<h3>主打题材</h3>
{format_tags(what.get("top_themes", []))}

<h3>标题公式</h3>
<ul>
{format_formulas(what.get("title_formulas", []))}
</ul>

<h3>钩子模式</h3>
<ul>
{format_list(what.get("hook_patterns", []))}
</ul>

<h3>封面策略</h3>
<p>{what.get("cover_strategy", "")}</p>
</div>

<h2>🏆 爆款视频分析</h2>
{format_videos(what.get("best_performers", []))}

<h2>💡 可执行洞察</h2>

<h3>✅ 可复制技巧</h3>
{format_tips(insights.get("copyable_tactics", []))}

<h3>⚠️ 踩坑提醒</h3>
{format_warns(insights.get("avoid_pitfalls", []))}

<div class="footer">
<p>数据来源: YouTube Data API + LLM分析 | 生成时间: {llm.get("analyzed_at", "")[:19]} | 模型: {llm.get("model", "")}</p>
</div>

</body>
</html>'''

# 写入HTML文件
output_path = ROOT / "output" / "dream_drama_analysis.html"
output_path.parent.mkdir(exist_ok=True)
with open(output_path, "w") as f:
    f.write(html)

print(f"HTML已生成: {output_path}")
print("请用浏览器打开HTML文件，然后Ctrl+P打印为PDF")
