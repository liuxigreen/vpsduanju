#!/usr/bin/env python3
"""
duanju Panel v3 — 专家驱动的短剧运营面板

功能：
- 仪表盘：数据概览
- 上架助手：输入剧名 → 标题(3) + 封面指令(3) + 频道配置
- 账号分析：竞品数据看板
- 规则库：三位专家规则浏览
- AI助手：直接对话 nuwa

用法：
    python3 scripts/panel_v3.py --port 8009 --open
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import threading
import time
import traceback
from datetime import datetime, timedelta, timezone
from pathlib import Path
import socket
import subprocess
import httpx
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


class DualStackServer(ThreadingHTTPServer):
    """IPv6 dual-stack: accepts both IPv4 and IPv6 connections."""
    address_family = socket.AF_INET6

    def server_bind(self):
        self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import keychain_helper as kc

# ── 数据路径集中管理 ──────────────────────────────────────────
# 所有 data/ 下的路径在这里定义一次，API 里用 DATA_PATHS["xxx"] 引用
DATA_PATHS = {
    # 自有频道
    "our_channels":    ROOT / "data" / "own" / "our_channels.json",
    "channel_analysis": ROOT / "data" / "own" / "channel_analysis_latest.json",
    "channel_diagnosis": ROOT / "data" / "own" / "channel_diagnosis",
    # 竞品
    "competitor_dynamic": ROOT / "data" / "competitors_channels_all.json",
    "competitor_static":  ROOT / "data" / "competitors_50channels.json",
    "competitor_tiers":   ROOT / "data" / "competitor_tiers.json",
    # 快照（P3-10: 修正路径，与 channel_weekly_snapshot.py 的 SNAPSHOT_DIR 一致）
    "channel_snapshots": ROOT / "data" / "own" / "channel_snapshots",
    # 市场洞察
    "market_insights": ROOT / "data",
    # 蒸馏
    "distill_outputs": ROOT / "distill" / "outputs",
    # 规则库
    "rules_dir": ROOT / "data" / "rules",
    # 提案历史
    "proposal_history": ROOT / "data" / "proposal_history",
    # 剧本分析
    "drama_analysis": ROOT / "data" / "drama_analysis",
    # 采集注册表
    "registry_deep60": ROOT / "data" / "registry_collected" / "deep_60_fast.json",
    # manifests
    "manifests": ROOT / "data" / "manifests",
    # YouTube OAuth
    "accounts_json": ROOT.parent / ".hermes" / "duanju" / "accounts.json",
    "yt_accounts_cache": ROOT / "data" / "own" / "yt_accounts_cache.json",
}


def _check_path(key: str, label: str = "") -> Path | None:
    """检查 DATA_PATHS 里的路径是否存在，不存在则打日志"""
    p = DATA_PATHS.get(key)
    if p and p.exists():
        return p
    log.warning("数据文件缺失: %s → %s", label or key, p)
    return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("panel_v3")

JOB_LOCK = threading.Lock()

# 简单内存缓存: key=(drama,region,action) -> (timestamp, result)
_GENERATION_CACHE: dict = {}
CACHE_TTL_SECONDS = 300  # 5分钟缓存

# ── 文件级 mtime 缓存 ─────────────────────────────────────────
# 每次请求检查 stat().st_mtime，不变则返回缓存对象，避免重复 read_text + json.loads
from typing import Any

_FILE_CACHE: dict[str, tuple[float, Any]] = {}  # path -> (mtime, parsed_data)
_FILE_CACHE_LOCK = threading.Lock()
FILE_CACHE_TTL = 30  # 即使 mtime 未变，每 30s 也重新 stat 一次（避免高频 stat）
_FILE_CACHE_STAT: dict[str, float] = {}  # path -> last_stat_time


def cached_json_read(path: Path | str, encoding: str = "utf-8") -> dict | list:
    """读取 JSON 文件，基于 mtime 的内存缓存。线程安全。"""
    p = str(path)
    now = time.time()
    with _FILE_CACHE_LOCK:
        cached = _FILE_CACHE.get(p)
        if cached:
            cached_mtime, cached_data = cached
            last_stat = _FILE_CACHE_STAT.get(p, 0)
            # TTL 内直接返回，不 stat
            if now - last_stat < FILE_CACHE_TTL:
                return cached_data
            # 超过 TTL，检查 mtime
            try:
                current_mtime = Path(p).stat().st_mtime
            except OSError:
                return cached_data  # 文件被删了，返回旧缓存
            _FILE_CACHE_STAT[p] = now
            if current_mtime == cached_mtime:
                return cached_data
            # mtime 变了，重新读取
        else:
            try:
                current_mtime = Path(p).stat().st_mtime
            except OSError:
                return {}
            _FILE_CACHE_STAT[p] = now

    # 缓存未命中或 mtime 变了 → 读文件（释放锁避免阻塞其他请求）
    try:
        data = json.loads(Path(p).read_text(encoding=encoding))
    except (OSError, json.JSONDecodeError) as e:
        log.warning("cached_json_read 失败: %s → %s", p, e)
        return {}
    with _FILE_CACHE_LOCK:
        _FILE_CACHE[p] = (current_mtime, data)
    return data


def cached_text_read(path: Path | str, encoding: str = "utf-8") -> str:
    """读取文本文件，基于 mtime 的内存缓存。"""
    p = str(path)
    now = time.time()
    with _FILE_CACHE_LOCK:
        cached = _FILE_CACHE.get(p)
        if cached:
            cached_mtime, cached_data = cached
            last_stat = _FILE_CACHE_STAT.get(p, 0)
            if now - last_stat < FILE_CACHE_TTL:
                return cached_data
            try:
                current_mtime = Path(p).stat().st_mtime
            except OSError:
                return cached_data
            _FILE_CACHE_STAT[p] = now
            if current_mtime == cached_mtime:
                return cached_data
        else:
            try:
                current_mtime = Path(p).stat().st_mtime
            except OSError:
                return ""
            _FILE_CACHE_STAT[p] = now

    try:
        data = Path(p).read_text(encoding=encoding)
    except OSError as e:
        log.warning("cached_text_read 失败: %s → %s", p, e)
        return ""
    with _FILE_CACHE_LOCK:
        _FILE_CACHE[p] = (current_mtime, data)
    return data


_COMPETITOR_INDEX: dict = {}  # 竞品频道 ID 索引缓存

def invalidate_file_cache(path: Path | str | None = None):
    """清除文件缓存。path=None 清除全部。"""
    with _FILE_CACHE_LOCK:
        if path is None:
            _FILE_CACHE.clear()
            _FILE_CACHE_STAT.clear()
        else:
            p = str(path)
            _FILE_CACHE.pop(p, None)
            _FILE_CACHE_STAT.pop(p, None)


def _cache_key(drama: str, region: str, action: str) -> str:
    return f"{drama}:{region}:{action}"


def _get_cached(drama: str, region: str, action: str):
    key = _cache_key(drama, region, action)
    entry = _GENERATION_CACHE.get(key)
    if not entry:
        return None
    ts, result = entry
    if datetime.now(timezone.utc).timestamp() - ts > CACHE_TTL_SECONDS:
        del _GENERATION_CACHE[key]
        return None
    return result


def _set_cached(drama: str, region: str, action: str, result: dict):
    _GENERATION_CACHE[_cache_key(drama, region, action)] = (datetime.now(timezone.utc).timestamp(), result)


# ── duanju Agent 调用 ──────────────────────────
# 地区→Agent语种映射
REGION_TO_LANG = {
    "hk": "繁中", "tw": "繁中", "sg": "繁中", "mo": "繁中",
    "en": "en", "us": "en", "gb": "en", "au": "en", "ca": "en",
    "id": "id",
    "es": "es", "mx": "es", "ar": "es", "cl": "es", "co": "es", "pe": "es",
    "pt": "葡萄牙", "br": "葡萄牙",
    "tr": "tr",
    "jp": "jp",
}

# 豆包搜索缓存目录
DRAMA_ANALYSIS_DIR = DATA_PATHS["drama_analysis"]


def _lookup_local_drama(drama_name: str) -> str:
    """从本地查找剧情数据：优先 drama_analysis/，其次 drama_db.json"""
    # 1. 查 drama_analysis/ 目录（精确匹配）
    if DRAMA_ANALYSIS_DIR.exists():
        exact = DRAMA_ANALYSIS_DIR / f"{drama_name}.json"
        if exact.exists():
            try:
                data = cached_json_read(exact)
                return data.get("raw_search", "") or data.get("plot_summary", "")
            except Exception:
                pass
        # 模糊匹配（包含关键词）
        for f in DRAMA_ANALYSIS_DIR.glob("*.json"):
            if f.name == "test.json" or f.name.startswith("manual_"):
                continue
            if drama_name in f.stem:
                try:
                    data = cached_json_read(f)
                    return data.get("raw_search", "") or data.get("plot_summary", "")
                except Exception:
                    continue

    # 2. 查 drama_db.json（豆包联网搜索的剧情库）
    drama_db_path = ROOT / "data" / "drama_db.json"
    if drama_db_path.exists():
        try:
            db = cached_json_read(drama_db_path)
            # 精确匹配
            if drama_name in db:
                entry = db[drama_name]
                plot = entry.get("plot", "")
                if plot:
                    log.info(f"📖 从 drama_db 精确匹配: {drama_name}")
                    return plot
            # 模糊匹配（key 包含输入，或输入包含 key）
            for key, entry in db.items():
                if drama_name in key or key in drama_name:
                    plot = entry.get("plot", "")
                    if plot:
                        log.info(f"📖 从 drama_db 模糊匹配: {key}")
                        return plot
        except Exception:
            pass

    return ""


# ── 蒸馏数据加载 ──────────────────────────
def _load_distill_for_region(region: str) -> dict:
    """加载指定地区的蒸馏数据（从 duanju profile knowledge 目录）"""
    lang = REGION_TO_LANG.get(region, region)
    distill_path = Path.home() / ".hermes" / "profiles" / "duanju" / "knowledge" / lang / "distill.json"
    if not distill_path.exists():
        # fallback: 尝试直接用 region 名
        distill_path = Path.home() / ".hermes" / "profiles" / "duanju" / "knowledge" / region / "distill.json"
    if not distill_path.exists():
        return {}
    try:
        return cached_json_read(distill_path)
    except Exception:
        return {}


def _extract_title_hashtags(distill: dict) -> list[str]:
    """从蒸馏数据中提取标题 hashtag 列表（去重排序）"""
    import re as _re
    hashtags = set()
    # 从 key_words 中提取 # 开头的
    keywords = distill.get("stats", {}).get("key_words", [])
    for kw in keywords:
        if kw.startswith("#"):
            hashtags.add(kw.lower())
    # 从 what/examples 中提取
    for w in distill.get("what", []):
        for ex in w.get("examples", []):
            for tag in _re.findall(r"#\w+", ex):
                hashtags.add(tag.lower())
    # 从 how/title_skeletons/examples 中提取
    how = distill.get("how", {})
    if isinstance(how, dict):
        for sk in how.get("title_skeletons", []):
            for ex in sk.get("examples", []):
                for tag in _re.findall(r"#\w+", ex):
                    hashtags.add(tag.lower())
    # 过滤掉纯数字和过短的
    return sorted([h for h in hashtags if len(h) > 2 and not h[1:].isdigit()])


def _calc_title_target_length(distill: dict, num_hashtags: int = 2) -> int:
    """计算标题目标长度（蒸馏平均值 - 预留hashtag空间）"""
    avg_len = distill.get("stats", {}).get("avg_title_length", 80)
    # 估算 hashtag 占用长度: "#tag " ≈ 每个5-8字符
    hashtag_overhead = num_hashtags * 7
    # 目标: 总长度(含hashtag) = 蒸馏平均值, 内容长度 = 平均值 - hashtag开销
    target = max(30, avg_len - hashtag_overhead)
    return target


# ── 持久会话管理 ──────────────────────────
SESSION_ID_FILE = ROOT / ".hermes" / "profiles" / "duanju" / "memories" / "session_id.txt"


def _get_session_id() -> str | None:
    """获取已有的session_id"""
    if SESSION_ID_FILE.exists():
        sid = SESSION_ID_FILE.read_text().strip()
        if sid:
            return sid
    return None


def _save_session_id(session_id: str):
    """保存session_id到文件"""
    SESSION_ID_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_ID_FILE.write_text(session_id)
    log.info(f"💾 Session ID 已保存: {session_id}")



# === Hermes API Server 配置 ===
HERMES_API_URL = "http://127.0.0.1:8642/v1/chat/completions"
HERMES_API_KEY="duanju-panel-2026"

def _call_hermes_api(prompt: str, timeout: int = 300) -> str:
    """通过 Hermes API Server 流式调用（常驻进程，不会超时）"""
    import httpx
    full_response = []
    with httpx.stream(
        "POST",
        HERMES_API_URL,
        headers={"Authorization": f"Bearer {HERMES_API_KEY}"},
        json={
            "model": "duanju",
            "messages": [{"role": "user", "content": prompt}],
            "stream": True,
        },
        timeout=timeout,
    ) as resp:
        resp.raise_for_status()
        for line in resp.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                chunk = json.loads(data)
                delta = chunk.get("choices", [{}])[0].get("delta", {})
                if "content" in delta:
                    full_response.append(delta["content"])
            except json.JSONDecodeError:
                continue
    return "".join(full_response)

def _build_hermes_cmd(prompt: str, resume: bool = False, toolsets: str = "") -> list[str]:
    """构建hermes命令。用 -z oneshot 模式，-t 限制工具才生效"""
    hermes_bin = str(Path.home() / ".hermes" / "hermes-agent" / "venv" / "bin" / "hermes")
    cmd = [hermes_bin, "-p", "duanju"]
    if toolsets:
        cmd.extend(["-t", toolsets])
    if resume:
        session_id = _get_session_id()
        if session_id:
            cmd.extend(["--resume", session_id])
    cmd.extend(["-z", prompt])
    return cmd


def _extract_session_id(output: str) -> str | None:
    """从hermes输出中提取session_id"""
    match = re.search(r'Session:\s+(\d{8}_\d{6}_[a-f0-9]+)', output)
    if match:
        return match.group(1)
    match = re.search(r'--resume\s+(\d{8}_\d{6}_[a-f0-9]+)', output)
    if match:
        return match.group(1)
    return None


def _load_duanju_memories(n: int = 10) -> str:
    """加载duanju agent的最近成功记忆，返回格式化字符串。只注入成功经验，不注入失败。"""
    mem_file = ROOT / ".hermes" / "profiles" / "duanju" / "memories" / "proposal_history.jsonl"
    if not mem_file.exists():
        return ""
    try:
        lines = mem_file.read_text().strip().split("\n")
        memories = [json.loads(l) for l in lines if l.strip()]
        # 只保留成功的记录
        successes = [m for m in memories if m.get("result") == "success" and m.get("titles")]
        if not successes:
            return ""
        recent = successes[-n:]
        parts = ["## 最近成功生成记录（参考风格，避免重复）"]
        for m in recent:
            titles = m.get("titles", [])
            parts.append(f"- {m.get('drama','?')}({m.get('region','?')}): {', '.join(titles[:3])}")
        return "\n".join(parts)
    except Exception:
        return ""


def _save_duanju_memory(drama_name: str, region: str, titles: list[str], result: str = "success"):
    """保存duanju agent的记忆"""
    mem_dir = ROOT / ".hermes" / "profiles" / "duanju" / "memories"
    mem_dir.mkdir(parents=True, exist_ok=True)
    mem_file = mem_dir / "proposal_history.jsonl"
    entry = {
        "drama": drama_name,
        "region": region,
        "titles": titles,
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    }
    with open(mem_file, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _call_duanju_agent(drama_name: str, region: str, direction: str = "", plot_content: str = "") -> dict:
    """调用 duanju Agent 生成 Proposal（用户手动输入剧情）"""
    lang = REGION_TO_LANG.get(region, region)

    prompt = f"""你是短剧YouTube运营专家。先用 skill_view 加载 short-drama-youtube skill，然后根据里面的骨架公式、钩子体系、包装模式规则，为以下短剧生成上架方案。

