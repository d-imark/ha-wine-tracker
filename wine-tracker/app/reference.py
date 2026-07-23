"""Reference-data layer (TP1): schema, idempotent seeding, matching, listing.

Bundled reference data (countries, regions, grapes, wine types, bottle formats)
lives in reference_data.py and is seeded into DB tables so users can extend it
with their own (is_custom=1) entries. Functions take a sqlite3 connection so they
are usable both inside the Flask app and in tests.
"""
from __future__ import annotations

import difflib
import json
import unicodedata

import reference_data as rd


# entity name -> (table, has_country_scope)
_ENTITY_TABLE = {
    "country": "ref_countries",
    "region": "ref_regions",
    "grape": "ref_grapes",
    "wine_type": "ref_wine_types",
}


class UnknownEntity(Exception):
    pass


def normalize_name(s) -> str:
    """lowercase, strip accents, collapse punctuation/whitespace - for matching."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    cleaned = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s.lower())
    return " ".join(cleaned.split())


# ── Schema ────────────────────────────────────────────────────────────────────

_DDL = [
    """CREATE TABLE IF NOT EXISTS ref_countries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE, name TEXT, norm TEXT, lat REAL, lon REAL,
        aliases TEXT, is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS ref_regions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT, norm TEXT, country_code TEXT, lat REAL, lon REAL,
        aliases TEXT, is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS ref_grapes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, norm TEXT, color TEXT, aliases TEXT,
        is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS ref_wine_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE, norm TEXT, color TEXT, aliases TEXT,
        is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS ref_bottle_formats (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, norm TEXT, liters REAL,
        is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
]


def create_reference_tables(db):
    for ddl in _DDL:
        db.execute(ddl)


# ── Seeding (idempotent, update-safe: only inserts missing built-ins) ─────────

def _exists(db, sql, params):
    return db.execute(sql, params).fetchone() is not None


def seed_reference_data(db):
    """Insert any missing built-in rows. Never overwrites or deletes existing
    rows, so user customs and manual edits to built-ins survive re-seeding."""
    for i, c in enumerate(rd.COUNTRIES):
        if not _exists(db, "SELECT 1 FROM ref_countries WHERE code=?", (c["code"],)):
            db.execute(
                "INSERT INTO ref_countries (code,name,norm,lat,lon,aliases,is_custom,sort_order) "
                "VALUES (?,?,?,?,?,?,0,?)",
                (c["code"], c["name"], normalize_name(c["name"]), c["lat"], c["lon"],
                 json.dumps(c.get("aliases", [])), i))

    for i, r in enumerate(rd.REGIONS):
        norm = normalize_name(r["name"])
        if not _exists(db, "SELECT 1 FROM ref_regions WHERE norm=? AND country_code=?",
                       (norm, r["country_code"])):
            db.execute(
                "INSERT INTO ref_regions (name,norm,country_code,lat,lon,aliases,is_custom,sort_order) "
                "VALUES (?,?,?,?,?,?,0,?)",
                (r["name"], norm, r["country_code"], r.get("lat"), r.get("lon"),
                 json.dumps(r.get("aliases", [])), i))

    for i, g in enumerate(rd.GRAPES):
        norm = normalize_name(g["name"])
        if not _exists(db, "SELECT 1 FROM ref_grapes WHERE norm=?", (norm,)):
            db.execute(
                "INSERT INTO ref_grapes (name,norm,color,aliases,is_custom,sort_order) "
                "VALUES (?,?,?,?,0,?)",
                (g["name"], norm, g.get("color"), json.dumps(g.get("aliases", [])), i))

    for i, w in enumerate(rd.WINE_TYPES):
        if not _exists(db, "SELECT 1 FROM ref_wine_types WHERE key=?", (w["key"],)):
            db.execute(
                "INSERT INTO ref_wine_types (key,norm,color,aliases,is_custom,sort_order) "
                "VALUES (?,?,?,?,0,?)",
                (w["key"], normalize_name(w["key"]), w.get("color"),
                 json.dumps(w.get("aliases", [])), i))

    for i, b in enumerate(rd.BOTTLE_FORMATS):
        norm = normalize_name(b["name"])
        if not _exists(db, "SELECT 1 FROM ref_bottle_formats WHERE norm=?", (norm,)):
            db.execute(
                "INSERT INTO ref_bottle_formats (name,norm,liters,is_custom,sort_order) "
                "VALUES (?,?,?,0,?)",
                (b["name"], norm, b["liters"], i))


# ── Matching ──────────────────────────────────────────────────────────────────

def _aliases_list(row):
    try:
        return list(json.loads(row["aliases"] or "[]"))
    except (json.JSONDecodeError, TypeError, IndexError):
        return []


def _alias_norms(row):
    return {normalize_name(a) for a in _aliases_list(row)}


