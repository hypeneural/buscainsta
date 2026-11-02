"""Forensic tests for metadata, comment previews, cache and optional live refresh."""
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from buscainsta.radar import query, store
from buscainsta.radar.instagrapi_normalizer import normalize_media
from buscainsta.radar.refresh import RefreshManager


def sample(**extra):
    return {"source": "fixture", "external_id": "m1", "username": "amizphoto",
            "kind": "video", "posted_at": "2026-11-01T09:00:00-03:00",
            "permalink": "https://www.instagram.com/reel/XYZABC123/", **extra}


def test_migration_and_nullable_engagement(tmp_path):
    root = tmp_path / "archive"
    store.initialize(root)
    post_id = store.upsert_post(root, sample(likes=-1, comments=3, plays=250,
        video_duration=12.5, media_product_type="REELS",
        comment_previews=[{"id": "c1", "username": "fotografia", "text": "Lindo trabalho!",
                           "likes": 4, "reply_count": 2}]))
    row = query.search_posts(root)["items"][0]
    assert row["id"] == post_id
    assert row["likes"] is None
    assert row["plays"] == 250
    assert row["shares"] is None
    assert row["media_product_type"] == "REELS"
    assert row["comment_previews"][0]["comment_text"] == "Lindo trabalho!"
    store.upsert_post(root, sample(likes=13, comments=None, shares=9, plays=None,
        comment_previews=[{"id": "c1", "username": "fotografia", "text": "Lindo trabalho!",
                           "likes": 4}]))
    again = query.search_posts(root)["items"][0]
    assert again["likes"] == 13 and again["comments"] == 3
    assert again["shares"] == 9 and again["plays"] == 250
    assert len(again["comment_previews"]) == 1
    assert store.stats(root)["metric_snapshots"] == 2
    assert query.search_posts(root, sort="shares")["total"] == 1
    assert query.search_posts(root, min_likes=15)["total"] == 0
    assert query.search_posts(root, has_comments=True)["total"] == 1
    # Idempotent migration over existing data.
    store.initialize(root)
    assert query.search_posts(root)["total"] == 1


def test_content_addressed_cache_hash_verification(tmp_path):
    root = tmp_path / "archive"
    store.initialize(root)
    media = tmp_path / "photo.jpg"
    media.write_bytes(b"\xff\xd8\xff" + b"abc" * 20)
    sha = store.archive_file(root, media)
    assert store.archive_file(root, media) == sha
    report = store.cache_report(root, verify_hashes=True)
    assert report["available"] == 1 and report["corrupt"] == 0
    blob = store.get_blob(root, sha)["path"]
    blob.write_bytes(b"\xff\xd8\xff" + b"xyz" * 20)
    assert store.cache_report(root, verify_hashes=False)["available"] == 1
    assert store.cache_report(root, verify_hashes=True)["corrupt"] == 1


def test_instagrapi_media_conversion_without_login():
    comment = SimpleNamespace(pk="com1", text="Muito bonito",
          user=SimpleNamespace(username="cliente_qualquer"),
          created_at_utc=datetime(2026, 11, 1, 14, tzinfo=timezone.utc),
          like_count=3, replies_count=1)
    media = SimpleNamespace(pk="123",code="ABC1",media_type=8,
        product_type="feed",caption_text="Natal",like_count=-1,
        comment_count=5, taken_at=datetime(2026,11,1,13,tzinfo=timezone.utc),
        like_and_view_counts_disabled=True, view_count=None, play_count=None,
        thumbnail_url="https://cdn.example/cover.jpg",
        comments_preview=SimpleNamespace(comments=[comment]),
        resources=[SimpleNamespace(media_type=1,thumbnail_url="https://cdn.example/1.jpg"),
                   SimpleNamespace(media_type=2,thumbnail_url="https://cdn.example/2.jpg",
                                   video_url="https://cdn.example/2.mp4")])
    converted = normalize_media(media, "amizphoto")
    assert converted["kind"] == "carousel"
    assert converted["likes"] is None and converted["shares"] is None
    assert [a["kind"] for a in converted["assets"]] == ["image", "video"]
    assert converted["comment_previews"][0]["text"] == "Muito bonito"


def test_opt_in_refresh_single_flight(monkeypatch, tmp_path):
    root = tmp_path / "archive"
    store.initialize(root)
    query.add_profile(root, "amizphoto")
    monkeypatch.setenv("RADAR_META_TOKEN", "synthetic-token")
    monkeypatch.setenv("RADAR_META_IG_USER_ID", "123")
    import threading
    release = threading.Event()
    reached = threading.Event()
    calls = []
    def fake_sync(root, username, identity, token, version, limit):
        calls.append(username)
        reached.set()
        assert release.wait(3)
        return {"posts_processed": 2}
    manager = RefreshManager(root, enabled=True, sync=fake_sync)
    assert manager.request()["started"] is True
    assert reached.wait(3)
    assert manager.request()["started"] is False
    release.set()
    import time
    for _ in range(100):
        if not manager.status()["running"]:
            break
        time.sleep(.01)
    assert not manager.status()["running"]
    assert manager.status()["status"] == "completed"
    assert manager.request(force=True)["started"] is False
    assert calls == ["amizphoto"]
    assert RefreshManager(root, enabled=False).request()["enabled"] is False


def test_authorized_instagrapi_json_import_idempotent(tmp_path):
    import json
    from buscainsta.radar.instagrapi_normalizer import import_authorized_export
    root = tmp_path / "archive"
    payload = {"medias": [{
        "pk": "abc-456", "code": "Example56", "media_type": 2,
        "product_type": "clips", "taken_at": "2026-11-01T11:00:00+00:00",
        "caption_text": "Reel do estúdio", "like_count": -1,
        "comment_count": 6, "video_url": "https://example.org/media.mp4",
        "thumbnail_url": "https://example.org/cover.jpg",
        "video_duration": 6.5,
        "comments_preview": {"comments": [{
            "pk": "cm1", "text": "Show", "user": {"username": "follower"},
            "created_at_utc": "2026-11-01T11:10:00+00:00", "like_count": 1
        }]}
    }]}
    path = tmp_path / "export.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    assert import_authorized_export(root, path, "amizphoto")["processed"] == 1
    assert import_authorized_export(root, path, "amizphoto")["processed"] == 1
    rows = query.search_posts(root)["items"]
    assert len(rows) == 1
    assert rows[0]["media_product_type"] == "REELS"
    assert rows[0]["likes"] is None
    assert rows[0]["comment_previews"][0]["comment_text"] == "Show"
    assert store.stats(root)["blobs"] == 0


def test_cache_reimport_repairs_same_size_corruption(tmp_path):
    root = tmp_path / "archive"
    store.initialize(root)
    media = tmp_path / "original.jpg"
    media.write_bytes(b"\xff\xd8\xff" + b"one" * 20)
    sha = store.archive_file(root, media)
    saved = store.get_blob(root, sha)["path"]
    saved.write_bytes(b"\xff\xd8\xff" + b"two" * 20)
    assert store.cache_report(root, verify_hashes=True)["corrupt"] == 1
    store.archive_file(root, media)
    assert store.cache_report(root, verify_hashes=True)["available"] == 1
