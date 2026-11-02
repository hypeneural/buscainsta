"""Opt-in background refresh of authorized official Meta public metadata.

Read-only HTTP requests return cached data immediately. No scraping, private
Instagram authentication, media downloads, or bypassing platform restrictions.
"""
from __future__ import annotations

import os
import threading
import time

from . import query
from .meta_business import sync_profile


class RefreshManager:
    def __init__(self, root, *, enabled=False, interval=1800, limit=20, sync=None,
                 clock=None):
        self.root = root
        self.enabled = bool(enabled)
        self.interval = max(900, int(interval))
        self.limit = min(30, max(1, int(limit)))
        self._sync = sync or sync_profile
        self._clock = clock or time.monotonic
        self._lock = threading.Lock()
        self._attempted = float("-inf")
        self._running = False
        self._last_result = "never"
        self._last_error = ""
        self._last_completed_at = ""
        self._processed = 0

    def status(self):
        with self._lock:
            return {"enabled": self.enabled, "running": self._running,
                    "status": self._last_result, "error_type": self._last_error,
                    "last_completed_at": self._last_completed_at,
                    "posts_processed": self._processed,
                    "interval_seconds": self.interval}

    def request(self, *, force=False):
        if not self.enabled:
            return self.status()
        with self._lock:
            clock = self._clock()
            # A force request still respects a minimum cooldown.
            cooldown = 300 if force else self.interval
            if self._running or (clock - self._attempted < cooldown):
                return {"enabled": True, "started": False, "reason": "busy_or_cooldown",
                        "running": self._running}
            token = os.getenv("RADAR_META_TOKEN", "")
            identity = os.getenv("RADAR_META_IG_USER_ID", "")
            if not token or not identity:
                self._last_result = "configuration_missing"
                return {"enabled": True, "started": False,
                        "reason": "credentials_not_configured", "running": False}
            version = os.getenv("RADAR_META_VERSION", "v25.0")
            self._attempted = clock
            self._running = True
            self._last_result = "running"
            self._last_error = ""
            worker = threading.Thread(
                target=self._run,
                args=(identity, token, version),
                name="radar-meta-refresh", daemon=True)
            worker.start()
            return {"enabled": True, "started": True, "running": True}

    def _run(self, identity, token, version):
        from .store import now
        errors = []
        count = 0
        try:
            profiles = [p["username"] for p in query.profiles(self.root) if p["enabled"]][:50]
            for username in profiles:
                try:
                    result = self._sync(self.root, username, identity, token,
                                        version=version, limit=self.limit)
                    count += result.get("posts_processed", 0)
                except Exception as exc:
                    # No secrets, URLs, captions or raw server responses in status.
                    errors.append(type(exc).__name__)
            status = "completed" if not errors else ("partial" if count else "failed")
        except Exception as exc:
            errors.append(type(exc).__name__)
            status = "failed"
        with self._lock:
            self._running = False
            self._last_completed_at = now()
            self._last_result = status
            self._last_error = ",".join(sorted(set(errors)))[:120]
            self._processed = count
