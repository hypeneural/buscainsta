"""Unit tests for batch live_sync and candidate matching."""
import csv
from pathlib import Path

from buscainsta.cli import COLUMNS
from buscainsta.live_sync import (
    clean_profile_name,
    contact_to_payload,
    load_env_file,
    match_user_to_contact,
    run_sync,
)
from buscainsta.pilot import REVIEW_COLUMNS


def create_consented_contacts(path: Path, count: int = 4) -> None:
    rows = []
    for i in range(1, count + 1):
        rows.append({
            "contact_id": f"TEST-{i:03d}",
            "full_name": f"Cliente Teste {i:03d}",
            "phone": f"+55 48 99123-{i:04d}",
            "email": f"test{i:03d}@example.invalid",
            "instagram": "",
            "consent": "yes",
            "consent_date": "2026-10-31",
            "consent_source": "test_consent",
        })
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)


def create_review_sheet(path: Path, count: int = 4) -> None:
    rows = []
    for i in range(1, count + 1):
        rows.append({
            "contact_id": f"TEST-{i:03d}",
            "invite_code": f"{i:016x}",
            "candidate_username": "",
            "discovery_method": "",
            "status": "pending",
            "confirmation_source": "",
        })
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=REVIEW_COLUMNS)
        w.writeheader()
        w.writerows(rows)


class FakeSyncClient:
    def __init__(self, responses=None):
        self.calls = []
        self.responses = responses or []
        self.response_idx = 0

    def login(self, login, password):
        self.calls.append(("login", login))

    def address_book_link(self, contacts):
        self.calls.append(("link", len(contacts)))
        if self.response_idx < len(self.responses):
            res = self.responses[self.response_idx]
            self.response_idx += 1
            return res
        return {"users": [], "suggested_users": []}

    def address_book_unlink(self):
        self.calls.append(("unlink",))


def test_contact_to_payload():
    row = {
        "full_name": "Ana Maria Silva",
        "phone": "+5548999991234",
        "email": "ana@example.com",
    }
    payload = contact_to_payload(row)
    assert payload["first_name"] == "Ana"
    assert payload["last_name"] == "Maria Silva"
    assert payload["phone_numbers"] == [{"phone_number": "+5548999991234"}]
    assert payload["email_addresses"] == [{"email_address": "ana@example.com"}]


def test_load_env_file(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comment\n"
        "BUSCAINSTA_IG_TEST_LOGIN = test_user \n"
        "BUSCAINSTA_IG_TEST_PASSWORD='secret_password'\n"
        "IGNORED_LINE\n",
        encoding="utf-8",
    )
    loaded = load_env_file(env_file)
    assert loaded["BUSCAINSTA_IG_TEST_LOGIN"] == "test_user"
    assert loaded["BUSCAINSTA_IG_TEST_PASSWORD"] == "secret_password"
    assert "IGNORED_LINE" not in loaded


def test_clean_profile_name_strips_bio_and_titles():
    assert clean_profile_name("Camila Pereira | Moda & Lifestyle") == "camila pereira"
    assert clean_profile_name("Dra. Ana Paula de Souza • Estética") == "ana paula souza"
    assert clean_profile_name("Arq. Juliana Costa - Interiores") == "juliana costa"


def test_match_user_to_contact_priority():
    contacts = [
        {"contact_id": "C-001", "full_name": "Juliana Santos"},
        {"contact_id": "C-002", "full_name": "Carlos Eduardo Lima"},
    ]

    # Priority 1: extra_display_name
    match1 = match_user_to_contact(
        {"username": "ju_santos_oficial", "extra_display_name": "Juliana Santos"},
        contacts,
    )
    assert match1 == "C-001"

    # Priority 2: full_name exact
    match2 = match_user_to_contact(
        {"username": "carlos_edu", "full_name": "Carlos Eduardo Lima"},
        contacts,
    )
    assert match2 == "C-002"

    # Priority 3: token overlap
    match3 = match_user_to_contact(
        {"username": "cadu_lima", "full_name": "Dr. Carlos Eduardo Lima Silva"},
        contacts,
    )
    assert match3 == "C-002"

    # No match
    assert match_user_to_contact({"username": "random_user", "full_name": "Desconhecido"}, contacts) is None


