"""SQLite archive for Radar. Files are content-addressed and never fetched implicitly."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import sqlite3
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

USERNAME = re.compile(r"^[a-zA-Z0-9._]{1,30}$")
SHA256 = re.compile(r"^[a-f0-9]{64}$")
MAX_ASSET_BYTES = 200 * 1024 * 1024

def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def private_root(root: Path) -> Path:
    path = root.expanduser().resolve()
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise ValueError("Radar archive must live outside Git repositories")
    return path

@contextmanager
def db_connect(root: Path):
    root = private_root(root)
    root.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(root / "radar.db", timeout=20)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=20000")
    try:
        yield con
        con.commit()
    except BaseException:
        con.rollback()
        raise
    finally:
        con.close()

def initialize(root: Path) -> None:
    with db_connect(root) as con:
        con.execute("PRAGMA journal_mode=WAL")
        con.executescript("""
        CREATE TABLE IF NOT EXISTS competitors(
          username TEXT PRIMARY KEY, enabled INTEGER NOT NULL DEFAULT 1,
          profile_name TEXT NOT NULL DEFAULT '', followers INTEGER,
          updated_at TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS posts(
          id INTEGER PRIMARY KEY,
          canonical_key TEXT NOT NULL UNIQUE,
          source TEXT NOT NULL,
          external_id TEXT NOT NULL,
          username TEXT NOT NULL REFERENCES competitors(username),
          kind TEXT NOT NULL CHECK(kind IN ('image','video','carousel','story')),
          caption TEXT NOT NULL DEFAULT '',
          permalink TEXT NOT NULL DEFAULT '',
          posted_at TEXT NOT NULL,
          first_seen_at TEXT NOT NULL,
          last_seen_at TEXT NOT NULL,
          expires_at TEXT,
          likes INTEGER, comments INTEGER, views INTEGER,
          cover_url TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS posts_time ON posts(posted_at DESC,id DESC);
        CREATE INDEX IF NOT EXISTS posts_profile_time ON posts(username,posted_at DESC);
        CREATE TABLE IF NOT EXISTS post_identities(
          source TEXT NOT NULL, external_id TEXT NOT NULL,
          post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
          PRIMARY KEY(source,external_id)
        );
        CREATE INDEX IF NOT EXISTS post_identity_post ON post_identities(post_id);
        CREATE TABLE IF NOT EXISTS blobs(
          sha256 TEXT PRIMARY KEY, relative_path TEXT NOT NULL UNIQUE,
          mime TEXT NOT NULL, bytes INTEGER NOT NULL, stored_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS post_assets(
          post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
          position INTEGER NOT NULL CHECK(position >= 0),
          kind TEXT NOT NULL CHECK(kind IN ('image','video')),
          sha256 TEXT REFERENCES blobs(sha256),
          remote_url TEXT NOT NULL DEFAULT '',
          poster_url TEXT NOT NULL DEFAULT '',
          PRIMARY KEY(post_id,position)
        );
        CREATE TABLE IF NOT EXISTS metric_snapshots(
          id INTEGER PRIMARY KEY,
          post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
          checked_at TEXT NOT NULL,
          likes INTEGER, comments INTEGER, views INTEGER
        );
        CREATE INDEX IF NOT EXISTS metric_post_time ON metric_snapshots(post_id,checked_at DESC);
        CREATE TABLE IF NOT EXISTS comment_previews(
          post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
          comment_id TEXT NOT NULL,
          username TEXT NOT NULL DEFAULT '',
          comment_text TEXT NOT NULL DEFAULT '',
          created_at TEXT,
          likes INTEGER,
          reply_count INTEGER,
          captured_at TEXT NOT NULL,
          PRIMARY KEY(post_id,comment_id)
        );
        CREATE INDEX IF NOT EXISTS comment_previews_post ON comment_previews(post_id,created_at DESC);
        CREATE TABLE IF NOT EXISTS collection_runs(
          id INTEGER PRIMARY KEY, provider TEXT NOT NULL,
          started_at TEXT NOT NULL, finished_at TEXT NOT NULL,
          status TEXT NOT NULL, imported INTEGER NOT NULL DEFAULT 0,
          error_type TEXT NOT NULL DEFAULT ''
        );
        """)
        con.execute("""INSERT OR IGNORE INTO post_identities(source,external_id,post_id)
            SELECT source,external_id,id FROM posts""")
        # Additive schema migration for archives created by the previous Radar release.
        for table, columns in {
            "posts": {"shares": "INTEGER", "saves": "INTEGER", "plays": "INTEGER",
                      "video_duration": "REAL", "media_product_type": "TEXT NOT NULL DEFAULT ''",
                      "metadata_checked_at": "TEXT NOT NULL DEFAULT ''",
                      "source_note": "TEXT NOT NULL DEFAULT ''"},
            "metric_snapshots": {"shares": "INTEGER", "saves": "INTEGER", "plays": "INTEGER"},
        }.items():
            existing = {row["name"] for row in con.execute("PRAGMA table_info(" + table + ")")}
            for name, definition in columns.items():
                if name not in existing:
                    con.execute("ALTER TABLE " + table + " ADD COLUMN " + name + " " + definition)
        con.execute("CREATE INDEX IF NOT EXISTS posts_metadata_checked ON posts(metadata_checked_at)")


def add_competitor(root: Path, username: str, name: str = "") -> None:
    username = username.lstrip("@").lower()
    if not USERNAME.fullmatch(username):
        raise ValueError("Invalid Instagram username")
    with db_connect(root) as con:
        con.execute("""INSERT INTO competitors(username,profile_name) VALUES(?,?)
            ON CONFLICT(username) DO UPDATE SET profile_name=
            CASE WHEN excluded.profile_name<>'' THEN excluded.profile_name ELSE competitors.profile_name END""",
            (username, name[:180]))

def list_competitors(root: Path) -> list[dict]:
    with db_connect(root) as con:
        return [dict(x) for x in con.execute("SELECT * FROM competitors ORDER BY username")]

def canonical_key(source: str, external_id: str, permalink: str) -> str:
    # A permalink with an Instagram shortcode joins duplicate feed/reel imports.
    match = re.search(r"instagram\.com/(?:p|reel|tv)/([a-zA-Z0-9_-]+)", permalink)
    return "ig:" + match.group(1) if match else source + ":" + external_id

def upsert_post(root: Path, record: dict) -> int:
    source = str(record["source"]).strip().lower()
    external_id = str(record["external_id"]).strip()
    username = str(record["username"]).lstrip("@").lower()
    kind = record["kind"]
    if kind not in ("image","video","carousel","story") or not source or not external_id:
        raise ValueError("Invalid post identifier or type")
    if not USERNAME.fullmatch(username) or len(source)>40 or len(external_id)>160:
        raise ValueError("Invalid post source or username")
    posted_at = str(record["posted_at"])
    timestamp = datetime.fromisoformat(posted_at.replace("Z","+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("posted_at must be timezone-aware")
    posted_at = timestamp.astimezone(timezone.utc).isoformat()
    permalink = str(record.get("permalink") or "")
    if permalink and not re.fullmatch(r"https://(www\.)?instagram\.com/[^\s]{1,350}",permalink):
        raise ValueError("Invalid Instagram permalink")
    metrics = {}
    for k in ("likes","comments","views","shares","saves","plays"):
        val = record.get(k)
        if val in (-1, None):
            val = None  # Instagram can report -1 when a count is hidden.
        if val is not None and (type(val) is not int or val < 0):
            raise ValueError("Invalid metric " + k)
        metrics[k] = val
    duration = record.get("video_duration")
    if duration is not None and (type(duration) not in (float,int) or not 0 <= duration <= 86400):
        raise ValueError("Invalid video duration")
    product_type = str(record.get("media_product_type") or "")[:40]
    previews = record.get("comment_previews")
    if previews is not None and (not isinstance(previews,list) or len(previews)>20):
        raise ValueError("Invalid comment previews")

    key = canonical_key(source,external_id,permalink)
    stamp = now()
    add_competitor(root,username)
    with db_connect(root) as con:
        previously = con.execute("""SELECT p.canonical_key FROM post_identities i
                JOIN posts p ON p.id=i.post_id
                WHERE i.source=? AND i.external_id=?""", (source, external_id)).fetchone()
        if previously:
            key = previously["canonical_key"]
        con.execute("""INSERT INTO posts(canonical_key,source,external_id,username,kind,caption,
              permalink,posted_at,first_seen_at,last_seen_at,expires_at,likes,comments,views,cover_url)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(canonical_key) DO UPDATE SET
              last_seen_at=excluded.last_seen_at,
              caption=CASE WHEN excluded.caption<>'' THEN excluded.caption ELSE posts.caption END,
              permalink=CASE WHEN excluded.permalink<>'' THEN excluded.permalink ELSE posts.permalink END,
              cover_url=CASE WHEN excluded.cover_url<>'' THEN excluded.cover_url ELSE posts.cover_url END,
              expires_at=COALESCE(excluded.expires_at,posts.expires_at),
              likes=COALESCE(excluded.likes,posts.likes),
              comments=COALESCE(excluded.comments,posts.comments),
              views=COALESCE(excluded.views,posts.views)""",
            (key,source,external_id,username,kind,str(record.get("caption") or "")[:12000],
             permalink,posted_at,stamp,stamp,record.get("expires_at"),
             metrics["likes"],metrics["comments"],metrics["views"],
             str(record.get("cover_url") or "")[:1600]))
        post_id = con.execute("SELECT id FROM posts WHERE canonical_key=?",(key,)).fetchone()["id"]
        con.execute("""INSERT OR IGNORE INTO post_identities(source,external_id,post_id)
                    VALUES(?,?,?)""", (source,external_id,post_id))
        con.execute("""UPDATE posts SET
            likes=COALESCE(?,likes),comments=COALESCE(?,comments),
            views=COALESCE(?,views),shares=COALESCE(?,shares),
            saves=COALESCE(?,saves),plays=COALESCE(?,plays),
            video_duration=COALESCE(?,video_duration),
            media_product_type=CASE WHEN ?<>'' THEN ? ELSE media_product_type END,
            metadata_checked_at=?, source_note=CASE WHEN ?<>'' THEN ? ELSE source_note END
            WHERE id=?""",
            (metrics["likes"],metrics["comments"],metrics["views"],metrics["shares"],
             metrics["saves"],metrics["plays"],duration,product_type,product_type,
             stamp,str(record.get("source_note") or "")[:200],
             str(record.get("source_note") or "")[:200],post_id))
        current = con.execute("""SELECT likes,comments,views,shares,saves,plays
                FROM posts WHERE id=?""", (post_id,)).fetchone()
        last = con.execute("""SELECT likes,comments,views,shares,saves,plays
                FROM metric_snapshots WHERE post_id=? ORDER BY id DESC LIMIT 1""",
                (post_id,)).fetchone()
        values = tuple(current)
        if any(v is not None for v in values) and (last is None or tuple(last)!=values):
            con.execute("""INSERT INTO metric_snapshots(
                post_id,checked_at,likes,comments,views,shares,saves,plays)
                VALUES(?,?,?,?,?,?,?,?)""",(post_id,stamp,*values))
        if previews is not None:
            for item in previews:
                if not isinstance(item,dict):
                    raise ValueError("Invalid comment preview item")
                cid = str(item.get("id") or "").strip()
                if not cid or len(cid)>120:
                    raise ValueError("Invalid comment id")
                author = str(item.get("username") or "")[:40]
                content = str(item.get("text") or "")[:3000]
                likes = item.get("likes")
                replies = item.get("reply_count")
                if any(val is not None and (type(val) is not int or val<0)
                       for val in (likes,replies)):
                    raise ValueError("Invalid comment metrics")
                con.execute("""INSERT INTO comment_previews(
                        post_id,comment_id,username,comment_text,created_at,
                        likes,reply_count,captured_at) VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(post_id,comment_id) DO UPDATE SET
                        comment_text=excluded.comment_text,
                        likes=COALESCE(excluded.likes,comment_previews.likes),
                        reply_count=COALESCE(excluded.reply_count,comment_previews.reply_count),
                        captured_at=excluded.captured_at""",
                    (post_id,cid,author,content,item.get("created_at"),
                     likes,replies,stamp))
        return post_id

def sniff(path: Path) -> tuple[str,str]:
    with path.open("rb") as f:
        header = f.read(32)
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg",".jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png",".png"
    if header.startswith(b"RIFF") and header[8:12]==b"WEBP":
        return "image/webp",".webp"
    if len(header)>=12 and header[4:8]==b"ftyp":
        return "video/mp4",".mp4"
    raise ValueError("Unsupported file signature: JPEG, PNG, WebP, MP4 only")

def archive_file(root: Path, original: Path) -> str:
    root = private_root(root)
    original = original.resolve(strict=True)
    if not original.is_file() or original.stat().st_size > MAX_ASSET_BYTES:
        raise ValueError("Missing or oversized media")
    mime, ext = sniff(original)
    digest = hashlib.sha256()
    size = 0
    with original.open("rb") as f:
        for chunk in iter(lambda:f.read(1024*1024),b""):
            size += len(chunk)
            if size > MAX_ASSET_BYTES:
                raise ValueError("Media over size limit")
            digest.update(chunk)
    sha = digest.hexdigest()
    rel = Path("blobs") / sha[:2] / (sha+ext)
    target = root / rel
    target.parent.mkdir(parents=True,exist_ok=True)
    if not target.exists():
        fd,tmp = tempfile.mkstemp(prefix=".radar-",dir=target.parent)
        try:
            with os.fdopen(fd,"wb") as out,original.open("rb") as source:
                shutil.copyfileobj(source,out,1024*1024)
                out.flush()
                os.fsync(out.fileno())
            verification = hashlib.sha256()
            with open(tmp,"rb") as check:
                for block in iter(lambda:check.read(1024*1024),b""):
                    verification.update(block)
            if verification.hexdigest()!=sha:
                raise OSError("Media changed during archive")
            os.replace(tmp,target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
    with db_connect(root) as con:
        con.execute("""INSERT OR IGNORE INTO blobs(sha256,relative_path,mime,bytes,stored_at)
            VALUES(?,?,?,?,?)""",(sha,str(rel).replace("\\","/"),mime,size,now()))
    return sha

def put_asset(root: Path, post_id:int, position:int, kind:str,
              local_file:Path|None=None, remote_url:str="",poster_url:str="") -> str|None:
    if type(position) is not int or position<0 or position>100 or kind not in ("image","video"):
        raise ValueError("Invalid carousel asset")
    sha = archive_file(root,local_file) if local_file is not None else None
    if remote_url and (not remote_url.startswith("https://") or len(remote_url)>2000):
        raise ValueError("Remote URL must be HTTPS")
    with db_connect(root) as con:
        con.execute("""INSERT INTO post_assets(post_id,position,kind,sha256,remote_url,poster_url)
              VALUES(?,?,?,?,?,?)
              ON CONFLICT(post_id,position) DO UPDATE SET
                kind=excluded.kind,
                sha256=COALESCE(excluded.sha256,post_assets.sha256),
                remote_url=CASE WHEN excluded.remote_url<>'' THEN excluded.remote_url ELSE post_assets.remote_url END,
                poster_url=CASE WHEN excluded.poster_url<>'' THEN excluded.poster_url ELSE post_assets.poster_url END""",
              (post_id,position,kind,sha,remote_url,poster_url))
    return sha

def get_blob(root: Path, sha: str):
    if not SHA256.fullmatch(sha):
        return None
    with db_connect(root) as con:
        row=con.execute("SELECT * FROM blobs WHERE sha256=?",(sha,)).fetchone()
    if row is None:
        return None
    path=(private_root(root)/row["relative_path"]).resolve()
    if not path.is_relative_to(private_root(root)/"blobs") or not path.is_file():
        return None
    if path.stat().st_size != row["bytes"]:
        return None
    return {"path":path,"mime":row["mime"],"bytes":row["bytes"]}

def list_posts(root:Path, username:str="",kind:str="",limit:int=40,offset:int=0)->list[dict]:
    if not (1<=limit<=100 and 0<=offset<=1000000):
        raise ValueError("Invalid pagination")
    if kind and kind not in ("image","video","carousel","story"):
        raise ValueError("Invalid media filter")
    where=[]; params=[]
    if username:
        if not USERNAME.fullmatch(username):
            raise ValueError("Invalid username")
        where.append("username=?");params.append(username.lower())
    if kind:
        where.append("kind=?");params.append(kind)
    clause=" WHERE "+" AND ".join(where) if where else ""
    with db_connect(root) as con:
        rows=[dict(x) for x in con.execute("SELECT * FROM posts"+clause+" ORDER BY posted_at DESC,id DESC LIMIT ? OFFSET ?",(*params,limit,offset))]
        for post in rows:
            assets=[dict(x) for x in con.execute("SELECT * FROM post_assets WHERE post_id=? ORDER BY position",(post["id"],))]
            for asset in assets:
                asset["local_url"]="/api/blob/"+asset["sha256"] if asset["sha256"] else None
            post["assets"]=assets
        return rows

def stats(root:Path)->dict:
    with db_connect(root) as con:
        values = {}
        for tab in ("competitors","posts","post_assets","blobs","metric_snapshots"):
            values[tab]=con.execute("SELECT COUNT(*) FROM "+tab).fetchone()[0]
        values["bytes_stored"]=con.execute("SELECT COALESCE(SUM(bytes),0) FROM blobs").fetchone()[0]
        values["last_run"]=dict(x) if (x:=con.execute("SELECT * FROM collection_runs ORDER BY id DESC LIMIT 1").fetchone()) else None
        return values

def record_run(root:Path, provider:str, start:str, status:str, imported:int=0,error_type:str=""):
    with db_connect(root) as con:
        con.execute("""INSERT INTO collection_runs(provider,started_at,finished_at,status,imported,error_type)
              VALUES(?,?,?,?,?,?)""",(provider,start,now(),status,imported,error_type[:100]))

def comment_previews(root: Path, post_id: int, limit: int = 20) -> list[dict]:
    if not 1 <= limit <= 20:
        raise ValueError("Invalid comment page size")
    with db_connect(root) as con:
        return [dict(x) for x in con.execute("""SELECT comment_id,username,comment_text,
            created_at,likes,reply_count,captured_at
            FROM comment_previews WHERE post_id=?
            ORDER BY COALESCE(created_at,captured_at) DESC,comment_id DESC LIMIT ?""",
            (post_id,limit))]


def cache_report(root: Path, *, verify_hashes: bool=False) -> dict:
    """Audit local media; no Instagram API calls or deletions."""
    with db_connect(root) as con:
        rows = [dict(x) for x in con.execute("SELECT sha256,relative_path,bytes FROM blobs")]
    report = {"registered": len(rows), "available": 0, "missing": 0,
              "corrupt": 0, "bytes": 0, "verified_sha256": bool(verify_hashes)}
    base = private_root(root) / "blobs"
    for row in rows:
        path = (private_root(root) / row["relative_path"]).resolve()
        if not path.is_relative_to(base) or not path.is_file():
            report["missing"] += 1
            continue
        if path.stat().st_size != row["bytes"]:
            report["corrupt"] += 1
            continue
        if verify_hashes:
            digest = hashlib.sha256()
            with path.open("rb") as source:
                for block in iter(lambda:source.read(1024*1024),b""):
                    digest.update(block)
            if digest.hexdigest() != row["sha256"]:
                report["corrupt"] += 1
                continue
        report["available"] += 1
        report["bytes"] += row["bytes"]
    return report
