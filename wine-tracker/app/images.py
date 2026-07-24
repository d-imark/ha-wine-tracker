"""Wine image collection (BP1): schema, migration and CRUD for multiple images
per wine across categories (scan/vivino/ki/manuell). Functions take a sqlite3
connection so they work both inside the Flask app and in tests. The legacy
`wines.image` column is kept in sync with the current default image so existing
display code keeps working unchanged.
"""
from __future__ import annotations

from datetime import datetime

CATEGORIES = ("scan", "vivino", "ki", "manuell")


def create_images_table(db):
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS wine_images (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            wine_id    INTEGER NOT NULL,
            category   TEXT NOT NULL,
            filename   TEXT NOT NULL,
            is_default INTEGER NOT NULL DEFAULT 0,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created    TEXT
        )
        """
    )
    db.execute("CREATE INDEX IF NOT EXISTS idx_wine_images_wine ON wine_images(wine_id)")


def _sync_wine_image(db, wine_id):
    row = db.execute(
        "SELECT filename FROM wine_images WHERE wine_id=? AND is_default=1 LIMIT 1",
        (wine_id,),
    ).fetchone()
    fname = row["filename"] if row else None
    db.execute("UPDATE wines SET image=? WHERE id=?", (fname, wine_id))


def add_image(db, wine_id, category, filename):
    if category not in CATEGORIES:
        raise ValueError("unknown category: %s" % category)
    cnt = db.execute(
        "SELECT COUNT(*) FROM wine_images WHERE wine_id=?", (wine_id,)
    ).fetchone()[0]
    is_default = 1 if cnt == 0 else 0
    cur = db.execute(
        "INSERT INTO wine_images (wine_id, category, filename, is_default, sort_order, created) "
        "VALUES (?,?,?,?,?,?)",
        (wine_id, category, filename, is_default, cnt, datetime.now().isoformat()),
    )
    if is_default:
        _sync_wine_image(db, wine_id)
    return cur.lastrowid


def list_images(db, wine_id):
    rows = db.execute(
        "SELECT id, category, filename, is_default, sort_order FROM wine_images "
        "WHERE wine_id=? ORDER BY sort_order, id",
        (wine_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_default_filename(db, wine_id):
    row = db.execute(
        "SELECT filename FROM wine_images WHERE wine_id=? AND is_default=1 LIMIT 1",
        (wine_id,),
    ).fetchone()
    return row["filename"] if row else None


def set_default(db, wine_id, image_id):
    row = db.execute(
        "SELECT id FROM wine_images WHERE id=? AND wine_id=?", (image_id, wine_id)
    ).fetchone()
    if not row:
        return False
    db.execute("UPDATE wine_images SET is_default=0 WHERE wine_id=?", (wine_id,))
    db.execute("UPDATE wine_images SET is_default=1 WHERE id=?", (image_id,))
    _sync_wine_image(db, wine_id)
    return True


def _promote_default_if_missing(db, wine_id):
    has = db.execute(
        "SELECT 1 FROM wine_images WHERE wine_id=? AND is_default=1 LIMIT 1", (wine_id,)
    ).fetchone()
    if has:
        return
    nxt = db.execute(
        "SELECT id FROM wine_images WHERE wine_id=? ORDER BY sort_order, id LIMIT 1",
        (wine_id,),
    ).fetchone()
    if nxt:
        db.execute("UPDATE wine_images SET is_default=1 WHERE id=?", (nxt["id"],))


def remove_image(db, wine_id, image_id):
    row = db.execute(
        "SELECT filename, is_default FROM wine_images WHERE id=? AND wine_id=?",
        (image_id, wine_id),
    ).fetchone()
    if not row:
        return None
    db.execute("DELETE FROM wine_images WHERE id=?", (image_id,))
    if row["is_default"]:
        _promote_default_if_missing(db, wine_id)
    _sync_wine_image(db, wine_id)
    return row["filename"]


def migrate_legacy_images(db):
    rows = db.execute(
        "SELECT id, image FROM wines WHERE image IS NOT NULL AND image != ''"
    ).fetchall()
    for w in rows:
        exists = db.execute(
            "SELECT 1 FROM wine_images WHERE wine_id=? LIMIT 1", (w["id"],)
        ).fetchone()
        if exists:
            continue
        db.execute(
            "INSERT INTO wine_images (wine_id, category, filename, is_default, sort_order, created) "
            "VALUES (?,?,?,?,?,?)",
            (w["id"], "scan", w["image"], 1, 0, datetime.now().isoformat()),
        )


def sync_primary(db, wine_id, old_filename, new_filename):
    if new_filename:
        existing = db.execute(
            "SELECT id FROM wine_images WHERE wine_id=? AND filename=? LIMIT 1",
            (wine_id, new_filename),
        ).fetchone()
        if existing:
            set_default(db, wine_id, existing["id"])
        else:
            new_id = add_image(db, wine_id, "scan", new_filename)
            set_default(db, wine_id, new_id)
    elif old_filename:
        row = db.execute(
            "SELECT id FROM wine_images WHERE wine_id=? AND filename=? LIMIT 1",
            (wine_id, old_filename),
        ).fetchone()
        if row:
            db.execute("DELETE FROM wine_images WHERE id=?", (row["id"],))
            _promote_default_if_missing(db, wine_id)
    _sync_wine_image(db, wine_id)
