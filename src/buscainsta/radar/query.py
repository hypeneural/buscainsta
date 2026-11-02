"""Read models for the Radar manager UI. All filters use parameterized SQL."""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from . import store

LOCAL_ZONE = ZoneInfo("America/Sao_Paulo")
SORTS = {
    "recent": "p.posted_at DESC, p.id DESC",
    "oldest": "p.posted_at ASC, p.id ASC",
    "likes": "p.likes IS NULL, p.likes DESC, p.posted_at DESC, p.id DESC",
    "comments": "p.comments IS NULL, p.comments DESC, p.posted_at DESC, p.id DESC",
    "shares": "p.shares IS NULL, p.shares DESC, p.posted_at DESC, p.id DESC",
    "plays": "COALESCE(p.plays,p.views) IS NULL, COALESCE(p.plays,p.views) DESC, p.posted_at DESC, p.id DESC",
    "detected": "p.first_seen_at DESC, p.id DESC",
}
KINDS = {"image", "video", "carousel", "story"}
ASSETS = {"all", "local", "missing"}


def normalize_username(value: str) -> str:
    value = value.strip()
    if value.startswith("https://"):
        url = urlsplit(value)
        if url.hostname not in ("instagram.com", "www.instagram.com") or url.query or url.fragment:
            raise ValueError("Only an Instagram profile URL is accepted")
        path = url.path.strip("/").split("/")
        if len(path) != 1:
            raise ValueError("Use a profile URL, not a post")
        value = path[0]
    value = value.lstrip("@").lower()
    if not store.USERNAME.fullmatch(value) or value in ("p", "reel", "stories", "explore"):
        raise ValueError("Invalid profile username")
    return value


def add_profile(root, value: str, name: str = "") -> dict:
    username = normalize_username(value)
    store.add_competitor(root, username, name.strip()[:180])
    return {"username": username, "status": "saved"}


def add_many_profiles(root, values: list[str]) -> dict:
    if not isinstance(values, list) or not 1 <= len(values) <= 50:
        raise ValueError("Submit 1 to 50 usernames")
    normalized = list(dict.fromkeys(normalize_username(str(x)) for x in values))
    created = 0
    with store.db_connect(root) as db:
        for username in normalized:
            created += db.execute("""INSERT OR IGNORE INTO competitors(username) VALUES(?)""",
                                  (username,)).rowcount
    return {"saved": len(normalized), "created": created,
            "existing": len(normalized) - created, "usernames": normalized}


def set_profile(root, value: str, enabled: bool) -> dict:
    username = normalize_username(value)
    if type(enabled) is not bool:
        raise ValueError("enabled must be a boolean")
    with store.db_connect(root) as db:
        cur = db.execute("UPDATE competitors SET enabled=? WHERE username=?", (int(enabled), username))
        if cur.rowcount != 1:
            raise ValueError("Profile not found")
    return {"username": username, "enabled": enabled}


def profiles(root) -> list[dict]:
    with store.db_connect(root) as db:
        return [dict(x) for x in db.execute("""
          SELECT c.username,c.profile_name,c.enabled,c.followers,c.updated_at,
                 COUNT(p.id) AS post_count,
                 COALESCE(SUM(CASE WHEN EXISTS(SELECT 1 FROM post_assets a
                        WHERE a.post_id=p.id AND a.sha256 IS NOT NULL) THEN 1 ELSE 0 END),0)
                        AS archived_count,
                 MAX(p.posted_at) AS latest_post_at
          FROM competitors c LEFT JOIN posts p ON p.username=c.username
          GROUP BY c.username ORDER BY c.enabled DESC, c.username
        """)]


def utc_boundary(value: str, plus_days: int = 0) -> str:
    day = date.fromisoformat(value)
    local = datetime(day.year, day.month, day.day, tzinfo=LOCAL_ZONE) + timedelta(days=plus_days)
    return local.astimezone(timezone.utc).isoformat()


