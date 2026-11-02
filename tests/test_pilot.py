"""Tests for a genuinely usable, but manually reviewed, consented MVP."""
import csv
import json
from pathlib import Path

import pytest

from buscainsta.pilot import REVIEW_COLUMNS, prepare, summarize, username


def create_contacts(path: Path):
    path.write_text(
        "contact_id,full_name,phone,email,instagram,consent,consent_date,consent_source\n"
        "LOCAL-001,Pessoa A,,a@example.invalid,,yes,2025-01-01,explicit_pilot_opt_in\n"
        "LOCAL-002,Pessoa B,,b@example.invalid,@pessoa_b,yes,2025-01-01,explicit_pilot_opt_in\n",
        encoding="utf-8",
    )


def test_prepare_and_review_aggregate(tmp_path):
    inp = tmp_path / "source.csv"
    out = tmp_path / "review.csv"
    create_contacts(inp)
    result = prepare(inp, out)
    assert result["records"] == 2
    with out.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert list(rows[0]) == list(REVIEW_COLUMNS)
    assert "@" not in rows[1]["candidate_username"]
    assert len(rows[0]["invite_code"]) == 16
    assert rows[0]["invite_code"] != rows[1]["invite_code"]
    assert rows[1]["status"] == "candidate"
    rows[0].update(candidate_username="pessoa_a", discovery_method="native_contact_suggestion",
                   status="confirmed", confirmation_source="client_confirmed")
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        w.writeheader(); w.writerows(rows)
    summary = summarize(out)
    assert summary["confirmed"] == 1 and summary["candidates"] == 1
    assert summary["review_rate"] == 1
    assert "pessoa_a" not in json.dumps(summary)
    assert "LOCAL-" not in json.dumps(summary)


def test_no_output_if_missing_specific_consent(tmp_path):
    source = tmp_path / "source.csv"
    create_contacts(source)
    source.write_text(source.read_text().replace(",yes,", ",no,"), encoding="utf-8")
    output = tmp_path / "private.csv"
    with pytest.raises(ValueError, match="invalid or non-consented"):
        prepare(source, output)
    assert not output.exists()


def test_exclusive_file_creation(tmp_path):
    source, target = tmp_path / "source.csv", tmp_path / "review.csv"
    create_contacts(source)
    prepare(source, target)
    with pytest.raises(ValueError, match="overwrite"):
        prepare(source, target)


def test_cannot_write_inside_repo(tmp_path):
    source = tmp_path / "source.csv"
    create_contacts(source)
    folder = tmp_path / "repo"
    folder.mkdir()
    (folder / ".git").mkdir()
    with pytest.raises(ValueError, match="outside the Git repository"):
        prepare(source, folder / "review.csv")


@pytest.mark.parametrize("raw", ["bad/username", "@", "a" * 31, ".start", "end.", "two..dots"])
def test_username_invalid(raw):
    assert username(raw) == ""


@pytest.mark.parametrize("raw, expected", [("@joao.silva", "joao.silva"), ("Teste_25", "teste_25")])
def test_username_normalization(raw, expected):
    assert username(raw) == expected


def test_confirm_needs_client_evidence(tmp_path):
    source, target = tmp_path / "source.csv", tmp_path / "review.csv"
    create_contacts(source)
    prepare(source, target)
    with target.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    rows[0].update(candidate_username="someone", status="confirmed",
                   discovery_method="name_search", confirmation_source="")
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ValueError, match="requires evidence"):
        summarize(target)


def test_duplicate_confirmed_usernames_are_rejected(tmp_path):
    source, target = tmp_path / "source.csv", tmp_path / "review.csv"
    create_contacts(source)
    prepare(source, target)
    with target.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    for row in rows:
        row.update(candidate_username="same_username", status="confirmed",
                   discovery_method="client_self_reported",
                   confirmation_source="client_self_reported")
    with target.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        writer.writeheader(); writer.writerows(rows)
    with pytest.raises(ValueError, match="multiple contacts"):
        summarize(target)


def test_corrupt_review_file_rejected(tmp_path):
    target = tmp_path / "review.csv"
    target.write_text("invalid,csv\nvalue,test\n", encoding="utf-8")
    with pytest.raises(ValueError, match="headers"):
        summarize(target)
