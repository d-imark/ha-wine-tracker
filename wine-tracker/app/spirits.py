"""Spirits (whisky) details, cask maturation and open-bottle tracking.

`spirit_details` holds the per-bottle facts that only apply to spirits;
`spirit_casks` is the ordered maturation chain (row 0 = initial cask, the
rest are finishes). Wine rows simply have no entry in either table.
"""
from datetime import datetime

import reference

DETAIL_FIELDS = [
    "abv", "age_years", "distilled_year", "bottled_year", "cask_summary",
    "bottler", "batch_number", "cask_strength", "single_cask", "cask_number",
    "chill_filtered", "peat_ppm", "opened_at", "fill_level",
]


def create_spirit_tables(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS spirit_details (
            wine_id        INTEGER PRIMARY KEY,
            abv            REAL,
            age_years      INTEGER,
            distilled_year INTEGER,
            bottled_year   INTEGER,
            cask_summary   TEXT,
            bottler        TEXT,
            batch_number   TEXT,
            cask_strength  INTEGER DEFAULT 0,
            single_cask    INTEGER DEFAULT 0,
            cask_number    TEXT,
            chill_filtered INTEGER,
            peat_ppm       INTEGER,
            opened_at      TEXT,
            fill_level     REAL,
            FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS spirit_casks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            wine_id   INTEGER NOT NULL,
            -- cask_id is a soft reference to ref_cask_types: resolved
            -- best-effort on save and left NULL for custom cask names. No FK
            -- declared because this table is created before the reference
            -- tables exist on a fresh database.
            cask_id   INTEGER,
            name      TEXT NOT NULL,
            years     REAL,
            position  INTEGER DEFAULT 0,
            FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_spirit_casks_wine ON spirit_casks(wine_id)")


def _coerce_years(value):
    if value in (None, ""):
        return None
    try:
        y = float(value)
    except (TypeError, ValueError):
        return None
    return y if 0 < y <= 100 else None


def _match_cask(db, name):
    """Resolve a cask name against the reference list. Tolerates the reference
    entity not existing yet (fresh database, older release)."""
    try:
        return reference.match_reference(db, "cask_type", name)
    except Exception:
        return None


def get_details(db, wine_id):
    """Always returns a dict with every field; missing row -> all None."""
    row = db.execute(
        "SELECT " + ", ".join(DETAIL_FIELDS) + " FROM spirit_details WHERE wine_id=?",
        (wine_id,)).fetchone()
    if not row:
        return {f: None for f in DETAIL_FIELDS}
    return {f: row[f] for f in DETAIL_FIELDS}


def set_details(db, wine_id, data):
    """UPSERT the detail row. Only keys in DETAIL_FIELDS are stored; unknown
    keys are ignored so callers can pass a whole form dict."""
    merged = get_details(db, wine_id)
    for key in DETAIL_FIELDS:
        if key in data:
            merged[key] = data[key]
    cols = ", ".join(DETAIL_FIELDS)
    marks = ", ".join(["?"] * len(DETAIL_FIELDS))
    db.execute(
        f"INSERT INTO spirit_details (wine_id, {cols}) VALUES (?, {marks}) "
        "ON CONFLICT(wine_id) DO UPDATE SET " +
        ", ".join(f"{c}=excluded.{c}" for c in DETAIL_FIELDS),
        [wine_id] + [merged[f] for f in DETAIL_FIELDS])
    db.commit()


def rebuild_cask_summary(db, wine_id):
    """Rebuild the display/search cache in spirit_details from the cask rows."""
    rows = db.execute(
        "SELECT name FROM spirit_casks WHERE wine_id=? ORDER BY position",
        (wine_id,)).fetchall()
    summary = " → ".join(r[0] for r in rows) or None
    set_details(db, wine_id, {"cask_summary": summary})
    return summary


def set_casks(db, wine_id, entries):
    """Replace the maturation chain. entries: [{"name", "years"}] in order,
    first entry = initial cask, the rest are finishes.

    Repeated cask types are kept on purpose - a whisky can spend time in two
    refill casks of the same kind, which is not a duplicate the way a repeated
    grape variety would be.
    """
    db.execute("DELETE FROM spirit_casks WHERE wine_id=?", (wine_id,))
    pos = 0
    for e in entries or []:
        name = (str(e.get("name") or "")).strip()
        if not name:
            continue
        ref = _match_cask(db, name)
        db.execute(
            "INSERT INTO spirit_casks (wine_id, cask_id, name, years, position) "
            "VALUES (?,?,?,?,?)",
            (wine_id, ref["id"] if ref else None,
             ref["name"] if ref else name, _coerce_years(e.get("years")), pos))
        pos += 1
    rebuild_cask_summary(db, wine_id)
    db.commit()


def list_casks(db, wine_id):
    rows = db.execute(
        "SELECT name, years, cask_id, position FROM spirit_casks "
        "WHERE wine_id=? ORDER BY position", (wine_id,)).fetchall()
    return [dict(r) for r in rows]


def _log(db, wine_id, action, quantity=1):
    db.execute(
        "INSERT INTO timeline (wine_id, action, quantity, timestamp) VALUES (?,?,?,?)",
        (wine_id, action, quantity, datetime.now().isoformat()))


def open_bottle(db, wine_id, today):
    """Move one sealed bottle to 'open'. Returns False when there is nothing
    sealed left or a bottle is already open."""
    if get_details(db, wine_id)["opened_at"]:
        return False
    row = db.execute("SELECT quantity FROM wines WHERE id=?", (wine_id,)).fetchone()
    if not row or (row[0] or 0) <= 0:
        return False
    db.execute("UPDATE wines SET quantity = quantity - 1 WHERE id=?", (wine_id,))
    set_details(db, wine_id, {"opened_at": today, "fill_level": 100})
    _log(db, wine_id, "opened")
    db.commit()
    return True


def set_fill_level(db, wine_id, percent):
    """Set the open bottle's fill level (0-100). Returns False on a bad value
    or when no bottle is open."""
    current = get_details(db, wine_id)
    if not current["opened_at"]:
        return False
    try:
        pct = float(percent)
    except (TypeError, ValueError):
        return False
    if pct < 0 or pct > 100:
        return False
    previous = current["fill_level"]
    set_details(db, wine_id, {"fill_level": pct})
    # A level going up is a correction, not consumption - log it so the
    # history does not read as if the bottle refilled itself.
    if previous is not None and pct > previous:
        _log(db, wine_id, "refilled")
    db.commit()
    return True


def finish_bottle(db, wine_id):
    """Mark the open bottle as empty. Returns False when none is open."""
    if not get_details(db, wine_id)["opened_at"]:
        return False
    set_details(db, wine_id, {"opened_at": None, "fill_level": None})
    _log(db, wine_id, "consumed")
    db.commit()
    return True
