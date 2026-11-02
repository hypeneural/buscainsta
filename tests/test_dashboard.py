"""Dashboard P0 regression tests. All profiles, images and Directs are mocked."""
import csv
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from buscainsta import dashboard_store as s
from buscainsta.dashboard import (
    Handler,
    extract_first_name,
    load_or_create_csrf,
    render_direct_message,
)
from buscainsta.instagram_actions import InstagramActions, photo_host_allowed
from buscainsta.live_sync import match_user_to_contact


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "private" / "clients.db"
    s.setup(path)
    rows = [
        ["C-001", "Camila Exemplo", "", "cliente@example.invalid", "", "", "", ""],
        ["C-002", "Outra Pessoa", "", "outra@example.invalid", "", "", "", ""],
    ]
    source = tmp_path / "original.csv"
    with source.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(s.CONTACT_COLUMNS)
        writer.writerows(rows)
    assert s.import_contacts(path, source) == 2
    return path


def test_extract_first_name_and_render_direct_message():
    assert extract_first_name("CAMILA PEREIRA") == "Camila"
    assert extract_first_name("Dra. Ana-Clara Souza") == "Ana-Clara"
    assert extract_first_name("Cliente CRM 1299") == ""
    assert render_direct_message("Oi {primeiro_nome}, Tudo bem?", "CAMILA PEREIRA") == "Oi Camila, Tudo bem?"
    assert render_direct_message("Oi {primeiro_nome}, Tudo bem?", "Cliente CRM 1299") == "Oi, Tudo bem?"


def test_store_review_and_flags(db):
    assert s.list_contacts(db)["total"] == 2
    with pytest.raises(ValueError):
        s.set_verified(db, "C-001", True)
    s.set_candidate(db, "C-001", "@cliente_teste")
    assert s.get_contact(db, "C-001")["manually_verified"] == 0
    s.set_verified(db, "C-001", True)
    assert s.get_contact(db, "C-001")["manually_verified"] == 1
    assert s.get_contact(db, "C-001")["dm_permitted"] == 0
    s.set_dm_permission(db, "C-001", True)
    assert s.get_contact(db, "C-001")["dm_permitted"] == 1
    s.set_candidate(db, "C-001", "outro_cliente")
    row = s.get_contact(db, "C-001")
    assert row["manually_verified"] == 0
    assert row["dm_permitted"] == 0


def test_store_auto_permit_and_reject(db):
    s.set_candidate(db, "C-001", "@cliente_teste")
    s.set_verified(db, "C-001", True, auto_permit_dm=True)
    row = s.get_contact(db, "C-001")
    assert row["manually_verified"] == 1
    assert row["dm_permitted"] == 1
    assert row["status"] == "manual_checked"

    s.set_rejected(db, "C-001", True)
    rejected = s.get_contact(db, "C-001")
    assert rejected["manually_verified"] == 0
    assert rejected["dm_permitted"] == 0
    assert rejected["status"] == "rejected"
    assert s.dashboard_stats(db)["rejected"] == 1

    s.set_rejected(db, "C-001", False)
    restored = s.get_contact(db, "C-001")
    assert restored["status"] == "candidate"


def test_persistent_csrf_across_restarts(db):
    token1 = load_or_create_csrf(db)
    token2 = load_or_create_csrf(db)
    assert len(token1) >= 24
    assert token1 == token2


def test_follow_statuses_are_account_specific(db):
    s.set_candidate(db, "C-001", "cliente_teste")
    payload = dict(username="cliente_teste", pk="123", full_name="Cliente Teste",
                   is_private="no", follows_us="yes", we_follow="no",
                   profile_url="https://www.instagram.com/cliente_teste/", photo_url="")
    s.save_profile(db, "C-001", "estudio_teste", payload)
    row = s.get_contact(db, "C-001")
    assert row["follows_us"] == "yes"
    assert row["we_follow"] == "no"
    assert row["checked_account"] == "estudio_teste"
    with pytest.raises(ValueError):
        s.save_profile(db, "C-001", "estudio_teste", {**payload, "username": "outro"})


def test_dm_guard_and_atomic_reservation(db):
    s.set_candidate(db, "C-001", "cliente_teste")
    profile = dict(username="cliente_teste", pk="123", full_name="Cliente",
                   is_private="no", follows_us="unknown", we_follow="unknown",
                   profile_url="https://www.instagram.com/cliente_teste/", photo_url="")
    s.save_profile(db, "C-001", "conta_estudio", profile)
    with pytest.raises(ValueError):
        s.reserve_dm(db, "C-001", "conta_estudio", "abc", "a1")
    s.set_verified(db, "C-001", True)
    s.set_dm_permission(db, "C-001", True)
    with pytest.raises(ValueError):
        s.reserve_dm(db, "C-001", "outra_conta", "abc", "a1")
    s.reserve_dm(db, "C-001", "conta_estudio", "abc", "a1")
    with pytest.raises(ValueError):
        s.reserve_dm(db, "C-001", "conta_estudio", "abc", "a2")
    s.finish_dm(db, "C-001", "a1", True, "DM123")
    row = s.get_contact(db, "C-001")
    assert row["last_dm_status"] == "accepted"
    assert row["last_dm_accepted_at"].endswith("+00:00")
    with pytest.raises(ValueError):
        s.reserve_dm(db, "C-001", "conta_estudio", "abc", "a3")