剧名：{drama_name}
目标市场：{region}（{lang}）
{f'剧情：{plot_content}' if plot_content else ''}
{f'题材方向：{direction}' if direction else ''}

输出 JSON，格式：{{"proposals": [{{"title": "标题", "variant_type": "骨架类型", "variant": "A", "title_hashtags": [], "thumbnail_prompt": "16:9 封面描述", "tags": [], "description": "描述"}}]}}
生成 3 个标题变体（A/B/C），分别对应不同骨架和钩子组合。"""
    try:
        output = _call_hermes_api(prompt, timeout=120)
        # 提取并保存session_id（持久会话）
        sid = _extract_session_id(output)
        if sid:
            _save_session_id(sid)
        # 提取JSON（兼容 oneshot 和 chat 两种输出格式）
        json_text = None
        
        # 方式1: 从 ╭─ Hermes 框内提取
        box_match = re.search(r'╭─.*?╮\s*\n(.*?)\n\s*╰', output, re.DOTALL)
        if box_match:
            json_text = box_match.group(1).strip()
        
        # 方式2: 从 markdown code block 提取
        if not json_text:
            code_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', output)
            if code_match:
                json_text = code_match.group(1).strip()
        
        # 方式3: 直接从输出中找 JSON
        if not json_text:
            json_text = output.strip()
        
        # 清理 JSON 文本
        json_text = re.sub(r'^```(?:json)?\s*\n?', '', json_text)
        json_text = re.sub(r'\n?```\s*$', '', json_text)
        json_text = re.sub(r'^json\s*\n', '', json_text)
        
        try:
            data = json.loads(json_text)
            if "proposals" in data or "titles" in data:
                items = data.get("proposals", data.get("titles", []))
                all_titles = [p.get("title", "") for p in items if p.get("title")]
                _save_duanju_memory(drama_name, region, all_titles)
                return data
        except json.JSONDecodeError:
            pass
        
        # fallback: 贪婪匹配 proposals 或 titles
        json_match = re.search(r'\{[\s\S]*"(?:proposals|titles)"\s*:\s*\[[\s\S]*\]\s*\}', output)
        if json_match:
            data = json.loads(json_match.group())
            items = data.get("proposals", data.get("titles", []))
            all_titles = [p.get("title", "") for p in items if p.get("title")]
            _save_duanju_memory(drama_name, region, all_titles)
            return data
        _save_duanju_memory(drama_name, region, [], result="no_json")
        return {"proposals": [], "error": "no_json", "raw": output[:500]}
    except httpx.TimeoutException:
        # P2-7: _call_hermes_api 用 httpx，原 subprocess.TimeoutExpired 是死代码
        _save_duanju_memory(drama_name, region, [], result="timeout")
        return {"proposals": [], "error": "AI 生成超时，请重试"}
    except Exception as e:
        _save_duanju_memory(drama_name, region, [], result=str(e))
        return {"proposals": [], "error": str(e)}


def _agent_to_proposal(agent_data: dict, drama_name: str, region: str, plot_content: str = "") -> dict:
    """将 Agent 输出转换为面板 proposal 格式"""
    # 兼容两种key: proposals 或 titles
    proposals = agent_data.get("proposals", agent_data.get("titles", []))
    titles = []
    ai_covers = []
    all_tags = set()
    all_title_hashtags = set()
    descriptions = []

    for p in proposals:
        title = p.get("title", "")
        if title:
            titles.append({
                "title": title,
                "style": p.get("variant_type", p.get("style", p.get("emotion", ""))),
                "variant": p.get("variant", ""),
                "title_hashtags": p.get("title_hashtags", []),
                "score": {"total": 0}
            })
        # 兼容多种封面字段名
        thumbnail = p.get("thumbnail_prompt", p.get("thumbnail", p.get("cover_prompt", p.get("cover_instruction", ""))))
        if thumbnail:
            ai_covers.append({
                "style": p.get("variant_type", p.get("style", "")),
                "instruction": thumbnail
            })
        for tag in p.get("tags", []):
            all_tags.add(tag)
        for ht in p.get("title_hashtags", []):
            all_title_hashtags.add(ht.lower())
        desc = p.get("description", p.get("description_template", ""))
        if desc:
            descriptions.append(desc)

    # 提取 publish_time（agent返回顶层字段）
    publish_time = agent_data.get("publish_time", {})

    return {
        "drama_name": drama_name,
        "region": region,
        "distill_model": "agent",
        "titles": titles,
        "ai_covers": ai_covers,
        "tags": list(all_tags)[:15],
        "title_hashtags": sorted(all_title_hashtags)[:8],
        "description_tags": list(all_tags)[:15],
        "description_template": descriptions[0] if descriptions else "",
        "publish_time": publish_time,
        "provider_used": "duanju-agent",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "plot_content": plot_content,
    }


def _call_duanju_agent_titles(plot_content: str, region: str, direction: str = "", target_length: int = 70, hashtags: list[str] | None = None, distill_how: dict | None = None) -> dict:
    """调用 duanju Agent 生成标题（快速模式）"""
    lang = REGION_TO_LANG.get(region, region)

    prompt = f"""你是短剧YouTube运营专家。先用 skill_view 加载 short-drama-youtube skill，然后根据里面的骨架公式和钩子体系，为以下短剧生成 10 个标题。

