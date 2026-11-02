"""Private SQLite store for the local BuscaInsta review dashboard.

No network, CRM writeback or GitHub integration. All paths must be outside
a Git worktree. UI manually verified != verified by the account owner.
"""
import csv
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

CONTACT_COLUMNS = (
    "contact_id", "full_name", "phone", "email", "instagram",
    "consent", "consent_date", "consent_source",
)
REVIEW_COLUMNS = (
    "contact_id", "invite_code", "candidate_username",
    "discovery_method", "status", "confirmation_source",
)


def timestamp() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def check_private_path(path: Path) -> Path:
    path = path.expanduser().resolve()
    for ancestor in (path, *path.parents):
        if (ancestor / ".git").exists():
            raise ValueError("Private data path must be outside any Git repository.")
    return path


@contextmanager
def connection(db_path: Path):
    conn = sqlite3.connect(str(db_path), timeout=10)
    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=10000")
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        conn.close()


def setup(db_path: Path) -> None:
    db_path = check_private_path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connection(db_path) as db:
        db.execute("PRAGMA journal_mode=WAL")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS contacts (
            contact_id TEXT PRIMARY KEY,
            full_name TEXT NOT NULL DEFAULT '',
            phone TEXT NOT NULL DEFAULT '',
            email TEXT NOT NULL DEFAULT '',
            candidate_username TEXT NOT NULL DEFAULT '',
            discovery_method TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'pending',
            manually_verified INTEGER NOT NULL DEFAULT 0,
            dm_permitted INTEGER NOT NULL DEFAULT 0,
            instagram_pk TEXT NOT NULL DEFAULT '',
            instagram_name TEXT NOT NULL DEFAULT '',
            is_private TEXT NOT NULL DEFAULT 'unknown',
            follows_us TEXT NOT NULL DEFAULT 'unknown',
            we_follow TEXT NOT NULL DEFAULT 'unknown',
            checked_account TEXT NOT NULL DEFAULT '',
            checked_at TEXT NOT NULL DEFAULT '',
            profile_url TEXT NOT NULL DEFAULT '',
            photo_url TEXT NOT NULL DEFAULT '',
            photo_local TEXT NOT NULL DEFAULT '',
            last_dm_status TEXT NOT NULL DEFAULT 'never',
            last_dm_attempt_at TEXT NOT NULL DEFAULT '',
            last_dm_accepted_at TEXT NOT NULL DEFAULT '',
            last_dm_message_id TEXT NOT NULL DEFAULT ''
        );
        CREATE TABLE IF NOT EXISTS dm_attempts (
            attempt_id TEXT PRIMARY KEY,
            contact_id TEXT NOT NULL REFERENCES contacts(contact_id),
            account TEXT NOT NULL,
            template_sha256 TEXT NOT NULL,
            attempted_at TEXT NOT NULL,
            accepted_at TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL DEFAULT 'pending',
            provider_message_id TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS ix_contacts_name ON contacts(full_name);
        """)
        existing = {item["name"] for item in db.execute("PRAGMA table_info(contacts)")}
        columns = {
            "crm_id": "TEXT NOT NULL DEFAULT ''",
            "vip_rank": "INTEGER NOT NULL DEFAULT 0",
            "vip_score": "REAL NOT NULL DEFAULT 0",
            "vip_segment": "TEXT NOT NULL DEFAULT ''",
            "total_orders": "INTEGER NOT NULL DEFAULT 0",
            "natal_sessions": "INTEGER NOT NULL DEFAULT 0",
            "natal_years": "INTEGER NOT NULL DEFAULT 0",
            "last_natal_year": "TEXT NOT NULL DEFAULT ''",
            "ltv_display": "TEXT NOT NULL DEFAULT ''",
            "natal_spend_display": "TEXT NOT NULL DEFAULT ''",
            "natal_2026": "TEXT NOT NULL DEFAULT ''",
            "legacy_updated_at": "TEXT NOT NULL DEFAULT ''",
        }
        for name, definition in columns.items():
            if name not in existing:
                db.execute(f"ALTER TABLE contacts ADD COLUMN {name} {definition}")


def _csv_rows(path: Path, columns: tuple[str, ...], max_rows: int):
    if not path.is_file() or path.stat().st_size > 5_000_000:
        raise ValueError("CSV is absent or exceeds the 5 MB local import limit.")
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if reader.fieldnames != list(columns):
            raise ValueError("CSV columns differ from expected BuscaInsta format.")
        count = 0
        for raw in reader:
            if count >= max_rows:
                raise ValueError("CSV exceeds local import limit.")
            if None in raw or any(raw.get(k) is None for k in columns):
                raise ValueError("Malformed CSV row.")
            row = {k: str(raw[k]).strip() for k in columns}
            if any(len(v) > 500 for v in row.values()):
                raise ValueError("Oversized CSV field.")
            count += 1
            yield row


def import_contacts(db_path: Path, path: Path) -> int:
    """Import even unreviewed contacts; does NOT infer consent for Direct."""
    count = 0
    with connection(db_path) as db:
        for row in _csv_rows(path, CONTACT_COLUMNS, 10000):
            if not row["contact_id"] or not row["full_name"]:
                raise ValueError("Contact ID and name are required.")
            db.execute("""
                INSERT INTO contacts(contact_id,full_name,phone,email,candidate_username,status)
                VALUES(?,?,?,?,?,'pending')
                ON CONFLICT(contact_id) DO UPDATE SET
                    full_name=excluded.full_name,phone=excluded.phone,email=excluded.email
            """, (
                row["contact_id"], row["full_name"], row["phone"], row["email"],
                "",  # do not consider the raw input Instagram field verified
            ))
            count += 1
    return count


def import_review(db_path: Path, path: Path) -> int:
    count = 0
    with connection(db_path) as db:
        for row in _csv_rows(path, REVIEW_COLUMNS, 10000):
            cid = row["contact_id"]
            existing = db.execute(
                "SELECT manually_verified,candidate_username FROM contacts WHERE contact_id=?", (cid,)
            ).fetchone()
            if existing is None or existing["manually_verified"]:
                continue
            username = row["candidate_username"].lstrip("@").lower()
            if username and not __import__("re").fullmatch(r"[a-z0-9._]{1,30}", username):
                continue
            if row["status"] not in ("pending", "candidate", "confirmed", "rejected", "not_found"):
                continue
            db.execute("""
                UPDATE contacts SET candidate_username=?,discovery_method=?,status=?
                WHERE contact_id=? AND manually_verified=0
            """, (
                username, row["discovery_method"],
                "candidate" if username else "pending", cid
            ))
            count += 1
    return count


def list_contacts(db_path: Path, query: str = "", page: int = 1, limit: int = 50,
                  segment: str = "", instagram_only: bool = False,
                  verified_only: bool = False) -> dict:
    page = max(1, min(int(page), 10000))
    limit = max(1, min(int(limit), 100))
    if segment not in ("", "P0", "P1", "P2", "P3", "P4", "Outros"):
        raise ValueError("Unsupported VIP segment.")
    term = "%" + query[:100].strip() + "%"
    where = """(full_name LIKE ? OR contact_id LIKE ? OR
             candidate_username LIKE ? OR phone LIKE ? OR crm_id LIKE ?)"""
    params = [term] * 5
    if segment:
        where += " AND vip_segment=?"
        params.append(segment)
    if instagram_only:
        where += " AND candidate_username<>''"
    if verified_only:
        where += " AND manually_verified=1"
    with connection(db_path) as db:
        total = db.execute(f"SELECT count(*) FROM contacts WHERE {where}", params).fetchone()[0]
        rows = db.execute(f"""
            SELECT contact_id,crm_id,full_name,phone,email,candidate_username,
                discovery_method,status,manually_verified,dm_permitted,
                instagram_pk,instagram_name,is_private,follows_us,we_follow,
                checked_account,checked_at,profile_url,photo_local,
                last_dm_status,last_dm_attempt_at,last_dm_accepted_at,
                vip_rank,vip_score,vip_segment,total_orders,natal_sessions,
                natal_years,last_natal_year,ltv_display,natal_spend_display,
                natal_2026
            FROM contacts WHERE {where}
            ORDER BY CASE WHEN vip_rank>0 THEN 0 ELSE 1 END,
                     vip_rank ASC, vip_score DESC,
                     full_name COLLATE NOCASE, contact_id
            LIMIT ? OFFSET ?
        """, [*params, limit, (page - 1) * limit]).fetchall()
        return {"total": total, "page": page, "limit": limit,
                "items": [dict(x) for x in rows]}


def dashboard_stats(db_path: Path) -> dict:
    """Aggregate metrics for manager cards without exposing private contacts."""
    with connection(db_path) as db:
        row = db.execute("""
            SELECT count(*) AS total,
                   sum(CASE WHEN candidate_username<>'' THEN 1 ELSE 0 END) AS candidates,
                   sum(CASE WHEN manually_verified=1 THEN 1 ELSE 0 END) AS verified,
                   sum(CASE WHEN follows_us='yes' THEN 1 ELSE 0 END) AS follows_us,
                   sum(CASE WHEN we_follow='yes' THEN 1 ELSE 0 END) AS we_follow,
                   sum(CASE WHEN last_dm_status='accepted' THEN 1 ELSE 0 END) AS dm_accepted,
                   sum(CASE WHEN last_dm_status='unknown' THEN 1 ELSE 0 END) AS dm_unknown
            FROM contacts
        """).fetchone()
        segment_rows = db.execute("""
            SELECT vip_segment, count(*) AS total
            FROM contacts GROUP BY vip_segment
        """).fetchall()
        values = dict(row)
        return {k: int(v or 0) for k, v in values.items()} | {
            "segments": {r["vip_segment"] or "Sem segmento": r["total"] for r in segment_rows}
        }


def get_contact(db_path: Path, cid: str) -> dict:
    with connection(db_path) as db:
        row = db.execute("SELECT * FROM contacts WHERE contact_id=?", (cid,)).fetchone()
        if row is None:
            raise ValueError("Contact not found.")
        return dict(row)


def set_candidate(db_path: Path, cid: str, candidate: str) -> None:
    from .pilot import username as normalize_username
    normalized = normalize_username(candidate)
    if not normalized:
        raise ValueError("Provide a valid @username.")
    with connection(db_path) as db:
        count = db.execute("""
            UPDATE contacts SET candidate_username=?,status='candidate',
                manually_verified=0,dm_permitted=0,instagram_pk='',instagram_name='',
                is_private='unknown',follows_us='unknown',we_follow='unknown',
                checked_at='',checked_account='',photo_url='',photo_local='',profile_url=''
            WHERE contact_id=?
        """, (normalized, cid)).rowcount
        if not count:
            raise ValueError("Contact not found.")


def set_verified(db_path: Path, cid: str, verified: bool) -> None:
    with connection(db_path) as db:
        row = db.execute("SELECT candidate_username FROM contacts WHERE contact_id=?",
                         (cid,)).fetchone()
        if row is None or (verified and not row[0]):
            raise ValueError("Select a candidate profile before manual verification.")
        db.execute("""
            UPDATE contacts SET manually_verified=?,status=?,
               dm_permitted=CASE WHEN ?=1 THEN dm_permitted ELSE 0 END
            WHERE contact_id=?
        """, (int(verified), "manual_checked" if verified else "candidate",
              int(verified), cid))


def set_dm_permission(db_path: Path, cid: str, allowed: bool) -> None:
    with connection(db_path) as db:
        row = db.execute(
            "SELECT manually_verified FROM contacts WHERE contact_id=?", (cid,)
        ).fetchone()
        if row is None or (allowed and not row[0]):
            raise ValueError("Manual profile verification is required first.")
        db.execute("UPDATE contacts SET dm_permitted=? WHERE contact_id=?",
                   (int(allowed), cid))


def save_profile(db_path: Path, cid: str, account: str, profile: dict,
                 photo_local: str = "") -> None:
    with connection(db_path) as db:
        row = db.execute(
            "SELECT candidate_username FROM contacts WHERE contact_id=?", (cid,)
        ).fetchone()
        if row is None or row[0].lower() != profile["username"].lower():
            raise ValueError("Candidate changed during lookup; result discarded.")
        db.execute("""
            UPDATE contacts SET instagram_pk=?, instagram_name=?,is_private=?,
                follows_us=?,we_follow=?,checked_account=?,checked_at=?,
                profile_url=?,photo_url=?,photo_local=?
            WHERE contact_id=?
        """, (
            str(profile["pk"]), profile["full_name"], profile["is_private"],
            profile["follows_us"], profile["we_follow"], account, timestamp(),
            profile["profile_url"], profile["photo_url"], photo_local, cid
        ))


def reserve_dm(db_path: Path, cid: str, account: str,
               template_sha256: str, attempt_id: str) -> dict:
    """Atomic single-send reservation. No retry for ambiguous outcomes."""
    with connection(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT * FROM contacts WHERE contact_id=?", (cid,)
        ).fetchone()
        if row is None or not row["manually_verified"] or not row["dm_permitted"]:
            raise ValueError("Profile verification and explicit Direct permission required.")
        if not row["instagram_pk"] or row["checked_account"] != account:
            raise ValueError("Recheck this profile from the selected Instagram account.")
        if row["last_dm_status"] != "never":
            raise ValueError("Direct already attempted. Manual reconciliation required.")
        moment = timestamp()
        db.execute("""
            INSERT INTO dm_attempts(attempt_id,contact_id,account,template_sha256,
                attempted_at,result) VALUES(?,?,?,?,?,'pending')
        """, (attempt_id, cid, account, template_sha256, moment))
        db.execute("""
            UPDATE contacts SET last_dm_status='pending',last_dm_attempt_at=?
            WHERE contact_id=?
        """, (moment, cid))
        return dict(row)


def finish_dm(db_path: Path, cid: str, attempt_id: str, accepted: bool,
              message_id: str = "") -> None:
    with connection(db_path) as db:
        result = "accepted" if accepted else "unknown"
        sent_at = timestamp() if accepted else ""
        db.execute("""
            UPDATE dm_attempts SET result=?,accepted_at=?,provider_message_id=?
            WHERE attempt_id=? AND contact_id=? AND result='pending'
        """, (result, sent_at, str(message_id)[:150], attempt_id, cid))
        db.execute("""
            UPDATE contacts SET last_dm_status=?,last_dm_accepted_at=?,
                last_dm_message_id=?
            WHERE contact_id=? AND last_dm_status='pending'
        """, (result, sent_at, str(message_id)[:150], cid))
