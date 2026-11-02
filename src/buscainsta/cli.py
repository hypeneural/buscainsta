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
# Brazilian geographic DDDs; does not verify ownership, active service or number allocation.
BRAZIL_DDDS = frozenset((11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38, 41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68, 69, 71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95, 96, 97, 98, 99))


def normalize_email(value: str) -> str:
    """Practical ASCII mailbox syntax check; cannot verify delivery or ownership."""
    value = value.strip().lower()
    if len(value) > 254 or value.count("@") != 1 or not value.isascii():
        return ""
    local, domain = value.split("@", 1)
    if not (1 <= len(local) <= 64) or not re.fullmatch(r"[a-z0-9!#$%&'*+/=?^_`{|}~.-]+", local):
        return ""
    if local.startswith(".") or local.endswith(".") or ".." in local:
        return ""
    labels = domain.split(".")
    if len(labels) < 2 or any(
        not (1 <= len(label) <= 63)
        or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
        for label in labels
    ):
        return ""
    return value


def normalize_phone(value: str) -> str:
    """Conservative BR E.164 formatting; not a carrier or ownership check."""
    value = value.strip()
    # Only ASCII digits and permitted punctuation; reject Unicode look-alikes.
    if not re.fullmatch(r"[+0-9 \t().-]*", value) or value.count("+") > 1 or ("+" in value and not value.startswith("+")):
        return ""
    digits = re.sub(r"[^0-9]", "", value)
    if digits.startswith("0055") and len(digits) in (14, 15):
        digits = digits[4:]
    elif digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) not in (10, 11):
        return ""
    if int(digits[:2]) not in BRAZIL_DDDS:
        return ""
    if len(digits) == 11 and digits[2] != "9":
        return ""
    if len(digits) == 10 and digits[2] not in "2345":
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
        # Strict generated-fixture contract: prevents accidental real numbers
        # or real Instagram handles being classified as synthetic test input.
        match = re.fullmatch(r"TEST-([0-9]{3})", row["contact_id"])
        if not match or not 1 <= int(match.group(1)) <= MAX_ROWS:
            errors.append("synthetic_requires_TEST_id")
        else:
            number = match.group(1)
            if row["full_name"] != f"Pessoa Ficticia {number}":
                errors.append("synthetic_name_mismatch")
            if row["email"] != f"test{number}@example.invalid":
                errors.append("synthetic_requires_reserved_email")
        if row["phone"]:
            errors.append("synthetic_phone_must_be_empty")
        if row["instagram"]:
            errors.append("synthetic_instagram_must_be_empty")
        if row["consent_date"]:
            errors.append("synthetic_consent_date_must_be_empty")
        if row["consent"] != "test_only" or row["consent_source"] != "synthetic":
            errors.append("synthetic_marker_missing")
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
                phone="", email=f"test{i:03}@example.invalid",
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
    mode = validate.add_mutually_exclusive_group(required=True)
    mode.add_argument("--synthetic", action="store_true", help="Strict generated fixture only")
    mode.add_argument("--local-consented", action="store_true", help="Offline validation of specifically authorized data; never uploads")
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
