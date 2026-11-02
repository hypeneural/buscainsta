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
from buscainsta.dashboard import Handler
from buscainsta.instagram_actions import InstagramActions, photo_host_allowed
from buscainsta.live_sync import match_user_to_contact


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "private" / "clients.db"
    s.setup(path)
    rows = [
        ["C-001", "Cliente Exemplo", "", "cliente@example.invalid", "", "", "", ""],
        ["C-002", "Outra Pessoa", "", "outra@example.invalid", "", "", "", ""],
    ]
    source = tmp_path / "original.csv"
    with source.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(s.CONTACT_COLUMNS)
        writer.writerows(rows)
    assert s.import_contacts(path, source) == 2
    return path


def test_store_review_and_flags(db):
    assert s.list_contacts(db)["total"] == 2
    with pytest.raises(ValueError):
        s.set_verified(db, "C-001", True)
    s.set_candidate(db, "C-001", "@cliente_teste")
    assert s.get_contact(db, "C-001")["manually_verified"] == 0
    s.set_verified(db, "C-001", True)
    assert s.get_contact(db, "C-001")["manually_verified"] == 1
    s.set_dm_permission(db, "C-001", True)
    assert s.get_contact(db, "C-001")["dm_permitted"] == 1
    s.set_candidate(db, "C-001", "outro_cliente")
    row = s.get_contact(db, "C-001")
    assert row["manually_verified"] == 0
    assert row["dm_permitted"] == 0


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
        username="cliente_teste",pk="123",full_name="",is_private="unknown",
        follows_us="unknown",we_follow="unknown",profile_url="",photo_url=""
    ))
    s.reserve_dm(db,"C-001","conta","sha","x1")
    s.finish_dm(db,"C-001","x1",False)
    assert s.get_contact(db,"C-001")["last_dm_status"]=="unknown"
    with pytest.raises(ValueError):
        s.reserve_dm(db,"C-001","conta","sha","x2")


def test_duplicate_name_match_is_ambiguous():
    contacts = [
        {"contact_id":"a","full_name":"Maria Silva","email":"a@example.invalid"},
        {"contact_id":"b","full_name":"Maria Silva","email":"b@example.invalid"},
    ]
    assert match_user_to_contact({"username":"marias","full_name":"Maria Silva"},contacts) is None


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
        self.username = "conta_estudio"
    def login(self, login, password):
        self.login_name = login
    def user_info_by_username(self, user):
        return SimpleNamespace(username=user,pk="123",full_name="Cliente",
                               is_private=False,profile_pic_url="",profile_pic_url_hd=None)
    def user_friendship_v1(self, pk):
        return SimpleNamespace(followed_by=True,following=False)
    def direct_send(self, message, user_ids):
        self.sent += 1
        assert user_ids == [123]
        return SimpleNamespace(id="DIRECT-1")


def test_instagram_adapter_one_to_one(monkeypatch):
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_LOGIN", "tester")
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_PASSWORD", "redacted")
    fake=FakeIG()
    adapter=InstagramActions("conta_estudio",client_factory=lambda:fake)
    profile=adapter.inspect("cliente_teste")
    assert profile["follows_us"]=="yes"
    assert profile["we_follow"]=="no"
    assert profile["photo_url"]==""
    assert adapter.direct_once(profile["pk"],"Mensagem de teste")=="DIRECT-1"
    assert fake.sent==1


def test_local_ui_flow(db, monkeypatch):
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_LOGIN", "tester")
    monkeypatch.setenv("BUSCAINSTA_IG_TEST_PASSWORD", "redacted")
    provider=InstagramActions("conta_estudio",client_factory=FakeIG)
    srv=ThreadingHTTPServer(("127.0.0.1",0),Handler)
    srv.context=SimpleNamespace(db=db,account="conta_estudio",read_enabled=True,
        direct_enabled=True,message="Mensagem fixa",csrf="unit-test-token",
        provider=provider)
    thread=threading.Thread(target=srv.serve_forever,daemon=True)
    thread.start()
    base=f"http://127.0.0.1:{srv.server_port}"
    def get(path):
        with urlopen(base+path,timeout=3) as response:
            return response.read().decode("utf-8")
    def post(action,value,csrf=True):
        req=Request(base+"/api/contacts/C-001/"+action,
                    data=json.dumps(value).encode(),
                    headers={"Content-Type":"application/json",
                             "X-CSRF-Token":"unit-test-token" if csrf else "bad"},
                    method="POST")
        with urlopen(req,timeout=4) as response:
            return json.loads(response.read())
    try:
        assert "BuscaInsta" in get("/")
        assert json.loads(get("/api/contacts"))["total"]==2
        with pytest.raises(HTTPError) as blocked:
            post("candidate",{"username":"cliente_teste"},False)
        assert blocked.value.code==403
        post("candidate",{"username":"cliente_teste"})
        post("inspect",{})
        assert s.get_contact(db,"C-001")["follows_us"]=="yes"
        post("verify",{"value":True})
        post("direct-permission",{"value":True})
        post("send-direct",{"confirm":True})
        row=s.get_contact(db,"C-001")
        assert row["last_dm_status"]=="accepted" and row["last_dm_accepted_at"]
        with pytest.raises(HTTPError) as duplicate:
            post("send-direct",{"confirm":True})
        assert duplicate.value.code==409
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
