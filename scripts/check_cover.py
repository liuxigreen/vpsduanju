#!/usr/bin/env python3
from __future__ import annotations


def score_cover_candidate(title: str, cover_brief: str, drama_analysis: dict, preset: str) -> dict:
    keywords = drama_analysis.get("hooks_and_twists", []) + drama_analysis.get("key_props", []) + drama_analysis.get("key_scenes", [])
    overlap = sum(1 for k in keywords if k and k in cover_brief)
    title_overlap = sum(1 for w in title.replace("：", " ").split() if w and w in cover_brief)

    click_bias = 15 if preset == "fast_validation" else 0
    consistency_bias = 15 if preset == "full_rebuild" else 0

    hook = min(50 + overlap * 10 + click_bias, 100)
    alignment = min(40 + overlap * 15 + consistency_bias, 100)
    clarity = min(50 + title_overlap * 10, 100)
    total = round(hook * 0.35 + alignment * 0.45 + clarity * 0.2, 2)
    return {"hook": hook, "alignment": alignment, "clarity": clarity, "total": total}
