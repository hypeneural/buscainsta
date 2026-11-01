"""Local, real-world review pilot. No API calls, scraping or CRM credentials.

Import specifically authorized contacts, record human-observed Instagram candidates,
and calculate only aggregate outcomes. This does not reverse-search Instagram.
"""
import argparse
import csv
import json
import os
import re
import secrets
from collections import Counter
from pathlib import Path

from .cli import MAX_ROWS, read_contacts, validate_row

REVIEW_COLUMNS = (
    "contact_id", "invite_code", "candidate_username",
    "discovery_method", "status", "confirmation_source",
)
METHODS = {"", "native_contact_suggestion", "name_search", "client_self_reported", "official_dm", "crm_existing"}
STATUS = {"pending", "candidate", "confirmed", "not_found", "rejected"}
CONFIRMATIONS = {"", "client_self_reported", "client_confirmed", "official_authorized_interaction"}
MAX_REVIEW_BYTES = 100_000


def username(value: str) -> str:
    """Syntactic validation only, not a lookup or proof of ownership."""
    value = value.strip().lstrip("@")
    if (not re.fullmatch(r"[A-Za-z0-9._]{1,30}", value)
            or value.startswith(".") or value.endswith(".") or ".." in value):
        return ""
    return value.lower()


def _private_output(path: Path) -> None:
    """Prevent casual placement of review files inside any Git worktree."""
    parent = path.parent.resolve()
    if not parent.is_dir():
        raise ValueError("Output directory does not exist.")
    for candidate in (parent, *parent.parents):
        if (candidate / ".git").exists():
            raise ValueError("Keep pilot review data outside the Git repository.")


def prepare(input_path: Path, output_path: Path) -> dict:
    rows = read_contacts(input_path, maximum=MAX_ROWS)
    invalid = sum(bool(validate_row(row, synthetic=False)) for row in rows)
    if invalid:
        raise ValueError("Input has invalid or non-consented records; no output created.")
    _private_output(output_path)
    try:
        stream = output_path.open("x", encoding="utf-8", newline="")
    except FileExistsError as exc:
        raise ValueError("Refusing to overwrite an existing pilot file.") from exc
    with stream:
        if os.name != "nt":
            os.chmod(output_path, 0o600)
        writer = csv.DictWriter(stream, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in rows:
            candidate = username(row["instagram"]) if row["instagram"] else ""
            writer.writerow({
                "contact_id": row["contact_id"],
                "invite_code": secrets.token_hex(8),
                "candidate_username": candidate,
                "discovery_method": "crm_existing" if candidate else "",
                "status": "candidate" if candidate else "pending",
                "confirmation_source": "",
            })
    return {"status": "prepared", "records": len(rows), "mode": "local_human_review",
            "instagram_lookup": "not_implemented", "uploaded_contacts": 0}


def summarize(input_path: Path) -> dict:
    if not input_path.is_file() or input_path.stat().st_size > MAX_REVIEW_BYTES:
        raise ValueError("Review file missing or too large.")
    states = Counter()
    ids: set[str] = set()
    claimed: set[str] = set()
    with input_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != list(REVIEW_COLUMNS):
            raise ValueError("Review CSV headers must match the template.")
        for row in reader:
            if sum(states.values()) >= MAX_ROWS:
                raise ValueError("Review file exceeds 100 rows.")
            if None in row or any(row.get(col) is None for col in REVIEW_COLUMNS):
                raise ValueError("Malformed review CSV.")
            if any(len(row[col]) > 256 for col in REVIEW_COLUMNS):
                raise ValueError("Review field exceeds size limit.")
            identity = row["contact_id"].strip()
            if not identity or identity in ids or not re.fullmatch(r"[a-f0-9]{16}", row["invite_code"]):
                raise ValueError("Review IDs/codes malformed or duplicated.")
            ids.add(identity)
            status = row["status"].strip() or "pending"
            method = row["discovery_method"].strip()
            confirmation = row["confirmation_source"].strip()
            name = username(row["candidate_username"]) if row["candidate_username"] else ""
            if status not in STATUS or method not in METHODS or confirmation not in CONFIRMATIONS:
                raise ValueError("Unknown review state or source.")
            if row["candidate_username"] and not name:
                raise ValueError("Invalid candidate username syntax.")
            if status in {"candidate", "confirmed"} and not name:
                raise ValueError("Candidate and confirmed states require a username.")
            if status == "confirmed":
                if confirmation not in {"client_self_reported", "client_confirmed", "official_authorized_interaction"}:
                    raise ValueError("Confirmation requires evidence from the account holder.")
                if name in claimed:
                    raise ValueError("One username cannot be confirmed for multiple contacts.")
                claimed.add(name)
            elif confirmation:
                raise ValueError("Unconfirmed records cannot claim confirmation.")
            states[status] += 1
    total = sum(states.values())
    if not total:
        raise ValueError("Review CSV contains no records.")
    reviewed = total - states["pending"]
    return {
        "total": total, "reviewed": reviewed,
        "pending": states["pending"], "candidates": states["candidate"],
        "confirmed": states["confirmed"], "not_found": states["not_found"],
        "rejected": states["rejected"],
        "review_rate": round(reviewed / total, 4),
        "confirmation_rate": round(states["confirmed"] / total, 4),
        "mode": "local_human_review",
        "instagram_lookup": "not_implemented",
        "uploaded_contacts": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="BuscaInsta authorized-contact pilot (local review only)")
    sub = parser.add_subparsers(dest="action", required=True)
    create = sub.add_parser("prepare", help="Generate private manual review sheet from consented CSV")
    create.add_argument("--input", required=True, type=Path)
    create.add_argument("--output", required=True, type=Path)
    summary = sub.add_parser("summarize", help="Aggregate review results, without PII")
    summary.add_argument("--input", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.action == "prepare":
            result = prepare(args.input, args.output)
        else:
            result = summarize(args.input)
        print(json.dumps(result, sort_keys=True))
    except (UnicodeError, csv.Error):
        parser.exit(2, "ERROR: Invalid UTF-8 or CSV structure.\n")
    except OSError:
        parser.exit(2, "ERROR: File operation failed.\n")
    except ValueError as exc:
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
