"""Read-only migration from the existing local painel_conferencia.html.

The legacy HTML embeds a const allData JSON array. This parser decodes only
the JSON, never executes Javascript and never logs contact values.
"""
import hashlib
import json
import re
from pathlib import Path

from .dashboard_store import check_private_path, connection, setup, timestamp


def _normalize_digits(phone: str) -> str:
    digits = re.sub(r"[^0-9]", "", phone or "")
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    return digits if 10 <= len(digits) <= 11 else ""


def _number(value) -> int:
    try:
        return max(0, int(float(str(value or "0"))))
    except (TypeError, ValueError, OverflowError):
        return 0


def parse_legacy(html_path: Path) -> list[dict]:
    """Parse contact data from local HTML, without evaluating JS."""
    html_path = check_private_path(html_path)
    if not html_path.is_file() or html_path.stat().st_size > 20_000_000:
        raise ValueError("Legacy HTML missing or exceeds local size limit.")
    html = html_path.read_text(encoding="utf-8-sig")
    matches = list(re.finditer(r"\bconst\s+allData\s*=", html))
    if len(matches) != 1:
        raise ValueError("Legacy HTML has no unique allData dataset.")
    payload = html[matches[0].end():].lstrip()
    try:
        rows, _ = json.JSONDecoder().raw_decode(payload)
    except (json.JSONDecodeError, ValueError) as exc:
        raise ValueError("Legacy HTML embedded customer JSON is malformed.") from exc
    if not isinstance(rows, list) or not 1 <= len(rows) <= 10000:
        raise ValueError("Legacy dataset is not a supported contact list.")
    if not all(isinstance(r, dict) for r in rows):
        raise ValueError("Legacy rows must be objects.")
    return rows


def import_legacy(db_path: Path, html_path: Path) -> dict:
    """Idempotently import by phone; never use nonunique CRM ID for joining.

    Preserve confirmed usernames, avatars and Direct history.
    """
    data = parse_legacy(html_path)
    setup(db_path)
    encountered = set()
    added = updated = skipped = imported_candidates = 0
    with connection(db_path) as db:
        db.execute("BEGIN IMMEDIATE")
        for r in data:
            phone = _normalize_digits(str(r.get("wa_clean") or r.get("phone_raw") or ""))
            name = str(r.get("name") or "").strip()
            if not phone or not name or len(name) > 200:
                skipped += 1
                continue
            if phone in encountered:
                skipped += 1
                continue
            encountered.add(phone)
            # The CRM ID repeats in the source. Match only an unambiguous phone.
            matches = db.execute(
                "SELECT contact_id,candidate_username,manually_verified FROM contacts "
                "WHERE replace(replace(replace(phone,'+',''),' ',''),'-','') IN (?,?)",
                (phone, "55" + phone)
            ).fetchall()
            if len(matches) > 1:
                skipped += 1
                continue
            cid = (matches[0]["contact_id"] if matches else
                   "BI-" + hashlib.sha256(phone.encode("ascii")).hexdigest()[:20])
            candidate = str(r.get("instagram") or "").strip().lstrip("@").lower()
            if candidate and not re.fullmatch(r"[a-z0-9._]{1,30}", candidate):
                candidate = ""
            stored = db.execute(
                "SELECT contact_id,manually_verified,candidate_username FROM contacts WHERE contact_id=?",
                (cid,)
            ).fetchone()
            if not stored:
                db.execute("""
                    INSERT INTO contacts(contact_id,full_name,phone,email,
                        candidate_username,discovery_method,status)
                    VALUES (?,?,?,?,?,?,?)
                """, (
                    cid, name, "+55" + phone, str(r.get("email") or "")[:254],
                    candidate, str(r.get("ig_method") or "")[:80],
                    "candidate" if candidate else "pending"
                ))
                added += 1
                if candidate:
                    imported_candidates += 1
            else:
                # Preserve all manual verifications, profile data and Direct history.
                db.execute("""
                    UPDATE contacts SET full_name=?,phone=?,
                      email=CASE WHEN email='' THEN ? ELSE email END
                    WHERE contact_id=?
                """, (name, "+55" + phone, str(r.get("email") or "")[:254], cid))
                if not stored["candidate_username"] and candidate and not stored["manually_verified"]:
                    db.execute("""
                        UPDATE contacts SET candidate_username=?,discovery_method=?,
                          status='candidate' WHERE contact_id=?
                    """, (candidate, str(r.get("ig_method") or "")[:80], cid))
                    imported_candidates += 1
                updated += 1
            db.execute("""
                UPDATE contacts SET crm_id=?,vip_rank=?,vip_score=?,vip_segment=?,
                    total_orders=?,natal_sessions=?,natal_years=?,last_natal_year=?,
                    ltv_display=?,natal_spend_display=?,natal_2026=?,
                    legacy_updated_at=? WHERE contact_id=?
            """, (
                str(r.get("crm_id") or "")[:32],
                _number(r.get("rank")),
                float(r.get("score_vip") or 0),
                str(r.get("segmento_vip") or "")[:30],
                _number(r.get("total_pedidos")),
                _number(r.get("ensaios_natal")),
                _number(r.get("anos_natal")),
                str(r.get("ultimo_natal_ano") or "")[:12],
                str(r.get("ltv_fmt") or "")[:40],
                str(r.get("gasto_natal_fmt") or "")[:40],
                str(r.get("situacao_2026") or "")[:100],
                timestamp(), cid
            ))
    return {
        "status": "imported", "source": "local_legacy_html",
        "source_rows": len(data), "added": added, "updated": updated,
        "skipped": skipped, "candidates_imported": imported_candidates,
        "crm_id_unique": False, "source_file_unchanged": True,
    }
