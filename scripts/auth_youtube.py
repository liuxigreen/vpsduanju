#!/usr/bin/env python3
"""
YouTube OAuth 多账号管理
- 安全存储：client_secret + token 全部存在 macOS Keychain
- 手动粘 code：不依赖 localhost 回调
- 支持几十个账号

用法：
  python3 auth_youtube.py init <client_id> <client_secret>   # 首次配置
  python3 auth_youtube.py auth <slug>                         # 授权一个账号
  python3 auth_youtube.py list                                # 列出所有账号
  python3 auth_youtube.py token <slug>                        # 查看 token 状态
  python3 auth_youtube.py revoke <slug>                       # 撤销授权
"""

from __future__ import annotations
import os
import sys
import json
import hashlib
import base64
import secrets
import urllib.parse
import urllib.request
import time
from datetime import datetime

# 同目录导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import keychain_helper as kc

# --- 常量 ---
SCOPES = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.force-ssl",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "https://duanju.opspilot.me/oauth/callback"

ACCOUNTS_FILE = os.path.expanduser("~/.hermes/duanju/accounts.json")

# --- 账号注册表 ---


def load_accounts() -> dict:
    if os.path.exists(ACCOUNTS_FILE):
        with open(ACCOUNTS_FILE) as f:
            return json.load(f)
    return {}


def save_accounts(accounts: dict):
    os.makedirs(os.path.dirname(ACCOUNTS_FILE), exist_ok=True)
    with open(ACCOUNTS_FILE, "w") as f:
        json.dump(accounts, f, ensure_ascii=False, indent=2)


def add_account(slug: str, google_email: str, channel_id: str = "",
                channel_title: str = "", market: str = ""):
    accounts = load_accounts()
    accounts[slug] = {
        "google_email": google_email,
        "channel_id": channel_id,
        "channel_title": channel_title,
        "market": market,
        "authorized_at": datetime.now().isoformat(),
    }
    save_accounts(accounts)
    print(f"✅ 账号 [{slug}] 已注册")


# --- PKCE ---


def _generate_pkce() -> tuple[str, str]:
    """生成 PKCE code_verifier 和 code_challenge"""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    return verifier, challenge


# --- OAuth 流程 ---


def cmd_init(client_id: str, client_secret: str):
    """首次配置：存 client 凭据到 Keychain"""
    kc.save_google_client(client_id, client_secret)
    print(f"  Client ID: {client_id[:30]}...")
    print("  后续 auth 命令会自动从 Keychain 读取")


