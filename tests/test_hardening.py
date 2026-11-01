"""Additional regression gates for synthetic isolation and conservative contact checks."""
import csv
import json
import subprocess
import sys

import pytest

from buscainsta.cli import COLUMNS, generate, normalize_email, normalize_phone, read_contacts, report, validate_row


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "buscainsta.cli", *map(str, args)],
        capture_output=True, text=True, timeout=15, check=False,
    )


@pytest.mark.parametrize("value", [
    "a@-example.com", "a@example-.com", "a@bad..com", "a@example.com/",
    "a..b@example.com", ".ab@example.com", "ab.@example.com",
    "a@example.com:443", "a@exam_ple.com", "a@exam ple.com",
    "a@éxample.com", "no-at-sign",
])
def test_email_malformed(value):
    assert normalize_email(value) == ""


@pytest.mark.parametrize("value, expected", [
    ("CLIENT+tag@Example.COM", "client+tag@example.com"),
    ("test001@example.invalid", "test001@example.invalid"),
])
def test_email_common_valid(value, expected):
    assert normalize_email(value) == expected


@pytest.mark.parametrize("value", [
    "２０４８９９９９９１２３４", "+55 20 99999-1234",
    "+55 48 19999-1234", "48 1333-4444",
    "48 99999-1234+", "48 99999-1234\n001",
])
def test_phone_rejects_invalid_ddd_and_confusables(value):
    assert normalize_phone(value) == ""


@pytest.mark.parametrize("value, expected", [
    ("+55 48 99999-1234", "+5548999991234"),
    ("(48) 3333-4444", "+554833334444"),
    ("0055 48 99999-1234", "+5548999991234"),
])
def test_phone_accepted_formats(value, expected):
    assert normalize_phone(value) == expected


def test_fixtures_never_contain_dialable_numbers(tmp_path):
    path = tmp_path / "synthetic.csv"
    generate(path, 100)
    rows = read_contacts(path)
    assert len(rows) == 100
    assert all(row["phone"] == "" for row in rows)
    assert all(row["email"].endswith("@example.invalid") for row in rows)
    assert report(rows, synthetic=True)["valid"] == 100


@pytest.mark.parametrize("column, altered, expected_issue", [
    ("phone", "+55 48 99999-1234", "synthetic_phone_must_be_empty"),
    ("instagram", "@existing_profile", "synthetic_instagram_must_be_empty"),
    ("consent_date", "2025-02-01", "synthetic_consent_date_must_be_empty"),
    ("full_name", "Pessoa diferente", "synthetic_name_mismatch"),
    ("email", "other@example.invalid", "synthetic_requires_reserved_email"),
    ("contact_id", "TEST-000", "synthetic_requires_TEST_id"),
])
def test_fixture_rejects_masquerading_data(tmp_path, column, altered, expected_issue):
    path = tmp_path / "synthetic.csv"
    generate(path, 1)
    row = read_contacts(path)[0]
    row[column] = altered
    assert expected_issue in validate_row(row, synthetic=True)


def test_local_mode_requires_opt_in(tmp_path):
    path = tmp_path / "sample.csv"
    generate(path, 1)
    out = run_cli("validate", "--input", path)
    assert out.returncode == 2
    assert "--synthetic" in out.stderr
    assert "--local-consented" in out.stderr


def test_implicit_consent_is_not_accepted(tmp_path):
    path = tmp_path / "consented.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerow(dict(
            contact_id="LOCAL-001", full_name="Pessoa Local",
            phone="", email="local@example.com", instagram="",
            consent="yes", consent_date="2025-01-01", consent_source="explicit_test_consent",
        ))
    implicit = run_cli("validate", "--input", path)
    assert implicit.returncode == 2
    opt_in = run_cli("validate", "--input", path, "--local-consented")
    assert opt_in.returncode == 0
    assert json.loads(opt_in.stdout)["mode"] == "consented_local"
    assert "local@example.com" not in opt_in.stdout + opt_in.stderr


def test_consent_does_not_validate_future_date():
    row = dict.fromkeys(COLUMNS, "")
    row.update(contact_id="LOCAL-002", full_name="Pessoa Local",
               email="local@example.com", consent="yes", consent_date="2999-01-01",
               consent_source="explicit_test_consent")
    assert "invalid_consent_date" in validate_row(row, synthetic=False)


def test_real_mode_does_not_autoconfirm_identity():
    row = dict.fromkeys(COLUMNS, "")
    row.update(contact_id="LOCAL-003", full_name="Pessoa Local",
               email="local@example.com", instagram="@not_verified",
               consent="yes", consent_date="2025-01-01", consent_source="test")
    assert validate_row(row, synthetic=False) == []
    # A valid row is merely syntactically valid; no actual Instagram lookup occurs.
    summary = report([row], synthetic=False)
    assert summary["instagram_lookup"] == "not_implemented"
    assert summary["network_calls"] == summary["external_uploads"] == 0