语言：{lang}（所有标题必须用{lang}语言输出）
剧情：{plot_content}
{f'方向：{direction}' if direction else ''}

要求：
- 每个标题用不同的骨架+钩子组合
- 标注每个标题对应的骨架类型和钩子类型
- 标题长度控制在 {target_length} 字符左右
- 每个标题附带 2-3 个 YouTube hashtags（#开头，用于视频标题末尾）

输出 JSON：{{"titles": [{{"title": "标题", "skeleton": "骨架名", "hook": "钩子类型", "style": "情绪风格", "title_hashtags": ["#tag1", "#tag2"]}}]}}"""
    try:
        output = _call_hermes_api(prompt, timeout=120)
        # 提取并保存session_id（持久会话）
        sid = _extract_session_id(output)
        if sid:
            _save_session_id(sid)
        # 提取JSON（兼容 oneshot 和 chat 两种输出格式）
        json_text = None
        
        # 方式1: 从 ╭─ Hermes 框内提取
        box_match = re.search(r'╭─.*?╮\s*\n(.*?)\n\s*╰', output, re.DOTALL)
        if box_match:
            json_text = box_match.group(1).strip()
        
        # 方式2: 从 markdown code block 提取
        if not json_text:
            code_match = re.search(r'```(?:json)?\s*\n([\s\S]*?)\n```', output)
            if code_match:
                json_text = code_match.group(1).strip()
        
        # 方式3: 直接从输出中找 JSON
        if not json_text:
            json_text = output.strip()
        
        # 清理 JSON 文本
        json_text = re.sub(r'^```(?:json)?\s*\n?', '', json_text)
        json_text = re.sub(r'\n?```\s*$', '', json_text)
        json_text = re.sub(r'^json\s*\n', '', json_text)
        
        try:
            return json.loads(json_text)
        except json.JSONDecodeError:
            pass
        
        # fallback: 贪婪匹配 {"titles": [...]}
        json_match = re.search(r'\{"titles":\s*\[[\s\S]*\]\s*\}', output)
        if json_match:
            try:
                return json.loads(json_match.group())
            except json.JSONDecodeError:
                # 尝试修复标题值中的未转义引号
                raw = json_match.group()
                # 修复: 在JSON值内部的双引号前面加反斜杠
                fixed = re.sub(r'(?<=: ")((?:[^"\\]|\\.)*)(?=")', lambda m: m.group(0).replace('\n', '\\n'), raw)
                try:
                    return json.loads(fixed)
                except json.JSONDecodeError:
                    pass
        return {"titles": [], "error": "no_json", "raw": output[:500]}
    except httpx.TimeoutException:
        # P2-7: _call_hermes_api 用 httpx，原 subprocess.TimeoutExpired 是死代码
        return {"titles": [], "error": "AI 生成超时，请重试"}
    except Exception as e:
        return {"titles": [], "error": str(e)}


# ── 上架方案历史记录 ──────────────────────────
PROPOSAL_HISTORY_DIR = DATA_PATHS["proposal_history"]


def _save_proposal_history(drama_name: str, region: str, proposal: dict):
    """保存上架方案到历史记录"""
    PROPOSAL_HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"{drama_name}_{region}_agent_{ts}.json"
    filepath = PROPOSAL_HISTORY_DIR / filename
    filepath.write_text(json.dumps(proposal, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"📝 方案已保存到历史: {filename}")


def _load_proposal_history(limit: int = 50) -> list[dict]:
    """加载历史记录列表（按generated_at时间倒序）"""
    if not PROPOSAL_HISTORY_DIR.exists():
        return []
    files = list(PROPOSAL_HISTORY_DIR.glob("*.json"))
    history = []
    for f in files:
        try:
            data = cached_json_read(f)
            record_type = "titles" if data.get("distill_model", "").endswith("_agent") and data.get("title_count", 0) > 0 else "proposal"
            if data.get("distill_model") == "titles_agent" or (data.get("title_count", 0) > 0 and not data.get("ai_covers")):
                record_type = "titles"
            history.append({
                "filename": f.name,
                "drama_name": data.get("drama_name", ""),
                "region": data.get("region", ""),
                "distill_model": data.get("distill_model", "agent"),
                "generated_at": data.get("generated_at", ""),
                "titles_count": len(data.get("titles", [])),
                "ai_covers_count": len(data.get("ai_covers", [])),
                "type": record_type,
            })
        except Exception:
            continue
    # 按generated_at倒序排序
    history.sort(key=lambda x: x.get("generated_at", ""), reverse=True)
    return history[:limit]


def _json(handler, data, status=200, cache_max_age=0):
    """返回 JSON 响应。cache_max_age>0 时加 Cache-Control 头。"""
    try:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Content-Length", str(len(body)))
        # 优先用参数，其次用 handler 上的 _cache_max_age
        max_age = cache_max_age or getattr(handler, "_cache_max_age", 0)
        if max_age > 0:
            handler.send_header("Cache-Control", f"public, max-age={max_age}")
        else:
            handler.send_header("Cache-Control", "no-cache")
        handler.end_headers()
        handler.wfile.write(body)
    except Exception as e:
        log.error(f"_json error: {e}")


def _parse_video_datetime(value: str) -> datetime | None:
    """Parse YouTube published_at strings for filtering/sorting."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None


def _recent_videos(videos: list, limit: int = 15) -> list:
    """Return videos sorted by published_at, newest first."""
    result = []
    for v in videos or []:
        dt = _parse_video_datetime(v.get("published_at", ""))
        if dt:
            result.append(v)
    result.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    return result[:limit]


# Backward-compatible name for callers/tests that used the previous helper name.
def _recent_month_videos(videos: list, now: datetime | None = None, days: int = 14) -> list:
    return _recent_videos(videos, limit=15)


def _score_value(score: dict) -> float:
    val = score.get("score")
    if val is None:
        val = score.get("scores", {}).get("llm")
    try:
        return float(val or 0)
    except (TypeError, ValueError):
        return 0.0


def _read_diagnosis_file(path: Path) -> dict:
    if not path.exists():
        return {}
    data = cached_json_read(path)
    return data if isinstance(data, dict) else {}


def _merge_video_scores_from_diagnoses(files: list[Path]) -> list:
    """Merge video_scores by video_id. Earlier files have priority."""
    merged = {}
    for fp in files:
        diag = _read_diagnosis_file(fp)
        for score in diag.get("video_scores", []) or []:
            vid = score.get("video_id")
            if vid and vid not in merged:
                merged[vid] = score
    return list(merged.values())


