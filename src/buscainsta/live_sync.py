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
import time
import unicodedata
from pathlib import Path
from typing import Callable, Optional

from .cli import validate_row
from .pilot import REVIEW_COLUMNS, username

COLUMNS = ("contact_id", "full_name", "phone", "email", "instagram", "consent", "consent_date", "consent_source")
STOP_TOKENS = frozenset({"de", "da", "do", "dos", "das", "e", "junior", "filho", "neto", "sobrinho"})
TITLE_TOKENS = frozenset({
    "dr", "dra", "doutor", "doutora", "arq", "arquiteta", "arquiteto",
    "prof", "profa", "eng", "psi", "psicologa", "psicologo",
    "nutri", "nutricionista", "adv", "advogada", "advogado",
    "oficial", "estudio", "studio", "fotografia",
})
GENERIC_EMAIL_LOCALS = frozenset({
    "contato", "financeiro", "comercial", "admin", "administracao",
    "atendimento", "sac", "vendas", "suporte", "info",
})
BIO_SEPARATOR_RE = re.compile(r"\s*(?:\||•|·|—|–|\s-\s|\s/\s|//|~)\s*")


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


def _tokenize_segment(segment: str) -> list[str]:
    clean = strip_accents(segment.casefold()).replace("_", " ")
    words = re.sub(r"[^a-z0-9\s]", " ", clean).split()
    return [
        w for w in words
        if len(w) >= 2 and w not in STOP_TOKENS and w not in TITLE_TOKENS
    ]


def clean_profile_name(raw_name: str) -> str:
    """Clean an Instagram or CRM display name by stripping bio suffixes and titles.

    Examples:
        'Camila Pereira | Moda & Lifestyle' -> 'camila pereira'
        'Dra. Ana Paula de Souza • Estética' -> 'ana paula souza'
    """
    if not raw_name:
        return ""
    for segment in BIO_SEPARATOR_RE.split(raw_name.strip()):
        tokens = _tokenize_segment(segment)
        if tokens and any(any(ch.isalpha() for ch in tok) for tok in tokens):
            return " ".join(tokens)
    return " ".join(_tokenize_segment(raw_name))


def name_parts(name: str) -> list[str]:
    """Return ordered cleaned tokens for a person name."""
    cleaned = clean_profile_name(name)
    return cleaned.split() if cleaned else []


def normalize_tokens(name: str) -> set[str]:
    """Extract lowercase alphanumeric tokens from a full name, minus particles/titles."""
    return set(name_parts(name))


def get_user_field(user_obj: object, field: str, default: str = "") -> str:
    """Extract a field from either a dict or an instagrapi User/UserShort model."""
    if isinstance(user_obj, dict):
        return str(user_obj.get(field, default) or "")
    return str(getattr(user_obj, field, default) or "")


def extract_search_user(item: object) -> Optional[object]:
    """Unwrap user objects from fbsearch_topsearch_flat or search_users responses."""
    if isinstance(item, dict) and "user" in item and item["user"] is not None:
        return item["user"]
    if get_user_field(item, "username"):
        return item
    return None


def compound_handle_match(clean_user: str, c_parts: list[str]) -> bool:
    """Check whether @username embeds first_name+surname (e.g. camilapereira.pera)."""
    user_compact = clean_user.replace(".", "").replace("_", "").casefold()
    if len(user_compact) < 6 or len(c_parts) < 2 or len(c_parts[0]) < 3:
        return False
    first = c_parts[0]
    for surname in c_parts[1:]:
        if len(surname) >= 4 and (
            f"{first}{surname}" in user_compact or f"{surname}{first}" in user_compact
        ):
            return True
    return False


