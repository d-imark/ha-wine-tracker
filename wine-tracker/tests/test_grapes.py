"""Tests for the wine_grapes module (1-n grape varieties with optional pct)."""
import pytest

import grapes


@pytest.fixture(autouse=True)
def _ensure_grapes_table(db):
    # The table is created by init_db (Task 2); ensure it exists for unit tests
    # that run against the raw db fixture regardless of wiring order.
    grapes.create_wine_grapes_table(db)
    db.commit()


# ── split_legacy ──────────────────────────────────────────────────────────────

def test_split_legacy_separators_and_dedup():
    assert grapes.split_legacy("Merlot, Cabernet & Syrah / Merlot") == [
        "Merlot", "Cabernet", "Syrah"
    ]


def test_split_legacy_trims_and_ignores_empty():
    assert grapes.split_legacy("  Merlot ,, /  Cabernet  ") == ["Merlot", "Cabernet"]


def test_split_legacy_empty_input():
    assert grapes.split_legacy("") == []
    assert grapes.split_legacy(None) == []


# ── set / list / rebuild ──────────────────────────────────────────────────────

def _insert_wine(db, grape=None):
    cur = db.execute(
        "INSERT INTO wines (name, type, region, quantity, grape) VALUES (?,?,?,?,?)",
        ("Testwein", "red", "Bordeaux", 1, grape))
    db.commit()
    return cur.lastrowid


def test_set_and_list_roundtrip_with_pct_and_ref(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [
        {"name": "Merlot", "pct": 60},
        {"name": "Cabernet Sauvignon", "pct": 40},
        {"name": "Hauswein XY", "pct": None},
    ])
    rows = grapes.list_wine_grapes(db, wid)
    assert [r["name"] for r in rows] == ["Merlot", "Cabernet Sauvignon", "Hauswein XY"]
    assert [r["pct"] for r in rows] == [60, 40, None]
    assert [r["position"] for r in rows] == [0, 1, 2]
    # Merlot is a built-in ref grape -> grape_id + color resolved
    assert rows[0]["grape_id"] is not None
    assert rows[0]["color"] == "red"
    # Unknown custom grape -> no ref match
    assert rows[2]["grape_id"] is None
    assert rows[2]["color"] is None


def test_set_replaces_existing_and_rebuilds_cache(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [{"name": "Merlot", "pct": None}])
    grapes.set_wine_grapes(db, wid, [
        {"name": "Syrah", "pct": None}, {"name": "Grenache", "pct": None}])
    rows = grapes.list_wine_grapes(db, wid)
    assert [r["name"] for r in rows] == ["Syrah", "Grenache"]
    cache = db.execute("SELECT grape FROM wines WHERE id=?", (wid,)).fetchone()[0]
    assert cache == "Syrah, Grenache"


def test_set_empty_clears_cache(db):
    wid = _insert_wine(db, grape="Merlot")
    grapes.set_wine_grapes(db, wid, [])
    assert grapes.list_wine_grapes(db, wid) == []
    assert db.execute("SELECT grape FROM wines WHERE id=?", (wid,)).fetchone()[0] is None


def test_set_skips_blank_names(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [
        {"name": "  ", "pct": 10}, {"name": "Merlot", "pct": 90}])
    assert [r["name"] for r in grapes.list_wine_grapes(db, wid)] == ["Merlot"]


def test_set_coerces_out_of_range_pct_to_none(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [
        {"name": "Merlot", "pct": 150}, {"name": "Syrah", "pct": "abc"}])
    rows = grapes.list_wine_grapes(db, wid)
    assert [r["pct"] for r in rows] == [None, None]


# ── backfill (Task 2) ─────────────────────────────────────────────────────────

def test_backfill_from_legacy_grape(db):
    wid = _insert_wine(db, grape="Cabernet Sauvignon, Merlot")
    db.execute("DELETE FROM wine_grapes WHERE wine_id=?", (wid,))
    db.commit()
    import app as wine_app
    wine_app.backfill_wine_grapes(db)
    rows = grapes.list_wine_grapes(db, wid)
    assert [r["name"] for r in rows] == ["Cabernet Sauvignon", "Merlot"]
    assert all(r["pct"] is None for r in rows)


def test_backfill_is_idempotent(db):
    wid = _insert_wine(db, grape="Merlot")
    import app as wine_app
    wine_app.backfill_wine_grapes(db)
    wine_app.backfill_wine_grapes(db)
    assert len(grapes.list_wine_grapes(db, wid)) == 1


# ── alias merging (Shiraz == Syrah) ───────────────────────────────────────────

def test_alias_duplicate_is_merged_to_canonical_name(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [
        {"name": "Shiraz", "pct": None},
        {"name": "Syrah", "pct": None},
        {"name": "Merlot", "pct": None},
    ])
    rows = grapes.list_wine_grapes(db, wid)
    assert [r["name"] for r in rows] == ["Syrah", "Merlot"]
    assert db.execute("SELECT grape FROM wines WHERE id=?", (wid,)).fetchone()[0] \
        == "Syrah, Merlot"


def test_single_alias_keeps_the_typed_name(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [{"name": "Shiraz", "pct": None}])
    rows = grapes.list_wine_grapes(db, wid)
    assert [r["name"] for r in rows] == ["Shiraz"]
    assert rows[0]["grape_id"] is not None       # still linked to the Syrah ref


