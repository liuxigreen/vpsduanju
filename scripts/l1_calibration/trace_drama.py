#!/usr/bin/env python3
"""维度5：国内原剧溯源（无豆包联网搜索版）。四路证据源：
  ① ytsearch引擎：yt-dlp 搜中文还原名/原梗概 → 中文搬运频道(茶剧会/追剧酱/紅果短劇官方)的
     标题+描述里常带【国内原名+演员】，实测"閃婚后成了滿級大佬心尖寵"→《闪婚成宠：首富大佬爱上我》直接命中
  ② 本地互查：自有竞品库繁中池(815条)标题/梗概模糊匹配——很多翻译剧的原版就在我们盯的频道里
  ③ bai 内部知识：主模型本身认识大量国内爆款短剧（红果/抖音热榜剧）
  ④ 人工辅助包：三路都拿不下时输出"红果App搜索包"（还原中文名+台词），用户App内一搜即中
产出 data/drama_trace/{video_id}.json

用法:
    python3 scripts/l1_calibration/trace_drama.py --limit 5
    python3 scripts/l1_calibration/trace_drama.py --video-id XXX
"""
import argparse
import difflib
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import GENRES_DIR, ROOT, call_bai, load_momentum_videos

TRACE_DIR = ROOT / "data" / "drama_trace"
PROMPTS = Path(__file__).resolve().parent / "prompts.md"

# 中文搬运/官方频道特征词——命中这些频道的搜索结果，标题/描述大概率含国内原名
CN_MARKERS = re.compile(r"红果|紅果|短剧|短劇|全集|完整版|饭桶|茶剧|追剧|星芒|番茄|听花|河马|麦芽|九州")


def yt_search(query, max_results=6, timeout=45):
    """yt-dlp 搜片，返回 [{title, channel, id}]，只留疑似中文原版的命中。"""
    try:
        r = subprocess.run(
            ["yt-dlp", f"ytsearch{max_results}:{query}", "--flat-playlist",
             "--print", "%(title)s\t%(channel)s\t%(id)s"],
            capture_output=True, text=True, timeout=timeout)
        hits = []
        for ln in r.stdout.splitlines():
            parts = ln.split("\t")
            if len(parts) == 3:
                t, c, i = parts
                hits.append({"title": t, "channel": c, "id": i,
                             "cn_signal": bool(CN_MARKERS.search(t) or CN_MARKERS.search(c))})
        return hits
    except Exception as e:
        print(f"    ⚠️ ytsearch失败: {str(e)[:80]}")
        return []


