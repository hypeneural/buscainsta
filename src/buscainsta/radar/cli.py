"""Radar archive CLI: never connects to Instagram."""
import argparse,json
from pathlib import Path
from . import importer,store

DEFAULT_ROOT=Path.home()/"BuscaInstaRadar"
def main():
    parser=argparse.ArgumentParser(description="BuscaInsta Radar local archive")
    parser.add_argument("--root",type=Path,default=DEFAULT_ROOT)
    sub=parser.add_subparsers(dest="command",required=True)
    sub.add_parser("init")
    sub.add_parser("stats")
    add=sub.add_parser("add-competitor");add.add_argument("username")
    imp=sub.add_parser("import");imp.add_argument("manifest",type=Path)
    imp.add_argument("--media-directory",type=Path)
    args=parser.parse_args()
    try:
        store.initialize(args.root)
        if args.command=="init": result={"status":"ready"}
        elif args.command=="stats":result=store.stats(args.root)
        elif args.command=="add-competitor":
            store.add_competitor(args.root,args.username);result={"status":"added","username":args.username}
        else:result=importer.import_manifest(args.root,args.manifest,args.media_directory)
        print(json.dumps(result,ensure_ascii=False,sort_keys=True))
    except (ValueError,OSError,KeyError,TypeError,json.JSONDecodeError) as exc:
        parser.exit(2,f"Radar failed: {type(exc).__name__}\n")

if __name__=="__main__":main()
