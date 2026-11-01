"""Mocked instagrapi probe: no real network or Meta account in CI."""
import csv

import pytest
from buscainsta.live_probe import candidate_usernames, run_probe
from buscainsta.cli import COLUMNS


def make_file(tmp_path, consent="yes"):
    p = tmp_path / "volunteer.csv"
    with p.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerow({
            "contact_id": "VOL-001", "full_name": "Voluntaria",
            "phone": "+55 48 99999-1234", "email": "test@example.invalid",
            "instagram": "@profile_known", "consent": consent,
            "consent_date": "2026-10-01", "consent_source": "voluntary_test_approval",
        })
    return p


class FakeClient:
    def __init__(self):
        self.calls = []
    def login(self, login, password):
        self.calls.append("login")
    def address_book_link(self, contacts):
        self.calls.append("link")
        assert len(contacts) == 1
        assert contacts[0]["phone_numbers"][0]["phone_number"] == "+5548999991234"
        return {"users": [{"username": "profile_known"}, {"username": "other"}]}
    def address_book_unlink(self):
        self.calls.append("unlink")


def test_one_volunteer_probe(tmp_path):
    p = make_file(tmp_path)
    client = FakeClient()
    result = run_probe(p, "VOL-001", "@profile_known", "tester", "secret", lambda: client)
    assert client.calls == ["login", "link", "unlink"]
    assert result["expected_username_in_suggestions"] is True
    assert result["candidate_count"] == 2
    assert result["unlink"] == "completed"
    assert "profile_known" not in str(result)
    assert "secret" not in str(result)


def test_authorization_required(tmp_path):
    p = make_file(tmp_path, consent="no")
    client = FakeClient()
    with pytest.raises(ValueError, match="lacks required authorization"):
        run_probe(p, "VOL-001", "@profile_known", "tester", "secret", lambda: client)
    assert client.calls == []


def test_no_guess_with_unknown_schema():
    assert candidate_usernames({"unexpected": [{"username": "abc"}]}) == set()
    assert candidate_usernames(None) == set()


def test_unlink_on_failed_upload(tmp_path):
    p = make_file(tmp_path)
    class FailingClient(FakeClient):
        def address_book_link(self, contacts):
            self.calls.append("link")
            raise RuntimeError("sensitive provider error")
    fake = FailingClient()
    with pytest.raises(RuntimeError):
        run_probe(p, "VOL-001", "profile_known", "tester", "secret", lambda: fake)
    assert fake.calls == ["login", "link", "unlink"]