def yt_desc(video_id, timeout=30):
    """拉单条候选的完整描述——搬运频道常在描述里写原名/演员表。"""
    try:
        r = subprocess.run(["yt-dlp", "--skip-download", "--print", "%(description)s",
                            f"https://www.youtube.com/watch?v={video_id}"],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout[:2000]
    except Exception:
        return ""


def local_match(synopsis, cn_names, pool):
    """②本地互查：繁中池标题与还原中文名/梗概做模糊匹配。"""
    out = []
    zh_titles = [(v, v["title"]) for v in pool if v.get("language") in ("繁中", "zh", "中文")]
    targets = [n for n in cn_names if n]
    for v, title in zh_titles:
        score = max((difflib.SequenceMatcher(None, t, title).ratio() for t in targets), default=0)
        if synopsis and synopsis[:20] in title:
            score = max(score, 0.8)
        if score > 0.55:
            out.append({"video_id": v["id"], "title": title, "channel": v.get("channel"), "sim": round(score, 2)})
    return sorted(out, key=lambda x: -x["sim"])[:5]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--video-id")
    ap.add_argument("--no-yt", action="store_true", help="跳过ytsearch（离线跑）")
    args = ap.parse_args()

    TRACE_DIR.mkdir(parents=True, exist_ok=True)
    tpl = PROMPTS.read_text(encoding="utf-8")
    m = re.search(r"--- prompt:trace ---\n(?:（.*?）\n)?(.*)$", tpl, re.S)
    if not m:
        raise RuntimeError("prompts.md 缺少 trace 模板")
    trace_tpl = m.group(1)

    files = ([GENRES_DIR / f"{args.video_id}.json"] if args.video_id else sorted(GENRES_DIR.glob("*.json")))
    pool = load_momentum_videos()

    todo = []
    for f in files:
        if not f.exists():
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("_status") not in ("ok", "ok_with_issues"):
            continue
        out = TRACE_DIR / f"{d['video_id']}.json"
        if out.exists() and json.loads(out.read_text(encoding="utf-8")).get("_status") == "matched":
            continue
        todo.append(d)
    if not args.video_id:
        todo = todo[: args.limit]
    print(f"待溯源: {len(todo)} 条")

    n_match = 0
    for i, d in enumerate(todo, 1):
        vid = d["video_id"]
        print(f"[{i}/{len(todo)}] {vid} {d.get('title','')[:50]}")
        chars = [c.get("name", "") for c in (d.get("characters") or []) if c.get("name")]
        lines = (d.get("distinctive_lines") or [])[:2]

        # ① 先让 bai 做"还原+直搜query生成"（它懂中文爆款剧名规律+人名音译）
        pre_prompt = (f"海外短剧字幕还原出这些角色名（外语拼写）：{chars}；台词：{lines[:1]}；"
                      f"梗概：{d.get('synopsis','')}。"
                      '输出JSON：{{"cn_char_names":["还原中文名，最多3个"],'
                      '"cn_title_guesses":["国内剧名最可能写法，最多3个"],'
                      '"search_queries":["3条中文搜索query，含红果/抖音/短剧关键词"]}}。只输出JSON。')
        pre, _, _ = call_bai(pre_prompt, max_tokens=600)
        queries = (pre or {}).get("search_queries") or []
        cn_guesses = (pre or {}).get("cn_title_guesses") or []
        cn_chars = (pre or {}).get("cn_char_names") or []

        # ② ytsearch 引擎
        yt_hits = []
        if not args.no_yt:
            for q in (queries or cn_guesses)[:2]:
                hits = yt_search(q)
                strong = [h for h in hits if h["cn_signal"]]
                for h in strong[:2]:
                    h["description"] = yt_desc(h["id"])[:800]
                yt_hits += strong
                print(f"    🔍 yt[{q[:30]}] → {len(strong)}/{len(hits)} 条中文信号")

        # ③ 本地互查
        loc = local_match(d.get("synopsis") or "", cn_guesses + cn_chars, pool)

        # ④ bai 裁决（三路证据一起喂）
        prompt = (trace_tpl.replace("{title}", d.get("title", ""))
                  .replace("{channel}", d.get("channel", ""))
                  .replace("{language}", d.get("language", ""))
                  .replace("{synopsis}", d.get("synopsis") or "null")
                  .replace("{characters}", json.dumps({"外文": chars, "还原中文": cn_chars}, ensure_ascii=False))
                  .replace("{lines}", json.dumps(lines, ensure_ascii=False))
                  .replace("{genres}", json.dumps({"l1": d.get("genre_l1"), "l2": d.get("genre_l2")}, ensure_ascii=False))
                  .replace("{origin_reason}", json.dumps(d.get("origin_signals") or {}, ensure_ascii=False))
                  .replace("{candidates}", json.dumps({"youtube中文搬运候选": yt_hits, "本地竞品库候选": loc}, ensure_ascii=False)[:9000] or "（无候选）"))
        rec = {"video_id": vid, "title": d.get("title"), "language": d.get("language"),
               "channel": d.get("channel"),
               "evidence": {"cn_guesses": cn_guesses, "cn_chars": cn_chars,
                            "yt_candidates": yt_hits, "local_candidates": loc}}
        try:
            parsed, raw, model = call_bai(prompt, max_tokens=4000)
            rec["_model"] = model
            if parsed:
                rec.update(parsed)
                rec["_status"] = "matched" if parsed.get("cn_title") else "no_match"
                if not parsed.get("cn_title"):
                    # ⑤ 人工辅助包：给用户的红果App搜索指令
                    rec["manual_pack"] = {"红果App搜索词": cn_guesses + cn_chars,
                                          "台词核对": lines, "梗概": d.get("synopsis")}
                n_match += bool(parsed.get("cn_title"))
            else:
                rec["_status"] = "parse_failed"
                (TRACE_DIR / f"{vid}.raw.txt").write_text(raw, encoding="utf-8")
        except Exception as e:
            rec["_status"] = f"error: {e}"
        (TRACE_DIR / f"{vid}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n✅ 命中 {n_match}/{len(todo)} → {TRACE_DIR}/（未命中的含 manual_pack 人工搜索包）")


if __name__ == "__main__":
    main()
