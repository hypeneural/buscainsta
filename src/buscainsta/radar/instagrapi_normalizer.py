"""Schema adapter for already-obtained, authorized instagrapi Media objects.

No instagrapi import, credentials, network requests, or account automation.
The caller is responsible for provenance and permission to store/export data.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def attribute(obj: Any, name: str, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def safe_url(value) -> str:
    value = str(value or "")
    return value[:2000] if value.startswith("https://") else ""


def maybe_count(value):
    # Hidden likes can be -1 on certain instagrapi public-web responses.
    return value if type(value) is int and value >= 0 else None


def utc_timestamp(value) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("instagrapi timestamps must be aware datetime objects")
    return value.astimezone(timezone.utc).isoformat()


def normalize_comments(media: Any, limit=10) -> list[dict]:
    """Only the inline previews included in the provided object, no extra API calls."""
    preview = attribute(media, "comments_preview")
    nodes = attribute(preview, "comments", []) or []
    nodes = list(nodes)[:limit]
    cleaned = []
    for node in nodes:
        pk = str(attribute(node, "pk") or "")
        if not pk:
            continue
        author = attribute(node, "user")
        created = attribute(node, "created_at_utc")
        cleaned.append({
            "id": pk, "username": str(attribute(author, "username") or ""),
            "text": str(attribute(node, "text") or ""),
            "created_at": utc_timestamp(created) if isinstance(created, datetime) else None,
            "likes": maybe_count(attribute(node, "like_count")),
            "reply_count": maybe_count(attribute(node, "replies_count")),
        })
    return cleaned


def normalize_media(media: Any, username: str) -> dict:
    kind_code = attribute(media, "media_type")
    kind = {1: "image", 2: "video", 8: "carousel"}.get(kind_code)
    if not kind:
        raise ValueError("Unsupported instagrapi media type")
    pk = str(attribute(media, "pk") or "")
    code = str(attribute(media, "code") or "")
    if not pk or not code:
        raise ValueError("Missing media identity")
    resources = list(attribute(media, "resources", []) or []) if kind == "carousel" else [media]
    assets = []
    for item in resources[:100]:
        child_type = attribute(item, "media_type")
        if child_type not in (1, 2):
            continue
        assets.append({
            "kind": "video" if child_type == 2 else "image",
            "remote_url": safe_url(attribute(item, "video_url" if child_type == 2 else "thumbnail_url")),
            "poster_url": safe_url(attribute(item, "thumbnail_url")),
        })
    original_type = str(attribute(media, "product_type") or "")
    product = "REELS" if original_type in ("clips", "reels") else "FEED"
    views = maybe_count(attribute(media, "view_count"))
    plays = maybe_count(attribute(media, "play_count"))
    return {
        "source": "instagrapi_authorized_export",
        "source_note": "Authorized offline conversion of the instagrapi Media model",
        "external_id": pk, "username": username,
        "kind": kind, "media_product_type": product,
        "posted_at": utc_timestamp(attribute(media, "taken_at")),
        "permalink": "https://www.instagram.com/" + ("reel" if product == "REELS" else "p") + "/" + code + "/",
        "caption": str(attribute(media, "caption_text") or ""),
        "likes": (None if attribute(media, "like_and_view_counts_disabled") else
                  maybe_count(attribute(media, "like_count"))),
        "comments": maybe_count(attribute(media, "comment_count")),
        "views": views, "plays": plays,
        "shares": None, "saves": None,  # Neither is a reliable public competitor count on Media.
        "video_duration": attribute(media, "video_duration") if kind == "video" else None,
        "cover_url": safe_url(attribute(media, "thumbnail_url")),
        "comment_previews": normalize_comments(media),
        "assets": assets,
    }
