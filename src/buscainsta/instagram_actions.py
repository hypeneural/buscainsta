"""Optional Instagram read and single-message actions.

The unofficial instagrapi adapter can break or cause account restrictions.
No implicit login, follow, DM retries, bulk requests or session files.
"""
import importlib
import ipaddress
import os
import re
import socket
import threading
import urllib.parse
import urllib.request
from pathlib import Path

MAX_IMAGE_BYTES = 750_000
ALLOWED_IMAGE_DOMAINS = ("cdninstagram.com", "fbcdn.net")


class PublicSafeError(RuntimeError):
    """A safe diagnostic that never includes credentials, URLs or response bodies."""


def photo_host_allowed(url: str) -> bool:
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or "").lower().rstrip(".")
        if p.scheme != "https" or not host or p.username or p.password or p.port not in (None, 443):
            return False
        if not any(host == base or host.endswith("." + base) for base in ALLOWED_IMAGE_DOMAINS):
            return False
        # Avoid direct IP URLs; DNS resolution is checked at download time too.
        try:
            ipaddress.ip_address(host)
            return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


def _public_dns_only(host: str) -> None:
    try:
        endpoints = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise PublicSafeError("Profile image host DNS failed.") from exc
    if not endpoints:
        raise PublicSafeError("Profile image DNS returned no address.")
    for endpoint in endpoints:
        try:
            address = ipaddress.ip_address(endpoint[4][0])
        except ValueError as exc:
            raise PublicSafeError("Profile image DNS address invalid.") from exc
        if not address.is_global:
            raise PublicSafeError("Profile image resolves to nonpublic network.")


class _RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not photo_host_allowed(newurl):
            raise PublicSafeError("Profile image redirect was not approved.")
        _public_dns_only(urllib.parse.urlsplit(newurl).hostname)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_avatar(url: str, destination_dir: Path, stable_id: str) -> str:
    """Fetch a small public CDN thumbnail into the private folder.

    Never uses client-provided filenames or remote paths.
    """
    if not photo_host_allowed(url):
        raise PublicSafeError("Profile image host not approved.")
    host = urllib.parse.urlsplit(url).hostname
    _public_dns_only(host)
    opener = urllib.request.build_opener(_RestrictedRedirect())
    request = urllib.request.Request(
        url, headers={"User-Agent": "BuscaInsta-LocalReview/0.3", "Accept": "image/*"}
    )
    try:
        with opener.open(request, timeout=8) as response:
            final_url = response.geturl()
            if not photo_host_allowed(final_url):
                raise PublicSafeError("Profile image response host not approved.")
            content_type = response.headers.get_content_type().lower()
            if content_type not in ("image/jpeg", "image/png", "image/webp"):
                raise PublicSafeError("Profile image type not supported.")
            data = response.read(MAX_IMAGE_BYTES + 1)
            if len(data) > MAX_IMAGE_BYTES:
                raise PublicSafeError("Profile image exceeds safe size.")
    except PublicSafeError:
        raise
    except Exception as exc:
        raise PublicSafeError("Profile image fetch unavailable.") from exc

    if data.startswith(b"\xff\xd8\xff"):
        ext = "jpg"
    elif data.startswith(b"\x89PNG\r\n\x1a\n"):
        ext = "png"
    elif data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        ext = "webp"
    else:
        raise PublicSafeError("Profile image signature not recognized.")
    destination_dir.mkdir(parents=True, exist_ok=True)
    import hashlib
    safe_name = hashlib.sha256(stable_id.encode("utf-8")).hexdigest()[:32]
    dest = destination_dir / (safe_name + "." + ext)
    temporary = dest.with_name(dest.name + ".part")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
        os.replace(temporary, dest)
        if os.name != "nt":
            os.chmod(dest, 0o600)
    finally:
        if temporary.exists():
            temporary.unlink()
    return str(dest)


def _status(value):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    return "unknown"


class InstagramActions:
    def __init__(self, account_label: str, client_factory=None):
        self.account_label = account_label
        self.client_factory = client_factory
        self.lock = threading.RLock()
        self._client = None

    def _connected(self):
        if self._client is not None:
            return self._client
        login = os.environ.get("BUSCAINSTA_IG_TEST_LOGIN", "")
        secret = os.environ.get("BUSCAINSTA_IG_TEST_PASSWORD", "")
        if not login or not secret:
            raise PublicSafeError("Set dedicated Instagram test account environment credentials.")
        try:
            cls = self.client_factory or importlib.import_module("instagrapi").Client
            client = cls()
            client.login(login, secret)
            actual = str(getattr(client, "username", "") or "").lstrip("@").lower()
            expected = self.account_label.lstrip("@").lower()
            if actual and actual != expected:
                raise PublicSafeError("Authenticated Instagram account differs from --account.")
            self._client = client
            return client
        except Exception as exc:
            raise PublicSafeError("Instagram login unavailable; check account manually.") from exc

    def inspect(self, username: str) -> dict:
        from .pilot import username as normalize
        name = normalize(username)
        if not name:
            raise PublicSafeError("Invalid username.")
        with self.lock:
            cl = self._connected()
            try:
                profile = cl.user_info_by_username(name)
                pk = str(profile.pk)
                relationship = cl.user_friendship_v1(pk)
            except Exception as exc:
                raise PublicSafeError("Instagram profile/relationship lookup unavailable.") from exc
            if name.lower() != str(profile.username).lower():
                raise PublicSafeError("Instagram username changed; review profile manually.")
            return {
                "username": str(profile.username),
                "pk": pk,
                "full_name": str(getattr(profile, "full_name", "") or "")[:150],
                "is_private": _status(getattr(profile, "is_private", None)),
                "follows_us": _status(getattr(relationship, "followed_by", None)),
                "we_follow": _status(getattr(relationship, "following", None)),
                "profile_url": "https://www.instagram.com/" + name + "/",
                "photo_url": str(
                    getattr(profile, "profile_pic_url_hd", None)
                    or getattr(profile, "profile_pic_url", None) or ""
                ),
            }

    def direct_once(self, user_id: str, message: str) -> str:
        if not re.fullmatch(r"[0-9]{1,30}", str(user_id)):
            raise PublicSafeError("Instagram profile ID is invalid.")
        if not message or len(message) > 1000:
            raise PublicSafeError("Fixed message is empty or too long.")
        with self.lock:
            cl = self._connected()
            try:
                sent = cl.direct_send(message, user_ids=[int(user_id)])
                pk = getattr(sent, "id", None) or getattr(sent, "pk", None)
                if not pk:
                    raise PublicSafeError("Direct outcome is uncertain; review the inbox.")
                return str(pk)
            except PublicSafeError:
                raise
            except Exception as exc:
                # A timeout might occur after the provider accepted a message.
                # Do not retry, do not leak raw errors.
                raise PublicSafeError("Direct outcome is unknown; check inbox before retry.") from exc
