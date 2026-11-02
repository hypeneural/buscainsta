"""Read-only media server with narrowly scoped, CSRF-protected local profile management."""
from __future__ import annotations

import argparse
import hmac
import json
import re
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import query, store
from .refresh import RefreshManager

STATIC = Path(__file__).with_name("static")
RANGE = re.compile(r"^bytes=(\d*)-(\d*)$")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        # Do not leak sensitive paths, query strings or imported captions.
        pass

    def _headers(self, status, mime, length, extras=None):
        self.send_response(status)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Cache-Control", "no-store")
        for k, v in (extras or {}).items():
            self.send_header(k, str(v))
        self.end_headers()

    def send_json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data),
            {"Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'"})
        self.wfile.write(data)

    def _site_allowed(self):
        return self.headers.get("Host", "") in {
            f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}"
        }

    def _static(self, path, mime):
        data = path.read_bytes()
        self._headers(200, mime, len(data), {
            "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; "
            "media-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'none'"
        })
        self.wfile.write(data)

    def _blob(self, sha):
        entry = store.get_blob(self.server.root, sha)
        if entry is None:
            return self.send_json({"error": "Arquivo não disponível"}, 404)
        size = entry["bytes"]
        start, end = 0, size - 1
        value = self.headers.get("Range", "")
        if value:
            m = RANGE.fullmatch(value)
            if not m or (not m.group(1) and not m.group(2)):
                return self._range_error(size)
            try:
                if not m.group(1):
                    suffix = int(m.group(2))
                    if suffix <= 0:
                        return self._range_error(size)
                    start = max(0, size - suffix)
                else:
                    start = int(m.group(1))
                    if m.group(2):
                        end = int(m.group(2))
                if start >= size or end < start:
                    return self._range_error(size)
                end = min(end, size - 1)
            except ValueError:
                return self._range_error(size)
        count = end - start + 1
        extra = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        if value:
            extra["Content-Range"] = f"bytes {start}-{end}/{size}"
        self._headers(206 if value else 200, entry["mime"], count, extra)
        with entry["path"].open("rb") as content:
            content.seek(start)
            remaining = count
            while remaining:
                part = content.read(min(65536, remaining))
                if not part:
                    break
                self.wfile.write(part)
                remaining -= len(part)

    def _range_error(self, size):
        self._headers(416, "text/plain; charset=utf-8", 0,
                      {"Content-Range": f"bytes */{size}"})

    def do_GET(self):
        if not self._site_allowed():
            return self.send_json({"error": "Acesso exclusivamente local"}, 403)
        try:
            parsed = urlsplit(self.path)
            if parsed.path == "/":
                return self._static(STATIC / "radar.html", "text/html; charset=utf-8")
            if parsed.path == "/radar.js":
                return self._static(STATIC / "radar.js", "application/javascript; charset=utf-8")
            if parsed.path == "/api/refresh-status":
                return self.send_json(self.server.refresh.status())
            if parsed.path == "/api/cache-health":
                return self.send_json(store.cache_report(self.server.root, verify_hashes=False))
            if parsed.path == "/api/config":
                self.server.refresh.request()
                return self.send_json({"csrf": self.server.csrf,
                                       "timezone": "America/Sao_Paulo",
                                       "mode": "offline_archive",
                                       "metadata_refresh": self.server.refresh.status()})
            if parsed.path == "/api/competitors":
                return self.send_json(query.profiles(self.server.root))
            if parsed.path == "/api/stats":
                self.server.refresh.request()
                return self.send_json(query.overview(self.server.root))
            if parsed.path == "/api/posts":
                params = parse_qs(parsed.query)
                def param(name, default=""):
                    return params.get(name, [default])[0]
                return self.send_json(query.search_posts(self.server.root,
                    username=param("username"), kind=param("kind"),
                    search=param("search"), from_date=param("from"),
                    to_date=param("to"), sort=param("sort", "recent"),
                    archived=param("archived", "all"),
                    min_likes=int(param("min_likes", "0")),
                    has_comments=param("has_comments", "false") == "true",
                    limit=int(param("limit", "40")), offset=int(param("offset", "0"))))
            if parsed.path.startswith("/api/blob/"):
                return self._blob(parsed.path.removeprefix("/api/blob/"))
            return self.send_json({"error": "Não encontrado"}, 404)
        except (ValueError, TypeError, OverflowError):
            return self.send_json({"error": "Filtro ou paginação inválidos"}, 400)
        except OSError:
            return self.send_json({"error": "Acervo local indisponível"}, 503)

    def do_POST(self):
        if not self._site_allowed():
            return self.send_json({"error": "Acesso exclusivamente local"}, 403)
        origin = self.headers.get("Origin", "")
        allowed = f"http://{self.headers.get('Host')}"
        if (origin != allowed or self.headers.get("Content-Type", "").split(";")[0] != "application/json"
                or not hmac.compare_digest(self.headers.get("X-Radar-CSRF", ""), self.server.csrf)):
            return self.send_json({"error": "Requisição não autorizada"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 4096:
                return self.send_json({"error": "Tamanho de requisição inválido"}, 413)
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("Invalid JSON body")
            if self.path == "/api/refresh":
                return self.send_json(self.server.refresh.request(force=True))
            if self.path == "/api/competitors":
                result = query.add_profile(self.server.root,
                                           str(data["username"]), str(data.get("name", "")))
            elif self.path == "/api/competitors/bulk":
                result = query.add_many_profiles(self.server.root, data["usernames"])
            elif self.path == "/api/competitors/status":
                result = query.set_profile(self.server.root, str(data["username"]), data["enabled"])
            else:
                return self.send_json({"error": "Rota inexistente"}, 404)
            return self.send_json(result, 200)
        except (ValueError, KeyError, TypeError, UnicodeError, json.JSONDecodeError):
            return self.send_json({"error": "Dados inválidos ou perfil inexistente"}, 400)
        except OSError:
            return self.send_json({"error": "Falha de armazenamento local"}, 503)


def create_server(root: Path, port: int = 8766, *, refresh_meta=False,
                  refresh_interval=1800, refresh_limit=20):
    store.initialize(root)
    http = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    http.root = store.private_root(root)
    http.csrf = secrets.token_urlsafe(32)
    http.refresh = RefreshManager(http.root, enabled=refresh_meta,
                                  interval=refresh_interval, limit=refresh_limit)
    http.daemon_threads = True
    return http


def main():
    parser = argparse.ArgumentParser(description="BuscaInsta Radar local dashboard")
    parser.add_argument("--root", type=Path, default=Path.home() / "BuscaInstaRadar")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--refresh-meta-on-access", action="store_true",
                        help="Explicitly allow background official Meta refresh while viewing")
    parser.add_argument("--refresh-interval", type=int, default=1800)
    parser.add_argument("--refresh-limit", type=int, default=20)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("Porta inválida")
    with create_server(args.root, args.port,
                       refresh_meta=args.refresh_meta_on_access,
                       refresh_interval=args.refresh_interval,
                       refresh_limit=args.refresh_limit) as http:
        print(f"Radar: http://127.0.0.1:{http.server_port}/", flush=True)
        http.serve_forever()


if __name__ == "__main__":
    main()