def _load_diagnosis_entry(name: str, diag_dir: Path, legacy_diag_dir: Path | None = None) -> dict | None:
    """Load latest diagnosis plus historical/legacy scores so old single-video advice is not hidden."""
    slug = name.replace(" ", "_")
    latest_fp = diag_dir / f"{slug}_latest.json"
    if not latest_fp.exists():
        return None

    diag = _read_diagnosis_file(latest_fp)
    if not diag:
        return None

    files = [latest_fp]
    files.extend(sorted(diag_dir.glob(f"{slug}_20*.json"), reverse=True))
    if legacy_diag_dir:
        legacy_fp = legacy_diag_dir / f"{slug}_latest.json"
        if legacy_fp.exists():
            files.append(legacy_fp)
    video_scores = _merge_video_scores_from_diagnoses(files)

    avg_score = diag.get("summary", {}).get("avg_score", 0)
    if not avg_score and video_scores:
        avg_score = round(sum(_score_value(v) for v in video_scores) / len(video_scores), 1)
    needs_optimization = diag.get("summary", {}).get("needs_optimization")
    if needs_optimization is None:
        needs_optimization = sum(1 for v in video_scores if _score_value(v) and _score_value(v) < 6)

    return {
        "avg_score": avg_score,
        "needs_optimization": needs_optimization or 0,
        "top_issues": diag.get("summary", {}).get("top_issues", []),
        "channel_llm": diag.get("channel_llm", {}),
        "video_scores": video_scores,
        "total_videos": len(video_scores),
        "retention_data": diag.get("retention_data"),
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(f"{self.address_string()} - {format % args}")

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        try:
            p = urlparse(self.path)
            # ── HTTP 缓存策略 ──
            _CACHE_POLICY = {
                "/api/channel-analysis": 120,
                "/api/competitor-channels": 120,
                "/api/distill": 300,
                "/api/market-insights": 300,
                "/api/analytics": 120,
                "/api/weekly-comparison": 120,
                "/api/review": 30,
                "/api/proposal-history": 60,
                "/api/dashboard": 120,
                "/api/yt-accounts": 30,
            }
            self._cache_max_age = _CACHE_POLICY.get(p.path, 0)
            if p.path == "/":
                return self._serve_html()
            if p.path.startswith("/assets/"):
                return self._serve_vue_assets(p.path.lstrip("/"))
            if p.path.startswith("/static/"):
                return self._serve_static(p.path[len("/static/"):])
            if p.path == "/api/dashboard":
                return self._api_dashboard()
            if p.path == "/api/outputs":
                return self._api_outputs()
            if p.path == "/api/rules":
                return self._api_rules()
            if p.path == "/api/analytics":
                return self._api_analytics()
            if p.path == "/oauth/callback":
                return self._oauth_callback()
            if p.path == "/api/yt-accounts":
                return self._api_yt_accounts()
            if p.path == "/api/yt-auth-url":
                return self._api_yt_auth_url()
            if p.path == "/api/yt-new-auth":
                return self._api_yt_new_auth()
            if p.path.startswith("/api/yt-analytics"):
                return self._api_yt_analytics()
            if p.path.startswith("/api/yt-auth-status"):
                return self._api_yt_auth_status()
            if p.path == "/api/channel-analysis":
                return self._api_channel_analysis()
            if p.path == "/api/weekly-comparison":
                return self._api_weekly_comparison()
            if p.path == "/api/competitor-channels":
                return self._api_competitor_channels()
            if p.path.startswith("/api/competitor-detail"):
                return self._api_competitor_detail()
            if p.path == "/api/distill":
                return self._api_distill()
            if p.path.startswith("/api/distill-detail"):
                return self._api_distill_detail()
            if p.path == "/api/market-insights":
                return self._api_market_insights()
            if p.path == "/api/proposal-history":
                return self._api_proposal_history()
            if p.path.startswith("/api/proposal-detail"):
                return self._api_proposal_detail()
            if p.path == "/api/review":
                return self._api_review()
            self.send_error(404, "Not Found")
        except BrokenPipeError:
            log.warning(f"Client disconnected: {self.path}")
        except ConnectionResetError:
            log.warning(f"Connection reset: {self.path}")
        except Exception as e:
            log.error(f"do_GET error: {e}\n{traceback.format_exc()}")
            try:
                self.send_error(500, str(e))
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_POST(self):
        try:
            p = urlparse(self.path)
            if p.path == "/api/generate":
                return self._api_generate()
            if p.path == "/api/nuwa_chat":
                return self._api_nuwa_chat()
            if p.path == "/api/proposal":
                return self._api_proposal()
            if p.path == "/api/generate-titles":
                return self._api_generate_titles()
            if p.path == "/api/review/approve":
                return self._api_review_approve()
            if p.path == "/api/review/reject":
                return self._api_review_reject()
            if p.path == "/api/review/run":
                return self._api_review_run()
            self.send_error(404)
        except BrokenPipeError:
            log.warning(f"Client disconnected: {self.path}")
        except ConnectionResetError:
            log.warning(f"Connection reset: {self.path}")
        except Exception as e:
            log.error(f"do_POST error: {e}\n{traceback.format_exc()}")
            try:
                self.send_error(500, str(e))
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _serve_html(self):
        # 优先 Vue 构建产物，fallback 到旧版 HTML
        vue_dist = ROOT / "panel" / "frontend" / "dist"
        vue_index = vue_dist / "index.html"
        if vue_index.exists():
            self._serve_file(vue_index, "text/html; charset=utf-8")
        else:
            fp = ROOT / "panel" / "web" / "index_v3.html"
            self._serve_file(fp, "text/html; charset=utf-8")

    def _serve_vue_assets(self, rel_path):
        """Vue 构建产物的静态文件（JS/CSS）"""
        fp = ROOT / "panel" / "frontend" / "dist" / rel_path
        if fp.exists():
            ext = fp.suffix.lower()
            mime_map = {".js": "application/javascript", ".css": "text/css", ".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".woff2": "font/woff2", ".woff": "font/woff"}
            mime = mime_map.get(ext, "application/octet-stream")
            self._serve_file(fp, mime)
        else:
            _json(self, {"error": "not_found"}, 404)

    def _serve_static(self, rel_path):
        fp = ROOT / "panel" / "web" / rel_path
        if fp.exists():
            mime = "text/css" if fp.suffix == ".css" else "application/javascript" if fp.suffix == ".js" else "image/png"
            self._serve_file(fp, mime)
        else:
            _json(self, {"error": "not_found"}, 404)

    def _serve_file(self, path: Path, mime):
        if not path.exists():
            _json(self, {"error": "not_found"}, 404)
            return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        if mime.startswith("text/html"):
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.end_headers()
        self.wfile.write(data)

    # ── API ──────────────────────────────────────────────

    def _api_dashboard(self):
        """仪表盘数据"""
        data = {
            "channels_collected": 0,
            "videos_collected": 0,
            "rules_total": 0,
            "experts_active": 3,
            "recent_activity": [],
        }
        # 统计采集数据
        registry = DATA_PATHS["registry_deep60"]
        if registry.exists():
            try:
                reg = cached_json_read(registry)
                data["channels_collected"] = len(reg)
                data["videos_collected"] = sum(len(v.get("videos", [])) for v in reg.values())
            except Exception:
                pass

        # 统计规则
        rules_dir = DATA_PATHS["rules_dir"]
        for f in ["short-drama-youtube", "short-drama-expert_v0.md", "distribution-expert_v0.md", "hk-traditional-market-expert_v0.md"]:
            p = rules_dir / f
            if p.exists():
                text = cached_text_read(p)
                data["rules_total"] += text.count("### 规则卡")

        # 最近生成的文件
        recent = []
        for subdir in ["output/titles", "output/covers", "panel/channel_setup"]:
            d = ROOT / subdir
            if d.exists():
                for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:3]:
                    recent.append({
                        "type": subdir.split("/")[-1],
                        "name": f.name,
                        "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                    })
        data["recent_activity"] = recent[:5]
        _json(self, data)

    def _api_outputs(self):
        qs = parse_qs(urlparse(self.path).query)
        kind = qs.get("kind", ["manifests"])[0]
        limit = int(qs.get("limit", [20])[0])
        items = []
        try:
            if kind == "manifests":
                base = DATA_PATHS["manifests"]
                for f in sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                    try:
                        m = cached_json_read(f)
                        items.append({
                            "file": str(f.relative_to(ROOT)),
                            "task": m.get("task_name", ""),
                            "region": m.get("target_region", ""),
                            "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                        })
                    except Exception:
                        pass
            elif kind == "titles":
                d = ROOT / "output" / "titles"
                if d.exists():
                    for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                        items.append({"file": str(f.relative_to(ROOT)), "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
            elif kind == "covers":
                d = ROOT / "output" / "covers"
                if d.exists():
                    for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                        items.append({"file": str(f.relative_to(ROOT)), "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
            elif kind == "channels":
                d = ROOT / "panel" / "channel_setup"
                if d.exists():
                    for f in sorted(d.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                        try:
                            c = cached_json_read(f)
                            items.append({
                                "file": str(f.relative_to(ROOT)),
                                "name": c.get("config", {}).get("name", f.stem),
                                "region": c.get("region", ""),
                                "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
                            })
                        except Exception:
                            pass
        except Exception as e:
            log.error(f"outputs error: {e}")
        _json(self, {kind: items})

    def _api_rules(self):
        qs = parse_qs(urlparse(self.path).query)
        expert = qs.get("expert", [""])[0]
        rules_dir = DATA_PATHS["rules_dir"]

        if not expert:
            # 列出所有专家
            experts = []
            for f in ["short-drama-youtube", "short-drama-expert", "distribution-expert", "hk-traditional-market-expert"]:
                md = rules_dir / f"{f}_v0.md"
                count = 0
                if md.exists():
                    count = cached_text_read(md).count("### 规则卡")
                experts.append({"slug": f, "name": f.replace("-", " ").title(), "rules": count})
            _json(self, {"experts": experts})
            return

        # 返回规则详情
        md = rules_dir / f"{expert}_v0.md"
        if not md.exists():
            _json(self, {"error": "not_found"}, 404)
            return

        text = cached_text_read(md)
        rules = []
        import re
        for m in re.finditer(r"### 规则卡 (\S+):\s*(.+?)\n", text):
            rid = m.group(1)
            name = m.group(2).strip()
            # 提取后面的关键行
            start = m.end()
            end = text.find("### 规则卡", start)
            if end == -1:
                end = len(text)
            block = text[start:end]
            condition = ""
            action = ""
            for line in block.splitlines():
                if line.startswith("- **条件**"):
                    condition = line.split("：", 1)[1] if "：" in line else ""
                elif line.startswith("- **执行**"):
                    action = line.split("：", 1)[1] if "：" in line else ""
            rules.append({"id": rid, "name": name, "condition": condition, "action": action})
        _json(self, {"expert": expert, "rules": rules})

    def _api_analytics(self):
        """竞品分析数据"""
        data = {"channels": [], "stats": {}}
        registry = DATA_PATHS["registry_deep60"]
        if registry.exists():
            try:
                reg = cached_json_read(registry)
                # Handle both formats: {channels: [...]} or {cid: {...}}
                if isinstance(reg, dict) and "channels" in reg and isinstance(reg["channels"], list):
                    channel_list = reg["channels"]
                elif isinstance(reg, dict):
                    channel_list = list(reg.values())
                else:
                    channel_list = []
                total_subs = 0
                total_videos = 0
                top_channels = []
                for ch in channel_list:
                    if not isinstance(ch, dict):
                        continue
                    # subscriber_count may be string like "17.6K" or int
                    raw_subs = ch.get("registry", {}).get("subscriber_count", 0)
                    if isinstance(raw_subs, str):
                        raw_subs = raw_subs.replace(",", "").replace("+", "").strip()
                        if raw_subs.upper().endswith("K"):
                            subs = int(float(raw_subs[:-1]) * 1000)
                        elif raw_subs.upper().endswith("M"):
                            subs = int(float(raw_subs[:-1]) * 1000000)
                        else:
                            subs = int(float(raw_subs)) if raw_subs else 0
                    else:
                        subs = int(raw_subs) if raw_subs else 0
                    vids = len(ch.get("videos", [])) or ch.get("video_count", 0)
                    total_subs += subs
                    total_videos += vids
                    top_channels.append({
                        "name": ch.get("name", ch.get("title", ch.get("channel_id", ""))),
                        "subs": subs,
                        "videos": vids,
                    })
                n = len(top_channels) or 1
                top_channels.sort(key=lambda x: x["subs"], reverse=True)
                data["stats"] = {
                    "total_channels": len(top_channels),
                    "total_videos": total_videos,
                    "avg_subs": round(total_subs / n, 0),
                    "max_subs": top_channels[0]["subs"] if top_channels else 0,
                }
                data["channels"] = top_channels[:10]
            except Exception as e:
                log.error(f"analytics error: {e}")
        _json(self, data)

    def _api_generate(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            return _json(self, {"error": "invalid_json"}, 400)

        action = payload.get("action", "")
        drama_name = payload.get("drama_name", "").strip()
        region = payload.get("region", "繁中").strip()

        if not drama_name:
            return _json(self, {"error": "missing_drama_name"}, 400)

        # 创建临时 manifest
        payload_mode = payload.get("cover_prompt_mode", "balanced").strip().lower()
        payload_aspect = payload.get("aspect_ratio", "16:9").strip()
        manifest = {
            "task_name": drama_name,
            "preset": "full_rebuild",
            "skills": ["short-drama-youtube"],
            "target_channel": f"{region}_main",
            "target_region": region,
            "files": [],
            "cover_prompt_mode": payload_mode,
            "aspect_ratio": payload_aspect,
        }
        mpath = DATA_PATHS["manifests"] / f"{drama_name}_{region}.json"
        mpath.parent.mkdir(parents=True, exist_ok=True)
        mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

        result = {"action": action, "drama_name": drama_name, "region": region}

        try:
            if action == "title":
                from generate_title import run_from_manifest
                out = run_from_manifest(str(mpath))
                data = cached_json_read(out)
                result["candidates"] = data.get("candidates", [])
                result["rejected"] = data.get("rejected", [])

            elif action == "cover":
                # 先确保有标题
                from generate_title import run_from_manifest as title_run
                title_run(str(mpath))
                from generate_cover import run_from_manifest as cover_run
                out = cover_run(str(mpath))
                data = cached_json_read(out)
                result["candidates"] = data.get("candidates", [])
                result["rejected"] = data.get("rejected", [])

            elif action == "cover_optimized":
                # 新增：双版本 prompt 生成（即梦 + GPT）
                from generate_cover_structured import generate_covers
                payload_mode = payload.get("cover_prompt_mode", "balanced").strip().lower()
                payload_aspect = payload.get("aspect_ratio", "16:9").strip()
                out_path = generate_covers(
                    drama_name,
                    region,
                    version="optimized",
                    cover_prompt_mode=payload_mode,
                    aspect_ratio=payload_aspect,
                )
                data = json.loads(open(out_path).read())
                result["prompts"] = data.get("prompts", {})  # {"jimeng": "...", "gpt": "..."}
                result["file"] = str(out_path.relative_to(ROOT))

            elif action == "channel":
                from generate_channel_setup import run
                out = run(region, "甜寵", "品牌化", 0)
                data = cached_json_read(out)
                result["config"] = data.get("config", {})
                result["score"] = data.get("score", {})

            elif action == "all":
                # 运行全部
                from generate_title import run_from_manifest as title_run
                from generate_cover import run_from_manifest as cover_run
                from generate_channel_setup import run as channel_run

                title_out = title_run(str(mpath))
                cover_out = cover_run(str(mpath))
                channel_out = channel_run(region, "甜寵", "品牌化", 0)

                result["titles"] = cached_json_read(title_out).get("candidates", [])
                result["covers"] = cached_json_read(cover_out).get("candidates", [])
                result["channel"] = cached_json_read(channel_out).get("config", {})

            else:
                return _json(self, {"error": "unknown_action"}, 400)

            _json(self, {"success": True, **result})

        except Exception as e:
            log.error(f"generate error: {e}\n{traceback.format_exc()}")
            _json(self, {"success": False, "error": str(e)}, 500)

    def _api_nuwa_chat(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            return _json(self, {"error": "invalid_json"}, 400)

        prompt = payload.get("prompt", "").strip()
        if not prompt:
            return _json(self, {"error": "missing_prompt"}, 400)

        # 拼接对话历史，让新 session 也有上下文
        history = payload.get("history", [])
        if history:
            history_text = "\n".join(
                f"{'用户' if m.get('role') == 'user' else 'AI'}: {m.get('text', '')}"
                for m in history
            )
            full_prompt = f"以下是之前的对话历史（仅供参考，不要复述）：\n{history_text}\n\n当前用户问题：{prompt}"
        else:
            full_prompt = prompt

        try:
            response = _call_hermes_api(full_prompt, timeout=120)
            
            _json(self, {"success": True, "response": response})
        except (httpx.ConnectError, ConnectionRefusedError) as e:
            # P0-2: Hermes gateway (8642) 未启动时降级为 503，给出明确提示
            log.error("nuwa_chat hermes-down: %s", e)
            _json(self, {"success": False, "error": "Hermes API 服务未启动 (127.0.0.1:8642)，请启动 hermes gateway"}, 503)
        except Exception as e:
            log.error(f"nuwa_chat error: {e}")
            _json(self, {"success": False, "error": str(e)}, 500)

    def _api_proposal(self):
        """一键上架方案（输入剧情内容，带缓存）"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            return _json(self, {"error": "invalid_json"}, 400)

        plot_content = payload.get("plot_content", "").strip()
        region = payload.get("region", "繁中").strip()
        direction = payload.get("direction", "").strip()
        drama_name = payload.get("drama_name", "").strip()

        # 自动从本地查找剧情
        if not plot_content and drama_name:
            plot_content = _lookup_local_drama(drama_name)
            if plot_content:
                log.info(f"📂 从本地加载剧情: {drama_name} ({len(plot_content)}字)")

        if not plot_content:
            return _json(self, {"error": "missing_plot_content", "hint": "请输入剧情内容或剧名（本地有数据时自动加载）"}, 400)

        # 用剧名（如有）或剧情前30字作为标识
        display_name = drama_name if drama_name else plot_content[:30]

        # 检查缓存
        cache_action = "proposal_agent"
        # 用剧情前50字作为缓存key
        cache_key_text = plot_content[:50]
        cached = _get_cached(cache_key_text, region, cache_action)
        if cached:
            cached["from_cache"] = True
            return _json(self, {"success": True, **cached})

        try:
            # 调用 duanju Agent（用户输入剧情）
            agent_data = _call_duanju_agent(display_name, region, direction, plot_content=plot_content)
            if agent_data.get("error"):
                return _json(self, {"success": False, "error": f"agent_error: {agent_data['error']}", "raw": agent_data.get("raw", "")}, 500)

            proposal = _agent_to_proposal(agent_data, display_name, region, plot_content)
            _set_cached(cache_key_text, region, cache_action, proposal)
            _save_proposal_history(display_name, region, proposal)

            _json(self, {"success": True, "proposal": proposal})

        except Exception as e:
            log.error(f"proposal error: {e}\n{traceback.format_exc()}")
            _json(self, {"success": False, "error": str(e)}, 500)

    def _api_generate_titles(self):
        """一键生成20个标题（基于蒸馏数据）"""
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except Exception:
            return _json(self, {"error": "invalid_json"}, 400)

        plot_content = payload.get("plot_content", "").strip()
        region = payload.get("region", "繁中").strip()
        direction = payload.get("direction", "").strip()
        drama_name = payload.get("drama_name", "").strip()

        # 自动从本地查找剧情
        if not plot_content and drama_name:
            plot_content = _lookup_local_drama(drama_name)
            if plot_content:
                log.info(f"📂 从本地加载剧情: {drama_name} ({len(plot_content)}字)")

        if not plot_content:
            return _json(self, {"error": "missing_plot_content", "hint": "请输入剧情内容或剧名（本地有数据时自动加载）"}, 400)

        # 加载蒸馏数据
        distill = _load_distill_for_region(region)
        hashtags = _extract_title_hashtags(distill) if distill else []
        target_length = _calc_title_target_length(distill, num_hashtags=2) if distill else 70

        log.info(f"🎯 生成标题: region={region}, target_len={target_length}, hashtags={len(hashtags)}")

        # 检查缓存
        cache_action = "titles_agent"
        cache_key_text = plot_content[:50]
        cached = _get_cached(cache_key_text, region, cache_action)
        if cached:
            cached["from_cache"] = True
            return _json(self, {"success": True, **cached})

        try:
            result = _call_duanju_agent_titles(
                plot_content, region, direction,
                target_length=target_length,
                hashtags=hashtags,
                distill_how=distill.get('how', {}) if distill else None
            )
            if result.get("error"):
                return _json(self, {"success": False, "error": result["error"], "raw": result.get("raw", "")}, 500)

            titles = result.get("titles", [])
            result_data = {
                "titles": titles,
                "distill_info": {
                    "avg_title_length": distill.get("stats", {}).get("avg_title_length", 0),
                    "target_length": target_length,
                    "available_hashtags": hashtags[:20],
                }
            }
            _set_cached(cache_key_text, region, cache_action, result_data)
            
            # 保存到历史记录
            display_name = drama_name if drama_name else "unknown"
            history_data = {
                "drama_name": display_name,
                "region": region,
                "distill_model": "titles_agent",
                "titles": titles,
                "title_count": len(titles),
                "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                "direction": direction,
                "target_length": target_length,
            }
            _save_proposal_history(display_name, region, history_data)
            
            _json(self, {"success": True, **result_data})
        except Exception as e:
            log.error(f"generate-titles error: {e}\n{traceback.format_exc()}")
            _json(self, {"success": False, "error": str(e)}, 500)

    def _api_proposal_history(self):
        """获取上架方案历史记录列表"""
        history = _load_proposal_history()
        _json(self, {"success": True, "history": history})

    def _api_proposal_detail(self):
        """获取单条历史记录详情"""
        from urllib.parse import parse_qs, urlparse
        p = urlparse(self.path)
        params = parse_qs(p.query)
        filename = params.get("file", [""])[0]
        if not filename:
            return _json(self, {"error": "missing_file_param"}, 400)
        # P0-1: 路径穿越防护 —— 拒绝绝对路径、分隔符、..
        if "/" in filename or "\\" in filename or ".." in filename or filename.startswith("/"):
            log.warning("proposal-detail rejected path: %r", filename)
            return _json(self, {"error": "invalid_file"}, 400)
        # 双重校验：resolve 后必须在 PROPOSAL_HISTORY_DIR 内
        try:
            base = PROPOSAL_HISTORY_DIR.resolve()
            filepath = (PROPOSAL_HISTORY_DIR / filename).resolve()
        except (OSError, ValueError):
            return _json(self, {"error": "invalid_file"}, 400)
        if filepath != base and base not in filepath.parents:
            log.warning("proposal-detail escaped dir: %r", filename)
            return _json(self, {"error": "invalid_file"}, 400)
        if not filepath.exists():
            return _json(self, {"error": "not_found"}, 404)
        try:
            data = cached_json_read(filepath)
            _json(self, {"success": True, "detail": data})
        except Exception as e:
            _json(self, {"error": str(e)}, 500)

    # ── YouTube OAuth + Analytics ──────────────────────────

    # PKCE verifier 暂存（内存）
    _pkce_verifiers: dict = {}  # slug -> verifier
    OAUTH_REDIRECT_URI="https://duanju.opspilot.me/oauth/callback"
    OAUTH_SCOPES = [
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/yt-analytics.readonly",
    ]

    def _oauth_callback(self):
        """Google OAuth 回调：接收 code → 换 token → 存 Keychain"""
        import hashlib, base64, secrets, urllib.parse as up2, urllib.request as ur2
        p = urlparse(self.path)
        params = parse_qs(p.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            return self._redirect_html(f"❌ 授权失败: {error}")

        if not code:
            return self._redirect_html("❌ 缺少授权码")

        # 从 cookie 或 state 取 slug
        slug = params.get("state", ["default"])[0]

        # 取暂存的 verifier
        verifier = self._pkce_verifiers.pop(slug, None)
        if not verifier:
            return self._redirect_html("❌ PKCE verifier 过期，请重新发起授权")

        # 换 token
        client = kc.load_google_client()
        if not client:
            return self._redirect_html("❌ 未配置 Google client")

        data = up2.urlencode({
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.OAUTH_REDIRECT_URI,
            "code_verifier": verifier,
        }).encode()

        req = ur2.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with ur2.urlopen(req, timeout=30) as resp:
                token = json.loads(resp.read().decode())
        except Exception as e:
            return self._redirect_html(f"❌ Token 交换失败: {e}")

        import time
        token["expires_at"] = time.time() + token.get("expires_in", 3600)
        token["authorized_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        kc.save_youtube_token(slug, token)

        # 获取频道信息
        channel_title = ""
        channel_id = ""
        channel_info_ok = False
        try:
            r = ur2.Request("https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true")
            r.add_header("Authorization", f"Bearer {token['access_token']}")
            with ur2.urlopen(r, timeout=15) as resp:
                ch_data = json.loads(resp.read().decode())
            ch = ch_data["items"][0]
            channel_id = ch["id"]
            channel_title = ch["snippet"]["title"]
            channel_info_ok = True
        except Exception as ch_err:
            log.warning(f"⚠️ 授权成功但获取频道信息失败({slug}): {ch_err}")

        # 更新 accounts.json — 自动处理 slug 冲突
        accounts_file = DATA_PATHS["accounts_json"]
        accounts = {}
        if accounts_file.exists():
            accounts = cached_json_read(accounts_file)

        # 智能 slug 分配：避免覆盖已有频道
        if channel_id:
            # 1) 此 channel_id 已注册在别的 slug 下 → 复用那个 slug
            existing_slug = None
            for s, acct in accounts.items():
                if acct.get("channel_id") == channel_id and s != slug:
                    existing_slug = s
                    break
            if existing_slug:
                slug = existing_slug
            # 2) 当前 slug 已被别的频道占用 → 自动生成新 slug
            elif accounts.get(slug, {}).get("channel_id") and accounts[slug]["channel_id"] != channel_id:
                import re
                base = re.sub(r'[^a-z0-9]+', '_', channel_title.lower()).strip('_')[:20]
                if not base:
                    base = "ch"
                new_slug = base
                counter = 1
                while new_slug in accounts:
                    counter += 1
                    new_slug = f"{base}_{counter}"
                slug = new_slug

        accounts[slug] = {
            "google_email": accounts.get(slug, {}).get("google_email", ""),
            "channel_id": channel_id,
            "channel_title": channel_title,
            "market": accounts.get(slug, {}).get("market", ""),
            "authorized_at": token["authorized_at"],
        }
        accounts_file.parent.mkdir(parents=True, exist_ok=True)
        accounts_file.write_text(json.dumps(accounts, ensure_ascii=False, indent=2))

        if channel_info_ok:
            try:
                invalidate_file_cache(DATA_PATHS.get("yt_accounts_cache"))
                subprocess.run([
                    sys.executable,
                    str(ROOT / "scripts" / "refresh_yt_accounts_cache.py"),
                ], cwd=str(ROOT), timeout=60, check=False)
            except Exception as cache_err:
                log.warning(f"⚠️ 授权成功但刷新账号缓存失败({slug}): {cache_err}")
            self._redirect_html(f"✅ {channel_title} ({slug}) 授权成功！可关闭此页。")
        else:
            self._redirect_html(f"⚠️ 授权成功，但未获取到频道信息。请确保在 Google 授权页面勾选了 YouTube 权限，然后回到面板点击「🔑 重新授权」。")

    def _redirect_html(self, msg):
        """返回一个简单 HTML 提示页"""
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
        <title>OAuth</title><style>
        body{{background:#0c0e12;color:#e8eaf0;font-family:system-ui;display:flex;align-items:center;justify-content:center;height:100vh;margin:0}}
        .box{{text-align:center;font-size:1.4em}}</style></head>
        <body><div class="box">{msg}</div></body></html>"""
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _api_yt_accounts(self):
        """列出所有 YouTube 账号（优先读后台生成的本地缓存）。"""
        cache_file = DATA_PATHS.get("yt_accounts_cache")
        if cache_file and cache_file.exists():
            try:
                data = cached_json_read(cache_file)
                accounts = data.get("accounts", []) if isinstance(data, dict) else []
                return _json(self, {"accounts": accounts, "cached": True, "updated_at": data.get("updated_at", "") if isinstance(data, dict) else ""})
            except Exception as e:
                log.warning(f"yt accounts cache read failed, fallback to live build: {e}")

        import time as _time

        # 1. 读注册表
        registry_path = DATA_PATHS["our_channels"]
        registry = {}
        if registry_path.exists():
            try:
                reg = cached_json_read(registry_path)
                for ch in reg.get("channels", []):
                    registry[ch["channel_id"]] = ch
            except Exception:
                pass

        # 2. 读 accounts.json (OAuth)
        accounts_file = DATA_PATHS["accounts_json"]
        accounts = {}
        if accounts_file.exists():
            accounts = cached_json_read(accounts_file)

        # 3. 合并：注册表为主，补充OAuth状态
        result = []
        seen_ids = set()

        # 先处理注册表里的频道
        for ch_id, ch_info in registry.items():
            # 查accounts.json里有没有对应的token
            oauth_slug = None
            for slug, acc_info in accounts.items():
                if acc_info.get("channel_id") == ch_id:
                    oauth_slug = slug
                    break

            status = "未授权"
            google_email = ""
            if oauth_slug:
                token = kc.load_youtube_token(oauth_slug)
                if token:
                    # 检查过期，尝试自动刷新
                    if token.get("expires_at", 0) < _time.time():
                        refreshed = self._refresh_token(oauth_slug, token)
                        if refreshed:
                            token = refreshed
                            status = "已授权"
                        else:
                            status = "token过期"
                    else:
                        status = "已授权"
                google_email = accounts[oauth_slug].get("google_email", "")

            result.append({
                "slug": oauth_slug or ch_info.get("slug", ch_info.get("market", "")),
                "channel_title": ch_info.get("name", ""),
                "channel_id": ch_id,
                "google_email": google_email,
                "market": ch_info.get("market", ""),
                "language": ch_info.get("language_cn", ch_info.get("language", "")),
                "operator": ch_info.get("operator", ""),
                "operator_type": ch_info.get("operator_type", ""),
                "niche": ch_info.get("niche", ""),
                "status": status,
                "source": "registry",
            })
            seen_ids.add(ch_id)

        # 再处理accounts.json里注册表没有的（旧数据/测试）
        for slug, info in accounts.items():
            cid = info.get("channel_id", "")
            if cid in seen_ids:
                continue
            token = kc.load_youtube_token(slug)
            status = "未授权"
            if token:
                # 检查过期，尝试自动刷新
                if token.get("expires_at", 0) < _time.time():
                    refreshed = self._refresh_token(slug, token)
                    if refreshed:
                        token = refreshed
                        status = "已授权"
                    else:
                        status = "token过期"
                else:
                    status = "已授权"
            result.append({
                "slug": slug,
                "channel_title": info.get("channel_title", ""),
                "channel_id": cid,
                "google_email": info.get("google_email", ""),
                "market": info.get("market", ""),
                "status": status,
                "source": "legacy",
            })

        # 批量获取频道头像（用 API Key）
        all_ids = [r["channel_id"] for r in result if r.get("channel_id")]
        thumb_map = {}
        if all_ids:
            try:
                import urllib.request as ur2
                from core.config import get_own_channel_api_key
                ak = get_own_channel_api_key()
                for i in range(0, len(all_ids), 50):
                    batch = all_ids[i:i+50]
                    req = ur2.Request(f"https://www.googleapis.com/youtube/v3/channels?part=snippet&id={','.join(batch)}&key={ak}")
                    with ur2.urlopen(req, timeout=10) as resp:
                        ch_data = json.loads(resp.read().decode())
                    for ch in ch_data.get("items", []):
                        thumb_map[ch["id"]] = ch["snippet"].get("thumbnails", {}).get("default", {}).get("url", "")
            except Exception:
                pass

        for r in result:
            r["thumbnail"] = thumb_map.get(r.get("channel_id", ""), "")

        _json(self, {"accounts": result})

    def _api_yt_auth_url(self):
        """生成 YouTube OAuth 授权链接"""
        import hashlib, base64, secrets, urllib.parse as up2
        p = urlparse(self.path)
        params = parse_qs(p.query)
        slug = params.get("slug", ["default"])[0]

        client = kc.load_google_client()
        if not client:
            return _json(self, {"error": "未配置 Google client"}, 400)

        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()

        # 暂存 verifier
        self._pkce_verifiers[slug] = verifier

        auth_params = {
            "client_id": client["client_id"],
            "redirect_uri": self.OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(self.OAUTH_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": slug,
        }
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{up2.urlencode(auth_params)}"
        _json(self, {"url": url, "slug": slug})

    def _api_yt_new_auth(self):
        """一键新增授权：自动生成 slug，返回 OAuth URL，回调自动注册"""
        import hashlib, base64, secrets, urllib.parse as up2, uuid
        p = urlparse(self.path)
        params = parse_qs(p.query)
        # 可选传 slug，不传就自动生成
        slug = params.get("slug", [f"ch_{uuid.uuid4().hex[:6]}"])[0]

        client = kc.load_google_client()
        if not client:
            return _json(self, {"error": "未配置 Google client"}, 400)

        verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).rstrip(b"=").decode()

        self._pkce_verifiers[slug] = verifier

        auth_params = {
            "client_id": client["client_id"],
            "redirect_uri": self.OAUTH_REDIRECT_URI,
            "response_type": "code",
            "scope": " ".join(self.OAUTH_SCOPES),
            "access_type": "offline",
            "prompt": "consent",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": slug,
        }
        url = f"https://accounts.google.com/o/oauth2/v2/auth?{up2.urlencode(auth_params)}"
        _json(self, {"url": url, "slug": slug})

    def _api_yt_auth_status(self):
        """检查某个 slug 的授权状态"""
        import time as _time
        p = urlparse(self.path)
        params = parse_qs(p.query)
        slug = params.get("slug", ["default"])[0]
        token = kc.load_youtube_token(slug)
        if not token:
            return _json(self, {"slug": slug, "status": "not_authorized"})
        expired = token.get("expires_at", 0) < _time.time()
        has_refresh = "refresh_token" in token
        _json(self, {
            "slug": slug,
            "status": "expired" if expired else "authorized",
            "has_refresh": has_refresh,
            "token_len": len(token.get("access_token", "")),
        })

    def _api_channel_analysis(self):
        """频道分析数据（含诊断详情）"""
        fp = DATA_PATHS["channel_analysis"]
        if not fp.exists():
            return _json(self, {"error": "no data", "channels": []})
        try:
            data = cached_json_read(fp)
            if not isinstance(data, dict):
                data = {}
            else:
                data = dict(data)
                data["channel_details"] = dict(data.get("channel_details", {}))
                for name, details in data["channel_details"].items():
                    if isinstance(details, dict):
                        details = dict(details)
                        details["recent_videos"] = _recent_videos(details.get("recent_videos", []), limit=15)
                        data["channel_details"][name] = details
            # 加载每个频道的诊断数据
            diag_dir = DATA_PATHS["channel_diagnosis"]
            legacy_diag_dir = ROOT / "data" / "panel" / "channel_diagnosis"
            diagnostics = {}
            if diag_dir.exists():
                for ch in data.get("channels", []):
                    name = ch.get("name", "")
                    if not name:
                        continue
                    entry = _load_diagnosis_entry(name, diag_dir, legacy_diag_dir)
                    if entry:
                        diagnostics[name] = entry
                        details = data.get("channel_details", {}).get(name, {})
                        if isinstance(details, dict):
                            recent_ids = {v.get("video_id") for v in details.get("recent_videos", []) if v.get("video_id")}
                            entry["recent_video_scores"] = [v for v in entry.get("video_scores", []) if v.get("video_id") in recent_ids]
            data["diagnostics"] = diagnostics

            # 合并 OAuth Analytics 数据（已授权的频道）
            accounts_file = DATA_PATHS["accounts_json"]
            if accounts_file.exists():
                try:
                    accounts = cached_json_read(accounts_file)
                    # 建立 channel_id → slug 映射
                    id_to_slug = {}
                    for slug, acct in accounts.items():
                        cid = acct.get("channel_id", "")
                        if cid:
                            id_to_slug[cid] = slug
                    # 从 registry 构建 name → channel_id 映射
                    registry_path = DATA_PATHS.get("our_channels")
                    name_to_id = {}
                    if registry_path and registry_path.exists():
                        try:
                            reg = cached_json_read(registry_path)
                            for rch in reg.get("channels", []):
                                name_to_id[rch.get("name", "")] = rch.get("channel_id", "")
                        except Exception:
                            pass
                    # 给每个频道附加 OAuth 数据（读缓存，不实时拉API）
                    for ch in data.get("channels", []):
                        ch_id = ch.get("channel_id", "") or name_to_id.get(ch.get("name", ""), "")
                        oauth_slug = id_to_slug.get(ch_id, "")
                        if not oauth_slug:
                            ch["oauth"] = {"authorized": False}
                            continue
                        acct = accounts.get(oauth_slug, {})
                        if not acct:
                            ch["oauth"] = {"authorized": False}
                            continue
                        # 读缓存的 analytics 数据
                        cache_file = ROOT / "data" / "yt_analytics" / f"{oauth_slug}.json"
                        if cache_file.exists():
                            try:
                                cached = json.loads(cache_file.read_text())
                                summary = cached.get("summary", {})
                                rows = summary.get("rows", [[]])[0] if summary.get("rows") else []
                                headers = summary.get("headers", [])
                                def _val(metric):
                                    idx = headers.index(metric) if metric in headers else -1
                                    return rows[idx] if idx >= 0 and idx < len(rows) else 0
                                ch["oauth"] = {
                                    "authorized": True,
                                    "slug": oauth_slug,
                                    "views_30d": _val("views"),
                                    "avg_view_pct": round(_val("averageViewPercentage"), 1) if _val("averageViewPercentage") else 0,
                                    "watch_minutes_30d": _val("estimatedMinutesWatched"),
                                    "subs_gained_30d": _val("subscribersGained"),
                                    "subs_lost_30d": _val("subscribersLost"),
                                    "avg_view_duration": round(_val("averageViewDuration"), 0) if _val("averageViewDuration") else 0,
                                    "collected_at": cached.get("collected_at", ""),
                                }
                            except Exception as e:
                                ch["oauth"] = {"authorized": True, "slug": oauth_slug, "error": str(e)[:100]}
                        else:
                            ch["oauth"] = {"authorized": True, "slug": oauth_slug, "no_data": True}
                except Exception:
                    pass

            _json(self, data)
        except Exception as e:
            _json(self, {"error": str(e), "channels": []})

    def _api_weekly_comparison(self):
        """周对比数据：本周vs上周快照"""
        from datetime import datetime, timedelta
        import glob as _glob
        
        snapshot_dir = DATA_PATHS["channel_snapshots"]
        if not snapshot_dir.exists():
            return _json(self, {"error": "no snapshots", "channels": []})
        
        today = datetime.now()
        # 找本周一和上周一的日期
        days_since_monday = today.weekday()
        this_monday = (today - timedelta(days=days_since_monday)).strftime("%Y%m%d")
        last_monday = (today - timedelta(days=days_since_monday + 7)).strftime("%Y%m%d")
        
        # 如果今天就是周一，用今天和7天前
        if days_since_monday == 0:
            this_monday = today.strftime("%Y%m%d")
            last_monday = (today - timedelta(days=7)).strftime("%Y%m%d")
        
        result = {
            "this_week": this_monday,
            "last_week": last_monday,
            "channels": [],
            "updated_at": today.isoformat(),
        }
        
        # 找每个频道的本周和上周快照
        all_files = sorted(_glob.glob(str(snapshot_dir / "*_*.json")))
        channel_files = {}
        for f in all_files:
            fname = Path(f).name
            if "_latest" in fname:
                continue
            parts = fname.rsplit("_", 1)
            if len(parts) != 2:
                continue
            ch_name = parts[0]
            date_str = parts[1].replace(".json", "")
            channel_files.setdefault(ch_name, {})[date_str] = f
        
        for ch_name, dates in channel_files.items():
            # 找最接近this_monday和last_monday的快照
            this_file = None
            last_file = None
            
            # 本周：找this_monday之后最近的
            for d in sorted(dates.keys()):
                if d >= this_monday:
                    this_file = dates[d]
                    break
            # 如果没找到本周的，用最新的
            if not this_file and dates:
                latest_d = sorted(dates.keys())[-1]
                this_file = dates[latest_d]
            
            # 上周：找last_monday之前最近的
            for d in sorted(dates.keys(), reverse=True):
                if d <= last_monday:
                    last_file = dates[d]
                    break
            # 如果没找到上周的，用最早的
            if not last_file and dates:
                earliest_d = sorted(dates.keys())[0]
                last_file = dates[earliest_d]
            
            if not this_file or not last_file:
                continue
            
            try:
                this_data = cached_json_read(Path(this_file))
                last_data = cached_json_read(Path(last_file))
            except:
                continue
            
            this_stats = this_data.get("channel_stats", {})
            last_stats = last_data.get("channel_stats", {})
            
            this_subs = this_stats.get("subscribers", 0)
            last_subs = last_stats.get("subscribers", 0)
            this_views = this_stats.get("total_views", 0)
            last_views = last_stats.get("total_views", 0)
            this_videos = this_stats.get("video_count", this_stats.get("total_videos", 0))
            last_videos = last_stats.get("video_count", last_stats.get("total_videos", 0))
            
            # 本周视频平均播放
            this_vids = this_data.get("videos", [])
            this_avg_views = sum(v.get("views", 0) for v in this_vids) / max(len(this_vids), 1) if this_vids else 0
            
            result["channels"].append({
                "name": ch_name,
                "this_subs": this_subs,
                "last_subs": last_subs,
                "subs_change": this_subs - last_subs,
                "this_views": this_views,
                "last_views": last_views,
                "views_change": this_views - last_views,
                "this_videos": this_videos,
                "last_videos": last_videos,
                "videos_change": this_videos - last_videos,
                "avg_views": round(this_avg_views),
            })
        
        # 按订阅增长排序
        result["channels"].sort(key=lambda x: x["subs_change"], reverse=True)
        _json(self, result)

    def _api_competitor_channels(self):
        """竞品频道列表（精简字段，去掉详情级大字段以减少响应体积）"""
        fp_dynamic = DATA_PATHS["competitor_dynamic"]
        fp_static = DATA_PATHS["competitor_static"]
        fp = fp_dynamic if fp_dynamic.exists() else fp_static
        if not fp.exists():
            return _json(self, {"error": "data not found", "channels": [], "total": 0})
        try:
            data = cached_json_read(fp)
            # 精简：列表只保留表格需要的字段，去掉 deep_analysis/video_analysis/analysis_text/videos_detail 等大字段
            LIGHT_KEYS = {"channel_id", "name", "language", "subscribers", "tier", "url",
                          "total_videos", "content_tags", "avg_views", "country",
                          "thumbnail_url", "analyzed_at", "growth_reasons", "top_covers", "tracking"}
            light_channels = []
            for ch in data.get("channels", []):
                light = {k: ch[k] for k in LIGHT_KEYS if k in ch}
                light_channels.append(light)
            data["channels"] = light_channels
            _json(self, data)
        except Exception as e:
            log.error(f"competitor channels error: {e}")
            _json(self, {"error": str(e), "channels": [], "total": 0})

    def _api_competitor_detail(self):
        """单个频道详情（优先读动态数据，fallback静态50频道）"""
        from urllib.parse import urlparse, parse_qs
        p = urlparse(self.path)
        params = parse_qs(p.query)
        channel_id = params.get("id", [""])[0]
        if not channel_id:
            return _json(self, {"error": "missing id"}, 400)
        # 优先：动态数据
        fp_dynamic = DATA_PATHS["competitor_dynamic"]
        fp_static = DATA_PATHS["competitor_static"]
        fp = fp_dynamic if fp_dynamic.exists() else fp_static
        try:
            data = cached_json_read(fp)
            # 用内存索引替代 O(n) 线性扫描
            idx_key = f"__competitor_index:{fp}"
            idx = _COMPETITOR_INDEX.get(idx_key)
            channels_list = data.get("channels", [])
            if idx is None or idx.get("__len") != len(channels_list):
                idx = {ch.get("channel_id"): ch for ch in channels_list if ch.get("channel_id")}
                idx["__len"] = len(channels_list)
                _COMPETITOR_INDEX[idx_key] = idx
            ch = idx.get(channel_id)
            if ch:
                return _json(self, ch)
            _json(self, {"error": "channel not found"}, 404)
        except Exception as e:
            _json(self, {"error": str(e)}, 500)

    def _api_distill(self):
        """蒸馏数据概览"""
        distill_dir = ROOT / "distill"
        result = {"regions": []}

        # 三层蒸馏输出
        outputs_dir = distill_dir / "outputs"
        if outputs_dir.exists():
            seen_langs = set()
            for f in sorted(outputs_dir.glob("distilled-rules-*.json")):
                raw_lang = f.stem.replace("distilled-rules-", "")
                # 跳过 -prev 和 -gpt55 后缀文件
                if raw_lang.endswith("-prev") or "-gpt55" in raw_lang:
                    continue
                lang = raw_lang
                if lang in seen_langs:
                    continue
                seen_langs.add(lang)
                try:
                    data = cached_json_read(f)
                except:
                    continue
                # 检查是否有上一版本
                prev_file = outputs_dir / f"distilled-rules-{lang}-prev.json"
                has_prev = prev_file.exists()
                # 从JSON提取sections
                how = data.get("how", {})
                sections = list(how.keys()) if how else []
                result["regions"].append({
                    "lang": lang,
                    "file": f.name,
                    "size": f.stat().st_size,
                    "sections": sections,
                    "has_prev": has_prev,
                })

        # 证据数据统计
        evidence_dir = distill_dir / "evidence"
        if evidence_dir.exists():
            for region in result["regions"]:
                lang = region["lang"]
                lang_dir = evidence_dir / lang
                if lang_dir.exists():
                    files = [f.name for f in lang_dir.glob("*.json")]
                    region["evidence_files"] = files
                    # 加载summary
                    summary_file = lang_dir / "summary.json"
                    if summary_file.exists():
                        region["summary"] = cached_json_read(summary_file)

        _json(self, result)

    def _api_distill_detail(self):
        """单个地区的蒸馏详情 — 多版本对比"""
        from urllib.parse import urlparse, parse_qs
        p = urlparse(self.path)
        params = parse_qs(p.query)
        lang = params.get("lang", [""])[0]
        if not lang:
            return _json(self, {"error": "missing lang"}, 400)

        distill_dir = ROOT / "distill"
        result = {"lang": lang}

        # MiMo 蒸馏（最新）
        mimo_json = distill_dir / "outputs" / f"distilled-rules-{lang}.json"
        if mimo_json.exists():
            try:
                mimo_data = cached_json_read(mimo_json)
                result["mimo_content"] = mimo_data
                result["mimo_version"] = mimo_data.get("meta", {}).get("version", "unknown")
                result["mimo_generated"] = mimo_data.get("meta", {}).get("generated_at", "")
            except:
                pass

        # GPT 蒸馏（最新）
        import glob as _glob
        gpt_files = sorted(_glob.glob(str(distill_dir / "outputs" / f"distilled-rules-{lang}-gpt55*.json")))
        if gpt_files:
            try:
                gpt_data = cached_json_read(Path(gpt_files[-1]))  # 取最新
                result["gpt_content"] = gpt_data
                result["gpt_version"] = gpt_data.get("meta", {}).get("version", "unknown")
                result["gpt_generated"] = gpt_data.get("meta", {}).get("generated_at", "")
            except:
                pass

        # 上一版本（对比用）
        prev_json = distill_dir / "outputs" / f"distilled-rules-{lang}-prev.json"
        if prev_json.exists():
            try:
                prev_data = cached_json_read(prev_json)
                result["prev_content"] = prev_data
                result["prev_version"] = prev_data.get("meta", {}).get("version", "unknown")
                result["prev_generated"] = prev_data.get("meta", {}).get("generated_at", "")
            except:
                pass

        # 证据数据
        lang_dir = distill_dir / "evidence" / lang
        if lang_dir.exists():
            for f in lang_dir.glob("*.json"):
                try:
                    result[f.stem] = cached_json_read(f)
                except:
                    pass

        _json(self, result)

    def _api_market_insights(self):
        """市场洞察数据（列表+单语种详情）"""
        from urllib.parse import urlparse, parse_qs
        p = urlparse(self.path)
        params = parse_qs(p.query)
        lang = params.get("lang", [""])[0]

        insights_dir = DATA_PATHS["market_insights"]
        files = sorted(insights_dir.glob("market_insights_*.json"))

        if not lang:
            # 返回可用语种列表（带channel_count）
            languages = []
            for f in files:
                lang_name = f.stem.replace("market_insights_", "")
                # 读取meta获取channel_count
                ch_count = 0
                try:
                    raw = cached_json_read(f)
                    ch_count = raw.get("meta", {}).get("channel_count", 0)
                except:
                    pass
                languages.append({"language": lang_name, "channel_count": ch_count})
            return _json(self, {"languages": languages})

        # 返回指定语种详情
        fp = insights_dir / f"market_insights_{lang}.json"
        if not fp.exists():
            return _json(self, {"error": f"no data for {lang}"}, 404)
        try:
            raw = cached_json_read(fp)
            # 转换为前端期望的格式
            meta = raw.get("meta", {})
            data = {
                "channel_count": meta.get("channel_count", 0),
                "model": meta.get("model", ""),
                "generated_at": meta.get("generated_at", ""),
                "language": meta.get("language", lang),
                "insights": raw.get("llm_insights", {}),
                "python_stats": raw.get("python_stats", {}),
            }
            _json(self, data)
        except Exception as e:
            _json(self, {"error": str(e)}, 500)

    def _api_yt_analytics(self):
        """读取 YouTube Analytics 缓存数据（由 collect_yt_analytics.py 每日采集）"""
        p = urlparse(self.path)
        params = parse_qs(p.query)
        slug = params.get("slug", ["default"])[0]

        cache_file = ROOT / "data" / "yt_analytics" / f"{slug}.json"
        if not cache_file.exists():
            return _json(self, {"error": f"频道 {slug} 暂无 Analytics 数据。请先运行: python3 scripts/collect_yt_analytics.py --slug {slug}"}, 404)

        try:
            data = json.loads(cache_file.read_text())
            _json(self, data)
        except Exception as e:
            log.error(f"[yt-analytics] cache read error: {e}")
            _json(self, {"error": str(e)}, 500)

    def _refresh_token(self, slug, token_data):
        """刷新 OAuth token"""
        import urllib.parse as up2, urllib.request as ur2, time as _time
        client = kc.load_google_client()
        if not client:
            return None
        refresh_token = token_data.get("refresh_token")
        if not refresh_token:
            return None
        data = up2.urlencode({
            "client_id": client["client_id"],
            "client_secret": client["client_secret"],
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode()
        req = ur2.Request("https://oauth2.googleapis.com/token", data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with ur2.urlopen(req, timeout=30) as resp:
                new_token = json.loads(resp.read().decode())
            if "refresh_token" not in new_token:
                new_token["refresh_token"] = refresh_token
            new_token["expires_at"] = _time.time() + new_token.get("expires_in", 3600)
            new_token["refreshed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            kc.save_youtube_token(slug, new_token)
            return new_token
        except:
            return None

    def _api_review(self):
        """获取待审核区数据 — 支持 ?lang= 按语种 + ?offset=&limit= 分页"""
        review_file = ROOT / "data" / "competitor_data" / "staging_review.json"
        if not review_file.exists():
            return _json(self, {"channels": [], "total": 0, "stats": {}})
        try:
            data = cached_json_read(review_file)
            # 统计各语种数量（轻量，不含频道详情）
            lang_stats = {}
            for ch in data:
                lang = ch.get("language", "unknown")
                lang_stats[lang] = lang_stats.get(lang, 0) + 1
            # ?lang= 参数过滤
            q = urlparse(self.path).query
            params = parse_qs(q)
            req_lang = params.get("lang", [None])[0]
            if req_lang:
                data = [ch for ch in data if ch.get("language") == req_lang]
            total = len(data)
            # ?offset=&limit= 分页（默认返回全部，保持向后兼容）
            offset = int(params.get("offset", [0])[0])
            limit = int(params.get("limit", [0])[0])
            if limit > 0:
                data = data[offset:offset + limit]
            # 构造轻量响应
            channels = []
            for ch in data:
                channels.append({
                    "channel_id": ch.get("channel_id"),
                    "name": ch.get("name"),
                    "language": ch.get("language", "unknown"),
                    "subscribers": ch.get("subscribers", 0),
                    "video_count": ch.get("video_count", 0),
                    "avg_views": ch.get("avg_views", 0),
                    "videos": ch.get("videos", [])[:3],
                    "country": ch.get("country", ""),
                    "status": ch.get("_review_status", "pending"),
                    "score": ch.get("_review_score"),
                    "signals": ch.get("_review_signals"),
                    "reasons": ch.get("_review_reasons", []),
                })
            _json(self, {"channels": channels, "stats": lang_stats, "total": total, "offset": offset, "limit": limit or total, "total_all": sum(lang_stats.values())})
        except Exception as e:
            log.error(f"review error: {e}")
            _json(self, {"error": str(e), "channels": [], "total": 0})

    def _api_review_approve(self):
        """确认收录频道到 latest.json"""
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            channel_ids = body.get("channel_ids", [])
            if not channel_ids:
                return _json(self, {"error": "missing channel_ids"}, 400)
            
            # 调用 screen.py 的 approve_review 函数
            sys.path.insert(0, str(ROOT / "scripts"))
            from competitor.screen import approve_review
            count = approve_review(channel_ids)
            # 清除相关文件缓存（staging_review.json 和 latest.json 被修改）
            invalidate_file_cache(DATA_PATHS["competitor_dynamic"])
            invalidate_file_cache(DATA_PATHS.get("competitor_static"))
            _json(self, {"approved": count, "message": f"已收录 {count} 个频道"})
        except Exception as e:
            log.error(f"review approve error: {e}")
            _json(self, {"error": str(e)}, 500)

    def _api_review_reject(self):
        """拒绝频道（从待审核区删除）"""
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
            channel_ids = body.get("channel_ids", [])
            if not channel_ids:
                return _json(self, {"error": "missing channel_ids"}, 400)
            
            # 调用 screen.py 的 reject_review 函数
            sys.path.insert(0, str(ROOT / "scripts"))
            from competitor.screen import reject_review
            count = reject_review(channel_ids)
            # 清除待审核缓存
            staging_review = ROOT / "data" / "competitor_data" / "staging_review.json"
            invalidate_file_cache(staging_review)
            _json(self, {"rejected": count, "message": f"已拒绝 {count} 个频道"})
        except Exception as e:
            log.error(f"review reject error: {e}")
            _json(self, {"error": str(e)}, 500)

    def _api_review_run(self):
        """运行筛选脚本，结果写入待审核区"""
        try:
            # 调用 screen.py 的筛选逻辑
            sys.path.insert(0, str(ROOT / "scripts"))
            from competitor.screen import screen_staging, write_to_review
            
            passed, review, rejected = screen_staging()
            result = write_to_review(passed, review)
            
            _json(self, {
                "message": f"筛选完成：{result['passed']} 通过，{result['review']} 待审查，{len(rejected)} 拒绝",
                "passed": result['passed'],
                "review": result['review'],
                "rejected": len(rejected),
                "total_in_review": result['total'],
            })
        except Exception as e:
            log.error(f"review run error: {e}")
            _json(self, {"error": str(e)}, 500)


def serve(port: int = 8009, open_browser: bool = False):
    server = DualStackServer(("::", port), Handler)
    log.info(f"Panel v3 → http://127.0.0.1:{port}")
    if open_browser:
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8009)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    serve(args.port, args.open)
