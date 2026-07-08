#!/usr/bin/env python3
"""duanju Panel v2 — 极简控制台（看内容 + nvwa规则库）"""
from __future__ import annotations
import argparse, json, threading, logging, traceback
from datetime import datetime
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
PANEL_DIR = ROOT / "panel"
DISTILL_DIR = ROOT / "distill"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("panel")

JOB_LOCK = threading.Lock()

def _json(handler, data, status=200):
    try:
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        handler.send_response(status)
        handler.send_header("Content-Type", "application/json; charset=utf-8")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)
    except Exception as e:
        log.error(f"_json error: {e}")

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        log.info(f"{self.address_string()} - {format%args}")

    def do_GET(self):
        try:
            p = urlparse(self.path)
            if p.path == "/":
                return self._serve_html()
            if p.path.startswith("/static/"):
                return self._serve_static(p.path[len("/static/"):])
            if p.path == "/api/runs":
                return self._api_runs()
            if p.path == "/api/outputs":
                return self._api_outputs()
            if p.path == "/api/rules":
                return self._api_rules()
            self.send_error(404, "Not Found")
        except Exception as e:
            log.error(f"do_GET error: {e}\n{traceback.format_exc()}")
            self.send_error(500, str(e))

    def do_POST(self):
        try:
            p = urlparse(self.path)
            if p.path == "/api/run":
                return self._api_run_POST(p)
            self.send_error(404)
        except Exception as e:
            log.error(f"do_POST error: {e}")
            self.send_error(500, str(e))

    def _serve_html(self):
        fp = PANEL_DIR / "web" / "index_v2.html"
        self._serve_file(fp, "text/html; charset=utf-8")

    def _serve_static(self, rel_path):
        fp = PANEL_DIR / "web" / rel_path
        if fp.exists():
            mime = "text/css" if fp.suffix == ".css" else "application/javascript" if fp.suffix == ".js" else "image/png"
            self._serve_file(fp, mime)
        else:
            _json(self, {"error": "not_found"}, 404)

    def _serve_file(self, path: Path, mime):
        if not path.exists():
            _json(self, {"error": "not_found"}, 404); return
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _api_runs(self):
        runs = []
        try:
            for f in sorted((PANEL_DIR / "web_runs").glob("*.yaml"), key=lambda x: x.stat().st_mtime, reverse=True)[:30]:
                runs.append({"id": f.stem, "file": str(f.relative_to(ROOT)), "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
        except Exception as e:
            log.warning(f"list runs error: {e}")
        _json(self, {"runs": runs})

    def _api_outputs(self):
        qs = parse_qs(urlparse(self.path).query)
        kind = qs.get("kind", ["manifests"])[0]
        limit = int(qs.get("limit", [20])[0])
        items = []
        try:
            if kind == "manifests":
                base = DATA_DIR / "manifests"
                for f in sorted(base.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                    try:
                        m = json.loads(f.read_text())
                        items.append({"file": str(f.relative_to(ROOT)), "task": m.get("task_name",""), "channel": m.get("target_channel",""), "region": m.get("target_region",""), "files": m.get("files",[]), "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
                    except Exception as e: log.debug(f"manifest parse error {f}: {e}")
            elif kind == "titles":
                for f in sorted((OUTPUT_DIR / "titles").glob("*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                    items.append({"file": str(f.relative_to(ROOT)), "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
            elif kind == "covers":
                for f in sorted((OUTPUT_DIR / "covers").glob("*.jpg"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                    items.append({"file": str(f.relative_to(ROOT)), "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
            elif kind == "videos":
                for f in sorted((OUTPUT_DIR / "videos").glob("*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
                    items.append({"file": str(f.relative_to(ROOT)), "mtime": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
        except Exception as e:
            log.error(f"outputs error: {e}")
        _json(self, {kind: items})

    def _api_rules(self):
        qs = parse_qs(urlparse(self.path).query)
        expert = qs.get("expert", [""])[0]
        experts = []
        try:
            for edir in sorted((DISTILL_DIR / "outputs").iterdir()):
                if not edir.is_dir(): continue
                rfile = edir / "rules.json"
                if rfile.exists():
                    rdata = json.loads(rfile.read_text())
                    experts.append({"slug": edir.name, "name": rdata.get("expert", edir.name), "rules": len(rdata.get("rules",[]))})
        except Exception as e:
            log.error(f"rules list error: {e}")
        if not expert:
            return _json(self, {"experts": experts})
        edir = DISTILL_DIR / "outputs" / expert
        rfile = edir / "rules.json"
        if not rfile.exists():
            return _json(self, {"error": "expert_not_found"}, 404)
        try:
            rules_raw = json.loads(rfile.read_text()).get("rules", [])
            evidence_map = {}
            ef = edir / "evidence.json"
            if ef.exists():
                for ev in json.loads(ef.read_text()).get("evidence", []):
                    evidence_map[ev["id"]] = ev
            rules_out = []
            for r in rules_raw:
                ev = evidence_map.get(r.get("id",""), {})
                rules_out.append({"id": r.get("id"), "name": r.get("name"), "module": r.get("module"), "condition": r.get("condition"), "action": r.get("action"), "check": r.get("check"), "evidence_tier": ev.get("tier"), "sample_size": ev.get("sample_size"), "confidence": ev.get("confidence")})
            _json(self, {"expert": expert, "rules": rules_out})
        except Exception as e:
            log.error(f"rules detail error: {e}")
            _json(self, {"error": "parse_error"}, 500)

    def _api_run_POST(self, p):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body)
        except:
            return _json(self, {"error": "invalid_json"}, 400)
        task_name = payload.get("task_name", "").strip()
        channel = payload.get("target_channel", "hk_main")
        region = payload.get("target_region", "hk")
        files = payload.get("files", [])
        mode = payload.get("mode", "semi-auto")
        if not task_name or not files:
            return _json(self, {"error": "missing_task_or_files"}, 400)
        def worker(jid):
            try:
                from scripts.build_manifest import build_manifest
                from scripts.generate_title import run_from_manifest as title_run
                from scripts.generate_cover import run_from_manifest as cover_run
                from scripts.edit_video import run_from_manifest as edit_run
                from scripts.translate_subtitle import run_from_manifest as subtitle_run
                manifest = build_manifest(task_name, "fast_validation", channel, region, files)
                mpath = DATA_DIR / "manifests" / f"{task_name}_{region}.json"
                mpath.parent.mkdir(parents=True, exist_ok=True)
                mpath.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
                if mode in ("auto","semi-auto"):
                    title_run(str(mpath))
                    cover_run(str(mpath))
                    edit_run(str(mpath))
                    subtitle_run(str(mpath))
                log.info(f"job {jid} done")
            except Exception as e:
                log.error(f"job {jid} error: {e}")
        with JOB_LOCK:
            job_id = f"{task_name}_{region}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
            t = threading.Thread(target=worker, args=(job_id,), daemon=True)
            t.start()
        return _json(self, {"job_id": job_id, "status": "started"})

def serve(port: int = 8008, open_browser: bool = False):
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log.info(f"Panel v2 → http://127.0.0.1:{port}")
    if open_browser:
        import webbrowser; webbrowser.open(f"http://127.0.0.1:{port}")
    server.serve_forever()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8008)
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()
    serve(args.port, args.open)
