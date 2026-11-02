"""Optional experimental one-contact live probe of Instagram's *unofficial* address-book API.

Requires a dedicated operator-owned Instagram test account, explicit consent of the
volunteer whose details are shared, and separate Meta/platform authorization review.
Does not enumerate strangers, store raw results, or write matches to the CRM.
"""
import argparse
import importlib
import json
import os
import sys
from pathlib import Path

from .cli import normalize_email, normalize_phone, read_contacts, validate_row
from .pilot import username


class ProbeInputError(ValueError):
    """Trusted local input validation failure."""


def candidate_usernames(payload: object) -> set[str]:
    """Recognize documented raw top-level candidate lists; unknown schema = inconclusive."""
    if not isinstance(payload, dict):
        return set()
    found: set[str] = set()
    for key in ("users", "suggested_users"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if isinstance(item, dict):
                candidate = item.get("username")
                if isinstance(candidate, str):
                    clean = username(candidate)
                    if clean:
                        found.add(clean)
    return found


def payload_contact(row: dict[str, str]) -> dict:
    phones = [dict(phone_number=normalize_phone(row["phone"]))] if row["phone"] else []
    emails = [dict(email_address=normalize_email(row["email"]))] if row["email"] else []
    # Only include the contact information the volunteer authorized.
    return {"phone_numbers": phones, "email_addresses": emails,
            "first_name": "", "last_name": ""}


def run_probe(
    path: Path, contact_id: str, expected: str,
    login: str, password: str, client_factory,
) -> dict:
    rows = read_contacts(path)
    found = [r for r in rows if r["contact_id"] == contact_id]
    if len(found) != 1 or validate_row(found[0], synthetic=False):
        raise ProbeInputError("Selected contact was not found or lacks required authorization.")
    normalized_expected = username(expected)
    if not normalized_expected:
        raise ProbeInputError("Expected volunteer username is invalid.")
    cl = client_factory()
    uploaded = False
    unlink_status = "not_needed"
    result: object = {}
    try:
        cl.login(login, password)
        # No bulk list, proxies, rate-limit retries or session persistence.
        uploaded = True  # unlink even if link fails midway
        result = cl.address_book_link([payload_contact(found[0])])
    finally:
        if uploaded:
            try:
                cl.address_book_unlink()
                unlink_status = "completed"
            except Exception:
                unlink_status = "failed"
    candidates = candidate_usernames(result)
    return {
        "probe": "unofficial_instagram_address_book",
        "contacts_submitted": 1,
        "expected_username_in_suggestions": normalized_expected in candidates,
        "candidate_count": len(candidates),
        "schema_recognized": isinstance(result, dict) and any(
            isinstance(result.get(k), list) for k in ("users", "suggested_users")
        ),
        "unlink": unlink_status,
        "meaning": "suggestion_only_not_identity_proof",
        "saved_usernames": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Experimental live probe: one consenting volunteer, unofficial API"
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--contact-id", required=True)
    parser.add_argument("--expected-username", required=True)
    parser.add_argument("--confirm-contact-sharing", action="store_true")
    args = parser.parse_args()
    if not args.confirm_contact_sharing:
        parser.exit(2, "ERROR: Explicit contact-sharing confirmation required.\n")
    login = os.environ.get("BUSCAINSTA_IG_TEST_LOGIN", "")
    password = os.environ.get("BUSCAINSTA_IG_TEST_PASSWORD", "")
    if not login or not password:
        parser.exit(2, "ERROR: Dedicated test account environment credentials missing.\n")
    try:
        try:
            Client = importlib.import_module("instagrapi").Client
        except ImportError:
            parser.exit(2, "ERROR: Optional instagrapi library not installed.\n")
        result = run_probe(args.input, args.contact_id, args.expected_username, login, password, Client)
        print(json.dumps(result, sort_keys=True))
        if result["unlink"] != "completed":
            parser.exit(3, "WARNING: Unlink failed; inspect the test account's contact settings.\n")
    except ProbeInputError as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    except (OSError, UnicodeError):
        parser.exit(2, "ERROR: Local input validation failed.\n")
    except Exception:
        # Avoid leaking Instagram error messages, account names, or tokens.
        parser.exit(3, "ERROR: Instagram live probe failed. Check the test account manually.\n")


if __name__ == "__main__":
    main()
