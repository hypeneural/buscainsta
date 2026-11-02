"""Import locally authorized exports, without network access."""
import json
from pathlib import Path
from . import store

def import_manifest(root:Path, path:Path, media_directory:Path|None=None) -> dict:
    """JSON: {"posts":[{source,external_id,username,kind,posted_at,assets:[{kind,file?}]}]}."""
    if path.stat().st_size>10*1024*1024:
        raise ValueError("Manifest too large")
    obj=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict) or not isinstance(obj.get("posts"),list) or len(obj["posts"])>1000:
        raise ValueError("Manifest must contain at most 1000 posts")
    store.initialize(root)
    start=store.now()
    imported=0
    try:
        for record in obj["posts"]:
            if not isinstance(record,dict) or not isinstance(record.get("assets",[]),list):
                raise ValueError("Invalid post record")
            if len(record.get("assets",[]))>100:
                raise ValueError("Too many assets")
            post_id=store.upsert_post(root,record)
            for index,asset in enumerate(record.get("assets",[])):
                if not isinstance(asset,dict):
                    raise ValueError("Invalid asset")
                local=None
                if asset.get("file"):
                    base=(media_directory or path.parent).resolve()
                    candidate=(base/str(asset["file"])).resolve()
                    if not candidate.is_relative_to(base):
                        raise ValueError("Media cannot escape import directory")
                    local=candidate
                store.put_asset(root,post_id,index,asset["kind"],local,
                                asset.get("remote_url",""),asset.get("poster_url",""))
            imported+=1
        store.record_run(root,"local_manifest",start,"completed",imported)
        return {"status":"completed","processed":imported,**store.stats(root)}
    except Exception as exc:
        store.record_run(root,"local_manifest",start,"failed",imported,type(exc).__name__)
        raise
