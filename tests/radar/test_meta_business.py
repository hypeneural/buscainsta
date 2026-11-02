"""Offline fixtures for the optional official Meta Business Discovery adapter."""
import json
import pytest
from buscainsta.radar import query, store
from buscainsta.radar.meta_business import ProviderError, fetch_discovery, sync_profile


def response(request):
    assert request.full_url.startswith("https://graph.facebook.com/v25.0/123456?")
    assert request.get_header("Authorization") == "Bearer example-for-test"
    payload = {"business_discovery": {
        "username": "amizphoto", "name": "Amiz Photo", "followers_count": 1000,
        "media": {"data": [
            {"id": "m1", "media_type": "CAROUSEL_ALBUM",
             "timestamp": "2026-11-01T18:40:00+0000",
             "caption": "Natal 2026", "permalink": "https://www.instagram.com/p/TEST12/",
             "like_count": 15, "comments_count": 3,
             "children": {"data": [
                {"id": "photo1", "media_type": "IMAGE",
                 "media_url": "https://instagram.cdn.example/photo.jpg"},
                {"id": "clip1", "media_type": "VIDEO",
                 "media_url": "https://instagram.cdn.example/clip.mp4"},
             ]}},
            {"id": "m2", "media_type": "VIDEO",
             "timestamp": "2026-11-01T20:15:00+0000",
             "permalink": "https://www.instagram.com/reel/TEST13/",
             "thumbnail_url": "https://instagram.cdn.example/cover.jpg",
             "media_url": "https://instagram.cdn.example/reel.mp4"}
        ]}}}
    return json.dumps(payload).encode()


def test_official_metadata_import_no_download(tmp_path):
    root = tmp_path / "radar"
    first = sync_profile(root, "amizphoto", "123456", "example-for-test", http_get=response)
    second = sync_profile(root, "amizphoto", "123456", "example-for-test", http_get=response)
    assert first["posts_processed"] == 2
    assert second["posts_processed"] == 2
    assert query.search_posts(root)["total"] == 2
    assert query.overview(root)["blobs"] == 0
    profiles = query.profiles(root)
    assert profiles[0]["followers"] == 1000
    post = query.search_posts(root, kind="carousel")["items"][0]
    assert len(post["assets"]) == 2
    assert [a["kind"] for a in post["assets"]] == ["image", "video"]
    assert all(a["local_url"] is None for a in post["assets"])
    assert all(a["remote_url"].startswith("https://") for a in post["assets"])


def test_meta_permissions_and_errors(tmp_path):
    with pytest.raises(ValueError):
        fetch_discovery("amizphoto", "bad-id", "token", http_get=response)
    with pytest.raises(ValueError):
        fetch_discovery("amizphoto", "123456", "token", version="../invalid", http_get=response)
    with pytest.raises(ProviderError):
        fetch_discovery("amizphoto", "123456", "example-for-test", http_get=lambda _: b'{}')
    with pytest.raises(ProviderError):
        fetch_discovery("amizphoto", "123456", "example-for-test", http_get=lambda _: b'{bad')
