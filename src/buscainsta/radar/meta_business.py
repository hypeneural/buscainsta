"""Optional official Meta Business Discovery importer.

This adapter does not download or cache third-party media bytes. It is enabled
only by an explicit CLI invocation with independently authorized credentials.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from . import query, store


class ProviderError(RuntimeError):
    """Sanitized diagnostic; never exposes an OAuth token or API response."""


API_VERSION = re.compile(r"^v\d{1,2}\.\d{1,2}$")
IG_ID = re.compile(r"^[0-9]{1,30}$")
MEDIA_TYPE = {
    "IMAGE": "image",
    "VIDEO": "video",
    "CAROUSEL_ALBUM": "carousel",
}


def normalize_payload(username: str, payload: dict) -> list[dict]:
    entries = payload.get("media", {}).get("data", [])
    if not isinstance(entries, list):
        raise ProviderError("Meta response is missing expected media list")
    posts = []
    for media in entries:
        if not isinstance(media, dict) or not media.get("id") or not media.get("timestamp"):
            continue
        kind = MEDIA_TYPE.get(media.get("media_type"))
        if kind is None:
            continue
        permalink = media.get("permalink") or ""
        published = str(media["timestamp"])
        try:
            instant = datetime.fromisoformat(published.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ProviderError("Invalid publication timestamp from Meta") from exc
        if instant.tzinfo is None:
            raise ProviderError("Meta publication timestamp missing timezone")
        assets = []
        children = media.get("children", {}).get("data", []) if kind == "carousel" else [media]
        if not isinstance(children, list):
            children = []
        for child in children[:100]:
            if not isinstance(child, dict):
                continue
            child_kind = "video" if child.get("media_type") == "VIDEO" else "image"
            media_url = str(child.get("media_url") or "")
            poster = str(child.get("thumbnail_url") or "")
            assets.append({
                "kind": child_kind,
                "remote_url": media_url if media_url.startswith("https://") else "",
                "poster_url": poster if poster.startswith("https://") else "",
            })
        posts.append({
            "source": "meta_business_discovery",
            "external_id": str(media["id"]),
            "username": username,
            "kind": kind,
            "posted_at": published,
            "permalink": permalink,
            "caption": str(media.get("caption") or ""),
            "likes": media.get("like_count"),
            "comments": media.get("comments_count"),
            "cover_url": str(media.get("thumbnail_url") or ""),
            "assets": assets,
        })
    return posts


def fetch_discovery(username: str, ig_user_id: str, token: str,
                    version: str = "v25.0", limit: int = 25,
                    http_get=None) -> dict:
    username = query.normalize_username(username)
    if not IG_ID.fullmatch(ig_user_id):
        raise ValueError("Invalid authorized Instagram professional account id")
    if not API_VERSION.fullmatch(version):
        raise ValueError("Invalid Graph API version")
    if not 1 <= limit <= 30:
        raise ValueError("Business Discovery limit must be 1 to 30")
    if not token or any(c.isspace() for c in token):
        raise ValueError("Missing authenticated Meta access token")
    fields = (
        "business_discovery.username(" + username + "){"
        "username,name,followers_count,media_count,"
        "media.limit(" + str(limit) + "){"
        "id,media_type,media_url,thumbnail_url,permalink,timestamp,"
        "caption,like_count,comments_count,"
        "children{id,media_type,media_url,thumbnail_url}}}"
    )
    url = ("https://graph.facebook.com/" + version + "/" + ig_user_id
           + "?" + urlencode({"fields": fields}))
    request = Request(url, headers={"Authorization": "Bearer " + token,
                                      "Accept": "application/json"},
                      method="GET")
    try:
        if http_get is None:
            with urlopen(request, timeout=15) as response:
                data = response.read(2 * 1024 * 1024 + 1)
        else:
            data = http_get(request)
        if len(data) > 2 * 1024 * 1024:
            raise ProviderError("Meta response is oversized")
        payload = json.loads(data)
    except HTTPError as exc:
        raise ProviderError("Meta Graph rejected the request (HTTP " + str(exc.code) + ")") from None
    except (URLError, TimeoutError, OSError):
        raise ProviderError("Meta Graph is unreachable") from None
    except (ValueError, UnicodeError):
        raise ProviderError("Meta Graph returned invalid JSON") from None
    discovery = payload.get("business_discovery") if isinstance(payload, dict) else None
    if not isinstance(discovery, dict):
        raise ProviderError("Business Discovery unavailable for this account/permission")
    return discovery


def sync_profile(root: Path, username: str, ig_user_id: str, token: str,
                 version: str = "v25.0", limit: int = 25, http_get=None) -> dict:
    username = query.normalize_username(username)
    started = store.now()
    processed = 0
    try:
        payload = fetch_discovery(username, ig_user_id, token, version, limit, http_get)
        posts = normalize_payload(username, payload)
        store.initialize(root)
        for post in posts:
            post_id = store.upsert_post(root, post)
            for position, asset in enumerate(post["assets"]):
                store.put_asset(root, post_id, position, asset["kind"],
                                remote_url=asset["remote_url"], poster_url=asset["poster_url"])
            processed += 1
        with store.db_connect(root) as db:
            db.execute("""UPDATE competitors SET profile_name=?,followers=?,updated_at=?
                          WHERE username=?""",
                       (str(payload.get("name") or "")[:180],
                        payload.get("followers_count"), store.now(), username))
        store.record_run(root, "meta_business_discovery", started, "completed", processed)
        return {"status": "completed", "username": username, "posts_processed": processed,
                "media_files_downloaded": 0, "source": "meta_business_discovery"}
    except Exception as exc:
        store.initialize(root)
        store.record_run(root, "meta_business_discovery", started, "failed",
                         processed, type(exc).__name__)
        raise