def test_match_bio_suffix_and_compound_username():
    contacts = [
        {"contact_id": "C-201", "full_name": "Camila Silva Pereira", "email": ""},
        {"contact_id": "C-202", "full_name": "Fernanda Costa Oliveira", "email": ""},
    ]
    # Bio suffix '| Moda & Lifestyle' previously polluted tokens and last name
    m1 = match_user_to_contact(
        {"username": "camilapereira.pera", "full_name": "Camila Pereira | Moda & Lifestyle"},
        contacts,
    )
    assert m1 == "C-201"

    # Compound @username with single-word display name
    m2 = match_user_to_contact(
        {"username": "arq.fernandaoliveira", "full_name": "Fernanda"},
        contacts,
    )
    assert m2 == "C-202"


def test_run_sync_batches_and_updates_review(tmp_path):
    contacts_path = tmp_path / "contacts.csv"
    review_path = tmp_path / "review.csv"
    create_consented_contacts(contacts_path, count=4)
    create_review_sheet(review_path, count=4)

    mock_responses = [
        {
            "users": [
                {"username": "cliente_001_ig", "extra_display_name": "Cliente Teste 001"},
            ]
        },
        {
            "suggested_users": [
                {"username": "cliente_003_ig", "full_name": "Cliente Teste 003"},
            ]
        },
    ]
    client = FakeSyncClient(responses=mock_responses)

    result = run_sync(
        contacts_path=contacts_path,
        review_path=review_path,
        login="tester",
        password="pwd",
        client_factory=lambda: client,
        batch_size=2,
        keep_linked=False,
        batch_delay=0,
    )

    assert result["status"] == "completed"
    assert result["contacts_submitted"] == 4
    assert result["suggestions_received"] == 2
    assert result["candidates_matched"] == 2
    assert result["unlink"] == "completed"

    assert client.calls == [
        ("login", "tester"),
        ("link", 2),
        ("link", 2),
        ("unlink",),
    ]

    with review_path.open("r", encoding="utf-8") as f:
        updated = list(csv.DictReader(f))

    assert updated[0]["contact_id"] == "TEST-001"
    assert updated[0]["candidate_username"] == "cliente_001_ig"
    assert updated[0]["status"] == "candidate"
    assert updated[0]["discovery_method"] == "native_contact_suggestion"

    assert updated[1]["contact_id"] == "TEST-002"
    assert updated[1]["status"] == "pending"
    assert updated[1]["candidate_username"] == ""

    assert updated[2]["contact_id"] == "TEST-003"
    assert updated[2]["candidate_username"] == "cliente_003_ig"
    assert updated[2]["status"] == "candidate"


def test_run_sync_keep_linked(tmp_path):
    contacts_path = tmp_path / "contacts.csv"
    review_path = tmp_path / "review.csv"
    create_consented_contacts(contacts_path, count=2)
    create_review_sheet(review_path, count=2)

    client = FakeSyncClient()
    result = run_sync(
        contacts_path=contacts_path,
        review_path=review_path,
        login="tester",
        password="pwd",
        client_factory=lambda: client,
        batch_size=2,
        keep_linked=True,
        batch_delay=0,
    )

    assert result["unlink"] == "not_requested"
    assert result["keep_linked"] is True
    assert ("unlink",) not in client.calls


def test_match_user_to_contact_accents_and_particles():
    contacts = [
        {"contact_id": "C-101", "full_name": "Jéssica de Souza Silva", "email": "jessica.souza@gmail.com"},
        {"contact_id": "C-102", "full_name": "Antônio Carlos dos Santos", "email": "toninho@empresa.com"},
    ]

    res1 = match_user_to_contact(
        {"username": "jessica_sz", "full_name": "Jessica Souza"},
        contacts,
    )
    assert res1 == "C-101"

    res2 = match_user_to_contact(
        {"username": "jessica.souza", "full_name": "J S"},
        contacts,
    )
    assert res2 == "C-101"

    res3 = match_user_to_contact(
        {"username": "antonio_cs", "extra_display_name": "Antonio Carlos dos Santos"},
        contacts,
    )
    assert res3 == "C-102"
