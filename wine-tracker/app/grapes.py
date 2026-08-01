"""Grape varieties per wine (1-n, each with an optional percentage).

`wine_grapes` is the source of truth for a wine's blend. The plain-text
`wines.grape` column is kept as an auto-rebuilt cache so existing search,
filter, sort, export and chat paths keep working unchanged.
"""
import json
import re

import reference

_SPLIT_RE = re.compile(r"[,&/+]")


def create_wine_grapes_table(db):
    db.execute("""
        CREATE TABLE IF NOT EXISTS wine_grapes (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            wine_id   INTEGER NOT NULL,
            grape_id  INTEGER,
            name      TEXT NOT NULL,
            pct       REAL,
            position  INTEGER DEFAULT 0,
            FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE,
            FOREIGN KEY (grape_id) REFERENCES ref_grapes(id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_wine_grapes_wine ON wine_grapes(wine_id)")


def split_legacy(text):
    """Split a free-text grape string into an ordered, de-duplicated list."""
    if not text:
        return []
    out, seen = [], set()
    for part in _SPLIT_RE.split(text):
        name = part.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(name)
    return out


def _coerce_pct(value):
    if value in (None, ""):
        return None
    try:
        p = float(value)
    except (TypeError, ValueError):
        return None
    if p < 0 or p > 100:
        return None
    return p


def rebuild_cache(db, wine_id):
    rows = db.execute(
        "SELECT name FROM wine_grapes WHERE wine_id=? ORDER BY position", (wine_id,)
    ).fetchall()
    cache = ", ".join(r[0] for r in rows) or None
    db.execute("UPDATE wines SET grape=? WHERE id=?", (cache, wine_id))
    return cache


def set_wine_grapes(db, wine_id, entries):
    """Replace all grape rows for a wine. entries: [{"name", "pct"}].

    Entries that resolve to the same reference grape are merged - "Shiraz" and
    "Syrah" are one variety (alias), not two. A merged entry takes the canonical
    reference name; a name entered only once keeps exactly what was typed.
    Unknown (custom) names are de-duplicated by their normalized name instead.
    """
    db.execute("DELETE FROM wine_grapes WHERE wine_id=?", (wine_id,))

    resolved = []      # ordered entries: {name, pct, grape_id, ref_name}
    index = {}         # dedupe key -> position in `resolved`
    for e in entries or []:
        name = (str(e.get("name") or "")).strip()
        if not name:
            continue
        ref = reference.match_reference(db, "grape", name)
        grape_id = ref["id"] if ref else None
        key = ("id", grape_id) if grape_id is not None else ("name", name.lower())
        pct = _coerce_pct(e.get("pct"))
        if key in index:
            slot = resolved[index[key]]
            # Duplicate of an entry already kept: switch to the canonical name
            # and keep the first percentage that was given.
            if slot["ref_name"]:
                slot["name"] = slot["ref_name"]
            if slot["pct"] is None:
                slot["pct"] = pct
            continue
        index[key] = len(resolved)
        resolved.append({"name": name, "pct": pct, "grape_id": grape_id,
                         "ref_name": ref["name"] if ref else None})

    for pos, r in enumerate(resolved):
        db.execute(
            "INSERT INTO wine_grapes (wine_id, grape_id, name, pct, position) VALUES (?,?,?,?,?)",
            (wine_id, r["grape_id"], r["name"], r["pct"], pos))
    rebuild_cache(db, wine_id)
    db.commit()


def _aliases_of(row):
    try:
        return json.loads(row["aliases"] or "[]")
    except (json.JSONDecodeError, TypeError):
        return []


def merge_duplicate_reference_grapes(db):
    """Collapse reference entries describing the same variety - a row whose name
    is already another row's alias (e.g. "Sylvaner" next to "Silvaner").

    The row actually used by wines survives (ties go to the lower id); the other
    row's name and aliases move over as aliases, then it is removed.
    """
    rows = db.execute("SELECT id, name, norm, aliases FROM ref_grapes").fetchall()
    owners_by_alias = {}
    for r in rows:
        for a in _aliases_of(r):
            owners_by_alias.setdefault(reference.normalize_name(a), []).append(r)

    def usage(gid):
        return db.execute("SELECT COUNT(*) FROM wine_grapes WHERE grape_id=?", (gid,)).fetchone()[0]

    handled, merged = set(), 0
    for row in rows:
        if row["id"] in handled:
            continue
        for owner in owners_by_alias.get(row["norm"], []):
            if owner["id"] == row["id"] or owner["id"] in handled:
                continue
            pair = sorted((row, owner), key=lambda r: (-usage(r["id"]), r["id"]))
            keep, drop = pair[0], pair[1]
            names = {reference.normalize_name(a): a
                     for a in _aliases_of(keep) + _aliases_of(drop) + [drop["name"]]}
            names.pop(keep["norm"], None)          # never alias a row to itself
            db.execute("UPDATE wine_grapes SET grape_id=? WHERE grape_id=?", (keep["id"], drop["id"]))
            db.execute("UPDATE ref_grapes SET aliases=? WHERE id=?",
                       (json.dumps(sorted(names.values())), keep["id"]))
            db.execute("DELETE FROM ref_grapes WHERE id=?", (drop["id"],))
            handled.update((keep["id"], drop["id"]))
            merged += 1
            break
    return merged


def relink_unmatched(db):
    """Attach rows that had no reference match to reference grapes that exist
    now (e.g. varieties added to the seed list in a later release)."""
    linked = 0
    for row in db.execute("SELECT id, name FROM wine_grapes WHERE grape_id IS NULL").fetchall():
        ref = reference.match_reference(db, "grape", row["name"])
        if ref:
            db.execute("UPDATE wine_grapes SET grape_id=? WHERE id=?", (ref["id"], row["id"]))
            linked += 1
    return linked


def dedupe_wine_grapes(db):
    """One-time: collapse alias duplicates created before merging existed
    (e.g. a Vivino import that produced both "Shiraz" and "Syrah")."""
    wine_ids = [r[0] for r in db.execute(
        "SELECT wine_id FROM wine_grapes WHERE grape_id IS NOT NULL "
        "GROUP BY wine_id, grape_id HAVING COUNT(*) > 1").fetchall()]
    for wid in dict.fromkeys(wine_ids):          # de-dup the wine list, keep order
        current = list_wine_grapes(db, wid)
        set_wine_grapes(db, wid, [{"name": g["name"], "pct": g["pct"]} for g in current])
    return len(set(wine_ids))


def list_wine_grapes(db, wine_id):
    rows = db.execute(
        """SELECT wg.name, wg.pct, wg.grape_id, wg.position, rg.color AS color
             FROM wine_grapes wg
             LEFT JOIN ref_grapes rg ON rg.id = wg.grape_id
            WHERE wg.wine_id=? ORDER BY wg.position""",
        (wine_id,)).fetchall()
    return [dict(r) for r in rows]
