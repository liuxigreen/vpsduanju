#!/usr/bin/env python3
"""sister_clusters — 搬运溯源 v3 · L1 库内姊妹簇聚类（零网络，确定性）

思路（对大姓假阳性的克制）：
  聚类键 = (主题材L1, 角色名特征前缀对) —— 同一部剧被多语种搬运时，角色名音译
  高度一致；取每部视频角色名的前缀集合，用「主题材相同 + 共享≥2个前缀」做并查集
  连边。繁中/中文条目的角色名常带中文原名（如 "Yuan Yi（袁毅）"），直接抽 CJK 段
  作为锚点：簇内含繁中/中文名 → 剧名/角色中文名白送。

输入: data/subtitle_analysis/library_details.json
输出: data/drama_trace_v3/sister_clusters.json
"""
import json
import re
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data/subtitle_analysis/library_details.json"
OUT = ROOT / "data/drama_trace_v3/sister_clusters.json"

CJK = re.compile(r"[\u4e00-\u9fff]{1,4}")
LATIN = re.compile(r"[A-Za-z]{3,}")


def name_prefixes(names):
    """角色名 → 特征前缀集合（CJK取前2字，拉丁取前4字母，全小写）。"""
    out = set()
    for n in names or []:
        n = (n or "").strip()
        if not n:
            continue
        cjk = CJK.search(n)
        if cjk:
            w = cjk.group(0)
            out.add(w[:2])
            continue
        for w in LATIN.findall(n):
            out.add(w.lower()[:4])
    return out


class UF:
    def __init__(self):
        self.p = {}

    def find(self, x):
        self.p.setdefault(x, x)
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[rb] = ra


def build():
    details = json.load(open(SRC, encoding="utf-8"))
    vids = list(details.values())

    # 倒排: (prefix, primary_genre) -> [video_id]
    inv = defaultdict(list)
    for v in vids:
        pres = name_prefixes([c.get("name") for c in v.get("characters") or []])
        genre = (v.get("l1") or [""])[0]
        v["_prefixes"] = pres
        v["_genre"] = genre
        for p in pres:
            inv[(p, genre)].append(v["video_id"])

    # DF 过滤：在库内出现 >40 次的前缀是大姓/通用词（wang/shen/chen/lord），区分度低，
    # 是传递闭包滚成巨型簇的主因——连边前剔除。
    df = {k: len(vs) for k, vs in inv.items()}
    inv = {k: vs for k, vs in inv.items() if df[k] <= 40}
    # 连边用的前缀集合同步收窄到低 DF 前缀
    for v in vids:
        genre = v["_genre"]
        v["_prefixes"] = {p for p in v["_prefixes"] if (p, genre) in inv}

    # 星型聚类（贪心）：以播放量降序取未分配视频为种子，收编所有与其共享≥2个
    # 低DF前缀且主题材相同的视频。禁用传递闭包——union-find 的链式 A-B-C 会在
    # 霸总这种大池子里把几百条无关剧滚成一个巨簇。
    order = sorted(vids, key=lambda v: -(v.get("views") or 0))
    assigned = {}
    clusters_map = []
    for seed in order:
        if seed["video_id"] in assigned:
            continue
        members = [seed]
        assigned[seed["video_id"]] = True
        for v in order:
            if v["video_id"] in assigned or v["_genre"] != seed["_genre"]:
                continue
            if len(seed["_prefixes"] & v["_prefixes"]) >= 2:
                members.append(v)
                assigned[v["video_id"]] = True
        if len(members) >= 2:
            clusters_map.append(members)

    clusters = defaultdict(list)
    for members in clusters_map:
        key = members[0]["video_id"]
        clusters[key] = members

    out_clusters = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        langs = defaultdict(list)
        for m in members:
            langs[m.get("lang_code") or m.get("language") or "?"].append(m)
        if len(langs) < 2:
            continue  # 单语种重复(同剧上下集/合集)，溯源价值低
        zh_members = [m for m in members if (m.get("lang_code") in ("zh-Hant", "zh"))
                      or any(CJK.search(c.get("name") or "") for c in m.get("characters") or [])]
        out_clusters.append({
            "size": len(members),
            "languages": sorted(langs.keys()),
            "zh_anchor": bool(zh_members),
            "zh_titles": [m.get("title", "")[:40] for m in zh_members[:3]],
            "members": [{"video_id": m["video_id"], "title": (m.get("title") or "")[:44],
                         "lang": m.get("lang_code") or m.get("language"), "views": m.get("views") or 0}
                        for m in sorted(members, key=lambda x: -(x.get("views") or 0))],
        })
    out_clusters.sort(key=lambda c: (-c["zh_anchor"], -c["size"]))

    covered = sum(c["size"] for c in out_clusters)
    zh_covered = sum(c["size"] for c in out_clusters if c["zh_anchor"])
    out = {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "algorithm": "compound: 主题材相同 + 共享≥2个角色名前缀 (union-find)",
        "stats": {
            "videos": len(vids),
            "clusters_crosslang": len(out_clusters),
            "videos_in_clusters": covered,
            "coverage": round(covered / max(len(vids), 1), 3),
            "clusters_with_zh_anchor": sum(1 for c in out_clusters if c["zh_anchor"]),
            "videos_with_zh_anchor": zh_covered,
            "zh_anchor_coverage": round(zh_covered / max(len(vids), 1), 3),
        },
        "clusters": out_clusters[:400],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    s = out["stats"]
    print(f"跨语种簇 {s['clusters_crosslang']} 个 | 覆盖 {s['videos_in_clusters']}/{s['videos']} ({s['coverage']:.0%})")
    print(f"含中文锚点簇 {s['clusters_with_zh_anchor']} 个 | 锚点覆盖 {s['videos_with_zh_anchor']} ({s['zh_anchor_coverage']:.0%})")
    for c in out_clusters[:4]:
        print(f"  簇[{c['size']}条 {','.join(c['languages'])}] 锚点={c['zh_anchor']} → {c['members'][0]['title'][:36]}")


if __name__ == "__main__":
    build()
