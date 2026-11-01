"""BuscaInsta POC: local CSV checks only. No Instagram, CRM or network calls."""
import argparse
import csv
import json
import platform
import re
import sys
from collections import Counter
from datetime import date
from pathlib import Path

COLUMNS = ("contact_id", "full_name", "phone", "email", "instagram", "consent", "consent_date", "consent_source")
MAX_ROWS = 100
MAX_BYTES = 1_000_000
MAX_FIELD_CHARS = 512


def normalize_email(value: str) -> str:
    value = value.strip().lower()
    return value if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) else ""


def normalize_phone(value: str) -> str:
    """Conservative BR E.164 formatting; not a carrier or ownership check."""
    value = value.strip()
    if not re.fullmatch(r"[+\d\s().-]*", value):
        return ""
    digits = re.sub(r"\D", "", value)
    if digits.startswith("0055") and len(digits) in (14, 15):
        digits = digits[4:]
    elif digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        return ""
    if digits[0] == "0" or digits[1] == "0":
        return ""
    if len(digits) == 11 and digits[2] != "9":
        return ""
    return "+55" + digits


def read_contacts(path: Path, maximum: int = MAX_ROWS) -> list[dict[str, str]]:
    if maximum < 1 or maximum > MAX_ROWS:
        raise ValueError("Invalid maximum row limit.")
    if not path.is_file():
        raise ValueError("Input file was not found.")
    if path.stat().st_size > MAX_BYTES:
        raise ValueError("CSV exceeds 1 MB limit.")
    rows: list[dict[str, str]] = []
    ids: set[str] = set()
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, strict=True)
        headers = reader.fieldnames
        if not headers or len(headers) != len(COLUMNS) or set(headers) != set(COLUMNS):
            raise ValueError("CSV headers do not match documented schema.")
        for raw in reader:
            if len(rows) >= maximum:
                raise ValueError("More than 100 records supplied.")
            if None in raw or any(raw.get(column) is None for column in COLUMNS):
                raise ValueError("CSV has malformed or incomplete records.")
            row = {column: str(raw[column]).strip() for column in COLUMNS}
            if any(len(value) > MAX_FIELD_CHARS or "\x00" in value for value in row.values()):
                raise ValueError("CSV contains an oversized or invalid field.")
            if not row["contact_id"] or row["contact_id"] in ids:
                raise ValueError("CSV contains an empty or duplicate contact_id.")
            ids.add(row["contact_id"])
            rows.append(row)
    if not rows:
        raise ValueError("CSV has no contact records.")
    return rows


def validate_row(row: dict[str, str], synthetic: bool) -> list[str]:
    errors: list[str] = []
    if not row["full_name"]:
        errors.append("missing_name")
    phone_valid = normalize_phone(row["phone"]) if row["phone"] else ""
    email_valid = normalize_email(row["email"]) if row["email"] else ""
    if row["phone"] and not phone_valid:
        errors.append("invalid_phone")
    if row["email"] and not email_valid:
        errors.append("invalid_email")
    if not (phone_valid or email_valid):
        errors.append("missing_valid_contact")
    if synthetic:
        if not row["contact_id"].startswith("TEST-"):
            errors.append("synthetic_requires_TEST_id")
        if row["consent"] != "test_only" or row["consent_source"] != "synthetic":
            errors.append("synthetic_marker_missing")
        if row["email"] and not row["email"].lower().endswith("@example.invalid"):
            errors.append("synthetic_requires_reserved_email")
    else:
        if row["consent"].casefold() != "yes":
            errors.append("missing_explicit_consent")
        try:
            stamp = date.fromisoformat(row["consent_date"])
            if stamp.isoformat() != row["consent_date"] or stamp > date.today():
                errors.append("invalid_consent_date")
        except ValueError:
            errors.append("invalid_consent_date")
        if not row["consent_source"]:
            errors.append("missing_consent_source")
    return errors


def generate(path: Path, count: int) -> None:
    if not 1 <= count <= MAX_ROWS:
        raise ValueError("Generate between 1 and 100 synthetic rows.")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = path.open("x", encoding="utf-8", newline="")
    except FileExistsError as exc:
        raise ValueError("Refusing to overwrite an existing file.") from exc
    with handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for i in range(1, count + 1):
            writer.writerow(dict(
                contact_id=f"TEST-{i:03}", full_name=f"Pessoa Ficticia {i:03}",
                phone=f"4899{i:07d}", email=f"test{i:03}@example.invalid",
                instagram="", consent="test_only", consent_date="", consent_source="synthetic",
            ))


def report(rows: list[dict[str, str]], synthetic: bool) -> dict:
    issues: Counter[str] = Counter()
    valid = 0
    for row in rows:
        problems = validate_row(row, synthetic)
        issues.update(problems)
        if not problems:
            valid += 1
    return {
        "mode": "synthetic" if synthetic else "consented_local",
        "total": len(rows), "valid": valid, "invalid": len(rows) - valid,
        "issues": dict(sorted(issues.items())),
        "network_calls": 0, "external_uploads": 0,
        "instagram_lookup": "not_implemented",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="BuscaInsta: offline validation only")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sample = sub.add_parser("sample", help="Create reserved-email synthetic contacts")
    sample.add_argument("--out", type=Path, default=Path("data/synthetic.csv"))
    sample.add_argument("--count", type=int, default=100)
    validate = sub.add_parser("validate", help="Check local CSV with aggregated output")
    validate.add_argument("--input", type=Path, required=True)
    validate.add_argument("--synthetic", action="store_true")
    sub.add_parser("doctor", help="Show PII-free runtime diagnostics")
    args = parser.parse_args()
    try:
        if args.cmd == "sample":
            generate(args.out, args.count)
            print(json.dumps({"status": "generated", "mode": "synthetic", "count": args.count}))
        elif args.cmd == "doctor":
            print(json.dumps({
                "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
                "os": platform.system(), "python_supported": sys.version_info >= (3, 11),
                "crm_integration": "not_implemented",
                "instagram_integration": "not_implemented",
            }, sort_keys=True))
            if sys.version_info < (3, 11):
                parser.exit(2)
        else:
            result = report(read_contacts(args.input), args.synthetic)
            print(json.dumps(result, sort_keys=True))
            if result["invalid"]:
                parser.exit(2)
    except UnicodeError:
        parser.exit(2, "ERROR: Input must be UTF-8.\n")
    except csv.Error:
        parser.exit(2, "ERROR: Invalid CSV format.\n")
    except (OSError, ValueError) as exc:
        # Never print CSV row values. File names must be kept out of public reports.
        if isinstance(exc, OSError):
            parser.exit(2, "ERROR: File I/O failed.\n")
        parser.exit(2, f"ERROR: {exc}\n")


if __name__ == "__main__":
    main()