def search_posts(root, *, username: str = "", kind: str = "", search: str = "",
                 from_date: str = "", to_date: str = "", sort: str = "recent",
                 archived: str = "all", min_likes: int = 0,
                 has_comments: bool = False,
                 limit: int = 40, offset: int = 0) -> dict:
    if type(limit) is not int or not 1 <= limit <= 100 or type(offset) is not int or not 0 <= offset <= 100000:
        raise ValueError("Invalid pagination")
    if sort not in SORTS or (kind and kind not in KINDS) or archived not in ASSETS:
        raise ValueError("Invalid filter")
    if type(min_likes) is not int or not 0 <= min_likes <= 1000000000 or type(has_comments) is not bool:
        raise ValueError("Invalid engagement filter")
    if len(search) > 120:
        raise ValueError("Search too long")
    conditions = []
    params = []
    if username:
        username = normalize_username(username)
        conditions.append("p.username=?")
        params.append(username)
    if kind:
        conditions.append("p.kind=?")
        params.append(kind)
    if search.strip():
        conditions.append("p.caption LIKE ? ESCAPE '!'")
        safe = search.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        params.append("%" + safe + "%")
    if from_date:
        conditions.append("p.posted_at>=?")
        params.append(utc_boundary(from_date))
    if to_date:
        conditions.append("p.posted_at<?")
        params.append(utc_boundary(to_date, 1))
    if from_date and to_date and date.fromisoformat(from_date)>date.fromisoformat(to_date):
        raise ValueError("Invalid date interval")
    if min_likes > 0:
        conditions.append("p.likes>=?")
        params.append(min_likes)
    if has_comments:
        conditions.append("p.comments>0")
    if archived == "local":
        conditions.append("EXISTS (SELECT 1 FROM post_assets a WHERE a.post_id=p.id AND a.sha256 IS NOT NULL)")
    elif archived == "missing":
        conditions.append("NOT EXISTS (SELECT 1 FROM post_assets a WHERE a.post_id=p.id AND a.sha256 IS NOT NULL)")
    clause = " WHERE " + " AND ".join(conditions) if conditions else ""
    with store.db_connect(root) as db:
        total = db.execute("SELECT COUNT(*) FROM posts p" + clause, params).fetchone()[0]
        result = [dict(r) for r in db.execute(
            "SELECT p.* FROM posts p" + clause + " ORDER BY " + SORTS[sort] +
            " LIMIT ? OFFSET ?", (*params, limit, offset))]
        ids = [p["id"] for p in result]
        assets = {}
        if ids:
            placeholders = ",".join("?" for _ in ids)
            for item in db.execute(
                 "SELECT * FROM post_assets WHERE post_id IN (" + placeholders + ") ORDER BY post_id, position", ids):
                row = dict(item)
                row["local_url"] = "/api/blob/" + row["sha256"] if row["sha256"] else None
                # Remote URLs stay references, never auto-loaded by the browser.
                assets.setdefault(row["post_id"], []).append(row)
        comments_by_post = {}
        if ids:
            placeholders = ",".join("?" for _ in ids)
            for node in db.execute("""SELECT post_id,comment_id,username,comment_text,
                 created_at,likes,reply_count FROM comment_previews
                 WHERE post_id IN (""" + placeholders + """)
                 ORDER BY COALESCE(created_at,captured_at) DESC,comment_id DESC""", ids):
                group = comments_by_post.setdefault(node["post_id"], [])
                if len(group) < 10:
                    group.append(dict(node))
        for post in result:
            post["assets"] = assets.get(post["id"], [])
            post["comment_previews"] = comments_by_post.get(post["id"], [])
            post["locally_archived"] = any(a["sha256"] for a in post["assets"])
        return {"items": result, "total": total, "offset": offset,
                "limit": limit, "has_more": offset + len(result) < total}


def overview(root) -> dict:
    summary = store.stats(root)
    with store.db_connect(root) as db:
        summary["active_competitors"] = db.execute("SELECT COUNT(*) FROM competitors WHERE enabled=1").fetchone()[0]
        summary["archived_posts"] = db.execute("""SELECT COUNT(*) FROM posts p WHERE
            EXISTS (SELECT 1 FROM post_assets a WHERE a.post_id=p.id AND a.sha256 IS NOT NULL)""").fetchone()[0]
        summary["latest_post_at"] = db.execute("SELECT MAX(posted_at) FROM posts").fetchone()[0]
    return summary
