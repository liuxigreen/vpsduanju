"""edgefn模型配置与调用

模型分级：
  flash  → 简单任务：题材分类、标题优化、标签生成
  pro    → 复杂推理：深度分析、策略建议、多维度评估
"""
import os
import json
import requests

# 全局LLM调用间隔（秒），所有脚本统一，4个模型共用
CALL_INTERVAL = 30

# 模型映射
MODELS = {
    "flash": "DeepSeek-V4-Flash",
    "pro": "DeepSeek-V4-Pro",
    "glm": "GLM-5.1",
    "minimax": "MiniMax-M2.5",
}

# 任务→模型路由
TASK_MODEL = {
    # 简单任务用flash
    "genre_classify": "flash",
    "title_optimize": "pro",
    "tag_generate": "flash",
    "hook_suggest": "flash",
    # 复杂任务用pro
    "channel_strategy": "pro",
    "channel_analysis": "pro",
    "deep_analysis": "pro",
    "content_plan": "pro",
}

API_BASE = "https://api.edgefn.net/v1/chat/completions"


def get_api_key() -> str:
    # 1. hermes config (providers.edgefn.api_key) — 优先，规范来源
    try:
        import yaml
        cfg_path = os.path.expanduser("~/.hermes/config.yaml")
        if os.path.exists(cfg_path):
            with open(cfg_path) as f:
                cfg = yaml.safe_load(f)
            key = cfg.get("providers", {}).get("edgefn", {}).get("api_key", "")
            if key:
                return key
    except Exception:
        pass

    # 2. 环境变量（fallback）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if api_key:
        return api_key

    # 3. fallback: .env 文件
    env_path = os.path.expanduser("~/duanju/.env")
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                parts = line.strip().split("=", 1)
                if len(parts) == 2 and parts[0] == "DEEPSEEK_API_KEY" and parts[1]:
                    return parts[1]
    return ""


def call_edgefn(prompt: str, model: str = "flash", max_tokens: int = 4096,
                temperature: float = 0.1, json_mode: bool = False) -> dict:
    """调用edgefn API

    Args:
        prompt: 用户prompt
        model: "flash"/"pro"/"glm"/"minimax" 或完整模型名
        max_tokens: 最大输出tokens (pro推理模型需要4096+)
        temperature: 温度
        json_mode: 是否要求JSON输出

    Returns:
        {"content": str, "reasoning": str, "usage": dict, "error": str|None}
    """
    api_key = get_api_key()
    if not api_key:
        return {"content": "", "reasoning": "", "usage": {}, "error": "无API key，检查.env的DEEPSEEK_API_KEY"}

    model_name = MODELS.get(model, model)  # 支持传简称或完整名

    body = {
        "model": model_name,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}

    import time as _time
    for attempt in range(3):
        try:
            resp = requests.post(
                API_BASE,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=body,
                timeout=180,
            )
            if resp.status_code == 200:
                r = resp.json()
                msg = r["choices"][0]["message"]
                content = msg.get("content", "")
                # 检测空响应（可能是内容安全过滤）
                if not content and attempt < 2:
                    print(f"  ⚠️ 空响应（可能触发安全过滤），等待重试...")
                    _time.sleep(15 * (attempt + 1))
                    continue
                return {
                    "content": content,
                    "reasoning": msg.get("reasoning_content", ""),
                    "usage": r.get("usage", {}),
                    "error": None,
                }
            elif resp.status_code == 429 and attempt < 2:
                wait = 30 * (attempt + 1)
                print(f"  ⏳ 429限速，等待{wait}秒后重试...")
                _time.sleep(wait)
                continue
            elif resp.status_code == 400 and attempt < 2:
                # 内容安全过滤可能返回400
                err_text = resp.text[:200]
                if 'safety' in err_text.lower() or 'content' in err_text.lower() or 'flag' in err_text.lower():
                    print(f"  ⚠️ 内容安全拦截(400)，等待重试...")
                    _time.sleep(15 * (attempt + 1))
                    continue
                return {"content": "", "reasoning": "", "usage": {},
                        "error": f"HTTP {resp.status_code}: {err_text}"}
            else:
                return {"content": "", "reasoning": "", "usage": {},
                        "error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
        except Exception as e:
            if attempt < 2:
                _time.sleep(10)
                continue
            return {"content": "", "reasoning": "", "usage": {}, "error": str(e)}


def call_for_task(task: str, prompt: str, **kwargs) -> dict:
    """按任务类型自动选模型

    Args:
        task: 任务类型，见 TASK_MODEL
        prompt: 用户prompt
        **kwargs: 传给 call_edgefn 的其他参数
    """
    model = TASK_MODEL.get(task, "flash")
    return call_edgefn(prompt, model=model, **kwargs)


def parse_json_response(result: dict) -> dict:
    """从LLM响应中解析JSON"""
    text = result.get("content", "") or result.get("reasoning", "")
    if not text:
        return {"error": result.get("error", "空响应")}

    # 去掉markdown代码块
    if "```" in text:
        parts = text.split("```")
        text = parts[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        return {"error": f"JSON解析失败", "raw": text[:200]}