def match_reference(db, entity, value, country_code=None):
    """Return the matching reference row or None.

    entity: 'country' | 'region' | 'grape' | 'wine_type'
    Country matches by ISO code first, then normalized name/aliases. Region is
    matched within country_code when given.
    """
    nv = normalize_name(value)

    if entity == "country":
        code = (str(value) or "").strip().upper()
        if len(code) == 2:
            row = db.execute("SELECT * FROM ref_countries WHERE code=?", (code,)).fetchone()
            if row:
                return row
        for row in db.execute("SELECT * FROM ref_countries"):
            if row["norm"] == nv or nv in _alias_norms(row):
                return row
        return None

    if entity == "grape":
        if not nv:
            return None
        for row in db.execute("SELECT * FROM ref_grapes"):
            if row["norm"] == nv or nv in _alias_norms(row):
                return row
        return None

    if entity == "wine_type":
        if not nv:
            return None
        for row in db.execute("SELECT * FROM ref_wine_types"):
            if row["norm"] == nv or normalize_name(row["key"]) == nv or nv in _alias_norms(row):
                return row
        return None

    if entity == "region":
        if not nv:
            return None
        cc = country_code.upper() if country_code else None
        for row in db.execute("SELECT * FROM ref_regions"):
            if cc and (row["country_code"] or "").upper() != cc:
                continue
            if row["norm"] == nv or nv in _alias_norms(row):
                return row
        return None

    raise UnknownEntity(entity)


def add_custom_entry(db, entity, **fields):
    """Add an is_custom=1 reference entry. Idempotent: returns the existing row
    if one already matches (so repeated Vivino imports don't create duplicates)."""
    lookup = fields.get("name") or fields.get("key") or fields.get("code")
    existing = match_reference(db, entity, lookup, fields.get("country_code"))
    if existing:
        return existing

    name = fields.get("name", "")
    norm = normalize_name(name or fields.get("key", ""))
    aliases = json.dumps(fields.get("aliases", []))

    if entity == "grape":
        cur = db.execute(
            "INSERT INTO ref_grapes (name,norm,color,aliases,is_custom,sort_order) VALUES (?,?,?,?,1,0)",
            (name, norm, fields.get("color"), aliases))
        return db.execute("SELECT * FROM ref_grapes WHERE id=?", (cur.lastrowid,)).fetchone()

    if entity == "region":
        cur = db.execute(
            "INSERT INTO ref_regions (name,norm,country_code,lat,lon,aliases,is_custom,sort_order) "
            "VALUES (?,?,?,?,?,?,1,0)",
            (name, norm, fields.get("country_code"), fields.get("lat"), fields.get("lon"), aliases))
        return db.execute("SELECT * FROM ref_regions WHERE id=?", (cur.lastrowid,)).fetchone()

    raise UnknownEntity(f"add_custom_entry unsupported for entity: {entity}")


def suggest_matches(db, entity, value, country_code=None, limit=5):
    """Return reference rows ranked by fuzzy similarity to `value`, best first.

    Basis for the no-AI reconciliation fallback: when a value doesn't match
    exactly, offer the closest known entries. Regions are scoped to country_code.
    Score = best fuzzy ratio over the entry's name + its aliases.
    """
    table = _ENTITY_TABLE.get(entity)
    if not table:
        raise UnknownEntity(entity)
    nv = normalize_name(value)
    cc = country_code.upper() if country_code else None

    scored = []
    for row in db.execute(f"SELECT * FROM {table}"):
        if entity == "region" and cc and (row["country_code"] or "").upper() != cc:
            continue
        candidates = [row["norm"]] + list(_alias_norms(row))
        score = max((difflib.SequenceMatcher(None, nv, c).ratio() for c in candidates if c),
                    default=0.0)
        scored.append((score, row))
    scored.sort(key=lambda t: t[0], reverse=True)
    return [row for _, row in scored[:limit]]


def add_alias(db, entity, entry_id, alias):
    """Append `alias` to an existing reference entry (idempotent). Lets a
    confirmed reconciliation teach the reference so future values match."""
    table = _ENTITY_TABLE.get(entity)
    if not table:
        raise UnknownEntity(entity)
    row = db.execute(f"SELECT aliases FROM {table} WHERE id=?", (entry_id,)).fetchone()
    if not row:
        return False
    if not alias or not alias.strip():
        return True
    aliases = _aliases_list(row)
    if normalize_name(alias) not in {normalize_name(a) for a in aliases}:
        aliases.append(alias.strip())
        db.execute(f"UPDATE {table} SET aliases=? WHERE id=?", (json.dumps(aliases), entry_id))
    return True


# ── Listing (read API) ─────────────────────────────────────────────────────────

_LIST = {
    "countries":      ("ref_countries",      "name"),
    "regions":        ("ref_regions",        "name"),
    "grapes":         ("ref_grapes",         "name"),
    "wine_types":     ("ref_wine_types",     "key"),
    "bottle_formats": ("ref_bottle_formats", "sort_order"),
}


def list_reference(db, entity, country=None):
    if entity not in _LIST:
        raise UnknownEntity(entity)
    table, name_col = _LIST[entity]
    sql = f"SELECT * FROM {table}"
    params = []
    if entity == "regions" and country:
        sql += " WHERE country_code=?"
        params.append(country.upper())
    sql += f" ORDER BY sort_order, {name_col}"
    items = []
    for row in db.execute(sql, params):
        d = dict(row)
        if "aliases" in d:
            try:
                d["aliases"] = json.loads(d["aliases"] or "[]")
            except (json.JSONDecodeError, TypeError):
                d["aliases"] = []
        items.append(d)
    return items