def test_merge_keeps_first_given_pct(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [
        {"name": "Shiraz", "pct": None}, {"name": "Syrah", "pct": 40}])
    rows = grapes.list_wine_grapes(db, wid)
    assert [(r["name"], r["pct"]) for r in rows] == [("Syrah", 40)]


def test_unknown_custom_names_are_not_merged(db):
    wid = _insert_wine(db)
    grapes.set_wine_grapes(db, wid, [
        {"name": "Hauswein A", "pct": None}, {"name": "Hauswein B", "pct": None}])
    assert [r["name"] for r in grapes.list_wine_grapes(db, wid)] == ["Hauswein A", "Hauswein B"]


def test_dedupe_migration_fixes_existing_rows(db):
    wid = _insert_wine(db)
    # simulate pre-merge data: two rows pointing at the same reference grape
    ref_id = db.execute("SELECT id FROM ref_grapes WHERE name='Syrah'").fetchone()[0]
    db.execute("INSERT INTO wine_grapes (wine_id, grape_id, name, pct, position) VALUES (?,?,?,?,?)",
               (wid, ref_id, "Shiraz", None, 0))
    db.execute("INSERT INTO wine_grapes (wine_id, grape_id, name, pct, position) VALUES (?,?,?,?,?)",
               (wid, ref_id, "Syrah", None, 1))
    db.commit()
    fixed = grapes.dedupe_wine_grapes(db)
    assert fixed == 1
    assert [r["name"] for r in grapes.list_wine_grapes(db, wid)] == ["Syrah"]
    # running it again is a no-op
    assert grapes.dedupe_wine_grapes(db) == 0


def test_relink_attaches_newly_seeded_reference_grapes(db):
    wid = _insert_wine(db)
    # a row stored before the variety existed in the reference list
    db.execute("INSERT INTO wine_grapes (wine_id, grape_id, name, pct, position) VALUES (?,?,?,?,?)",
               (wid, None, "Petite Arvine", None, 0))
    db.commit()
    assert grapes.relink_unmatched(db) == 1
    row = grapes.list_wine_grapes(db, wid)[0]
    assert row["grape_id"] is not None and row["name"] == "Petite Arvine"
    assert grapes.relink_unmatched(db) == 0   # idempotent


def test_swiss_varieties_are_in_the_reference_list(db):
    for name in ("Petite Arvine", "Humagne Rouge", "Amigne", "Gamaret",
                 "Rondinella", "Nero di Troia", "Savagnin"):
        assert db.execute("SELECT 1 FROM ref_grapes WHERE name=?", (name,)).fetchone(), name
    # alias lookups resolve to the canonical entry
    import reference
    assert reference.match_reference(db, "grape", "Uva di Troia")["name"] == "Nero di Troia"
    assert reference.match_reference(db, "grape", "Mantonegro")["name"] == "Manto Negro"


# ── reference list tidy-up (duplicate entries) ────────────────────────────────

def test_merge_duplicate_reference_entries(db):
    import json as J
    # 'Sylvaner' is already an alias of 'Silvaner' -> the standalone row must go
    db.execute("INSERT INTO ref_grapes (name, norm, color, aliases, is_custom) "
               "VALUES ('Sylvaner','sylvaner','white','[]',0)")
    db.commit()
    dup_id = db.execute("SELECT id FROM ref_grapes WHERE name='Sylvaner'").fetchone()[0]
    keep_id = db.execute("SELECT id FROM ref_grapes WHERE name='Silvaner'").fetchone()[0]

    assert grapes.merge_duplicate_reference_grapes(db) >= 1
    assert db.execute("SELECT 1 FROM ref_grapes WHERE id=?", (dup_id,)).fetchone() is None
    survivor = db.execute("SELECT name, aliases FROM ref_grapes WHERE id=?", (keep_id,)).fetchone()
    assert survivor["name"] == "Silvaner"
    assert "Sylvaner" in J.loads(survivor["aliases"])
    # both spellings still resolve
    import reference
    assert reference.match_reference(db, "grape", "Sylvaner")["id"] == keep_id
    assert grapes.merge_duplicate_reference_grapes(db) == 0     # idempotent


def test_merge_keeps_the_entry_wines_point_at(db):
    wid = _insert_wine(db)
    db.execute("INSERT INTO ref_grapes (name, norm, color, aliases, is_custom) "
               "VALUES ('Sylvaner','sylvaner','white','[]',0)")
    db.commit()
    used_id = db.execute("SELECT id FROM ref_grapes WHERE name='Sylvaner'").fetchone()[0]
    db.execute("INSERT INTO wine_grapes (wine_id, grape_id, name, pct, position) VALUES (?,?,?,?,?)",
               (wid, used_id, "Sylvaner", None, 0))
    db.commit()

    grapes.merge_duplicate_reference_grapes(db)
    # the referenced row survives; the wine keeps a valid link
    row = grapes.list_wine_grapes(db, wid)[0]
    assert row["grape_id"] is not None
    assert db.execute("SELECT 1 FROM ref_grapes WHERE id=?", (row["grape_id"],)).fetchone()


def test_no_duplicate_entries_in_seed_data():
    import reference_data as rd
    from reference import normalize_name
    owners = {}
    for g in rd.GRAPES:
        for a in g.get("aliases", []):
            owners.setdefault(normalize_name(a), []).append(g["name"])
    for g in rd.GRAPES:
        clash = [o for o in owners.get(normalize_name(g["name"]), []) if o != g["name"]]
        assert not clash, f"{g['name']} is also an alias of {clash}"
