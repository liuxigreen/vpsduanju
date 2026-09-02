#!/usr/bin/env python3
"""trace_v2 — 搬运溯源 v2（本地指纹聚类 + 中文信号还原，零外部搜索）

v1 失败根因: 依赖 yt-dlp 向外搜索中文频道, 但搬运剧标题/描述已本地化。
v2 核心: 向内聚 — 用字幕内容层的 华裔姓氏音译 + 角色名还原 + 剧情指纹聚类。

三层证据链:
  层1 翻译判定  origin_signals.feels_translated + reason
  层2 中文信号  华裔姓氏 → 中文姓氏候选 + bai 角色名/剧名还原
  层3 指纹聚类  题材L1×剧情结构 → 找跨语种姊妹版（"这部剧也被搬到了..."）

用法:
    python3 scripts/l1_calibration/trace_v2.py --video-id XXX
    python3 scripts/l1_calibration/trace_v2.py --all
    python3 scripts/l1_calibration/trace_v2.py --fingerprint-report   # 只看聚类
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENRES_DIR, ROOT, call_bai, load_vocab, norm_genre
import yaml

TRACE_DIR = ROOT / "data" / "drama_trace_v2"
SURNAME_PATH = Path(__file__).resolve().parent / "cn_surname.yaml"

# ── 层4: 中文搜索引擎验证（百度主/搜狗备，DDG 兜底；零 key 依赖）──
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
_CN_DRAMA_MARKS = re.compile(r"短剧|紅果|红果|抖音|百度百科|豆瓣|快手|番茄|主演|全集|微剧|剧情")
_SESSION = None


def _sess():
    global _SESSION
    if _SESSION is None:
        import requests
        _SESSION = requests.Session()
        _SESSION.headers.update({
            "User-Agent": _UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
    return _SESSION


def _extract_h3(html):
    out = []
    for x in re.findall(r"<h3[^>]*>(.*?)</h3>", html, re.S):
        t = re.sub(r"<[^>]+>", "", x)
        t = t.replace("&quot;", '"').replace("&amp;", "&").strip()
        if t:
            out.append(t)
    return out[:6]


_BAIDU_LAST_CALL = [0.0]


def _baidu_titles(q, timeout=15):
    import time
    import requests
    # 百度对同 IP 高频敏感：每次新建会话（复用 cookie 会被降级壳页）+ ≥8s 间隔
    wait = _BAIDU_LAST_CALL[0] + 8.0 - time.time()
    if wait > 0:
        time.sleep(wait)
    _BAIDU_LAST_CALL[0] = time.time()
    s = requests.Session()
    s.headers.update({"User-Agent": _UA,
                      "Accept-Language": "zh-CN,zh;q=0.9"})
    r = s.get("https://www.baidu.com/s", params={"wd": q, "ie": "utf-8"}, timeout=timeout)
    r.encoding = "utf-8"  # 响应头无 charset，默认 latin-1 会把验证码页解码成乱码漏检
    # 验证码/降级壳页约 1.5KB，正常结果页 >500KB
    if r.status_code != 200 or len(r.text) < 50000 or "安全验证" in r.text or "wappass" in r.text:
        return None  # 反爬/验证码 → 不可判
    return _extract_h3(r.text)


_DDG_LAST_CALL = [0.0]


def _ddg_titles(q, timeout=15):
    import time
    import requests
    # 连续请求会触发 202 反爬，强制 ≥3s 间隔
    wait = _DDG_LAST_CALL[0] + 3.0 - time.time()
    if wait > 0:
        time.sleep(wait)
    _DDG_LAST_CALL[0] = time.time()
    r = requests.get("https://html.duckduckgo.com/html/", params={"q": q},
                     headers={"User-Agent": _UA}, timeout=timeout)
    if r.status_code != 200:
        return None
    raw = re.findall(r'class="result__a"[^>]*>(.*?)</a>', r.text)
    return [re.sub(r"<[^>]+>", "", t).strip() for t in raw][:6]


def cn_verify(cn_title, timeout=15):
    """验证候选中文剧名是否真实存在。百度主查、DDG 兜底。
    判定：结果标题同时含剧名前缀 + 短剧特征标记 → verified。
    引擎反爬/网络失败 → verified=None（不可判，不误伤）。"""
    import time
    q = f'"{cn_title}" 短剧'
    titles = _baidu_titles(q, timeout)
    engine = "baidu"
    if titles is None:
        time.sleep(2)
        titles = _ddg_titles(q, timeout)
        engine = "ddg"
    if titles is None:
        return {"verified": None, "error": "all engines blocked"}
    pref = cn_title[:4] if len(cn_title) >= 4 else cn_title
    hits = [t for t in titles if _CN_DRAMA_MARKS.search(t) and pref in t]
    return {"verified": len(hits) > 0, "engine": engine,
            "n_hits": len(hits), "top_titles": titles[:4]}


# 兼容旧名
ddg_verify = cn_verify

# 剧情结构指纹标记（synopsis 特征词 → 结构位）
STRUCT_MARKS = {
    "has_marriage": ["婚", "嫁", "结婚"],
    "has_baby": ["宝", "孕", "萌", "女儿", "儿子", "孩子"],
    "has_revenge": ["仇", "复仇", "报复", "复仇者"],
    "has_identity": ["秘", "隐藏", "假", "真实身份", "马甲", "真身"],
    "has_rebirth": ["重生", "穿越", "前世"],
    "has_wealth": ["总裁", "CEO", "億万", "亿万", "富豪", "豪门", "千金"],
    "has_power": ["帝", "王", "战神", "神医", "修仙", "宗门", "修为"],
    "has_betrayal": ["背叛", "出轨", "绿", "小三", "未婚夫"],
    "has_abuse": ["虐", "血库", "虐待", "打脸"],
}


def load_rows():
    """加载全部字幕分析结果（video_genres/*.json，兼容 P0 回传）。"""
    rows = []
    # 优先新校准产物
    files = sorted(GENRES_DIR.glob("*.json"))
    for fp in files:
        if fp.name.endswith(".raw.txt"):
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        if d.get("_status") not in ("ok", "ok_with_issues"):
            continue
        rows.append(d)
    # 兼容 P0 旧格式（output/subtitle_task/results_p0.jsonl）
    if not rows:
        src = ROOT / "output/subtitle_task/results_p0.jsonl"
        if src.exists():
            for line in src.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                a = d.get("analysis") or {}
                rows.append({
                    "video_id": d.get("video_id"),
                    "title": d.get("title", ""),
                    "language": d.get("language", d.get("lang", "")),
                    "channel": d.get("channel", ""),
                    "synopsis": a.get("synopsis", ""),
                    "genre_l1": a.get("genre_l1", []),
                    "genre_l2": a.get("genre_l2", []),
                    "characters": a.get("characters", []),
                    "distinctive_lines": a.get("distinctive_lines", []),
                    "origin_signals": a.get("origin_signals", {}),
                    "analysis": a,
                })
    # schema 适配：P0 回传无 synopsis/characters 字段，内容证据在
    # opening_hook/key_reveals/payoffs/origin_signals.reason 里，拼成 content_text
    for d in rows:
        if not d.get("synopsis"):
            a = d.get("analysis") or {}
            parts = [a.get("opening_hook") or ""]
            parts += [str(x) for x in (a.get("key_reveals") or [])]
            parts += [str(x) for x in (a.get("payoffs") or [])]
            parts += [str(x) for x in (a.get("distinctive_lines") or [])]
            d["synopsis"] = "。".join(p for p in parts if p)
        if not d.get("characters"):
            a = d.get("analysis") or {}
            d["_surname_text"] = " ".join([
                str(a.get("opening_hook") or ""),
                " ".join(str(x) for x in (a.get("key_reveals") or [])),
                str((a.get("origin_signals") or {}).get("reason") or ""),
                " ".join(str(c) if isinstance(c, str) else c.get("name", "")
                         for c in (d.get("characters") or [])),
            ])
    return rows


def extract_surnames(rows, text):
    """从角色名/文本中提取华裔姓氏音译。"""
    surs = yaml.safe_load(SURNAME_PATH.read_text(encoding="utf-8"))
    mapping = surs["surname_romaji"]
    hits = []
    for romaji, cn in sorted(mapping.items(), key=lambda x: -len(x[0])):
        # 角色名整体匹配（Word边界），避免误匹配普通词
        if re.search(rf"\b{re.escape(romaji)}\b", text, re.I):
            hits.append({"romaji": romaji, "cn": cn})
    return hits


def fingerprint(d):
    """剧情结构指纹：题材 + 结构标记位。"""
    s = d.get("synopsis") or ""
    struct = {k: any(w in s for w in marks) for k, marks in STRUCT_MARKS.items()}
    genre = tuple(sorted(d.get("genre_l1") or []))
    return {"genre": genre, "struct": struct}


def cluster_by_fingerprint(rows):
    """按指纹聚类 → 跨语种姊妹版。"""
    clusters = defaultdict(list)
    for d in rows:
        fp = fingerprint(d)
        key = (fp["genre"], tuple(sorted(fp["struct"].items())))
        clusters[key].append(d)
    return clusters


def find_siblings(rows, target, max_n=6):
    """找目标视频的跨语种姊妹版。"""
    tfp = fingerprint(target)
    tkey = (tfp["genre"], tuple(sorted(tfp["struct"].items())))
    siblings = []
    for d in rows:
        if d.get("video_id") == target.get("video_id"):
            continue
        fp = fingerprint(d)
        key = (fp["genre"], tuple(sorted(fp["struct"].items())))
        if key == tkey:
            siblings.append(d)
    # 按语种去重（同一语种保留播放最高的）
    by_lang = {}
    for s in siblings:
        lc = s.get("language") or "?"
        if lc not in by_lang or (s.get("views") or 0) > (by_lang[lc].get("views") or 0):
            by_lang[lc] = s
    return list(by_lang.values())[:max_n]


def trace_one(d, rows):
    """单视频三层溯源。"""
    osig = d.get("origin_signals") or {}
    feels_translated = bool(osig.get("feels_translated"))
    reason = osig.get("reason", "")

    result = {
        "video_id": d.get("video_id"),
        "title": d.get("title", ""),
        "language": d.get("language", ""),
        "channel": d.get("channel", ""),
        "feels_translated": feels_translated,
        "origin_reason": reason[:200] if reason else "",
    }
    if not feels_translated:
        result["verdict"] = "not_translated"
        result["note"] = "本地原创或非中文译制剧，溯源终止"
        return result

    # 层2: 华裔姓氏 + 角色名 → 中文信号
    chars = " ".join(c.get("name", "") if isinstance(c, dict) else str(c)
                     for c in (d.get("characters") or []))
    # P0 schema 无 characters 字段时用内容文本兜底（含音译残留）
    surname_text = d.get("_surname_text") or chars
    surnames = extract_surnames(rows, surname_text)
    result["surname_hits"] = surnames
    result["cn_surname"] = list({h["cn"] for h in surnames})[:3]

    # 核心守卫：无华裔姓氏信号 → 不硬猜剧名（原设计查不准的根源就是无信号硬猜）
    if not surnames:
        result["verdict"] = "translated_no_surname"
        result["note"] = "翻译剧但角色名无华裔姓氏音译信号，不硬猜剧名（置信度必然低）"
        siblings = find_siblings(rows, d)
        result["siblings"] = [
            {"video_id": s.get("video_id"), "title": (s.get("title") or "")[:60],
             "language": s.get("language"), "channel": s.get("channel")}
            for s in siblings
        ]
        result["has_siblings"] = len(siblings) > 0
        return result

    # bai 还原（角色名 → 中文名；synopsis → 中文剧名）
    synopsis = d.get("synopsis") or ""
    lines = (d.get("distinctive_lines") or [])[:2]
    genre_l1 = d.get("genre_l1") or []
    genre_l2 = d.get("genre_l2") or []
    prompt = (
        "你是国内短剧专家，熟悉红果/抖音/番茄上的热播中文短剧。以下是海外YouTube上的一部翻译剧内容线索，"
        "请对照你已知的国内短剧库，找出它的中文母本。\n"
        f"外语标题: {d.get('title','')}\n"
        f"语种: {d.get('language','')}\n"
        f"题材L1: {genre_l1} | 题材L2: {genre_l2}\n"
        f"梗概: {synopsis[:600]}\n"
        f"角色名: {chars[:300]}\n"
        f"台词: {lines}\n"
        f"已检测到华裔姓氏: {result['cn_surname']}\n"
        "判断思路：①用华裔姓氏(角色名音译残留)锁定中文姓氏；②用题材+梗概结构匹配你知识库里的国内短剧；"
        "③外语标题直译回中文也是线索（如 'Only poor girl passed 99 tests' → 999保姆/总裁面试）。\n"
        '输出JSON: {"candidates": [{"cn_title": "最匹配的国内剧名", "match_evidence": "匹配依据", "confidence": 0-1}], '
        '（最多3个，按置信度排序，无把握也给出最像的）}。只输出JSON。'
    )
    try:
        parsed, raw, model = call_bai(prompt, max_tokens=1500, retries=3)
    except Exception as e:
        result["cn_title_guess"] = None
        result["_call_error"] = str(e)[:200]
        # 即便 bai 失败也继续聚类
        siblings = find_siblings(rows, d)
        result["siblings"] = [
            {"video_id": s.get("video_id"), "title": (s.get("title") or "")[:60],
             "language": s.get("language"), "channel": s.get("channel")}
            for s in siblings
        ]
        result["has_siblings"] = len(siblings) > 0
        return result
    if parsed:
        cands = parsed.get("candidates") or []
        # 层4: DDG 联网验证每个候选（剧名真实存在 = verified）
        for c in cands[:3]:
            t = (c.get("cn_title") or "").strip("《》")
            if t:
                c["ddg"] = ddg_verify(t)
        # 重排：验证通过的优先，其次按置信度
        cands.sort(key=lambda c: (
            -(1 if (c.get("ddg") or {}).get("verified") else 0),
            -(c.get("confidence") or 0)))
        if cands:
            best = cands[0]
            result["cn_title_guess"] = best.get("cn_title")
            result["confidence"] = best.get("confidence")
            result["guess_reason"] = best.get("match_evidence", "")
            result["ddg_verified"] = (best.get("ddg") or {}).get("verified")
            result["candidates"] = cands[:3]
        else:
            result["cn_title_guess"] = None
        result["cn_char_names"] = parsed.get("cn_char_names") or {}
        result["_model"] = model
    else:
        result["cn_title_guess"] = None
        result["_parse_error"] = raw[:200]

    # 层3: 指纹聚类 → 跨语种姊妹版
    siblings = find_siblings(rows, d)
    result["siblings"] = [
        {"video_id": s.get("video_id"), "title": (s.get("title") or "")[:60],
         "language": s.get("language"), "channel": s.get("channel")}
        for s in siblings
    ]
    result["has_siblings"] = len(siblings) > 0
    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--video-id")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--fingerprint-report", action="store_true")
    args = ap.parse_args()

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_rows()
    print(f"加载 {len(rows)} 条字幕分析")

    if args.fingerprint_report:
        clusters = cluster_by_fingerprint(rows)
        multi = {k: v for k, v in clusters.items() if len(set(d.get("language") for d in v)) > 1}
        print(f"\n跨语种指纹聚类: {len(multi)} 组")
        for k, v in sorted(multi.items(), key=lambda x: -len(x[1]))[:10]:
            langs = sorted(set(d.get("language") for d in v))
            print(f"  🎯 {k[0]} | {len(v)}条 | 语种: {langs}")
            for d in v[:3]:
                print(f"     [{d.get('language')}] {(d.get('title') or '')[:50]}")
        return

    targets = []
    if args.video_id:
        targets = [d for d in rows if d.get("video_id") == args.video_id]
    elif args.all:
        targets = rows
    else:
        targets = rows[:5]

    n_trans = n_match = 0
    for d in targets:
        print(f"\n{'='*60}\n▶ {d.get('video_id')} | {(d.get('title') or '')[:50]}")
        r = trace_one(d, rows)
        print(json.dumps(r, ensure_ascii=False, indent=1)[:1200])
        n_trans += r["feels_translated"]
        n_match += bool(r.get("cn_title_guess"))
        out = TRACE_DIR / f"{d['video_id']}.json"
        out.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✅ 完成: {len(targets)} 条, 翻译剧 {n_trans}, 中文剧名命中 {n_match} → {TRACE_DIR}/")


if __name__ == "__main__":
    main()
