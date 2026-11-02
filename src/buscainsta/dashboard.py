"""Loopback-only BuscaInsta review dashboard (Python stdlib).

A human may review a candidate, inspect their profile/follow relationship,
cache a tiny avatar privately, and individually send one fixed Direct message
after explicit manual verification and permission. Never bulk-sends.
"""
import argparse
import hashlib
import json
import secrets
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, unquote, urlsplit

from . import dashboard_store as store
from .instagram_actions import InstagramActions, PublicSafeError, fetch_avatar

DEFAULT_MESSAGE = (
    "Olá! Aqui é o Estúdio Evydência. "
    "Podemos conversar por aqui sobre as fotos de Natal? 🎄"
)


class Handler(BaseHTTPRequestHandler):
    server_version = "BuscaInstaLocal/0.3"

    def log_message(self, format, *args):
        # Never log URLs containing contact identifiers or payloads.
        return

    @property
    def context(self):
        return self.server.context

    def _headers(self, status: int, content_type: str, size: int):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; object-src 'none'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'"
        )
        self.end_headers()

    def _send(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._headers(status, "application/json; charset=utf-8", len(data))
        self.wfile.write(data)

    def _site_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").lower()
        port = str(self.server.server_port)
        return host in {f"127.0.0.1:{port}", f"localhost:{port}"}

    def _page(self):
        page = Path(__file__).resolve().parent / "static" / "dashboard.html"
        content = page.read_text(encoding="utf-8").replace(
            "__CSRF_TOKEN__", self.context.csrf
        ).encode("utf-8")
        self._headers(200, "text/html; charset=utf-8", len(content))
        self.wfile.write(content)

    def do_GET(self):
        if not self._site_allowed():
            return self._send({"error": "Local host only."}, 403)
        path = urlsplit(self.path)
        if path.path == "/":
            return self._page()
        if path.path == "/api/stats":
            return self._send(store.dashboard_stats(self.context.db))
        if path.path == "/api/config":
            return self._send({
                "account": self.context.account,
                "read_enabled": self.context.read_enabled,
                "direct_enabled": self.context.direct_enabled,
                "fixed_message": self.context.message,
            })
        if path.path == "/api/contacts":
            args = parse_qs(path.query)
            try:
                p = int(args.get("page", ["1"])[0])
                q = args.get("q", [""])[0]
                segment = args.get("segment", [""])[0]
                instagram_only = args.get("instagram", ["false"])[0] == "true"
                verified_only = args.get("verified", ["false"])[0] == "true"
                return self._send(store.list_contacts(
                    self.context.db, q, p, segment=segment,
                    instagram_only=instagram_only, verified_only=verified_only))
            except ValueError:
                return self._send({"error": "Invalid pagination."}, 400)
        if path.path == "/api/avatar":
            args = parse_qs(path.query)
            cid = args.get("cid", [""])[0]
            try:
                row = store.get_contact(self.context.db, cid)
                file = Path(row["photo_local"]).resolve()
                folder = (self.context.db.parent / "photos").resolve()
                if not row["photo_local"] or not file.is_relative_to(folder) or not file.is_file():
                    return self._send({"error": "No cached photo."}, 404)
                content = file.read_bytes()
                kind = {".jpg": "image/jpeg", ".png": "image/png",
                        ".webp": "image/webp"}.get(file.suffix)
                if not kind or len(content) > 750_000:
                    return self._send({"error": "Photo is unavailable."}, 404)
                self._headers(200, kind, len(content))
                return self.wfile.write(content)
            except (OSError, ValueError):
                return self._send({"error": "Photo unavailable."}, 404)
        return self._send({"error": "Not found."}, 404)

    def do_POST(self):
        if not self._site_allowed():
            return self._send({"error": "Local host only."}, 403)
        origin = self.headers.get("Origin")
        port = str(self.server.server_port)
        if origin and origin not in (f"http://localhost:{port}", f"http://127.0.0.1:{port}"):
            return self._send({"error": "Origin rejected."}, 403)
        if self.headers.get("X-CSRF-Token") != self.context.csrf:
            return self._send({"error": "Invalid dashboard session."}, 403)
        if not self.headers.get("Content-Type", "").startswith("application/json"):
            return self._send({"error": "JSON expected."}, 415)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 2 or length > 4096:
                return self._send({"error": "Invalid request length."}, 413)
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(data, dict):
                return self._send({"error": "Invalid JSON."}, 400)
        except (ValueError, UnicodeError):
            return self._send({"error": "Invalid JSON."}, 400)
        chunks = urlsplit(self.path).path.split("/")
        if len(chunks) != 5 or chunks[1:3] != ["api", "contacts"]:
            return self._send({"error": "Not found."}, 404)
        cid, action = unquote(chunks[3]), chunks[4]
        if not cid or len(cid) > 500:
            return self._send({"error": "Invalid contact."}, 400)
        try:
            if action == "candidate":
                if not isinstance(data.get("username"), str):
                    raise ValueError("Invalid username.")
                store.set_candidate(self.context.db, cid, data["username"])
            elif action == "verify":
                if type(data.get("value")) is not bool:
                    raise ValueError("Expected checkbox value.")
                store.set_verified(self.context.db, cid, data["value"])
            elif action == "direct-permission":
                if type(data.get("value")) is not bool:
                    raise ValueError("Expected checkbox value.")
                store.set_dm_permission(self.context.db, cid, data["value"])
            elif action == "inspect":
                if not self.context.read_enabled:
                    raise ValueError("Start the panel with --enable-instagram to query profiles.")
                row = store.get_contact(self.context.db, cid)
                if not row["candidate_username"]:
                    raise ValueError("Enter @username before inspecting.")
                result = self.context.provider.inspect(row["candidate_username"])
                cached = ""
                if result["photo_url"]:
                    try:
                        cached = fetch_avatar(
                            result["photo_url"], self.context.db.parent / "photos",
                            cid + "-" + result["pk"]
                        )
                    except PublicSafeError:
                        pass  # Photo failure must not hide the profile or relationship.
                store.save_profile(self.context.db, cid, self.context.account,
                                   result, cached)
            elif action == "send-direct":
                if not self.context.direct_enabled:
                    raise ValueError("Direct disabled; launch with --enable-dm and fixed message file.")
                if data.get("confirm") is not True:
                    raise ValueError("Explicit send confirmation required.")
                import os
                if not (os.environ.get("BUSCAINSTA_IG_TEST_LOGIN")
                        and os.environ.get("BUSCAINSTA_IG_TEST_PASSWORD")):
                    raise ValueError("Instagram test account credentials missing.")
                attempt_id = uuid.uuid4().hex
                sha = hashlib.sha256(self.context.message.encode("utf-8")).hexdigest()
                contact = store.reserve_dm(self.context.db, cid, self.context.account,
                                           sha, attempt_id)
                try:
                    message_id = self.context.provider.direct_once(
                        contact["instagram_pk"], self.context.message
                    )
                except Exception:
                    store.finish_dm(self.context.db, cid, attempt_id, False)
                    return self._send({
                        "error": "Direct outcome unknown. Check Instagram inbox; do not retry automatically.",
                        "status": "unknown",
                    }, 409)
                store.finish_dm(self.context.db, cid, attempt_id, True, message_id)
            else:
                return self._send({"error": "Unknown action."}, 404)
            return self._send({"ok": True, "contact": store.get_contact(self.context.db, cid)})
        except (ValueError, PublicSafeError) as exc:
            return self._send({"error": str(exc)}, 409)
        except Exception:
            # Never echo raw provider errors, local filesystem, tokens or personal data.
            return self._send({"error": "Operation failed. Check local diagnostics."}, 500)


def main():
    parser = argparse.ArgumentParser(description="BuscaInsta local browser dashboard")
    parser.add_argument("--db", required=True, type=Path, help="Private SQLite file outside Git")
    parser.add_argument("--contacts", type=Path, help="Import BuscaInsta contacts CSV once or update")
    parser.add_argument("--review", type=Path, help="Import matching results from live_sync review CSV")
    parser.add_argument("--legacy-panel", type=Path, help="Read-only import of existing painel_conferencia.html")
    parser.add_argument("--account", default="conta_teste", help="Instagram account label shown in table")
    parser.add_argument("--port", default=8765, type=int)
    parser.add_argument("--enable-instagram", action="store_true", help="Allow individual read-only Instagram lookups")
    parser.add_argument("--enable-dm", action="store_true", help="Allow explicitly authorized single Direct messages")
    parser.add_argument("--message-file", type=Path, help="Private text file defining the one fixed Direct message")
    args = parser.parse_args()

    if args.enable_dm and not args.enable_instagram:
        parser.error("--enable-dm requires --enable-instagram")
    if args.enable_dm and not args.message_file:
        parser.error("--enable-dm requires --message-file")
    if args.port < 1024 or args.port > 65535:
        parser.error("Choose a local TCP port between 1024 and 65535.")
    try:
        db = store.check_private_path(args.db)
        store.setup(db)
        if args.contacts:
            print("Contacts loaded:", store.import_contacts(db, args.contacts))
        if args.review:
            print("Review entries loaded:", store.import_review(db, args.review))
        if args.legacy_panel:
            import sqlite3
            from .legacy_import import import_legacy
            # Create an online, consistent one-time backup before migration.
            if db.exists():
                backup = db.with_name(db.name + ".before-legacy.backup")
                if not backup.exists():
                    with sqlite3.connect(str(db)) as src, sqlite3.connect(str(backup)) as dst:
                        src.backup(dst)
            print("Legacy panel migrated:", json.dumps(import_legacy(db, args.legacy_panel), sort_keys=True))
        message = DEFAULT_MESSAGE
        if args.message_file:
            store.check_private_path(args.message_file)
            message = args.message_file.read_text(encoding="utf-8").strip()
            if not message or len(message) > 1000:
                parser.error("Fixed message file must have 1–1000 characters.")
        context = SimpleNamespace(
            db=db, account=args.account.strip()[:100],
            read_enabled=args.enable_instagram, direct_enabled=args.enable_dm,
            message=message, csrf=secrets.token_urlsafe(24),
            provider=InstagramActions(args.account),
        )
        with ThreadingHTTPServer(("127.0.0.1", args.port), Handler) as server:
            server.context = context
            print(f"Painel BuscaInsta: http://127.0.0.1:{server.server_port}/")
            print("Local-only. Direct:", "enabled" if args.enable_dm else "disabled")
            server.serve_forever()
    except (ValueError, OSError) as exc:
        parser.exit(2, "ERROR: Check private local paths, CSV files or TCP port.\n")


if __name__ == "__main__":
    main()