def build_search_queries(full_name: str, email: str = "") -> list[str]:
    """Build ordered, deduplicated Instagram search queries for a contact."""
    queries: list[str] = []
    seen: set[str] = set()

    def add(q: str) -> None:
        q = q.strip()
        key = strip_accents(q.casefold())
        if len(q) >= 3 and key not in seen:
            seen.add(key)
            queries.append(q)

    if full_name.strip():
        add(full_name.strip())
    parts = name_parts(full_name)
    if len(parts) >= 2:
        add(f"{parts[0]} {parts[-1]}")
    if len(parts) > 2:
        add(f"{parts[0]} {parts[1]}")
    if len(parts) >= 2 and len(parts[-1]) >= 4:
        add(f"{parts[0]}{parts[-1]}")

    email_local = email.split("@", 1)[0].strip() if email and "@" in email else ""
    if (
        len(email_local) >= 5
        and email_local.casefold() not in GENERIC_EMAIL_LOCALS
        and not email_local.isdigit()
    ):
        add(email_local)
    return queries


def score_candidate_for_contact(
    user_item: object,
    full_name: str,
    email: str = "",
    follows_us: str = "unknown",
    we_follow: str = "unknown",
) -> tuple[int, str]:
    """Compute a human-review compatibility score (0..99) and Portuguese explanation."""
    clean_user = username(get_user_field(user_item, "username"))
    if not clean_user:
        return 0, "Sem @username válido"

    c_clean = clean_profile_name(full_name)
    c_parts = c_clean.split() if c_clean else []
    c_tokens = set(c_parts)

    raw_display = get_user_field(user_item, "full_name") or get_user_field(user_item, "extra_display_name")
    p_clean = clean_profile_name(raw_display)
    p_parts = p_clean.split() if p_clean else []
    p_tokens = set(p_parts)

    user_compact = clean_user.replace(".", "").replace("_", "").casefold()
    email_local = (
        email.split("@", 1)[0].casefold().replace(".", "").replace("_", "")
        if email and "@" in email else ""
    )

    score = 0
    reasons: list[str] = []

    if c_clean and p_clean and c_clean == p_clean:
        score = 82
        reasons.append("Nome completo exato")
    elif len(c_tokens) >= 2 and len(p_tokens) >= 2 and (c_tokens.issubset(p_tokens) or p_tokens.issubset(c_tokens)):
        score = 76
        reasons.append("Nome e sobrenome compatíveis")
    elif (
        len(c_parts) >= 2 and len(p_parts) >= 2 and c_parts[0] == p_parts[0]
        and bool({s for s in c_parts[1:] if len(s) >= 4} & {s for s in p_parts[1:] if len(s) >= 4})
    ):
        score = 68
        reasons.append("Primeiro nome + sobrenome")
    elif c_parts and p_parts and c_parts[0] == p_parts[0] and len(c_parts[0]) >= 3:
        score = 36
        reasons.append("Primeiro nome igual")

    if compound_handle_match(clean_user, c_parts):
        score = max(score + 12, 70)
        reasons.append("@ contém nome+sobrenome")
    elif c_parts and len(c_parts[0]) >= 4 and user_compact.startswith(c_parts[0]):
        score = max(score + 5, 28)
        if not reasons:
            reasons.append("@ inicia com o primeiro nome")

    if len(email_local) >= 4 and email_local == user_compact:
        score = max(score + 14, 74)
        reasons.append("Igual ao prefixo do e-mail")

    if follows_us == "yes":
        score += 15
        reasons.insert(0, "Nos segue")
    if we_follow == "yes":
        score += 5
        reasons.append("Seguimos")

    score = min(score, 99)
    return score, " · ".join(reasons) if reasons else "Resultado de busca nominal"


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
    extra_clean = clean_profile_name(get_user_field(user_item, "extra_display_name"))
    profile_clean = clean_profile_name(get_user_field(user_item, "full_name"))
    tokens = set(profile_clean.split()) if profile_clean else set()
    parts = profile_clean.split() if profile_clean else []
    p_surnames = {p for p in parts[1:] if len(p) >= 4}
    user_local = clean_user.replace(".", "").replace("_", "").casefold()

    # Strict priority, not fuzzy scoring. Ambiguity at the strongest tier
    # cannot safely be resolved by falling back to a weaker signal.
    strategies = [
        lambda c: bool(extra_clean) and clean_profile_name(c.get("full_name", "")) == extra_clean,
        lambda c: bool(profile_clean) and clean_profile_name(c.get("full_name", "")) == profile_clean,
        lambda c: len(tokens) >= 2 and (
            lambda ct: len(ct) >= 2 and (ct.issubset(tokens) or tokens.issubset(ct))
        )(normalize_tokens(c.get("full_name", ""))),
        lambda c: len(parts) >= 2 and (
            lambda cp: len(cp) >= 2 and cp[0] == parts[0] and cp[-1] == parts[-1]
        )(name_parts(c.get("full_name", ""))),
        lambda c: len(parts) >= 2 and bool(p_surnames) and (
            lambda cp: len(cp) >= 2 and cp[0] == parts[0]
            and bool({s for s in cp[1:] if len(s) >= 4} & p_surnames)
        )(name_parts(c.get("full_name", ""))),
        lambda c: (
            lambda cp: compound_handle_match(clean_user, cp)
            and (not parts or parts[0] == cp[0])
        )(name_parts(c.get("full_name", ""))),
        lambda c: len(user_local) >= 4 and bool(c.get("email")) and (
            c["email"].split("@", 1)[0].casefold().replace(".", "").replace("_", "") == user_local
        ),
    ]
    for rule in strategies:
        ids = {c["contact_id"] for c in contacts if rule(c)}
        if len(ids) == 1:
            return next(iter(ids))
        if len(ids) > 1:
            return None
    return None


