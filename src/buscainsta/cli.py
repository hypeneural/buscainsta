"""Offline tools. No Instagram client, network I/O, or CRM access."""
import argparse
import csv
import json
import re
import secrets
from collections import Counter
from datetime import date
from pathlib import Path

COLUMNS = ("contact_id", "full_name", "phone", "email", "instagram", "consent", "consent_date", "consent_source")
STATES = {"confirmed", "candidate", "not_found", "unreviewed"}

def normalize_email(value: str) -> str:
    value = value.strip().lower()
    return value if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value) else ""

def normalize_phone(value: str) -> str:
    """Conservative Brazil-only heuristic. Ambiguity is rejected; not a carrier validation."""
    digits = re.sub(r"\D", "", value)
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("55") and len(digits) in (12, 13):
        digits = digits[2:]
    if len(digits) == 11 and digits[2] == "9" and digits[:2] not in ("00",):
        return "+55" + digits
    if len(digits) == 10 and digits[:2] not in ("00",):
        return "+55" + digits
    return ""

def read_contacts(path: Path, maximum: int = 100) -> list[dict[str, str]]:
    if not path.is_file():
        raise ValueError("Input file not found.")
    if path.stat().st_size > 1_000_000:
        raise ValueError("Input too large (max 1 MB).")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or set(reader.fieldnames) != set(COLUMNS):
            raise ValueError("CSV headers must match the documented schema exactly.")
        rows = []
        ids = set()
        for raw in reader:
            if len(rows) >= maximum:
                raise ValueError("Maximum of 100 rows exceeded.")
            row = {key: (raw.get(key) or "").strip() for key in COLUMNS}
            if None in raw or not row["contact_id"] or row["contact_id"] in ids:
                raise ValueError("Malformed or duplicate contact_id.")
            ids.add(row["contact_id"])
            rows.append(row)
    return rows

def validate_row(row: dict[str, str], synthetic: bool) -> list[str]:
    errors = []
    if not row["full_name"]:
        errors.append("missing_name")
    if not (normalize_phone(row["phone"]) or normalize_email(row["email"])):
        errors.append("invalid_contact")
    if synthetic:
        if not row["contact_id"].startswith("TEST-"):
            errors.append("synthetic_requires_TEST_id")
    else:
        if row["consent"].casefold() != "yes":
            errors.append("missing_explicit_consent")
        try:
            stamp = date.fromisoformat(row["consent_date"])
            if stamp > date.today():
                errors.append("future_consent_date")
        except ValueError:
            errors.append("invalid_consent_date")
        if not row["consent_source"]:
            errors.append("missing_consent_source")
    return errors

def generate(path: Path, count: int) -> None:
    if not 1 <= count <= 100:
        raise ValueError("Generate between 1 and 100 synthetic rows.")
    if path.exists():
        raise ValueError("Refusing to overwrite an existing file.")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        for i in range(1, count + 1):
            writer.writerow(dict(contact_id=f"TEST-{i:03}", full_name=f"Pessoa Ficticia {i:03}", phone=f"4899{i:07d}", email=f"test{i:03}@example.invalid", instagram="", consent="test_only", consent_date="", consent_source="synthetic"))

def report(rows: list[dict[str, str]], synthetic: bool) -> dict:
    problems = Counter()
    for row in rows:
        problems.update(validate_row(row, synthetic))
    return {"mode": "synthetic" if synthetic else "consented_local", "total": len(rows), "valid": sum(not validate_row(r, synthetic) for r in rows), "invalid": sum(bool(validate_row(r, synthetic)) for r in rows), "issues": dict(problems), "network_calls": 0, "external_uploads": 0, "instagram_lookup": "not_implemented"}

def main() -> None:
    parser = argparse.ArgumentParser(description="BuscaInsta offline contact validation")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sample = sub.add_parser("sample", help="Generate synthetic CSV")
    sample.add_argument("--out", type=Path, default=Path("data/synthetic.csv"))
    sample.add_argument("--count", type=int, default=100)
    validate = sub.add_parser("validate", help="Validate CSV locally, no external calls")
    validate.add_argument("--input", required=True, type=Path)
    validate.add_argument("--synthetic", action="store_true")
    args = parser.parse_args()
    try:
        if args.cmd == "sample":
            generate(args.out, args.count)
            print(json.dumps({"status": "generated", "count": args.count, "mode": "synthetic", "path": str(args.out)}))
        else:
            print(json.dumps(report(read_contacts(args.input), args.synthetic), sort_keys=True))
    except (OSError, ValueError) as exc:
        parser.exit(2, f"ERROR: {exc}\n")

if __name__ == "__main__":
    main()