def cmd_auth(slug: str):
    """授权一个账号：生成链接 → 用户粘 code → 换 token → 存 Keychain"""
    client = kc.load_google_client()
    if not client:
        print("❌ 未配置 Google client 凭据，先运行: python3 auth_youtube.py init <client_id> <client_secret>")
        sys.exit(1)

    client_id = client["client_id"]
    client_secret = client["client_secret"]

    # PKCE
    verifier, challenge = _generate_pkce()

    # 构建授权链接
    params = {
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"

    print(f"\n🔐 授权账号: {slug}")
    print(f"📋 在浏览器打开以下链接：\n")
    print(f"  {auth_url}\n")
    print("授权后浏览器会跳转到回调页面。")
    print("从地址栏复制 code= 后面的值粘贴到这里：")
    print("（如果页面打不开也没关系，code 在 URL 参数里）\n")

    code = input("\n> ").strip()
    if not code:
        print("❌ 未输入授权码")
        sys.exit(1)

    # 交换 token
    print("🔄 正在交换 token...")
    token_data = _exchange_code(client_id, client_secret, code, verifier)
    if "error" in token_data:
        print(f"❌ 交换失败: {token_data.get('error_description', token_data['error'])}")
        sys.exit(1)

    # 存入 Keychain
    kc.save_youtube_token(slug, token_data)
    print(f"✅ Token 已存入 Keychain [duanju:youtube:{slug}:token]")

    # 获取频道信息并更新注册表
    _update_account_info(slug, token_data)

    expires_in = token_data.get("expires_in", 0)
    has_refresh = "refresh_token" in token_data
    print(f"  Access Token 有效期: {expires_in}s")
    print(f"  Refresh Token: {'✅ 有' if has_refresh else '❌ 无'}")


def _exchange_code(client_id: str, client_secret: str,
                   code: str, code_verifier: str) -> dict:
    """用授权码交换 token"""
    data = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "grant_type": "authorization_code",
        "redirect_uri": REDIRECT_URI,
        "code_verifier": code_verifier,
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return json.loads(body)
        except:
            return {"error": "http_error", "error_description": body}


def _refresh_token(slug: str, token_data: dict) -> dict | None:
    """刷新 access token"""
    client = kc.load_google_client()
    if not client:
        return None

    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        print(f"❌ [{slug}] 没有 refresh_token，需要重新授权")
        return None

    data = urllib.parse.urlencode({
        "client_id": client["client_id"],
        "client_secret": client["client_secret"],
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }).encode()

    req = urllib.request.Request(TOKEN_URL, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            new_token = json.loads(resp.read().decode())
            # Google 刷新时不会返回新的 refresh_token，保留原来的
            if "refresh_token" not in new_token:
                new_token["refresh_token"] = refresh_token
            new_token["refreshed_at"] = datetime.now().isoformat()
            kc.save_youtube_token(slug, new_token)
            print(f"✅ [{slug}] Token 已刷新")
            return new_token
    except Exception as e:
        print(f"❌ [{slug}] 刷新失败: {e}")
        return None


def get_valid_token(slug: str) -> dict | None:
    """获取有效的 token，过期自动刷新"""
    token_data = kc.load_youtube_token(slug)
    if not token_data:
        print(f"❌ [{slug}] 未授权")
        return None

    # 检查是否过期
    expires_at = token_data.get("expires_at", 0)
    if time.time() > expires_at - 60:  # 提前 60s 刷新
        print(f"🔄 [{slug}] Token 过期，刷新中...")
        token_data = _refresh_token(slug, token_data)
        if not token_data:
            return None

    return token_data


def _update_account_info(slug: str, token_data: dict):
    """用 token 获取频道信息并更新注册表"""
    try:
        import urllib.request
        req = urllib.request.Request(
            "https://www.googleapis.com/youtube/v3/channels?part=snippet,statistics&mine=true"
        )
        req.add_header("Authorization", f"Bearer {token_data['access_token']}")
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode())

        items = result.get("items", [])
        if not items:
            print("⚠️ 该账号下没有 YouTube 频道")
            return

        ch = items[0]
        accounts = load_accounts()
        entry = accounts.get(slug, {})
        entry["channel_id"] = ch["id"]
        entry["channel_title"] = ch["snippet"]["title"]
        entry["google_email"] = entry.get("google_email", "")
        accounts[slug] = entry
        save_accounts(accounts)
        print(f"  频道: {ch['snippet']['title']} ({ch['id']})")
        if len(items) > 1:
            print(f"  ⚠️ 该账号下有 {len(items)} 个频道，已关联第一个")

    except Exception as e:
        print(f"⚠️ 获取频道信息失败: {e}")


def cmd_list():
    """列出所有账号"""
    accounts = load_accounts()
    if not accounts:
        print("📋 暂无注册账号")
        return

    print(f"\n📋 共 {len(accounts)} 个账号:\n")
    for slug, info in accounts.items():
        token = kc.load_youtube_token(slug)
        status = "✅ 已授权" if token else "❌ 未授权"
        if token and token.get("expires_at", 0) < time.time():
            status = "🔄 需刷新"
        print(f"  [{slug}]")
        print(f"    状态: {status}")
        print(f"    邮箱: {info.get('google_email', '-')}")
        print(f"    频道: {info.get('channel_title', '-')}")
        print(f"    ID:   {info.get('channel_id', '-')}")
        print(f"    市场: {info.get('market', '-')}")
        print()


def cmd_token(slug: str):
    """查看 token 状态"""
    token = kc.load_youtube_token(slug)
    if not token:
        print(f"❌ [{slug}] 无 token")
        return

    expires_at = token.get("expires_at", 0)
    has_refresh = "refresh_token" in token
    refreshed_at = token.get("refreshed_at", token.get("authorized_at", "未知"))

    print(f"\n🔑 [{slug}] Token 状态:")
    print(f"  过期时间: {datetime.fromtimestamp(expires_at).strftime('%Y-%m-%d %H:%M:%S') if expires_at else '未知'}")
    print(f"  已过期: {'是' if time.time() > expires_at else '否'}")
    print(f"  Refresh Token: {'有' if has_refresh else '无'}")
    print(f"  上次刷新: {refreshed_at}")
    print(f"  权限范围: {token.get('scope', '未知')}")


def cmd_revoke(slug: str):
    """撤销授权"""
    token = kc.load_youtube_token(slug)
    if not token:
        print(f"❌ [{slug}] 无 token")
        return

    # 尝试调用 Google revoke
    access_token = token.get("access_token")
    if access_token:
        try:
            data = f"token={access_token}".encode()
            req = urllib.request.Request(
                "https://oauth2.googleapis.com/revoke",
                data=data,
                method="POST",
            )
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            urllib.request.urlopen(req, timeout=10)
        except:
            pass  # 即使 revoke API 失败也继续清理本地

    kc.delete_secret(f"youtube:{slug}:token")
    print(f"✅ [{slug}] Token 已撤销并删除")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    action = sys.argv[1]

    if action == "init":
        if len(sys.argv) < 4:
            print("用法: python3 auth_youtube.py init <client_id> <client_secret>")
            sys.exit(1)
        cmd_init(sys.argv[2], sys.argv[3])

    elif action == "auth":
        if len(sys.argv) < 3:
            print("用法: python3 auth_youtube.py auth <slug>")
            print("  slug: 账号标识，如 hk, us, jp 等")
            sys.exit(1)
        slug = sys.argv[2]
        # 如果账号未注册，先让用户输入邮箱
        accounts = load_accounts()
        if slug not in accounts:
            email = input(f"Google 邮箱 (用于 {slug}): ").strip()
            market = input(f"市场 (如 HK/TW, US/Global): ").strip()
            add_account(slug, email, market=market)
        cmd_auth(slug)

    elif action == "list":
        cmd_list()

    elif action == "token":
        if len(sys.argv) < 3:
            print("用法: python3 auth_youtube.py token <slug>")
            sys.exit(1)
        cmd_token(sys.argv[2])

    elif action == "revoke":
        if len(sys.argv) < 3:
            print("用法: python3 auth_youtube.py revoke <slug>")
            sys.exit(1)
        cmd_revoke(sys.argv[2])

    else:
        print(f"❌ 未知操作: {action}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
