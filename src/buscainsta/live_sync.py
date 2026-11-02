"""Automated batch address-book sync and suggestion matching.

Uploads consented contacts in controlled batches via Instagram's private
address_book API, captures suggested profiles, and correlates them locally
with contact names to populate candidate usernames in the review sheet.
Also supports automated nominal search for contacts not found in suggestions.
"""
import argparse
import csv
import importlib
import json
import os
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Callable, Optional

from .cli import MAX_ROWS, normalize_email, normalize_phone, validate_row
from .pilot import REVIEW_COLUMNS, username

COLUMNS = ("contact_id", "full_name", "phone", "email", "instagram", "consent", "consent_date", "consent_source")
STOP_TOKENS = frozenset({"de", "da", "do", "dos", "das", "e", "junior", "filho", "neto", "sobrinho"})


def read_consented_contacts(path: Path, max_rows: int = 5000) -> list[dict[str, str]]:
    """Read and validate contacts for live sync, supporting batches up to max_rows."""
    if not path.is_file():
        raise ValueError("Contacts CSV not found.")
    ids: set[str] = set()
    rows: list[dict[str, str]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        headers = reader.fieldnames
        if not headers or len(headers) != len(COLUMNS) or set(headers) != set(COLUMNS):
            raise ValueError("CSV headers do not match documented schema.")
        for raw in reader:
            if len(rows) >= max_rows:
                raise ValueError(f"More than {max_rows} records supplied.")
            if None in raw or any(raw.get(col) is None for col in COLUMNS):
                raise ValueError("CSV has malformed or incomplete records.")
            row = {col: str(raw[col]).strip() for col in COLUMNS}
            if not row["contact_id"] or row["contact_id"] in ids:
                raise ValueError("CSV contains an empty or duplicate contact_id.")
            ids.add(row["contact_id"])
            rows.append(row)
    if not rows:
        raise ValueError("CSV has no contact records.")
    return rows


def strip_accents(text: str) -> str:
    """Strip accents and diacritics from text."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(c for c in normalized if not unicodedata.combining(c))


def load_env_file(path: Path) -> dict[str, str]:
    """Load simple KEY=VALUE pairs from a local .env file without external deps."""
    loaded: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            loaded[k.strip()] = v.strip().strip("'\"")
    return loaded


def contact_to_payload(row: dict[str, str]) -> dict:
    """Format a single contact row for the mobile address_book_link payload."""
    phones = [dict(phone_number=row["phone"])] if row.get("phone") else []
    emails = [dict(email_address=row["email"])] if row.get("email") else []
    parts = row.get("full_name", "").strip().split(maxsplit=1)
    first_name = parts[0] if parts else ""
    last_name = parts[1] if len(parts) > 1 else ""
    return {
        "phone_numbers": phones,
        "email_addresses": emails,
        "first_name": first_name,
        "last_name": last_name,
    }


def normalize_tokens(name: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from a full name, accent-free and minus particles."""
    clean = strip_accents(name.casefold())
    tokens = {t for t in re.sub(r"[^\w\s]", "", clean).split() if len(t) >= 2}
    return tokens - STOP_TOKENS


def get_user_field(user_obj: object, field: str, default: str = "") -> str:
    """Extract a field from either a dict or an instagrapi User/UserShort model."""
    if isinstance(user_obj, dict):
        return str(user_obj.get(field, default) or "")
    return str(getattr(user_obj, field, default) or "")


def match_user_to_contact(
    user_item: object,
    contacts: list[dict[str, str]],
) -> Optional[str]:
    """Return a *unique candidate* only; never choose the first similar name.

    Matching is an unconfirmed suggestion, not proof of the person's identity.
    If multiple CRM contacts fit the best available signal, return None.
    """
    clean_user = username(get_user_field(user_item, "username"))
    if not clean_user:
        return None
    extra = strip_accents(get_user_field(
        user_item, "extra_display_name").strip().casefold())
    profile = strip_accents(get_user_field(
        user_item, "full_name").strip().casefold())
    tokens = normalize_tokens(profile)
    parts = [v for v in profile.split()
             if v not in STOP_TOKENS and len(v) >= 2]
    user_local = clean_user.replace(".", "").replace("_", "")
    # Strict priority, not fuzzy scoring. Ambiguity at the strongest tier
    # cannot safely be resolved by falling back to a weaker signal.
    strategies = [
        lambda c: bool(extra) and strip_accents(
            c.get("full_name", "").strip().casefold()) == extra,
        lambda c: bool(profile) and strip_accents(
            c.get("full_name", "").strip().casefold()) == profile,
        lambda c: len(tokens) >= 2 and len(normalize_tokens(c.get("full_name", ""))) >= 2
            and (normalize_tokens(c.get("full_name", "")).issubset(tokens)
                 or tokens.issubset(normalize_tokens(c.get("full_name", "")))),
        lambda c: len(parts) >= 2 and (
            lambda cp: len(cp) >= 2 and cp[0] == parts[0] and cp[-1] == parts[-1]
        )([v for v in strip_accents(c.get("full_name", "").casefold()).split()
           if v not in STOP_TOKENS and len(v) >= 2]),
        lambda c: len(user_local) >= 4 and bool(c.get("email")) and
            c["email"].split("@", 1)[0].casefold().replace(".", "").replace("_", "") == user_local,
    ]
    for rule in strategies:
        ids = {c["contact_id"] for c in contacts if rule(c)}
        if len(ids) == 1:
            return next(iter(ids))
        if len(ids) > 1:
            return None
    return None


def run_sync(
    contacts_path: Path,
    review_path: Path,
    login: str,
    password: str,
    client_factory: Callable,
    batch_size: int = 25,
    keep_linked: bool = True,
    batch_delay: float = 1.0,
    search_unmatched: bool = True,
    search_delay: float = 1.2,
    max_contacts: int = 2000,
    max_search: int = 100,
) -> dict:
    """Execute batch address book link, fetch suggestions, search remaining, and update review CSV."""
    if not (1 <= batch_size <= 100 and 0 <= max_search <= 5000):
        raise ValueError("Invalid batch or search limit.")
    if not contacts_path.is_file():
        raise ValueError("Contacts CSV not found.")
    if not review_path.is_file():
        raise ValueError("Review CSV not found.")

    contacts = read_consented_contacts(contacts_path, max_rows=max_contacts)
    invalid = [r for r in contacts if validate_row(r, synthetic=False)]
    if invalid:
        raise ValueError("Contacts file contains invalid or unconsented records.")

    # Load existing review rows
    with review_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != list(REVIEW_COLUMNS):
            raise ValueError("Review CSV headers do not match documented schema.")
        review_rows = list(reader)

    review_by_id = {r["contact_id"]: r for r in review_rows}
    all_suggestions: list[object] = []

    cl = client_factory()
    cl.login(login, password)

    unlink_status = "not_requested" if keep_linked else "pending"
    try:
        # 1. Address book link in batches
        for i in range(0, len(contacts), batch_size):
            batch = contacts[i: i + batch_size]
            payloads = [contact_to_payload(c) for c in batch]
            result = cl.address_book_link(payloads)

            if isinstance(result, dict):
                for key in ("users", "suggested_users"):
                    items = result.get(key)
                    if isinstance(items, list):
                        all_suggestions.extend(items)

            if i + batch_size < len(contacts) and batch_delay > 0:
                time.sleep(batch_delay)

        # 2. Also fetch account-level recommendations / suggested profiles
        user_id = getattr(cl, "user_id", None)
        if user_id and hasattr(cl, "fbsearch_suggested_profiles"):
            try:
                recs = cl.fbsearch_suggested_profiles(user_id)
                if isinstance(recs, list):
                    all_suggestions.extend(recs)
            except Exception:
                pass
    finally:
        if not keep_linked:
            try:
                cl.address_book_unlink()
                unlink_status = "completed"
            except Exception:
                unlink_status = "failed"

    # Match suggestions against contacts
    matched_from_suggestions = 0
    assigned_usernames: set[str] = set()

    for item in all_suggestions:
        raw_u = get_user_field(item, "username")
        u = username(raw_u)
        if not u or u in assigned_usernames:
            continue

        cid = match_user_to_contact(item, contacts)
        if cid and cid in review_by_id:
            row = review_by_id[cid]
            if row.get("status") == "pending" and not row.get("candidate_username"):
                row["candidate_username"] = u
                row["discovery_method"] = "native_contact_suggestion"
                row["status"] = "candidate"
                assigned_usernames.add(u)
                matched_from_suggestions += 1

    # 3. Search nominal for remaining pending contacts (cascade queries)
    matched_from_search = 0
    if search_unmatched and hasattr(cl, "search_users"):
        contacts_by_id = {c["contact_id"]: c for c in contacts}
        searched = 0
        for row in review_rows:
            if searched >= max_search:
                break
            if row.get("status") != "pending" or row.get("candidate_username"):
                continue

            c = contacts_by_id.get(row["contact_id"])
            if not c or not c.get("full_name"):
                continue

            searched += 1
            full_name = c["full_name"].strip()
            c_name = strip_accents(full_name.casefold())
            c_tokens = normalize_tokens(full_name)
            c_parts = [t for t in strip_accents(full_name).split() if t.lower() not in STOP_TOKENS and len(t) >= 2]

            queries_to_try = [full_name]
            if len(c_parts) > 2:
                queries_to_try.append(f"{c_parts[0]} {c_parts[-1]}")

            email_local = c.get("email", "").split("@", 1)[0].strip()
            if email_local and len(email_local) >= 5 and "." in email_local:
                queries_to_try.append(email_local)

            matched_this_contact = False
            for query in queries_to_try:
                try:
                    results = cl.search_users(query)
                    if isinstance(results, list):
                        for res_user in results:
                            u = username(get_user_field(res_user, "username"))
                            if not u or u in assigned_usernames:
                                continue

                            res_name = strip_accents(get_user_field(res_user, "full_name").strip().casefold())
                            res_tokens = normalize_tokens(res_name)
                            res_parts = [t for t in res_name.split() if t not in STOP_TOKENS and len(t) >= 2]

                            is_match = False
                            if res_name and res_name == c_name:
                                is_match = True
                            elif len(c_tokens) >= 2 and (c_tokens.issubset(res_tokens) or res_tokens.issubset(c_tokens)):
                                is_match = True
                            elif len(c_parts) >= 2 and len(res_parts) >= 2 and c_parts[0] == res_parts[0] and c_parts[-1] == res_parts[-1]:
                                is_match = True

                            if is_match and match_user_to_contact(res_user, contacts) == row["contact_id"]:
                                row["candidate_username"] = u
                                row["discovery_method"] = "name_search"
                                row["status"] = "candidate"
                                assigned_usernames.add(u)
                                matched_from_search += 1
                                matched_this_contact = True
                                break

                    if search_delay > 0:
                        time.sleep(search_delay)
                except Exception:
                    matched_this_contact = True
                    break

                if matched_this_contact:
                    break

    # Save updated review sheet
    with review_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        writer.writerows(review_rows)

    return {
        "status": "completed",
        "mode": "live_sync",
        "contacts_submitted": len(contacts),
        "suggestions_received": len(all_suggestions),
        "candidates_matched": matched_from_suggestions + matched_from_search,
        "matched_from_suggestions": matched_from_suggestions,
        "matched_from_search": matched_from_search,
        "total_candidates_identified": matched_from_suggestions + matched_from_search,
        "unlink": unlink_status,
        "keep_linked": keep_linked,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BuscaInsta live_sync: batch upload contacts, suggestions & nominal search"
    )
    parser.add_argument("--contacts", required=True, type=Path, help="Consented contacts CSV")
    parser.add_argument("--review", required=True, type=Path, help="Review sheet CSV to update")
    parser.add_argument("--batch-size", type=int, default=25, help="Contacts per API call (default 25)")
    parser.add_argument("--keep-linked", action="store_true", help="Do not unlink after sync")
    parser.add_argument("--confirm-sync", action="store_true", help="Explicit confirmation required")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="Path to optional .env file")
    parser.add_argument("--no-search", action="store_true", help="Disable nominal search for unmatched contacts")
    parser.add_argument("--limit-search", type=int, default=100, help="Max contacts to search nominally")
    args = parser.parse_args()

    if not args.confirm_sync:
        parser.exit(2, "ERROR: Explicit sync confirmation required (--confirm-sync).\n")

    # Load credentials: env vars take precedence, then .env file
    env_file_vars = load_env_file(args.env_file)
    login = os.environ.get("BUSCAINSTA_IG_TEST_LOGIN") or env_file_vars.get("BUSCAINSTA_IG_TEST_LOGIN", "")
    password = os.environ.get("BUSCAINSTA_IG_TEST_PASSWORD") or env_file_vars.get("BUSCAINSTA_IG_TEST_PASSWORD", "")

    if not login or not password:
        parser.exit(2, "ERROR: Dedicated test account credentials missing (set in .env or environment).\n")

    try:
        try:
            Client = importlib.import_module("instagrapi").Client
        except ImportError:
            parser.exit(2, "ERROR: Optional instagrapi library not installed in this environment.\n")

        result = run_sync(
            contacts_path=args.contacts,
            review_path=args.review,
            login=login,
            password=password,
            client_factory=Client,
            batch_size=args.batch_size,
            keep_linked=args.keep_linked,
            search_unmatched=not args.no_search,
            max_contacts=5000,
            max_search=args.limit_search,
        )
        print(json.dumps(result, sort_keys=True))
        if result["unlink"] == "failed":
            parser.exit(3, "WARNING: Unlink failed; check contact settings in Instagram.\n")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    except Exception as exc:
        # Avoid leaking raw Instagram error responses or tokens
        parser.exit(3, f"ERROR: Instagram live sync failed: {type(exc).__name__}. Check test account manually.\n")


if __name__ == "__main__":
    main()
