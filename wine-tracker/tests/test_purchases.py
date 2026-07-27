"""Purchase lots: weighted average, CRUD recompute, migration backfill."""
import os
import sqlite3
import sys

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, APP_DIR)

import purchases


def _db():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE wines (id INTEGER PRIMARY KEY, price REAL, quantity INTEGER, purchased_at TEXT)")
    db.execute("INSERT INTO wines (id, price, quantity) VALUES (1, NULL, 6)")
    purchases.create_purchases_table(db)
    return db


def test_weighted_average_and_recompute():
    db = _db()
    purchases.add_purchase(db, 1, {"quantity": 2, "unit_price": 10})
    purchases.add_purchase(db, 1, {"quantity": 3, "unit_price": 20})
    wa = purchases.weighted_average(db, 1)
    assert wa["total_qty"] == 5
    assert wa["total_spent"] == 80
    assert wa["avg"] == 16.0
    assert db.execute("SELECT price FROM wines WHERE id=1").fetchone()[0] == 16.0


def test_delete_recomputes_and_nulls():
    db = _db()
    p1 = purchases.add_purchase(db, 1, {"quantity": 1, "unit_price": 5})
    purchases.delete_purchase(db, p1)
    assert db.execute("SELECT price FROM wines WHERE id=1").fetchone()[0] is None
    assert purchases.list_purchases(db, 1) == []


def test_update_recomputes():
    db = _db()
    p1 = purchases.add_purchase(db, 1, {"quantity": 1, "unit_price": 10})
    purchases.update_purchase(db, p1, {"quantity": 4, "unit_price": 10})
    assert purchases.weighted_average(db, 1)["total_qty"] == 4
    assert db.execute("SELECT price FROM wines WHERE id=1").fetchone()[0] == 10.0


def test_invalid_quantity_raises():
    db = _db()
    import pytest
    with pytest.raises(ValueError):
        purchases.add_purchase(db, 1, {"quantity": 0, "unit_price": 5})


def test_migration_backfill(tmp_path, monkeypatch):
    import app as wine_app
    dbp = str(tmp_path / "m.db")
    monkeypatch.setattr(wine_app, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(wine_app, "UPLOAD_DIR", str(tmp_path / "up"))
    os.makedirs(str(tmp_path / "up"), exist_ok=True)
    monkeypatch.setattr(wine_app, "DB_PATH", dbp)
    wine_app.init_db()  # full schema, empty
    con = sqlite3.connect(dbp)
    con.execute("INSERT INTO wines (name, price, quantity, added) VALUES ('W', 25.0, 4, '2026-01-01')")
    con.commit()
    con.close()
    wine_app.init_db()  # idempotent; backfill runs because wine_purchases is empty
    con = sqlite3.connect(dbp)
    con.row_factory = sqlite3.Row
    lots = con.execute("SELECT * FROM wine_purchases").fetchall()
    assert len(lots) == 1
    assert lots[0]["unit_price"] == 25.0
    assert lots[0]["quantity"] == 4
    assert con.execute("SELECT price FROM wines").fetchone()[0] == 25.0
    con.close()
