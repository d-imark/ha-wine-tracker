"""Purchase lots per wine.

Each row records one purchase event (when, how many bottles, where, unit price).
These are pure cost/provenance records and are intentionally decoupled from the
stock quantity (`wines.quantity`). The quantity-weighted average unit price is
cached back into `wines.price` so existing value statistics keep working.
"""
from datetime import datetime


def create_purchases_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS wine_purchases (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            wine_id       INTEGER NOT NULL,
            purchase_date TEXT,
            quantity      INTEGER NOT NULL DEFAULT 1,
            unit_price    REAL NOT NULL,
            location      TEXT,
            note          TEXT,
            created       TEXT NOT NULL,
            FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE
        )
    """)


def _coerce(data):
    """Validate + normalise incoming purchase data. Raises ValueError on bad input."""
    q = int(data.get("quantity") or 0)
    if q <= 0:
        raise ValueError("quantity_must_be_positive")
    up = float(data.get("unit_price") if data.get("unit_price") not in (None, "") else -1)
    if up < 0:
        raise ValueError("price_must_be_non_negative")
    date = (str(data.get("purchase_date") or "")).strip() or None
    loc = (str(data.get("location") or "")).strip() or None
    note = (str(data.get("note") or "")).strip() or None
    return q, up, date, loc, note


def weighted_average(db, wine_id):
    row = db.execute(
        "SELECT COALESCE(SUM(quantity), 0) q, COALESCE(SUM(quantity * unit_price), 0) s "
        "FROM wine_purchases WHERE wine_id=?", (wine_id,)).fetchone()
    q, s = row[0], row[1]
    avg = round(s / q, 2) if q else None
    return {"avg": avg, "total_qty": q, "total_spent": round(s, 2)}


def recompute_wine_price(db, wine_id):
    avg = weighted_average(db, wine_id)["avg"]
    db.execute("UPDATE wines SET price=? WHERE id=?", (avg, wine_id))
    return avg


def list_purchases(db, wine_id):
    rows = db.execute(
        "SELECT id, wine_id, purchase_date, quantity, unit_price, location, note, created "
        "FROM wine_purchases WHERE wine_id=? ORDER BY COALESCE(purchase_date, ''), id",
        (wine_id,)).fetchall()
    return [dict(r) for r in rows]


def add_purchase(db, wine_id, data):
    q, up, date, loc, note = _coerce(data)
    cur = db.execute(
        "INSERT INTO wine_purchases (wine_id, purchase_date, quantity, unit_price, location, note, created) "
        "VALUES (?,?,?,?,?,?,?)",
        (wine_id, date, q, up, loc, note, datetime.now().isoformat()))
    db.commit()
    recompute_wine_price(db, wine_id)
    db.commit()
    return cur.lastrowid


def update_purchase(db, pid, data):
    row = db.execute("SELECT wine_id FROM wine_purchases WHERE id=?", (pid,)).fetchone()
    if not row:
        return False
    q, up, date, loc, note = _coerce(data)
    db.execute(
        "UPDATE wine_purchases SET purchase_date=?, quantity=?, unit_price=?, location=?, note=? WHERE id=?",
        (date, q, up, loc, note, pid))
    db.commit()
    recompute_wine_price(db, row[0])
    db.commit()
    return True


def delete_purchase(db, pid):
    row = db.execute("SELECT wine_id FROM wine_purchases WHERE id=?", (pid,)).fetchone()
    if not row:
        return False
    db.execute("DELETE FROM wine_purchases WHERE id=?", (pid,))
    db.commit()
    recompute_wine_price(db, row[0])
    db.commit()
    return True
