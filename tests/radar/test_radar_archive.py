import json
from pathlib import Path
import pytest
from buscainsta.radar import store,importer

def record(**overrides):
    base={"source":"manual","external_id":"a1","username":"amizphoto","kind":"carousel",
          "posted_at":"2026-11-01T14:15:00-03:00",
          "permalink":"https://www.instagram.com/p/ABC123/",
          "likes":5,"comments":2}
    base.update(overrides)
    return base

def test_idempotence_and_snapshot(tmp_path):
    root=tmp_path/"private";store.initialize(root)
    one=store.upsert_post(root,record())
    two=store.upsert_post(root,record(external_id="other",source="other",likes=8))
    assert one==two
    assert store.stats(root)["posts"]==1
    assert store.stats(root)["metric_snapshots"]==2
    assert store.list_posts(root)[0]["likes"]==8
    assert store.list_posts(root)[0]["posted_at"].startswith("2026-11-01T17:15")

def test_hash_dedup_and_asset_positions(tmp_path):
    root=tmp_path/"private";store.initialize(root)
    p=tmp_path/"a.jpg";p.write_bytes(b"\xff\xd8\xff"+b"x"*50)
    q=tmp_path/"b.jpg";q.write_bytes(p.read_bytes())
    item=store.upsert_post(root,record())
    s1=store.put_asset(root,item,0,"image",p)
    s2=store.put_asset(root,item,1,"image",q)
    assert s1==s2
    assert store.stats(root)["blobs"]==1
    assert store.stats(root)["post_assets"]==2
    assert store.get_blob(root,s1)["path"].is_file()

def test_manifest_repeated_and_traversal(tmp_path):
    root=tmp_path/"private"
    media=tmp_path/"input";media.mkdir()
    (media/"one.jpg").write_bytes(b"\xff\xd8\xff"+b"x")
    manifest=media/"posts.json"
    obj={"posts":[{**record(),"assets":[{"kind":"image","file":"one.jpg"}]}]}
    manifest.write_text(json.dumps(obj))
    importer.import_manifest(root,manifest)
    importer.import_manifest(root,manifest)
    assert store.stats(root)["posts"]==1
    assert store.stats(root)["blobs"]==1
    assert store.stats(root)["post_assets"]==1
    obj["posts"][0]["assets"][0]["file"]="../outside.jpg"
    manifest.write_text(json.dumps(obj))
    with pytest.raises(ValueError,match="escape"):
        importer.import_manifest(root,manifest)

def test_invalid_input(tmp_path):
    root=tmp_path/"private";store.initialize(root)
    with pytest.raises(ValueError):
        store.upsert_post(root,record(posted_at="2026-11-01T12:00:00"))
    with pytest.raises(ValueError):
        store.upsert_post(root,record(likes=-1))
    with pytest.raises(ValueError):
        store.add_competitor(root,"bad/name")
    with pytest.raises(ValueError):
        store.list_posts(root,kind="whatever")
    with pytest.raises(ValueError):
        store.put_asset(root,123,0,"image",remote_url="http://invalid")

def test_no_repo_storage(tmp_path):
    git=tmp_path/"git";git.mkdir();(git/".git").mkdir()
    with pytest.raises(ValueError):
        store.initialize(git/"secrets")
