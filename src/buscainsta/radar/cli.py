"""Radar archive CLI. Network access requires explicit official Meta API command."""
import argparse
import json
import os
from pathlib import Path

from . import importer, query, store
from .meta_business import ProviderError, sync_profile

DEFAULT_ROOT = Path.home() / "BuscaInstaRadar"


def main():
    parser = argparse.ArgumentParser(description="BuscaInsta Radar local archive")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init")
    sub.add_parser("stats")
    sub.add_parser("verify-cache")
    add = sub.add_parser("add-competitor")
    add.add_argument("username")
    imp = sub.add_parser("import")
    imp.add_argument("manifest", type=Path)
    imp.add_argument("--media-directory", type=Path)
    meta = sub.add_parser("sync-meta", help="Read official Meta Business Discovery; metadata only")
    selected = meta.add_mutually_exclusive_group(required=True)
    selected.add_argument("--username")
    selected.add_argument("--all", action="store_true")
    meta.add_argument("--limit", type=int, default=25)
    meta.add_argument("--confirm-official-api", action="store_true")
    args = parser.parse_args()
    try:
        store.initialize(args.root)
        if args.command == "init":
            result = {"status": "ready"}
        elif args.command == "stats":
            result = query.overview(args.root)
        elif args.command == "verify-cache":
            result = store.cache_report(args.root, verify_hashes=True)
        elif args.command == "add-competitor":
            result = query.add_profile(args.root, args.username)
        elif args.command == "import":
            result = importer.import_manifest(args.root, args.manifest, args.media_directory)
        else:
            if not args.confirm_official_api:
                raise ValueError("Explicit confirmation required for external Meta API request")
            token = os.getenv("RADAR_META_TOKEN", "")
            ig_user = os.getenv("RADAR_META_IG_USER_ID", "")
            version = os.getenv("RADAR_META_VERSION", "v25.0")
            if not token or not ig_user:
                raise ValueError("Dedicated professional account credentials not configured")
            usernames = ([p["username"] for p in query.profiles(args.root) if p["enabled"]]
                         if args.all else [query.normalize_username(args.username)])
            if not usernames:
                raise ValueError("No active competitors configured")
            result = {"source": "meta_business_discovery", "profiles": []}
            for username in usernames:
                result["profiles"].append(sync_profile(args.root, username, ig_user, token,
                                                      version=version, limit=args.limit))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError, ProviderError) as exc:
        parser.exit(2, "Radar failed: " + type(exc).__name__ + "\n")


if __name__ == "__main__":
    main()
