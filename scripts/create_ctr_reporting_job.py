#!/usr/bin/env python3
"""为已 OAuth 授权的频道创建 YouTube Reporting API 的 CTR 报表 job。

背景：CTR/impressions 只在 Reporting API 可拿，Analytics API v2 没有。
job 创建后 24-48h 才有第一份报表；此脚本只负责建 job + 写回 our_channels.json 的 ctr_job_id。

用法：
  python3 scripts/create_ctr_reporting_job.py                # 所有 OAuth 频道
  python3 scripts/create_ctr_reporting_job.py --slug hk      # 指定频道
  python3 scripts/create_ctr_reporting_job.py --list         # 只列出现有 jobs 不创建
"""
import json, sys, argparse, urllib.request as ur, urllib.error as ue
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from collect_yt_analytics import get_access_token, load_accounts  # 复用

REGISTRY = ROOT / "data" / "own" / "our_channels.json"
REPORT_TYPE = "channel_reach_basic_a1"  # CTR / impressions 报表类型（YouTube Reporting 系统托管报表）
REPORT_TYPE_TRAFFIC = "channel_traffic_source_a3"  # 流量来源级 CTR（判"封面不行还是算法没推"）


def list_jobs(token):
    req = ur.Request("https://youtubereporting.googleapis.com/v1/jobs")
    req.add_header("Authorization", f"Bearer {token}")
    with ur.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode()).get("jobs", [])


def create_job(token, slug, report_type=REPORT_TYPE):
    body = json.dumps({
        "reportTypeId": report_type,
        "name": f"{report_type}_{slug}",
    }).encode()
    req = ur.Request("https://youtubereporting.googleapis.com/v1/jobs", data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    with ur.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def load_registry():
    return json.loads(REGISTRY.read_text())


def save_registry(reg):
    tmp = REGISTRY.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2))
    tmp.replace(REGISTRY)


def ensure_job_for_slug(slug, list_only=False, report_type=REPORT_TYPE):
    tok = get_access_token(slug)
    if not tok:
        print(f"[{slug}] no OAuth token, skip")
        return None
    try:
        jobs = list_jobs(tok)
    except ue.HTTPError as e:
        body = e.read().decode()[:300]
        print(f"[{slug}] list_jobs FAILED {e.code}: {body}")
        return None
    # 幂等：如已存在同名 job，直接返回
    existing = next((j for j in jobs if j.get("name") == f"{report_type}_{slug}"
                     or j.get("reportTypeId") == report_type), None)
    if existing:
        print(f"[{slug}] existing job id={existing['id']} name={existing.get('name')} "
              f"reportTypeId={existing.get('reportTypeId')} createTime={existing.get('createTime')}")
        return existing["id"]
    if list_only:
        print(f"[{slug}] no job yet (list-only mode, not creating)")
        return None
    try:
        created = create_job(tok, slug, report_type=report_type)
        print(f"[{slug}] CREATED job id={created['id']} reportTypeId={created['reportTypeId']} "
              f"createTime={created['createTime']}")
        return created["id"]
    except ue.HTTPError as e:
        body = e.read().decode()[:500]
        print(f"[{slug}] create_job FAILED {e.code}: {body}")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", help="only this slug")
    ap.add_argument("--list", action="store_true", help="only list existing jobs, do not create")
    ap.add_argument("--report-type", default=REPORT_TYPE,
                     choices=[REPORT_TYPE, REPORT_TYPE_TRAFFIC],
                     help="report type (default: channel_reach_basic_a1 for CTR)")
    args = ap.parse_args()

    reg = load_registry()
    channels = reg if isinstance(reg, list) else reg.get("channels", [])
    accounts = load_accounts()  # slug -> {..., channel_id}
    dirty = False
    job_key = "traffic_job_id" if args.report_type == REPORT_TYPE_TRAFFIC else "ctr_job_id"
    for c in channels:
        slug = c.get("slug")
        if args.slug and slug != args.slug:
            continue
        if slug not in accounts:
            print(f"[{slug}] not in accounts.json (no OAuth), skip")
            continue
        jid = ensure_job_for_slug(slug, list_only=args.list, report_type=args.report_type)
        if jid and c.get(job_key) != jid:
            c[job_key] = jid
            dirty = True
    if dirty and not args.list:
        save_registry(reg)
        print(f"registry updated: {REGISTRY}")
    elif not dirty:
        print("no registry change")


if __name__ == "__main__":
    main()
