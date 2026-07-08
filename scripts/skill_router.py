#!/usr/bin/env python3
"""Skill 路由：四层对齐 — rules / evidence / skill / meta，统一接入脚本。

Schema v1.1 (2026-04-22):
  rule 必须字段: id/name/module/condition/action/check/check_type/fail_action/source/tier/evidence_ref
  evidence 必须字段: id/tier/source/description/confidence/supports_rules
  check_type: eval(可执行表达式) | data(需外部数据) | manual(AI判断)
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable

SKILL_DIR = Path(__file__).resolve().parent.parent / "references"
RULES_DIR = Path(__file__).resolve().parent.parent / "distill" / "outputs"
EVIDENCE_DIR = Path(__file__).resolve().parent.parent / "distill" / "outputs"

SUPPORTED_SKILLS = [
    "short-drama-youtube",        # v3 蒸馏版（推荐）
    "overseas-drama-director",    # nuwa-style 全能运营总监
    "short-drama-expert",         # legacy 内容专家
    "distribution-expert",        # legacy 分发专家
]

TASK_KEYWORDS = {
    "short-drama-youtube": ["title", "cover", "edit", "drama", "题材", "标题", "封面", "剪辑", "content", "localization",
                            "distribution", "publish", "analytics", "signal", "分发", "发布时间", "运营", "frequency", "timing", "revenue",
                            "上架", "方案", "proposal", "upload", "yt", "youtube", "地区", "region", "标签", "描述", "骨架", "钩子"],
    "overseas-drama-director": ["title", "cover", "edit", "drama", "题材", "标题", "封面", "剪辑", "content", "localization",
                                 "distribution", "publish", "analytics", "signal", "分发", "发布时间", "运营", "frequency", "timing", "revenue",
                                 "上架", "方案", "proposal", "upload", "yt", "youtube", "地区", "region", "标签", "描述"],
    "short-drama-expert": ["title", "cover", "edit", "drama", "题材", "标题", "封面", "剪辑", "content", "localization"],
    "distribution-expert": ["distribution", "publish", "analytics", "signal", "分发", "发布时间", "运营", "frequency", "timing", "revenue"],
}

# ── 四层读取 ──────────────────────────────────────────────

def _read_skill(skill_name: str) -> str:
    """读取 skill 内容。优先读 PROMPT.md（API用精简版），不存在再读 SKILL.md"""
    # 优先读精简版（用于API调用）
    prompt_path = SKILL_DIR / skill_name / "PROMPT.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    # 回退到完整版
    path = SKILL_DIR / skill_name / "SKILL.md"
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def _read_meta(skill_name: str) -> dict:
    path = SKILL_DIR / skill_name / "META.md"
    if not path.exists():
        return {}
    meta = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("- "):
            parts = line[2:].split(": ", 1)
            if len(parts) == 2:
                meta[parts[0].strip()] = parts[1].strip()
    return meta


def _read_rules_full(skill_name: str) -> dict:
    """读取完整 rules.json（含顶层元数据）"""
    rules_file = RULES_DIR / skill_name / "rules.json"
    if not rules_file.exists():
        return {}
    try:
        return json.loads(rules_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, KeyError):
        return {}


def _read_rules(skill_name: str) -> list[dict]:
    data = _read_rules_full(skill_name)
    return data.get("rules", [])


def _read_evidence(skill_name: str) -> list[dict]:
    ev_file = EVIDENCE_DIR / skill_name / "evidence.json"
    if not ev_file.exists():
        return []
    try:
        data = json.loads(ev_file.read_text(encoding="utf-8"))
        return data.get("evidence", [])
    except (json.JSONDecodeError, KeyError):
        return []


# ── 过滤 ──────────────────────────────────────────────────

def _filter_rules(rules: list[dict], module: str | None = None, max_tier: int = 3,
                  check_type: str | None = None) -> list[dict]:
    filtered = rules
    if module:
        filtered = [r for r in filtered if r.get("module") == module]
    filtered = [r for r in filtered if r.get("tier", 3) <= max_tier]
    if check_type:
        filtered = [r for r in filtered if r.get("check_type") == check_type]
    return filtered


# ── 路由 ──────────────────────────────────────────────────

def select_skills(task: str) -> list[str]:
    task_l = task.lower()
    chosen: list[str] = []
    for skill in SUPPORTED_SKILLS:
        keys = TASK_KEYWORDS[skill]
        if any(k.lower() in task_l for k in keys):
            chosen.append(skill)
    if not chosen:
        chosen = ["short-drama-youtube"]
    return chosen


# ── 四层聚合 ──────────────────────────────────────────────

def get_skill_context(task: str, force_skills: Iterable[str] | None = None) -> dict:
    skills = list(force_skills) if force_skills else select_skills(task)
    return {
        "task": task,
        "skills": skills,
        "skill": {s: _read_skill(s) for s in skills},
        "contexts": {s: _read_skill(s) for s in skills},  # backward compat
        "rules": {s: _read_rules(s) for s in skills},
        "evidence": {s: _read_evidence(s) for s in skills},
        "meta": {s: _read_meta(s) for s in skills},
        "rules_header": {s: {k: v for k, v in _read_rules_full(s).items() if k != "rules"} for s in skills},
    }


def get_rules_for_task(task: str, module: str | None = None, max_tier: int = 2,
                       check_type: str | None = None) -> list[dict]:
    skills = select_skills(task)
    all_rules = []
    for skill in skills:
        skill_rules = _read_rules(skill)
        filtered = _filter_rules(skill_rules, module=module, max_tier=max_tier, check_type=check_type)
        all_rules.extend(filtered)
    return all_rules


def get_rules_for_module(module: str, skill: str | None = None, max_tier: int = 2) -> list[dict]:
    if skill:
        skills = [skill]
    else:
        skills = SUPPORTED_SKILLS
    all_rules = []
    for s in skills:
        skill_rules = _read_rules(s)
        filtered = _filter_rules(skill_rules, module=module, max_tier=max_tier)
        all_rules.extend(filtered)
    return all_rules


def get_evidence_for_rule(rule: dict, skill_name: str) -> list[dict]:
    ev_refs = rule.get("evidence_ref", [])
    if not ev_refs:
        return []
    all_ev = _read_evidence(skill_name)
    ev_by_id = {e["id"]: e for e in all_ev}
    return [ev_by_id[ref] for ref in ev_refs if ref in ev_by_id]


def get_evidence_by_tier(skill_name: str, max_tier: int = 2) -> list[dict]:
    all_ev = _read_evidence(skill_name)
    return [e for e in all_ev if e.get("tier", 4) <= max_tier]


# ── Prompt 构建 ───────────────────────────────────────────

def build_prompt_with_skill(task: str, base_prompt: str, force_skills: Iterable[str] | None = None) -> str:
    bundle = get_skill_context(task, force_skills)
    sections = [base_prompt, "\n\n# Skill Context"]

    for skill in bundle["skills"]:
        # Layer: skill — nuwa-style 不截断，完整注入认知操作系统
        skill_text = bundle["skill"].get(skill, "").strip()
        if skill_text:
            sections.append(f"\n## {skill}\n{skill_text}")

        # Layer: rules (规则卡)
        skill_rules = bundle["rules"].get(skill, [])
        if skill_rules:
            rule_cards = []
            for r in skill_rules[:10]:
                ev_refs = r.get("evidence_ref", [])
                ev_tag = f" [EV:{','.join(ev_refs[:2])}]" if ev_refs else ""
                ct = r.get("check_type", "")
                ct_tag = f" ({ct})" if ct else ""
                rule_cards.append(f"- [{r['id']}] {r['name']}: {r['action']}{ev_tag}{ct_tag}")
            sections.append(f"\n## {skill} 规则卡\n" + "\n".join(rule_cards))

        # Layer: meta
        meta = bundle["meta"].get(skill, {})
        if meta:
            meta_lines = [f"- {k}: {v}" for k, v in list(meta.items())[:12]]
            sections.append(f"\n## {skill} META\n" + "\n".join(meta_lines))

    return "\n".join(sections)


def build_prompt_with_evidence(task: str, base_prompt: str, max_tier: int = 2) -> str:
    skills = select_skills(task)
    sections = [base_prompt, "\n\n# Evidence Chain"]

    for skill in skills:
        ev = get_evidence_by_tier(skill, max_tier=max_tier)
        if ev:
            ev_lines = []
            for e in ev[:8]:
                conf = "★" * e.get("confidence", 3)
                ev_lines.append(f"- [{e['id']}] {e['description']} (tier={e['tier']}, {conf})")
            sections.append(f"\n## {skill} 证据\n" + "\n".join(ev_lines))

    return "\n".join(sections)


# ── 规则检查 ──────────────────────────────────────────────

def check_rules(task: str, check_data: dict, max_tier: int = 2) -> list[dict]:
    """用规则检查数据，返回失败列表。只执行 check_type=eval 的规则。"""
    rules = get_rules_for_task(task, max_tier=max_tier)
    failures = []
    for rule in rules:
        check_expr = rule.get("check", "")
        check_type = rule.get("check_type", "data")
        if not check_expr or check_type != "eval":
            continue
        try:
            # eval 上下文：只暴露 check_data + re
            ctx = {"re": re, "len": len, "any": any, "all": all, **check_data}
            result = eval(check_expr, {"__builtins__": {}}, ctx)
            if not result:
                failures.append({
                    "rule_id": rule["id"],
                    "rule_name": rule["name"],
                    "action": rule.get("fail_action", "WARN"),
                    "source": rule.get("source", ""),
                    "evidence_ref": rule.get("evidence_ref", []),
                    "check_type": check_type,
                })
        except Exception as e:
            failures.append({
                "rule_id": rule["id"],
                "rule_name": rule["name"],
                "action": "ERROR",
                "error": str(e),
                "check_type": check_type,
            })
    return failures


# ── Schema 验证 ───────────────────────────────────────────

REQUIRED_RULE_FIELDS = {"id", "name", "module", "condition", "action", "check", "check_type", "fail_action", "source", "tier", "evidence_ref"}
OPTIONAL_RULE_FIELDS = {"check_hint"}
REQUIRED_EV_FIELDS = {"id", "tier", "description", "confidence", "supports_rules"}
OPTIONAL_EV_FIELDS = {"source", "sample_size", "detail", "channels", "status", "validation"}


def validate_rules_schema(skill_name: str) -> list[str]:
    """验证 rules.json + evidence.json 的字段完整性，返回问题列表"""
    issues = []

    # Validate rules
    rules = _read_rules(skill_name)
    full = _read_rules_full(skill_name)
    schema_ver = full.get("schema_version", "0")
    if schema_ver != "1.1":
        issues.append(f"rules.json schema_version={schema_ver}, expected 1.1")

    ev_ids_in_evidence = {e["id"] for e in _read_evidence(skill_name)}
    rule_ids = set()

    for r in rules:
        rid = r.get("id", "?")
        rule_ids.add(rid)
        missing = REQUIRED_RULE_FIELDS - set(r.keys())
        if missing:
            issues.append(f"{rid}: missing fields {missing}")
        extra = set(r.keys()) - REQUIRED_RULE_FIELDS - OPTIONAL_RULE_FIELDS
        if extra:
            issues.append(f"{rid}: unknown fields {extra}")
        # evidence_ref integrity
        for ref in r.get("evidence_ref", []):
            if ref not in ev_ids_in_evidence:
                issues.append(f"{rid}: evidence_ref {ref} not in evidence.json")

    # Validate evidence
    evidence = _read_evidence(skill_name)
    for e in evidence:
        eid = e.get("id", "?")
        missing = REQUIRED_EV_FIELDS - set(e.keys())
        if missing:
            issues.append(f"{eid}: missing fields {missing}")
        extra = set(e.keys()) - REQUIRED_EV_FIELDS - OPTIONAL_EV_FIELDS
        if extra:
            issues.append(f"{eid}: unknown fields {extra}")
        # reverse ref
        for sr in e.get("supports_rules", []):
            if sr not in rule_ids:
                issues.append(f"{eid}: supports_rules {sr} not in rules.json")
        # tier-1 must have sample_size + detail
        if e.get("tier") == 1:
            if not e.get("sample_size"):
                issues.append(f"{eid}: tier=1 but no sample_size")
            if not e.get("detail"):
                issues.append(f"{eid}: tier=1 but no detail")

    # Check orphan evidence (not referenced by any rule)
    refs_used = set()
    for r in rules:
        for ref in r.get("evidence_ref", []):
            refs_used.add(ref)
    for e in evidence:
        if e["id"] not in refs_used and e.get("supports_rules"):
            issues.append(f"{e['id']}: orphan evidence (not referenced by any rule, supports_rules non-empty)")

    return issues


def get_schema_version(skill_name: str) -> str:
    """返回 rules.json 的 schema_version"""
    full = _read_rules_full(skill_name)
    return full.get("schema_version", "0")
