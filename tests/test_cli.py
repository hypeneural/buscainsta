from pathlib import Path
import csv
import pytest
from buscainsta.cli import COLUMNS, generate, normalize_phone, normalize_email, read_contacts, report, validate_row

def test_phone_and_email():
    assert normalize_phone("(48) 99999-1234") == "+5548999991234"
    assert normalize_phone("+55 48 99999-1234") == "+5548999991234"
    assert normalize_phone("12345") == ""
    assert normalize_email(" NAME@Example.Com ") == "name@example.com"
    assert normalize_email("invalid") == ""

def test_generate_validate(tmp_path):
    path = tmp_path / "sample.csv"
    generate(path, 100)
    rows = read_contacts(path)
    result = report(rows, True)
    assert (result["total"], result["valid"], result["invalid"]) == (100, 100, 0)
    assert result["network_calls"] == 0
    with pytest.raises(ValueError, match="overwrite"):
        generate(path, 1)

def test_reject_real_without_consent():
    row = dict.fromkeys(COLUMNS, "")
    row.update(contact_id="CRM-1", full_name="Pessoa", email="x@example.com")
    assert "missing_explicit_consent" in validate_row(row, False)
    assert "invalid_consent_date" in validate_row(row, False)

def test_reject_oversize(tmp_path):
    path = tmp_path / "large.csv"
    generate(path, 100)
    with path.open("a", encoding="utf-8") as f:
        f.write("TEST-101,Extra,48999999999,extra@example.invalid,,test_only,,synthetic\n")
    with pytest.raises(ValueError, match="100"):
        read_contacts(path)

def test_duplicate_ids(tmp_path):
    path = tmp_path / "dupes.csv"
    generate(path, 1)
    with path.open("a", encoding="utf-8") as f:
        f.write("TEST-001,Extra,48999999999,extra@example.invalid,,test_only,,synthetic\n")
    with pytest.raises(ValueError, match="duplicate"):
        read_contacts(path)
