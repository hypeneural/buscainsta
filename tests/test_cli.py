"""Offline unit + CLI smoke checks; synthetic inputs only."""
import csv
import json
import subprocess
import sys

import pytest
from buscainsta.cli import (
    COLUMNS, generate, normalize_phone, normalize_email,
    read_contacts, report, validate_row, MAX_ROWS,
)


def invoke(*args):
    return subprocess.run(
        [sys.executable, "-m", "buscainsta.cli", *map(str, args)],
        text=True, capture_output=True, timeout=15, check=False,
    )


@pytest.mark.parametrize(("source", "expected"), [
    ("(48) 99999-1234", "+5548999991234"),
    ("+55 48 99999-1234", "+5548999991234"),
    ("0055 48 99999-1234", "+5548999991234"),
    ("48 3333-4444", "+554833334444"),
    ("12345", ""), ("x48 99999-1234", ""), ("0048 99999-1234", ""),
    ("00 99999-1234", ""),
])
def test_phone(source, expected):
    assert normalize_phone(source) == expected


def test_email():
    assert normalize_email(" NAME@Example.Com ") == "name@example.com"
    assert normalize_email("invalid") == ""


def test_generate_validate(tmp_path):
    path = tmp_path / "synthetic.csv"
    generate(path, 100)
    rows = read_contacts(path)
    result = report(rows, True)
    assert (result["total"], result["valid"], result["invalid"]) == (100, 100, 0)
    assert result["external_uploads"] == result["network_calls"] == 0
    with pytest.raises(ValueError, match="overwrite"):
        generate(path, 1)


def test_cli_doctor_no_paths_or_pii():
    completed = invoke("doctor")
    assert completed.returncode == 0, completed.stderr
    info = json.loads(completed.stdout)
    assert info["python_supported"] is True
    assert info["instagram_integration"] == "not_implemented"


def test_cli_smoke(tmp_path):
    path = tmp_path / "sample.csv"
    generated = invoke("sample", "--out", path, "--count", "100")
    assert generated.returncode == 0, generated.stderr
    checked = invoke("validate", "--input", path, "--synthetic")
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)["valid"] == 100
    repeated = invoke("sample", "--out", path, "--count", "100")
    assert repeated.returncode == 2
    assert "overwrite" in repeated.stderr


def test_invalid_csv_exit_code(tmp_path):
    path = tmp_path / "sample.csv"
    generate(path, 1)
    data = path.read_text(encoding="utf-8")
    path.write_text(data.replace("test001@example.invalid", "test001@example.com"), encoding="utf-8")
    invalid = invoke("validate", "--input", path, "--synthetic")
    assert invalid.returncode == 2
    summary = json.loads(invalid.stdout)
    assert summary["invalid"] == 1
    assert summary["issues"]["synthetic_requires_reserved_email"] == 1
    assert "test001@example.com" not in invalid.stdout + invalid.stderr


def test_missing_consent():
    row = dict.fromkeys(COLUMNS, "")
    row.update(contact_id="LOCAL-1", full_name="Pessoa", email="local@example.invalid")
    assert "missing_explicit_consent" in validate_row(row, False)
    assert "invalid_consent_date" in validate_row(row, False)


def test_synthetic_requires_markers():
    row = dict.fromkeys(COLUMNS, "")
    row.update(contact_id="TEST-001", full_name="Pessoa", email="a@example.invalid")
    assert "synthetic_marker_missing" in validate_row(row, True)


def test_rows_exceed_limit(tmp_path):
    path = tmp_path / "large.csv"
    generate(path, MAX_ROWS)
    with path.open("a", encoding="utf-8") as f:
        f.write("TEST-101,Extra,48999999999,extra@example.invalid,,test_only,,synthetic\n")
    with pytest.raises(ValueError, match="100"):
        read_contacts(path)


def test_duplicate_ids(tmp_path):
    path = tmp_path / "duplicates.csv"
    generate(path, 1)
    with path.open("a", encoding="utf-8") as f:
        f.write("TEST-001,Extra,48999999999,extra@example.invalid,,test_only,,synthetic\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_contacts(path)


@pytest.mark.parametrize("content", [
    ",".join(COLUMNS) + "\n",
    "contact_id,full_name,phone,email,instagram,consent,consent_date,consent_date\n",
])
def test_bad_headers_or_empty(tmp_path, content):
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match="headers|no contact"):
        read_contacts(path)


def test_incomplete_record(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text(",".join(COLUMNS) + "\nTEST-001,Person,48999999999\n", encoding="utf-8")
    with pytest.raises(ValueError, match="incomplete"):
        read_contacts(path)


def test_report_does_not_print_pii(tmp_path):
    path = tmp_path / "sample.csv"
    generate(path, 1)
    output = str(report(read_contacts(path), True))
    assert "Pessoa Ficticia" not in output
    assert "test001@example.invalid" not in output
    assert "48990000001" not in output


def test_synthetic_csv_values(tmp_path):
    path = tmp_path / "s.csv"
    generate(path, 2)
    with path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    assert all(row["consent"] == "test_only" for row in rows)
    assert all(row["email"].endswith("@example.invalid") for row in rows)


def test_invalid_utf8_hides_bytes(tmp_path):
    path = tmp_path / "encoding.csv"
    path.write_bytes(b"\xff\xfe")
    failed = invoke("validate", "--input", path, "--synthetic")
    assert failed.returncode == 2
    assert failed.stderr.strip() == "ERROR: Input must be UTF-8."
