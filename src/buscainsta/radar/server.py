"""Local-only, read-only Radar web server."""
import argparse
import json
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
from . import store

HTML=Path(__file__).with_name("static")/"radar.html"

class Handler(BaseHTTPRequestHandler):
    def log_message(self,fmt,*args):
        pass
    def send_json(self,payload,status=200):
        data=json.dumps(payload,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header("Content-Type","application/json; charset=utf-8")
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Content-Security-Policy","default-src 'none'; frame-ancestors 'none'")
        self.send_header("Content-Length",str(len(data)))
        self.end_headers()
        self.wfile.write(data)
    def do_GET(self):
        if self.headers.get("Host","").split(":")[0] not in ("127.0.0.1","localhost"):
            return self.send_json({"error":"Local host only"},403)
        try:
            parsed=urlsplit(self.path)
            if parsed.path=="/":
                data=HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Cache-Control","no-store")
                self.send_header("Content-Security-Policy","default-src 'self'; img-src 'self' data:; media-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; frame-ancestors 'none'")
                self.send_header("Content-Length",str(len(data)))
                self.end_headers();self.wfile.write(data);return
            if parsed.path=="/radar.js":
                data=HTML.with_name("radar.js").read_bytes()
                self.send_response(200);self.send_header("Content-Type","text/javascript; charset=utf-8")
                self.send_header("Content-Length",str(len(data)));self.end_headers()
                self.wfile.write(data);return
            if parsed.path=="/api/competitors":
                return self.send_json(store.list_competitors(self.server.root))
            if parsed.path=="/api/stats":
                return self.send_json(store.stats(self.server.root))
            if parsed.path=="/api/posts":
                q=parse_qs(parsed.query)
                return self.send_json(store.list_posts(self.server.root,
                   q.get("username",[""])[0],q.get("kind",[""])[0],
                   int(q.get("limit",["40"])[0]),int(q.get("offset",["0"])[0])))
            if parsed.path.startswith("/api/blob/"):
                sha=parsed.path.removeprefix("/api/blob/")
                item=store.get_blob(self.server.root,sha)
                if not item: return self.send_json({"error":"Not found"},404)
                self.send_response(200)
                self.send_header("Content-Type",item["mime"])
                self.send_header("Content-Length",str(item["bytes"]))
                self.send_header("X-Content-Type-Options","nosniff")
                self.send_header("Cache-Control","private, max-age=3600")
                self.end_headers()
                with item["path"].open("rb") as media:
                    while part:=media.read(65536):
                        self.wfile.write(part)
                return
            return self.send_json({"error":"Not found"},404)
        except (ValueError,TypeError):
            return self.send_json({"error":"Invalid request"},400)
        except (OSError, BrokenPipeError):
            return self.send_json({"error":"Media unavailable"},404)
    def do_POST(self):
        return self.send_json({"error":"Read-only. Import via local CLI."},405)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path.home()/"BuscaInstaRadar")
    parser.add_argument("--port",type=int,default=8766)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error("Invalid port")
    store.initialize(args.root)
    with ThreadingHTTPServer(("127.0.0.1",args.port),Handler) as http:
        http.root=store.private_root(args.root)
        print(f"Radar: http://127.0.0.1:{args.port}/",flush=True)
        http.serve_forever()

if __name__=="__main__":main()
