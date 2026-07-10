#!/usr/bin/env python3
"""
WeChat QR login via Tencent iLink Bot API.
Gets QR code URL, prints it, polls until user scans + confirms.
"""
import asyncio
import json
import sys
import time

sys.path.insert(0, '/home/ubuntu/.hermes/hermes-agent')

from gateway.platforms.weixin import (
    ILINK_BASE_URL,
    ILINK_APP_ID,
    ILINK_APP_CLIENT_VERSION,
    EP_GET_BOT_QR,
    EP_GET_QR_STATUS,
    QR_TIMEOUT_MS,
    _make_ssl_connector,
    save_weixin_account,
)

async def main():
    import aiohttp

    async with aiohttp.ClientSession(trust_env=True, connector=_make_ssl_connector()) as session:
        # Step 1: Get QR code
        url = f"{ILINK_BASE_URL}/{EP_GET_BOT_QR}?bot_type=3"
        headers = {
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
        }
        async with session.get(url, headers=headers) as resp:
            raw = await resp.text()
            data = json.loads(raw)

        qrcode_value = str(data.get("qrcode") or "")
        qrcode_url = str(data.get("qrcode_img_content") or "")

        if not qrcode_value:
            print("ERROR: Failed to get QR code from iLink API", flush=True)
            return

        qr_scan_data = qrcode_url if qrcode_url else qrcode_value

        # Write QR info to file immediately for reading
        with open("/tmp/weixin_qr_info.json", "w") as f:
            json.dump({"qrcode_url": qrcode_url, "qrcode_value": qrcode_value, "timestamp": time.time()}, f)

        print("=" * 60, flush=True)
        print("微信 Bot 登录", flush=True)
        print("=" * 60, flush=True)
        print("", flush=True)
        if qrcode_url:
            print(f"二维码链接: {qrcode_url}", flush=True)
        print("", flush=True)
        print("请用微信扫描上方二维码，然后在手机上确认登录。", flush=True)
        print("我会在后台持续等待（最长 8 分钟）...", flush=True)
        print("", flush=True)

        # Step 2: Poll for scan/confirm
        deadline = time.monotonic() + 480
        current_base_url = ILINK_BASE_URL
        refresh_count = 0

        while time.monotonic() < deadline:
            try:
                poll_url = f"{current_base_url}/{EP_GET_QR_STATUS}?qrcode={qrcode_value}"
                async with session.get(poll_url, headers=headers) as resp:
                    raw = await resp.text()
                    status_resp = json.loads(raw)
            except asyncio.TimeoutError:
                await asyncio.sleep(1)
                continue
            except Exception as exc:
                print(f"Poll error: {exc}", flush=True)
                await asyncio.sleep(1)
                continue

            status = str(status_resp.get("status") or "wait")
            if status == "wait":
                print(".", end="", flush=True)
            elif status == "scaned":
                print("\n已扫码！请在微信上点击确认...", flush=True)
            elif status == "scaned_but_redirect":
                redirect_host = str(status_resp.get("redirect_host") or "")
                if redirect_host:
                    current_base_url = f"https://{redirect_host}"
            elif status == "expired":
                refresh_count += 1
                if refresh_count > 3:
                    print("\n二维码多次过期，需要重新运行。", flush=True)
                    return
                print(f"\n二维码已过期，刷新中 ({refresh_count}/3)...", flush=True)
                async with session.get(url, headers=headers) as resp:
                    raw2 = await resp.text()
                    data = json.loads(raw2)
                qrcode_value = str(data.get("qrcode") or "")
                qrcode_url = str(data.get("qrcode_img_content") or "")
                qr_scan_data = qrcode_url if qrcode_url else qrcode_value
                if qrcode_url:
                    print(f"新二维码链接: {qrcode_url}", flush=True)
            elif status == "confirmed":
                account_id = str(status_resp.get("ilink_bot_id") or "")
                token = str(status_resp.get("bot_token") or "")
                base_url = str(status_resp.get("baseurl") or ILINK_BASE_URL)
                user_id = str(status_resp.get("ilink_user_id") or "")
                if not account_id or not token:
                    print("ERROR: 扫码成功但凭证不完整", flush=True)
                    return
                save_weixin_account(
                    "/home/ubuntu/.hermes",
                    account_id=account_id,
                    token=token,
                    base_url=base_url,
                    user_id=user_id,
                )
                print("\n" + "=" * 60, flush=True)
                print("微信 Bot 登录成功！", flush=True)
                print(f"  account_id: {account_id}", flush=True)
                print(f"  token: {token[:16]}...", flush=True)
                print(f"  base_url: {base_url}", flush=True)
                print("=" * 60, flush=True)
                print("", flush=True)
                print("账号已保存到 ~/.hermes/weixin/accounts/", flush=True)
                print("重启 Gateway 即可生效：", flush=True)
                print("  hermes gateway restart", flush=True)
                print("", flush=True)

                # Write result to a file so we can detect success
                with open("/tmp/weixin_login_result.json", "w") as f:
                    json.dump({"account_id": account_id, "token": token, "base_url": base_url, "user_id": user_id}, f)
                return
            await asyncio.sleep(1)

        print("\n登录超时（8分钟）。需要重新运行。", flush=True)

if __name__ == "__main__":
    asyncio.run(main())