def test_dm_unknown_not_retried(db):
    s.set_candidate(db, "C-001", "cliente_teste")
    s.set_verified(db, "C-001", True)
    s.set_dm_permission(db, "C-001", True)
    s.save_profile(db, "C-001", "conta", dict(
        username="cliente_teste", pk="123", full_name="", is_private="unknown",
        follows_us="unknown", we_follow="unknown", profile_url="", photo_url=""
    ))
    s.reserve_dm(db, "C-001", "conta", "sha", "x1")
    s.finish_dm(db, "C-001", "x1", False)
    assert s.get_contact(db, "C-001")["last_dm_status"] == "unknown"
    with pytest.raises(ValueError):
        s.reserve_dm(db, "C-001", "conta", "sha", "x2")


def test_duplicate_name_match_is_ambiguous():
    contacts = [
        {"contact_id": "a", "full_name": "Maria Silva", "email": "a@example.invalid"},
        {"contact_id": "b", "full_name": "Maria Silva", "email": "b@example.invalid"},
    ]
    assert match_user_to_contact({"username": "marias", "full_name": "Maria Silva"}, contacts) is None


def test_image_allowlist():
    assert photo_host_allowed("https://scontent.cdninstagram.com/v/avatar.jpg")
    assert photo_host_allowed("https://scontent.xx.fbcdn.net/profile.jpg")
    assert not photo_host_allowed("http://scontent.cdninstagram.com/x")
    assert not photo_host_allowed("https://cdninstagram.com.attacker.test/x")
    assert not photo_host_allowed("https://127.0.0.1/image")
    assert not photo_host_allowed("https://user:pass@cdninstagram.com/x")


class FakeIG:
    def __init__(self):
        self.sent = 0
        self.last_message = ""
        self.username = "conta_estudio"
        self.user_id = "999000"
        self.last_json = {}

    def login(self, login, password):
        self.login_name = login

    def user_info_by_username_v1(self, user):
        return SimpleNamespace(
            username=user, pk="123", full_name="Camila Exemplo | Moda & Lifestyle",
            is_private=True, profile_pic_url="", profile_pic_url_hd=None
        )

    def user_friendship_v1(self, pk):
        return SimpleNamespace(followed_by=True, following=False)

    def user_friendships_v1(self, pks):
        return [SimpleNamespace(user_id=str(pk), following=False, is_private=False) for pk in pks]

    def search_followers_v1(self, uid, query):
        return [
            SimpleNamespace(
                username="camilaexemplo.oficial", pk="123",
                full_name="Camila Exemplo | Moda & Lifestyle", is_private=False
            )
        ]

    def fbsearch_topsearch_flat(self, query):
        return [
            {
                "position": 0,
                "user": {
                    "username": "outro_perfil",
                    "pk": "456",
                    "full_name": "Cliente Outra Cidade",
                    "is_private": True,
                },
            }
        ]

    def direct_send(self, message, user_ids):
        self.sent += 1
        self.last_message = message
        assert user_ids == [123]
        return SimpleNamespace(id="DIRECT-1")


def test_private_profile_missing_reel_flags_fallback(monkeypatch):
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_LOGIN", "tester")
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_PASSWORD", "redacted")

    class PrivateProfileIG(FakeIG):
        def user_friendship_v1(self, pk):
            # Simulate instagrapi Pydantic ValidationError on private profiles
            self.last_json = {"user_id": pk, "followed_by": False, "following": False, "status": "ok"}
            raise RuntimeError("ValidationError: is_blocking_reel Field required")

    adapter = InstagramActions("conta_estudio", client_factory=PrivateProfileIG)
    prof = adapter.inspect("perfil_privado")
    assert prof["is_private"] == "yes"
    assert prof["follows_us"] == "no"
    assert prof["we_follow"] == "no"


