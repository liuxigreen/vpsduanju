# AGENTS

## Scope
This file applies to the entire repository.

## Working rules
- Keep refactors minimal and composable.
- Preserve existing script names; add adapters instead of breaking flows.
- Route model selection via `scripts/model_router.py`; do not hardcode model names in new logic.
- Route skill context via `scripts/skill_router.py`; do not inline SKILL text in business scripts.
- Prefer writing outputs under `data/` and `output/` with deterministic JSON schema.
