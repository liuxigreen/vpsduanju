#!/usr/bin/env python3
"""简易订阅链接服务器"""
import base64, json
from http.server import HTTPServer, BaseHTTPRequestHandler

DOMAIN = "proxy.mulan.dpdns.org"

vmess_obj = {"v":"2","ps":"VMess-WS","add":DOMAIN,"port":"443","id":"ca7c184b-8f3d-435c-a5fc-c04e73ab1b67","aid":"0","scy":"auto","net":"ws","type":"none","host":DOMAIN,"path":"/oyukvws","tls":"tls","sni":DOMAIN,"alpn":"","fp":"chrome"}
vmess_link = "vmess://" + base64.b64encode(json.dumps(vmess_obj).encode()).decode()

NODES = [
    f"vless://7f31e965-b862-4da8-a4ce-024d4766abb5@{DOMAIN}:8443?security=reality&sni=vuejs-jp.org&fp=chrome&pbk=BfzObZgV0pxbIjYOftaeaKBR0XWQVcXMFN8Yo0im50g&sid=6ba85179e30d4fc2&type=tcp#Reality",
    f"vless://c96ff39b-0975-4b0d-b2b6-39149bd85d2f@{DOMAIN}:443?security=tls&sni={DOMAIN}&fp=chrome&flow=xtls-rprx-vision&type=tcp#Vision",
    f"vless://c96ff39b-0975-4b0d-b2b6-39149bd85d2f@{DOMAIN}:443?security=tls&sni={DOMAIN}&fp=chrome&type=ws&path=%2Foyukws#VLESS-WS",
    f"trojan://c81fd911c329e29d26178a37618852aa@{DOMAIN}:443?security=tls&sni={DOMAIN}&type=tcp&fp=chrome#Trojan",
    vmess_link,
]

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/sub", "/"):
            content = "\n".join(NODES).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Disposition", "attachment; filename=sub.txt")
            self.end_headers()
            self.wfile.write(base64.b64encode(content))
        else:
            self.send_response(404)
            self.end_headers()
    def log_message(self, fmt, *args):
        pass

HTTPServer(("0.0.0.0", 8880), Handler).serve_forever()