def _is_plausible_search_hit(res_user: object, full_name: str, email: str = "") -> bool:
    clean_u = username(get_user_field(res_user, "username"))
    if not clean_u:
        return False
    c_clean = clean_profile_name(full_name)
    c_parts = c_clean.split() if c_clean else []
    c_tokens = set(c_parts)

    res_clean = clean_profile_name(get_user_field(res_user, "full_name"))
    res_parts = res_clean.split() if res_clean else []
    res_tokens = set(res_parts)

    if res_clean and res_clean == c_clean:
        return True
    if len(c_tokens) >= 2 and len(res_tokens) >= 2 and (
        c_tokens.issubset(res_tokens) or res_tokens.issubset(c_tokens)
    ):
        return True
    if (
        len(c_parts) >= 2 and len(res_parts) >= 2 and c_parts[0] == res_parts[0]
        and (
            c_parts[-1] == res_parts[-1]
            or bool({s for s in c_parts[1:] if len(s) >= 4} & {s for s in res_parts[1:] if len(s) >= 4})
        )
    ):
        return True
    if compound_handle_match(clean_u, c_parts) and (not res_parts or res_parts[0] == c_parts[0]):
        return True
    email_local = (
        email.split("@", 1)[0].casefold().replace(".", "").replace("_", "")
        if email and "@" in email else ""
    )
    user_local = clean_u.replace(".", "").replace("_", "").casefold()
    if len(user_local) >= 4 and email_local and email_local == user_local:
        return True
    return False


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
    session_path: Optional[Path] = None,
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

    with review_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        if reader.fieldnames != list(REVIEW_COLUMNS):
            raise ValueError("Review CSV headers do not match documented schema.")
        review_rows = list(reader)

    review_by_id = {r["contact_id"]: r for r in review_rows}
    all_suggestions: list[object] = []

    cl = client_factory()
    if hasattr(cl, "delay_range"):
        cl.delay_range = [1, 3]
    if session_path and session_path.is_file() and hasattr(cl, "load_settings"):
        try:
            cl.load_settings(session_path)
        except Exception:
            pass
    cl.login(login, password)
    if session_path and hasattr(cl, "dump_settings"):
        try:
            session_path.parent.mkdir(parents=True, exist_ok=True)
            cl.dump_settings(session_path)
        except Exception:
            pass

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

    # 3. Multi-channel search for remaining pending contacts
    matched_from_search = 0
    has_any_search = any(
        hasattr(cl, attr)
        for attr in ("search_followers_v1", "fbsearch_topsearch_flat", "search_users_v1", "search_users")
    )
    if search_unmatched and has_any_search:
        contacts_by_id = {c["contact_id"]: c for c in contacts}
        studio_uid = str(getattr(cl, "user_id", "") or "")
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
            email = c.get("email", "")
            c_parts = name_parts(full_name)
            matched_this_contact = False

            # 3a. Priority check inside studio's own followers
            if studio_uid and c_parts and hasattr(cl, "search_followers_v1"):
                try:
                    f_hits = cl.search_followers_v1(studio_uid, c_parts[0])
                    if isinstance(f_hits, list):
                        for hit in f_hits:
                            u = username(get_user_field(hit, "username"))
                            if not u or u in assigned_usernames:
                                continue
                            if _is_plausible_search_hit(hit, full_name, email) and (
                                match_user_to_contact(hit, contacts) == row["contact_id"]
                            ):
                                row["candidate_username"] = u
                                row["discovery_method"] = "follower_search"
                                row["status"] = "candidate"
                                assigned_usernames.add(u)
                                matched_from_search += 1
                                matched_this_contact = True
                                break
                    if search_delay > 0:
                        time.sleep(search_delay * 0.5)
                except Exception:
                    pass

            if matched_this_contact:
                continue

            # 3b. Cascade search via TopSearch + nominal directory
            for idx, query in enumerate(build_search_queries(full_name, email)):
                try:
                    candidates_pool: list[object] = []
                    if idx == 0 and hasattr(cl, "fbsearch_topsearch_flat"):
                        try:
                            flat = cl.fbsearch_topsearch_flat(query)
                            if isinstance(flat, list):
                                for item in flat:
                                    unwrapped = extract_search_user(item)
                                    if unwrapped is not None:
                                        candidates_pool.append(unwrapped)
                        except Exception:
                            pass

                    if hasattr(cl, "search_users_v1"):
                        res = cl.search_users_v1(query, 15)
                        if isinstance(res, list):
                            candidates_pool.extend(res)
                    elif hasattr(cl, "search_users"):
                        res = cl.search_users(query)
                        if isinstance(res, list):
                            candidates_pool.extend(res)

                    seen_u: set[str] = set()
                    ranked: list[tuple[int, str, object]] = []
                    for raw_cand in candidates_pool:
                        u = username(get_user_field(raw_cand, "username"))
                        if not u or u in assigned_usernames or u in seen_u:
                            continue
                        seen_u.add(u)
                        if _is_plausible_search_hit(raw_cand, full_name, email):
                            sc, _ = score_candidate_for_contact(raw_cand, full_name, email)
                            ranked.append((sc, u, raw_cand))

                    ranked.sort(key=lambda item: item[0], reverse=True)
                    for _, u, raw_cand in ranked:
                        if match_user_to_contact(raw_cand, contacts) == row["contact_id"]:
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
    parser.add_argument("--session-file", type=Path, help="Optional private session JSON outside Git")
    parser.add_argument("--no-search", action="store_true", help="Disable nominal search for unmatched contacts")
    parser.add_argument("--limit-search", type=int, default=100, help="Max contacts to search nominally")
    args = parser.parse_args()

    if not args.confirm_sync:
        parser.exit(2, "ERROR: Explicit sync confirmation required (--confirm-sync).\n")

    env_file_vars = load_env_file(args.env_file)
    login = os.environ.get("BUSCAINSTA_IG_TEST_LOGIN") or env_file_vars.get("BUSCAINSTA_IG_TEST_LOGIN", "")
    password = os.environ.get("BUSCAINSTA_IG_TEST_PASSWORD") or env_file_vars.get("BUSCAINSTA_IG_TEST_PASSWORD", "")

    if not login or not password:
        parser.exit(2, "ERROR: Dedicated test account credentials missing (set in .env or environment).\n")

    try:
        session_path = None
        if args.session_file:
            from .dashboard_store import check_private_path
            session_path = check_private_path(args.session_file)
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
            session_path=session_path,
        )
        print(json.dumps(result, sort_keys=True))
        if result["unlink"] == "failed":
            parser.exit(3, "WARNING: Unlink failed; check contact settings in Instagram.\n")
    except (ValueError, OSError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")
    except Exception as exc:
        parser.exit(3, f"ERROR: Instagram live sync failed: {type(exc).__name__}. Check test account manually.\n")


if __name__ == "__main__":
    main()
