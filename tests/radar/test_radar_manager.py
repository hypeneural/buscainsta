"""Manager and HTTP regression tests. No third-party network access."""
import json
import threading
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from buscainsta.radar import query, store
from buscainsta.radar.server import create_server


def example(external, username="amizphoto", when="2026-11-01T10:00:00-03:00",
            kind="image", caption="Ensaio de Natal", **more):
    return {"source": "fixture", "external_id": external, "username": username,
            "kind": kind, "posted_at": when, "caption": caption, **more}


def test_profile_onboarding_and_disable(tmp_path):
    root = tmp_path / "archive"
    store.initialize(root)
    a = query.add_profile(root, "https://www.instagram.com/amizphoto/", "Foto Amiz")
    assert a["username"] == "amizphoto"
    query.add_profile(root, "@AMIZPHOTO")
    assert len(query.profiles(root)) == 1
    assert query.profiles(root)[0]["profile_name"] == "Foto Amiz"
    assert query.set_profile(root, "amizphoto", False)["enabled"] is False
    assert query.profiles(root)[0]["enabled"] == 0
    with pytest.raises(ValueError):
        query.set_profile(root, "not_registered", True)
    with pytest.raises(ValueError):
        query.set_profile(root, "amizphoto", 1)
    for value in ("https://www.instagram.com/p/abc123/", "https://other.test/fake/",
                  "https://www.instagram.com/amizphoto/?secret=a", "../escape"):
        with pytest.raises(ValueError):
            query.normalize_username(value)


def test_recent_timeline_date_search_and_null_metrics(tmp_path):
    root = tmp_path / "archive"
    store.initialize(root)
    first = store.upsert_post(root, example("older", caption="Bastidores do Natal",
                     when="2026-11-01T09:00:00-03:00", likes=8))
    store.upsert_post(root, example("newer", "brunacarlafoto", "2026-11-01T15:00:00-03:00",
                     kind="video", caption="Ofertas 10%", likes=27))
    store.upsert_post(root, example("next-day", "brunacarlafoto", "2026-11-02T00:05:00-03:00",
                     kind="carousel", caption="Música nova", likes=None))
    result = query.search_posts(root)
    assert [r["external_id"] for r in result["items"]] == ["next-day", "newer", "older"]
    assert result["total"] == 3
    assert query.search_posts(root, from_date="2026-11-01", to_date="2026-11-01")["total"] == 2
    assert query.search_posts(root, search="10%")["total"] == 1
    assert query.search_posts(root, kind="video", username="brunacarlafoto")["total"] == 1
    assert [r["external_id"] for r in query.search_posts(root, sort="likes")["items"]] == [
        "newer", "older", "next-day"]
    assert query.search_posts(root, limit=1)["has_more"]
    assert query.search_posts(root, limit=1, offset=2)["has_more"] is False
    assert query.search_posts(root, archived="missing")["total"] == 3
    pic = tmp_path / "image.jpg"
    pic.write_bytes(b"\xff\xd8\xff" + b"x" * 30)
    store.put_asset(root, first, 0, "image", pic)
    assert query.search_posts(root, archived="local")["total"] == 1
    assert query.overview(root)["archived_posts"] == 1
    with pytest.raises(ValueError):
        query.search_posts(root, from_date="2026-11-02", to_date="2026-11-01")
    with pytest.raises(ValueError):
        query.search_posts(root, sort="DROP TABLE posts")


def test_stable_identity_if_permalink_missing_on_next_import(tmp_path):
    root = tmp_path / "archive"
    store.initialize(root)
    first = store.upsert_post(root, example("same", permalink="https://www.instagram.com/reel/XYZ123/"))
    second = store.upsert_post(root, example("same", permalink="", likes=14))
    assert first == second
    assert query.search_posts(root)["total"] == 1
    # Simulate older private archive missing new identity mapping table.
    with store.db_connect(root) as db:
        db.execute("DROP TABLE post_identities")
    store.initialize(root)
    third = store.upsert_post(root, example("same", likes=18))
    assert third == first


@pytest.fixture
def running_server(tmp_path):
    root = tmp_path / "radar"
    server = create_server(root, port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server, root, f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def request_json(url, path, method="GET", payload=None, token=None, origin=None):
    headers = {}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
        if token is not None:
            headers["X-Radar-CSRF"] = token
        if origin is not None:
            headers["Origin"] = origin
    req = Request(url + path, data=data, headers=headers, method=method)
    with urlopen(req, timeout=5) as resp:
        return resp.status, json.load(resp)


def test_http_profile_management_csrf(running_server):
    server, root, url = running_server
    status, settings = request_json(url, "/api/config")
    assert status == 200
    assert settings["mode"] == "offline_archive"
    with pytest.raises(HTTPError) as wrong:
        request_json(url, "/api/competitors", "POST",
                     {"username": "amizphoto"}, token="incorrect", origin=url)
    assert wrong.value.code == 403
    with pytest.raises(HTTPError) as wrong_origin:
        request_json(url, "/api/competitors", "POST",
                     {"username": "amizphoto"}, token=settings["csrf"], origin="http://evil.invalid")
    assert wrong_origin.value.code == 403
    status, new = request_json(url, "/api/competitors", "POST",
        {"username": "https://www.instagram.com/amizphoto/"}, token=settings["csrf"], origin=url)
    assert new["username"] == "amizphoto"
    assert status == 200
    assert len(request_json(url, "/api/competitors")[1]) == 1
    status, disabled = request_json(url, "/api/competitors/status", "POST",
        {"username": "amizphoto", "enabled": False}, token=settings["csrf"], origin=url)
    assert disabled["enabled"] is False


def test_http_blob_video_ranges_and_filters(running_server, tmp_path):
    server, root, url = running_server
    video = tmp_path / "clip.mp4"
    contents = b"\x00\x00\x00\x14ftypisom" + b"abcde" * 40
    video.write_bytes(contents)
    post_id = store.upsert_post(root, example("clip", kind="video"))
    sha = store.put_asset(root, post_id, 0, "video", video)
    data = request_json(url, "/api/posts?kind=video&sort=recent")[1]
    assert data["total"] == 1
    assert data["items"][0]["assets"][0]["local_url"] == "/api/blob/" + sha
    req = Request(url + "/api/blob/" + sha, headers={"Range": "bytes=2-12"})
    with urlopen(req, timeout=5) as res:
        assert res.status == 206
        assert res.headers["Content-Range"] == f"bytes 2-12/{len(contents)}"
        assert res.read() == contents[2:13]
    req = Request(url + "/api/blob/" + sha, headers={"Range": "bytes=9999-"})
    with pytest.raises(HTTPError) as error:
        urlopen(req, timeout=5)
    assert error.value.code == 416
    with urlopen(url + "/radar.js", timeout=5) as script:
        assert b"switchView" in script.read()
