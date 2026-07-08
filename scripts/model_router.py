#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Dict

try:
    import yaml
except ModuleNotFoundError:
    yaml = None


@dataclass
class ModelSpec:
    name: str
    provider: str
    endpoint: str
    use_cases: list[str]


class ModelRouter:
    def __init__(self, registry_path: str = "config/model_registry.yaml"):
        if not os.path.exists(registry_path):
            registry_path = "config/model_registry.example.yaml"
        content = open(registry_path, "r", encoding="utf-8").read()
        if yaml:
            self.registry = yaml.safe_load(content)
        elif registry_path.endswith(".json"):
            self.registry = json.loads(content)
        else:
            raise RuntimeError("pyyaml not installed; use json registry or install pyyaml")

    def resolve(self, capability: str) -> ModelSpec:
        alias = self.registry.get("routing", {}).get(capability)
        if not alias:
            raise KeyError(f"未找到 capability 路由: {capability}")
        node = self.registry["models"][alias]
        return ModelSpec(node["model"], node.get("provider", "local"), node.get("endpoint", ""), node.get("use_cases", []))

    def infer(self, capability: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        spec = self.resolve(capability)
        return {
            "capability": capability,
            "model": spec.name,
            "provider": spec.provider,
            "endpoint": spec.endpoint,
            "payload_preview": str(payload)[:200],
            "status": "stub",
        }
