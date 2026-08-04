"""Tests for the spirits module (whisky details, casks, open bottles)."""
import pytest

import spirits


@pytest.fixture(autouse=True)
def _tables(db):
    spirits.create_spirit_tables(db)
    db.commit()


def _insert_wine(db, name="Testwhisky", category="whisky", quantity=1):
    cur = db.execute(
        "INSERT INTO wines (name, type, region, quantity) VALUES (?,?,?,?)",
        (name, "Single Malt", "Islay", quantity))
    db.commit()
    return cur.lastrowid


def test_details_roundtrip(db):
    wid = _insert_wine(db)
    spirits.set_details(db, wid, {
        "abv": 46.0, "age_years": 16, "distilled_year": 2005, "bottled_year": 2021,
        "bottler": "Original", "batch_number": "Batch 003", "cask_strength": 1,
        "single_cask": 0, "cask_number": "#1234", "chill_filtered": 0, "peat_ppm": 35,
    })
    d = spirits.get_details(db, wid)
    assert d["abv"] == 46.0
    assert d["age_years"] == 16
    assert d["batch_number"] == "Batch 003"
    assert d["cask_strength"] == 1
    assert d["peat_ppm"] == 35


def test_details_update_replaces_values(db):
    wid = _insert_wine(db)
    spirits.set_details(db, wid, {"abv": 40.0})
    spirits.set_details(db, wid, {"abv": 43.0, "age_years": 12})
    d = spirits.get_details(db, wid)
    assert d["abv"] == 43.0 and d["age_years"] == 12


def test_details_missing_row_is_empty_not_an_error(db):
    wid = _insert_wine(db)
    d = spirits.get_details(db, wid)
    assert d["abv"] is None and d["opened_at"] is None


def test_details_cascade_delete(db):
    wid = _insert_wine(db)
    spirits.set_details(db, wid, {"abv": 46.0})
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("DELETE FROM wines WHERE id=?", (wid,))
    db.commit()
    assert db.execute("SELECT COUNT(*) FROM spirit_details WHERE wine_id=?",
                      (wid,)).fetchone()[0] == 0


# ── orphan cleanup (pre-existing bug, fixed alongside) ───────────────────────

