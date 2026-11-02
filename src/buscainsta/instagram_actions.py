"""Optional Instagram read, candidate search, and single-message actions.

The unofficial instagrapi adapter can break or cause account restrictions.
No implicit follow, DM retries, bulk messaging, or public session files.
"""
import hashlib
import importlib
import ipaddress
import os
import re
import socket
import threading
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional

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
        url, headers={"User-Agent": "BuscaInsta-LocalReview/0.4", "Accept": "image/*"}
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
    safe_name = hashlib.sha256(stable_id.encode("utf-8")).hexdigest()[:32]
    dest = destination_dir / (safe_name + "." + ext)
    nonce = hashlib.sha256(os.urandom(8)).hexdigest()[:8]
    temporary = dest.with_name(f"{dest.name}.{nonce}.part")
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
    def __init__(
        self,
        account_label: str,
        client_factory=None,
        session_dir: Optional[Path] = None,
        env_file: Optional[Path] = None,
    ):
        self.account_label = account_label
        self.client_factory = client_factory
        self.session_dir = session_dir
        self.env_file = env_file
        self.lock = threading.RLock()
        self._client = None

    def _credentials(self) -> tuple[str, str]:
        login = os.environ.get("BUSCAINSTA_IG_TEST_LOGIN", "").strip()
        secret = os.environ.get("BUSCAINSTA_IG_TEST_PASSWORD", "").strip()
        if (not login or not secret) and self.env_file:
            from .live_sync import load_env_file
            env_vars = load_env_file(self.env_file)
            login = login or env_vars.get("BUSCAINSTA_IG_TEST_LOGIN", "").strip()
            secret = secret or env_vars.get("BUSCAINSTA_IG_TEST_PASSWORD", "").strip()
        return login, secret

    def has_credentials(self) -> bool:
        login, secret = self._credentials()
        return bool(login and secret)

    def _session_file(self) -> Optional[Path]:
        if not self.session_dir:
            return None
        from .dashboard_store import check_private_path
        folder = check_private_path(self.session_dir)
        safe_acc = re.sub(r"[^a-z0-9._-]", "_", self.account_label.lstrip("@").lower()) or "default"
        return folder / f"{safe_acc}.json"

    def _connected(self):
        if self._client is not None:
            return self._client
        login, secret = self._credentials()
        if not login or not secret:
            raise PublicSafeError("Set dedicated Instagram test account environment credentials.")
        session_file = self._session_file()
        try:
            cls = self.client_factory or importlib.import_module("instagrapi").Client
            client = cls()
            if hasattr(client, "delay_range"):
                client.delay_range = [1, 3]
            loaded_session = False
            if session_file and session_file.is_file() and hasattr(client, "load_settings"):
                try:
                    client.load_settings(session_file)
                    loaded_session = True
                except Exception:
                    loaded_session = False
            try:
                client.login(login, secret)
            except Exception:
                if not loaded_session:
                    raise
                # Stale session file: retry clean login once.
                client = cls()
                if hasattr(client, "delay_range"):
                    client.delay_range = [1, 3]
                client.login(login, secret)

            actual = str(getattr(client, "username", "") or "").lstrip("@").lower()
            expected = self.account_label.lstrip("@").lower()
            if actual and actual != expected:
                raise PublicSafeError("Authenticated Instagram account differs from --account.")

            if session_file and hasattr(client, "dump_settings"):
                try:
                    session_file.parent.mkdir(parents=True, exist_ok=True)
                    client.dump_settings(session_file)
                    if os.name != "nt" and session_file.exists():
                        os.chmod(session_file, 0o600)
                except Exception:
                    pass

            self._client = client
            return client
        except PublicSafeError:
            raise
        except Exception as exc:
            raise PublicSafeError("Instagram login unavailable; check account manually.") from exc

    def _lookup_profile(self, cl, name: str):
        if hasattr(cl, "user_info_by_username_v1"):
            return cl.user_info_by_username_v1(name)
        return cl.user_info_by_username(name)

    def inspect(self, username: str) -> dict:
        from .pilot import username as normalize
        name = normalize(username)
        if not name:
            raise PublicSafeError("Invalid username.")
        with self.lock:
            cl = self._connected()
            try:
                profile = self._lookup_profile(cl, name)
                pk = str(profile.pk)
                relationship = cl.user_friendship_v1(pk)
            except Exception as exc:
                if "login" in type(exc).__name__.lower():
                    self._client = None
                    try:
                        cl = self._connected()
                        profile = self._lookup_profile(cl, name)
                        pk = str(profile.pk)
                        relationship = cl.user_friendship_v1(pk)
                    except Exception as retry_exc:
                        raise PublicSafeError("Instagram profile/relationship lookup unavailable.") from retry_exc
                else:
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

    def search_candidates(
        self,
        full_name: str,
        email: str = "",
        query_override: str = "",
        limit: int = 6,
    ) -> list[dict]:
        """Search Instagram candidates via followers, TopSearch and nominal directory."""
        from .live_sync import (
            build_search_queries,
            extract_search_user,
            get_user_field,
            name_parts,
            score_candidate_for_contact,
        )
        from .pilot import username as normalize

        limit = max(1, min(int(limit), 10))
        override = query_override.strip().lstrip("@")
        queries = [override] if override else build_search_queries(full_name, email)[:3]
        if not queries:
            raise PublicSafeError("Informe um nome ou @username para pesquisar.")

        with self.lock:
            cl = self._connected()
            raw_by_username: dict[str, object] = {}
            follower_pks: set[str] = set()

            def collect(item: object, is_follower: bool = False) -> None:
                unwrapped = extract_search_user(item)
                if unwrapped is None:
                    return
                uname = normalize(get_user_field(unwrapped, "username"))
                if not uname:
                    return
                pk_val = get_user_field(unwrapped, "pk")
                if is_follower and pk_val:
                    follower_pks.add(pk_val)
                if uname not in raw_by_username:
                    raw_by_username[uname] = unwrapped

            try:
                # 1. Search inside studio's own followers first (highest signal)
                studio_uid = str(getattr(cl, "user_id", "") or "")
                parts = name_parts(full_name)
                f_query = override or (parts[0] if parts else queries[0])
                if studio_uid and f_query and hasattr(cl, "search_followers_v1"):
                    try:
                        for hit in cl.search_followers_v1(studio_uid, f_query) or []:
                            collect(hit, is_follower=True)
                    except Exception:
                        pass

                # 2. Unified TopSearch (social graph + locality ranking)
                if hasattr(cl, "fbsearch_topsearch_flat"):
                    try:
                        for hit in cl.fbsearch_topsearch_flat(queries[0]) or []:
                            collect(hit)
                    except Exception:
                        pass

                # 3. User directory search (cascade queries)
                for idx, q in enumerate(queries):
                    if idx > 0 and raw_by_username:
                        best_so_far = max(
                            score_candidate_for_contact(
                                obj, full_name, email,
                                follows_us="yes" if get_user_field(obj, "pk") in follower_pks else "unknown",
                            )[0]
                            for obj in raw_by_username.values()
                        )
                        if best_so_far >= 82:
                            break
                    if hasattr(cl, "search_users_v1"):
                        for hit in cl.search_users_v1(q, 15) or []:
                            collect(hit)
                    elif hasattr(cl, "search_users"):
                        for hit in cl.search_users(q) or []:
                            collect(hit)
            except Exception as exc:
                if not raw_by_username:
                    raise PublicSafeError("Pesquisa no Instagram indisponível no momento.") from exc

            # Initial ranking to select top candidates for relationship enrichment
            preliminary: list[tuple[int, str, object]] = []
            for uname, obj in raw_by_username.items():
                pk_val = get_user_field(obj, "pk")
                f_us = "yes" if pk_val and pk_val in follower_pks else "unknown"
                sc, _ = score_candidate_for_contact(obj, full_name, email, follows_us=f_us)
                preliminary.append((sc, uname, obj))
            preliminary.sort(key=lambda item: item[0], reverse=True)
            top_items = preliminary[:limit]

            # Batch enrich we_follow / is_private via friendships/show_many
            we_follow_map: dict[str, str] = {}
            private_map: dict[str, str] = {}
            pks = [get_user_field(obj, "pk") for _, _, obj in top_items if get_user_field(obj, "pk")]
            if pks and hasattr(cl, "user_friendships_v1"):
                try:
                    for rel in cl.user_friendships_v1(pks) or []:
                        uid = str(getattr(rel, "user_id", "") or "")
                        if uid:
                            we_follow_map[uid] = _status(getattr(rel, "following", None))
                            private_map[uid] = _status(getattr(rel, "is_private", None))
                except Exception:
                    pass

            # Exact two-way follow check for top 3 candidates when follows_us is still unknown
            follows_us_map: dict[str, str] = {pk: "yes" for pk in follower_pks}
            if hasattr(cl, "user_friendship_v1"):
                checked_exact = 0
                for _, _, obj in top_items:
                    if checked_exact >= 3:
                        break
                    pk_val = get_user_field(obj, "pk")
                    if not pk_val or pk_val in follows_us_map:
                        continue
                    checked_exact += 1
                    try:
                        rel = cl.user_friendship_v1(pk_val)
                        follows_us_map[pk_val] = _status(getattr(rel, "followed_by", None))
                        we_follow_map[pk_val] = _status(getattr(rel, "following", None))
                    except Exception:
                        pass

            results: list[dict] = []
            for _, uname, obj in top_items:
                pk_val = get_user_field(obj, "pk")
                raw_priv = getattr(obj, "is_private", obj.get("is_private") if isinstance(obj, dict) else None)
                is_priv = private_map.get(pk_val) or _status(raw_priv)
                f_us = follows_us_map.get(pk_val, "unknown")
                w_fol = we_follow_map.get(pk_val, "unknown")
                sc, reason = score_candidate_for_contact(
                    obj, full_name, email, follows_us=f_us, we_follow=w_fol
                )
                results.append({
                    "username": uname,
                    "pk": pk_val,
                    "full_name": get_user_field(obj, "full_name")[:150],
                    "is_private": is_priv,
                    "follows_us": f_us,
                    "we_follow": w_fol,
                    "score": sc,
                    "match_reason": reason,
                    "profile_url": f"https://www.instagram.com/{uname}/",
                })

            results.sort(key=lambda r: r["score"], reverse=True)
            return results

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
