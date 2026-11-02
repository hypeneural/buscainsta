"""Legacy report compatibility. Never embed real customer snapshots in Git."""
import json
from pathlib import Path

import pytest

from buscainsta import dashboard_store as store
from buscainsta.legacy_import import import_legacy, parse_legacy


def make_legacy(tmp_path: Path, rows=None):
    if rows is None:
        rows = [
            dict(crm_id="123", name="Cliente A", wa_clean="5548999991234",
                 email="a@example.invalid", instagram="perfil_a", ig_method="name_search",
                 score_vip=92, segmento_vip="P0", rank=1, total_pedidos="8",
                 ensaios_natal="5", anos_natal="4", ultimo_natal_ano="2025",
                 ltv_fmt="R$ 1.000,00", gasto_natal_fmt="R$ 500,00",
                 situacao_2026="Revalidar"),
            dict(crm_id="123", name="Cliente B", wa_clean="5548999995678",
                 email="b@example.invalid", instagram="", ig_method="",
                 score_vip=80, segmento_vip="P1", rank=2, total_pedidos="2",
                 ensaios_natal="1", anos_natal="1", ultimo_natal_ano="2024",
                 ltv_fmt="R$ 400,00", gasto_natal_fmt="R$ 250,00",
                 situacao_2026="Revalidar"),
        ]
    source = tmp_path / "painel_conferencia.html"
    source.write_text(
        '<!doctype html><html><script> const allData = ' +
        json.dumps(rows,ensure_ascii=False) + ';\n</script></html>',
        encoding="utf-8"
    )
    return source


def test_migrate_legacy_preserves_records_and_ranking(tmp_path):
    source = make_legacy(tmp_path)
    initial_hash = source.read_bytes()
    db = tmp_path / "private" / "local.db"
    first = import_legacy(db, source)
    assert first["added"] == 2
    assert first["candidates_imported"] == 1
    assert first["crm_id_unique"] is False
    assert source.read_bytes() == initial_hash
    items = store.list_contacts(db)["items"]
    assert len(items) == 2
    assert items[0]["vip_rank"] == 1 and items[1]["vip_rank"] == 2
    assert items[0]["candidate_username"] == "perfil_a"
    assert items[0]["crm_id"] == items[1]["crm_id"] == "123"
    assert store.dashboard_stats(db)["segments"] == {"P0": 1, "P1": 1}
    assert store.list_contacts(db, segment="P0")["total"] == 1
    assert store.list_contacts(db, instagram_only=True)["total"] == 1
    second = import_legacy(db, source)
    assert second["added"] == 0 and second["updated"] == 2
    assert store.list_contacts(db)["total"] == 2


def test_preserves_confirmation_on_reimport(tmp_path):
    source = make_legacy(tmp_path)
    db = tmp_path / "private" / "local.db"
    import_legacy(db, source)
    cid = store.list_contacts(db)["items"][0]["contact_id"]
    store.set_verified(db,cid,True)
    store.set_dm_permission(db,cid,True)
    assert store.get_contact(db,cid)["manually_verified"] == 1
    import_legacy(db, source)
    again = store.get_contact(db,cid)
    assert again["manually_verified"] == 1
    assert again["dm_permitted"] == 1


def test_different_phones_same_crm_id_are_not_merged(tmp_path):
    source = make_legacy(tmp_path)
    db = tmp_path / "private" / "local.db"
    import_legacy(db,source)
    items = store.list_contacts(db)["items"]
    assert len({r["contact_id"] for r in items}) == 2
    assert len({r["phone"] for r in items}) == 2


def test_no_eval_and_no_partial_import_on_error(tmp_path):
    source = make_legacy(tmp_path)
    db = tmp_path / "private" / "local.db"
    import_legacy(db,source)
    baseline = store.list_contacts(db)["total"]
    source.write_text('<script> const allData = [not JavaScript]; </script>',encoding="utf-8")
    with pytest.raises(ValueError):
        import_legacy(db,source)
    assert store.list_contacts(db)["total"] == baseline


def test_import_transaction_rollback(tmp_path):
    source = make_legacy(tmp_path)
    db = tmp_path / "private" / "local.db"
    rows = parse_legacy(source)
    rows[1]["score_vip"] = "cannot_be_converted"
    source = make_legacy(tmp_path, rows=rows)
    with pytest.raises(ValueError):
        import_legacy(db,source)
    assert store.list_contacts(db)["total"] == 0


def test_list_filters_do_not_expose_other_records(tmp_path):
    source = make_legacy(tmp_path)
    db = tmp_path / "private" / "local.db"
    import_legacy(db,source)
    assert store.list_contacts(db,query="Cliente A")["total"] == 1
    assert store.list_contacts(db,query="5548999995678")["total"] == 1
    assert store.list_contacts(db,verified_only=True)["total"] == 0
    with pytest.raises(ValueError):
        store.list_contacts(db,segment="ANY")

def test_standard_csv_does_not_silently_merge_repeated_crm_ids(tmp_path):
    # Historical report uses repeated CRM IDs, so standard import must not
    # silently overwrite a second person's phone. Use legacy importer instead.
    import csv
    db = tmp_path / "private" / "local.db"
    store.setup(db)
    inp = tmp_path / "contacts.csv"
    with inp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.writer(stream)
        writer.writerow(store.CONTACT_COLUMNS)
        writer.writerow(["123", "Cliente A", "+5548999991111", "", "", "", "", ""])
        writer.writerow(["123", "Cliente B", "+5548999992222", "", "", "", "", ""])
    with pytest.raises(ValueError, match="Duplicate contact_id"):
        store.import_contacts(db,inp)
    assert store.list_contacts(db)["total"] == 0