def test_deleting_a_wine_removes_its_child_rows(client, db):
    import json as J
    client.post("/add", data={
        "name": "Orphan Test", "type": "red", "region": "X", "quantity": "1",
        "grapes": J.dumps([{"name": "Merlot", "pct": 100}]),
    }, follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Orphan Test'").fetchone()[0]
    client.post(f"/api/wine/{wid}/purchases", json={"quantity": 1, "unit_price": 10})
    spirits.set_details(db, wid, {"abv": 40})
    db.execute("INSERT INTO spirit_casks (wine_id, name, years, position) VALUES (?,?,?,?)",
               (wid, "Ex-Bourbon", 5, 0))
    db.commit()

    client.post(f"/delete/{wid}", follow_redirects=True)

    for table in ("wine_grapes", "wine_purchases", "wine_images",
                  "spirit_details", "spirit_casks"):
        assert db.execute(f"SELECT COUNT(*) FROM {table} WHERE wine_id=?",
                          (wid,)).fetchone()[0] == 0, table


def test_timeline_survives_deletion_on_purpose(client, db):
    """The timeline shows '(deleted)' for removed wines - keep its rows."""
    client.post("/add", data={"name": "History Test", "type": "red", "quantity": "1"},
                follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='History Test'").fetchone()[0]
    client.post(f"/delete/{wid}", follow_redirects=True)
    assert db.execute("SELECT COUNT(*) FROM timeline WHERE wine_id=?",
                      (wid,)).fetchone()[0] > 0


def test_cleanup_orphans_removes_leftovers(db):
    import app as wine_app
    db.execute("INSERT INTO wine_grapes (wine_id, name, pct, position) "
               "VALUES (999999, 'Ghost', NULL, 0)")
    db.execute("INSERT INTO spirit_details (wine_id, abv) VALUES (999999, 40)")
    db.commit()
    removed = wine_app.cleanup_orphans(db)
    assert removed >= 2
    assert db.execute("SELECT COUNT(*) FROM wine_grapes WHERE wine_id=999999").fetchone()[0] == 0
    assert db.execute("SELECT COUNT(*) FROM spirit_details WHERE wine_id=999999").fetchone()[0] == 0
    assert wine_app.cleanup_orphans(db) == 0     # idempotent


# ── casks (ordered maturation chain) ──────────────────────────────────────────

def test_casks_roundtrip_keeps_order_and_years(db):
    wid = _insert_wine(db)
    spirits.set_casks(db, wid, [
        {"name": "Ex-Bourbon", "years": 12},
        {"name": "PX Sherry", "years": 2},
    ])
    rows = spirits.list_casks(db, wid)
    assert [(r["name"], r["years"]) for r in rows] == [("Ex-Bourbon", 12), ("PX Sherry", 2)]
    assert [r["position"] for r in rows] == [0, 1]


def test_casks_build_summary_cache(db):
    wid = _insert_wine(db)
    spirits.set_casks(db, wid, [{"name": "Ex-Bourbon", "years": None},
                                {"name": "PX Sherry", "years": None}])
    assert spirits.get_details(db, wid)["cask_summary"] == "Ex-Bourbon → PX Sherry"


def test_casks_single_entry_summary_is_plain_name(db):
    wid = _insert_wine(db)
    spirits.set_casks(db, wid, [{"name": "Oloroso Sherry", "years": 10}])
    assert spirits.get_details(db, wid)["cask_summary"] == "Oloroso Sherry"


def test_casks_repeated_type_is_kept(db):
    """Unlike grapes, the same cask twice is meaningful (e.g. refill)."""
    wid = _insert_wine(db)
    spirits.set_casks(db, wid, [{"name": "Refill Hogshead", "years": 8},
                                {"name": "Refill Hogshead", "years": 4}])
    assert len(spirits.list_casks(db, wid)) == 2


def test_casks_replace_previous_entries(db):
    wid = _insert_wine(db)
    spirits.set_casks(db, wid, [{"name": "Ex-Bourbon", "years": None}])
    spirits.set_casks(db, wid, [{"name": "Port", "years": None}])
    assert [r["name"] for r in spirits.list_casks(db, wid)] == ["Port"]


def test_casks_skip_blank_names_and_clear_summary(db):
    wid = _insert_wine(db)
    spirits.set_casks(db, wid, [{"name": "  ", "years": 3}])
    assert spirits.list_casks(db, wid) == []
    assert spirits.get_details(db, wid)["cask_summary"] is None


def test_casks_coerce_bad_years_to_none(db):
    wid = _insert_wine(db)
    spirits.set_casks(db, wid, [{"name": "Ex-Bourbon", "years": "abc"}])
    assert spirits.list_casks(db, wid)[0]["years"] is None


# ── open bottles ──────────────────────────────────────────────────────────────

def _actions(db, wid):
    return [r[0] for r in db.execute(
        "SELECT action FROM timeline WHERE wine_id=? ORDER BY id", (wid,)).fetchall()]


def test_open_bottle_moves_one_from_sealed(db):
    wid = _insert_wine(db, quantity=2)
    assert spirits.open_bottle(db, wid, "2026-03-12") is True
    assert db.execute("SELECT quantity FROM wines WHERE id=?", (wid,)).fetchone()[0] == 1
    d = spirits.get_details(db, wid)
    assert d["opened_at"] == "2026-03-12" and d["fill_level"] == 100
    assert "opened" in _actions(db, wid)


def test_open_bottle_refused_when_none_sealed(db):
    wid = _insert_wine(db, quantity=0)
    assert spirits.open_bottle(db, wid, "2026-03-12") is False
    assert spirits.get_details(db, wid)["opened_at"] is None


def test_open_bottle_refused_when_already_open(db):
    wid = _insert_wine(db, quantity=2)
    spirits.open_bottle(db, wid, "2026-03-12")
    assert spirits.open_bottle(db, wid, "2026-03-13") is False
    assert db.execute("SELECT quantity FROM wines WHERE id=?", (wid,)).fetchone()[0] == 1


def test_set_fill_level(db):
    wid = _insert_wine(db, quantity=1)
    spirits.open_bottle(db, wid, "2026-03-12")
    assert spirits.set_fill_level(db, wid, 55) is True
    assert spirits.get_details(db, wid)["fill_level"] == 55


def test_set_fill_level_rejects_out_of_range(db):
    wid = _insert_wine(db, quantity=1)
    spirits.open_bottle(db, wid, "2026-03-12")
    for bad in (-5, 150, "abc"):
        assert spirits.set_fill_level(db, wid, bad) is False
    assert spirits.get_details(db, wid)["fill_level"] == 100


def test_set_fill_level_needs_an_open_bottle(db):
    wid = _insert_wine(db, quantity=1)
    assert spirits.set_fill_level(db, wid, 50) is False


def test_raising_the_fill_level_logs_refilled(db):
    wid = _insert_wine(db, quantity=1)
    spirits.open_bottle(db, wid, "2026-03-12")
    spirits.set_fill_level(db, wid, 40)
    spirits.set_fill_level(db, wid, 70)
    assert "refilled" in _actions(db, wid)


def test_finish_bottle_clears_and_logs(db):
    wid = _insert_wine(db, quantity=1)
    spirits.open_bottle(db, wid, "2026-03-12")
    assert spirits.finish_bottle(db, wid) is True
    d = spirits.get_details(db, wid)
    assert d["opened_at"] is None and d["fill_level"] is None
    assert _actions(db, wid).count("consumed") == 1
    assert spirits.finish_bottle(db, wid) is False


# ── schema wiring ─────────────────────────────────────────────────────────────

def test_category_column_exists_and_defaults_to_wine(db):
    cols = {r[1] for r in db.execute("PRAGMA table_info(wines)")}
    assert "category" in cols
    cur = db.execute("INSERT INTO wines (name, type, quantity) VALUES ('X','red',1)")
    db.commit()
    assert db.execute("SELECT category FROM wines WHERE id=?",
                      (cur.lastrowid,)).fetchone()[0] == "wine"


def test_spirit_tables_created_by_init_db(db):
    names = {r[0] for r in db.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"spirit_details", "spirit_casks"} <= names
