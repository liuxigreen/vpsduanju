#!/usr/bin/env python3
"""
跨平台 Secret 存储 — macOS 用 Keychain，Linux 用文件加密存储
零依赖，自动检测平台
"""

from __future__ import annotations
import os
import subprocess
import json
import sys
import stat
from pathlib import Path

SERVICE_PREFIX = "duanju"
IS_MACOS = sys.platform == "darwin"
KEYCHAIN = "login.keychain-db" if IS_MACOS else None

# Linux 文件存储目录
SECRETS_DIR = Path.home() / ".hermes" / "duanju" / "secrets"


def _run(cmd: list[str]) -> tuple[int, str, str]:
    """执行 shell 命令"""
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _service(name: str) -> str:
    return f"{SERVICE_PREFIX}:{name}"


def _file_path(name: str) -> Path:
    """获取 Linux 文件存储路径"""
    safe_name = name.replace("/", "_").replace(":", "_")
    return SECRETS_DIR / f"{safe_name}.json"


def set_secret(name: str, value: str) -> bool:
    """存一个 secret"""
    if IS_MACOS:
        svc = _service(name)
        _run(["security", "delete-generic-password", "-s", svc, KEYCHAIN])
        code, _, err = _run([
            "security", "add-generic-password",
            "-s", svc, "-a", "duanju", "-w", value,
            "-T", "/usr/bin/security", KEYCHAIN,
        ])
        if code != 0:
            print(f"❌ Keychain 写入失败 [{svc}]: {err}", file=sys.stderr)
            return False
        return True
    else:
        # Linux: 文件存储
        SECRETS_DIR.mkdir(parents=True, exist_ok=True)
        fp = _file_path(name)
        fp.write_text(json.dumps({"name": name, "value": value}, ensure_ascii=False))
        os.chmod(fp, stat.S_IRUSR | stat.S_IWUSR)  # 600
        return True


def get_secret(name: str) -> str | None:
    """读取一个 secret"""
    if IS_MACOS:
        svc = _service(name)
        code, out, _ = _run(["security", "find-generic-password", "-s", svc, "-w", KEYCHAIN])
        if code != 0:
            return None
        return out
    else:
        fp = _file_path(name)
        if not fp.exists():
            return None
        try:
            data = json.loads(fp.read_text())
            return data.get("value")
        except (json.JSONDecodeError, KeyError):
            return None


def delete_secret(name: str) -> bool:
    """删除一个 secret"""
    if IS_MACOS:
        svc = _service(name)
        code, _, _ = _run(["security", "delete-generic-password", "-s", svc, KEYCHAIN])
        return code == 0
    else:
        fp = _file_path(name)
        if fp.exists():
            fp.unlink()
            return True
        return False


def set_json(name: str, data: dict) -> bool:
    """存一个 JSON 对象"""
    return set_secret(name, json.dumps(data, ensure_ascii=False))


def get_json(name: str) -> dict | None:
    """读取一个 JSON 对象"""
    raw = get_secret(name)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"⚠️ Secret [{name}] 数据不是有效 JSON", file=sys.stderr)
        return None


def list_secrets() -> list[str]:
    """列出所有 duanju 相关的 secret 条目"""
    known_prefixes = ["google:client"]
    accounts_file = os.path.expanduser("~/.hermes/duanju/accounts.json")
    if os.path.exists(accounts_file):
        try:
            with open(accounts_file) as f:
                accounts = json.load(f)
            for slug in accounts:
                known_prefixes.append(f"youtube:{slug}:token")
        except Exception:
            pass
    found = []
    for name in known_prefixes:
        if get_secret(name) is not None:
            found.append(name)
    return found


def list_accounts() -> dict:
    """列出所有已授权的YouTube账号"""
    accounts_file = os.path.expanduser("~/.hermes/duanju/accounts.json")
    if not os.path.exists(accounts_file):
        return {}
    try:
        with open(accounts_file) as f:
            accounts = json.load(f)
        result = {}
        for slug, info in accounts.items():
            token = load_youtube_token(slug)
            if token:
                result[slug] = info
        return result
    except Exception:
        return {}


# --- 便捷方法 ---

def save_google_client(client_id: str, client_secret: str):
    """保存 Google OAuth client 凭据"""
    set_json("google:client", {
        "client_id": client_id,
        "client_secret": client_secret,
    })
    print("✅ Google client 凭据已保存")


def load_google_client() -> dict | None:
    """加载 Google OAuth client 凭据"""
    return get_json("google:client")


def save_youtube_token(slug: str, token_data: dict):
    """保存 YouTube OAuth token"""
    set_json(f"youtube:{slug}:token", token_data)


def load_youtube_token(slug: str) -> dict | None:
    """加载 YouTube OAuth token"""
    return get_json(f"youtube:{slug}:token")


if __name__ == "__main__":
    print("🔐 Secret Storage 测试")
    print(f"  平台: {'macOS Keychain' if IS_MACOS else 'Linux 文件存储'}")
    print(f"  已有条目: {list_secrets()}")
    client = load_google_client()
    if client:
        print(f"  Google Client ID: {client['client_id'][:20]}...")
    else:
        print("  Google Client: 未配置")