def test_instagram_adapter_one_to_one_and_search(monkeypatch, tmp_path):
    monkeypatch.delenv("BUSCAINSTA_IG_TEST_LOGIN", raising=False)
    monkeypatch.delenv("BUSCAINSTA_IG_TEST_PASSWORD", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BUSCAINSTA_IG_TEST_LOGIN=tester\nBUSCAINSTA_IG_TEST_PASSWORD=redacted\n",
        encoding="utf-8",
    )
    fake = FakeIG()
    adapter = InstagramActions(
        "conta_estudio",
        client_factory=lambda: fake,
        session_dir=tmp_path / "sessions",
        env_file=env_file,
    )
    assert adapter.has_credentials() is True
    profile = adapter.inspect("cliente_teste")
    assert profile["follows_us"] == "yes"
    assert profile["we_follow"] == "no"
    assert profile["photo_url"] == ""

    hits = adapter.search_candidates("Camila Exemplo")
    assert len(hits) >= 1
    assert hits[0]["username"] == "camilaexemplo.oficial"
    assert hits[0]["follows_us"] == "yes"
    assert hits[0]["we_follow"] == "no"
    assert hits[0]["score"] >= 90

    assert adapter.direct_once(profile["pk"], "Mensagem de teste") == "DIRECT-1"
    assert fake.sent == 1


def test_local_ui_flow(db, monkeypatch, tmp_path):
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_LOGIN", "tester")
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_PASSWORD", "redacted")
    fake = FakeIG()
    provider = InstagramActions("conta_estudio", client_factory=lambda: fake)
    msg_file = tmp_path / "private" / "mensagem.txt"
    msg_file.write_text("Mensagem inicial", encoding="utf-8")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.context = SimpleNamespace(
        db=db, account="conta_estudio", read_enabled=True,
        direct_enabled=True, message="Mensagem inicial", message_file=msg_file,
        csrf="unit-test-token", provider=provider
    )
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{srv.server_port}"

    def get(path):
        with urlopen(base + path, timeout=3) as response:
            return response.read().decode("utf-8")

    def post_raw(url_path, value, csrf=True):
        req = Request(
            base + url_path,
            data=json.dumps(value).encode(),
            headers={
                "Content-Type": "application/json",
                "X-CSRF-Token": "unit-test-token" if csrf else "bad",
            },
            method="POST",
        )
        with urlopen(req, timeout=4) as response:
            return json.loads(response.read())

    def post(action, value, csrf=True):
        return post_raw("/api/contacts/C-001/" + action, value, csrf=csrf)

    try:
        html = get("/")
        assert "BuscaInsta" in html
        assert "Permissão Direct" not in html
        assert "photoDialog" in html
        assert "Pesquisar IG" in html
        assert "<svg" in get("/favicon.ico")
        cfg = json.loads(get("/api/config"))
        assert cfg["csrf_token"] == "unit-test-token"
        assert json.loads(get("/api/contacts"))["total"] == 2
        with pytest.raises(HTTPError) as blocked:
            post("candidate", {"username": "cliente_teste"}, False)
        assert blocked.value.code == 403

        # Update Direct template with {primeiro_nome}
        updated_tpl = post_raw("/api/message", {"message": "Oi {primeiro_nome}, Tudo bem?"})
        assert updated_tpl["fixed_message"] == "Oi {primeiro_nome}, Tudo bem?"
        assert msg_file.read_text(encoding="utf-8").strip() == "Oi {primeiro_nome}, Tudo bem?"

        search_res = post("search-ig", {})
        assert search_res["candidates"][0]["username"] == "camilaexemplo.oficial"

        post("select-candidate", {"username": "cliente_teste"})
        assert s.get_contact(db, "C-001")["follows_us"] == "yes"
        assert s.get_contact(db, "C-001")["we_follow"] == "no"

        post("reject", {"value": True})
        assert s.get_contact(db, "C-001")["status"] == "rejected"

        post("verify", {"value": True, "auto_permit_dm": True})
        verified_row = s.get_contact(db, "C-001")
        assert verified_row["manually_verified"] == 1
        assert verified_row["dm_permitted"] == 1

        post("send-direct", {"confirm": True})
        assert fake.last_message == "Oi Camila, Tudo bem?"
        row = s.get_contact(db, "C-001")
        assert row["last_dm_status"] == "accepted" and row["last_dm_accepted_at"]
        with pytest.raises(HTTPError) as duplicate:
            post("send-direct", {"confirm": True})
        assert duplicate.value.code == 409
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=2)


def test_reject_wrong_authenticated_account(monkeypatch):
    from buscainsta.instagram_actions import PublicSafeError
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_LOGIN", "tester")
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_PASSWORD", "redacted")

    class WrongAccount(FakeIG):
        def __init__(self):
            super().__init__()
            self.username = "somebody_else"

    adapter = InstagramActions("conta_estudio", client_factory=WrongAccount)
    with pytest.raises(PublicSafeError, match="login unavailable|differs"):
        adapter.inspect("cliente_teste")
