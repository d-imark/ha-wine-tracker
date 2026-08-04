"""Reference-data layer (TP1): schema, idempotent seeding, matching, listing.

Bundled reference data (countries, wine + spirit regions, grapes, wine types,
spirit types, cask types, bottle formats)
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
    "spirit_region": "ref_spirit_regions",
    "grape": "ref_grapes",
    "wine_type": "ref_wine_types",
}

# Both region entities share the same table shape and country scoping.
_REGION_ENTITIES = ("region", "spirit_region")


def region_entity(category):
    """Wine and spirits keep separate region lists - pick the right one."""
    return "spirit_region" if str(category or "").lower() in ("whisky", "spirit") else "region"


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
    """CREATE TABLE IF NOT EXISTS ref_spirit_regions (
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
    """CREATE TABLE IF NOT EXISTS ref_spirit_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE, norm TEXT, color TEXT, aliases TEXT,
        is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS ref_cask_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, norm TEXT, aliases TEXT,
        is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
]


def create_reference_tables(db):
    for ddl in _DDL:
        db.execute(ddl)


# ── Seeding (idempotent, update-safe: only inserts missing built-ins) ─────────

def seed_reference_data(db):
    """Insert any missing built-in rows. Never overwrites or deletes existing
    rows, so user customs and manual edits to built-ins survive re-seeding.

    Uses one existence query + a single executemany per entity, so seeding a
    fresh DB (tests, first install) is a handful of statements instead of one
    per row.
    """
    def _al(x):
        return json.dumps(x.get("aliases", []))

    # `seen` starts from existing DB keys and also absorbs duplicates *within*
    # the seed list (e.g. gavinr lists territories under a shared ISO code).
    # countries - natural key: code
    seen = {r[0] for r in db.execute("SELECT code FROM ref_countries")}
    rows = []
    for i, c in enumerate(rd.COUNTRIES):
        if c["code"] in seen:
            continue
        seen.add(c["code"])
        rows.append((c["code"], c["name"], normalize_name(c["name"]), c["lat"], c["lon"], _al(c), i))
    if rows:
        db.executemany("INSERT INTO ref_countries (code,name,norm,lat,lon,aliases,sort_order) "
                       "VALUES (?,?,?,?,?,?,?)", rows)

    # regions - natural key: (norm, country_code)
    seen = {(r[0], r[1]) for r in db.execute("SELECT norm, country_code FROM ref_regions")}
    rows = []
    for i, r in enumerate(rd.REGIONS):
        norm = normalize_name(r["name"])
        key = (norm, r["country_code"])
        if key in seen:
            continue
        seen.add(key)
        rows.append((r["name"], norm, r["country_code"], r.get("lat"), r.get("lon"), _al(r), i))
    if rows:
        db.executemany("INSERT INTO ref_regions (name,norm,country_code,lat,lon,aliases,sort_order) "
                       "VALUES (?,?,?,?,?,?,?)", rows)

    # spirit regions - own list, same natural key: (norm, country_code)
    seen = {(r[0], r[1]) for r in db.execute("SELECT norm, country_code FROM ref_spirit_regions")}
    rows = []
    for i, r in enumerate(rd.SPIRIT_REGIONS):
        norm = normalize_name(r["name"])
        key = (norm, r["country_code"])
        if key in seen:
            continue
        seen.add(key)
        rows.append((r["name"], norm, r["country_code"], r.get("lat"), r.get("lon"), _al(r), i))
    if rows:
        db.executemany("INSERT INTO ref_spirit_regions (name,norm,country_code,lat,lon,aliases,sort_order) "
                       "VALUES (?,?,?,?,?,?,?)", rows)

    # grapes - natural key: norm
    seen = {r[0] for r in db.execute("SELECT norm FROM ref_grapes")}
    rows = []
    for i, g in enumerate(rd.GRAPES):
        norm = normalize_name(g["name"])
        if norm in seen:
            continue
        seen.add(norm)
        rows.append((g["name"], norm, g.get("color"), _al(g), i))
    if rows:
        db.executemany("INSERT INTO ref_grapes (name,norm,color,aliases,sort_order) "
                       "VALUES (?,?,?,?,?)", rows)

    # wine_types - natural key: key
    seen = {r[0] for r in db.execute("SELECT key FROM ref_wine_types")}
    rows = []
    for i, w in enumerate(rd.WINE_TYPES):
        if w["key"] in seen:
            continue
        seen.add(w["key"])
        rows.append((w["key"], normalize_name(w["key"]), w.get("color"), _al(w), i))
    if rows:
        db.executemany("INSERT INTO ref_wine_types (key,norm,color,aliases,sort_order) "
                       "VALUES (?,?,?,?,?)", rows)

    # bottle_formats - natural key: norm
    seen = {r[0] for r in db.execute("SELECT norm FROM ref_bottle_formats")}
    rows = []
    for i, b in enumerate(rd.BOTTLE_FORMATS):
        norm = normalize_name(b["name"])
        if norm in seen:
            continue
        seen.add(norm)
        rows.append((b["name"], norm, b["liters"], i))
    if rows:
        db.executemany("INSERT INTO ref_bottle_formats (name,norm,liters,sort_order) "
                       "VALUES (?,?,?,?)", rows)

    # spirit_types - natural key: key
    seen = {r[0] for r in db.execute("SELECT key FROM ref_spirit_types")}
    rows = []
    for i, s in enumerate(rd.SPIRIT_TYPES):
        if s["key"] in seen:
            continue
        seen.add(s["key"])
        rows.append((s["key"], normalize_name(s["key"]), s.get("color"), _al(s), i))
    if rows:
        db.executemany("INSERT INTO ref_spirit_types (key,norm,color,aliases,sort_order) "
                       "VALUES (?,?,?,?,?)", rows)

    # cask_types - natural key: norm
    seen = {r[0] for r in db.execute("SELECT norm FROM ref_cask_types")}
    rows = []
    for i, c in enumerate(rd.CASK_TYPES):
        norm = normalize_name(c["name"])
        if norm in seen:
            continue
        seen.add(norm)
        rows.append((c["name"], norm, _al(c), i))
    if rows:
        db.executemany("INSERT INTO ref_cask_types (name,norm,aliases,sort_order) "
                       "VALUES (?,?,?,?)", rows)


# ── Matching ──────────────────────────────────────────────────────────────────

def _aliases_list(row):
    try:
        return list(json.loads(row["aliases"] or "[]"))
    except (json.JSONDecodeError, TypeError, IndexError):
        return []


def _alias_norms(row):
    return {normalize_name(a) for a in _aliases_list(row)}


def migrate_spirit_regions_out_of_regions(db):
    """Remove the whisky regions that an earlier build seeded into ref_regions.

    They now live in ref_spirit_regions. Only built-in rows (is_custom=0) are
    dropped - a region the user added themselves stays where they put it. The
    wines' region text is never touched.

    Deliberately an explicit list, NOT all of SPIRIT_REGIONS: names like Jerez
    and Cognac are genuine wine regions too and must stay in ref_regions.
    """
    stray = [("Islay", "GB"), ("Speyside", "GB"), ("Highlands", "GB"),
             ("Lowlands", "GB"), ("Campbeltown", "GB"), ("Islands", "GB")]
    removed = 0
    for name, cc in stray:
        cur = db.execute(
            "DELETE FROM ref_regions WHERE norm=? AND country_code=? AND is_custom=0",
            (normalize_name(name), cc))
        removed += cur.rowcount or 0
    return removed


def match_reference(db, entity, value, country_code=None):
    """Return the matching reference row or None.

    entity: 'country' | 'region' | 'spirit_region' | 'grape' | 'wine_type' |
            'spirit_type' | 'cask_type'
    Country matches by ISO code first, then normalized name/aliases. Both region
    entities are matched within country_code when given.
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

    if entity == "spirit_type":
        if not nv:
            return None
        for row in db.execute("SELECT * FROM ref_spirit_types"):
            if row["norm"] == nv or normalize_name(row["key"]) == nv or nv in _alias_norms(row):
                return row
        return None

    if entity == "cask_type":
        if not nv:
            return None
        for row in db.execute("SELECT * FROM ref_cask_types"):
            if row["norm"] == nv or nv in _alias_norms(row):
                return row
        return None

    if entity in _REGION_ENTITIES:
        if not nv:
            return None
        cc = country_code.upper() if country_code else None
        for row in db.execute(f"SELECT * FROM {_ENTITY_TABLE[entity]}"):
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

    if entity in _REGION_ENTITIES:
        table = _ENTITY_TABLE[entity]
        cur = db.execute(
            f"INSERT INTO {table} (name,norm,country_code,lat,lon,aliases,is_custom,sort_order) "
            "VALUES (?,?,?,?,?,?,1,0)",
            (name, norm, fields.get("country_code"), fields.get("lat"), fields.get("lon"), aliases))
        return db.execute(f"SELECT * FROM {table} WHERE id=?", (cur.lastrowid,)).fetchone()

    raise UnknownEntity(f"add_custom_entry unsupported for entity: {entity}")


def suggest_scored(db, entity, value, country_code=None, limit=5):
    """Like suggest_matches, but returns (score, row) pairs.

    The caller needs the scores to decide whether asking an AI is worth it: a
    near-perfect fuzzy hit needs no second opinion, and a hopeless one has no
    candidate for the AI to pick either way.
    """
    table = _ENTITY_TABLE.get(entity)
    if not table:
        raise UnknownEntity(entity)
    nv = normalize_name(value)
    cc = country_code.upper() if country_code else None

    scored = []
    for row in db.execute(f"SELECT * FROM {table}"):
        if entity in _REGION_ENTITIES and cc and (row["country_code"] or "").upper() != cc:
            continue
        candidates = [row["norm"]] + list(_alias_norms(row))
        score = max((difflib.SequenceMatcher(None, nv, c).ratio() for c in candidates if c),
                    default=0.0)
        scored.append((score, row))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:limit]


def suggest_matches(db, entity, value, country_code=None, limit=5):
    """Return reference rows ranked by fuzzy similarity to `value`, best first.

    Basis for the no-AI reconciliation fallback: when a value doesn't match
    exactly, offer the closest known entries. Regions are scoped to country_code.
    Score = best fuzzy ratio over the entry's name + its aliases.
    """
    return [row for _, row in suggest_scored(db, entity, value, country_code, limit)]


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


# ── Custom CRUD (management UI backs onto this) ───────────────────────────────
# Per plural entity: table, columns we accept, required columns, the name column,
# and how to detect a duplicate of a candidate row.
_CRUD = {
    "countries":      {"table": "ref_countries", "cols": ["code", "name", "lat", "lon", "aliases"],
                        "required": ["code", "name"], "namecol": "name"},
    "regions":        {"table": "ref_regions", "cols": ["name", "country_code", "lat", "lon", "aliases"],
                        "required": ["name", "country_code"], "namecol": "name"},
    "spirit_regions": {"table": "ref_spirit_regions",
                        "cols": ["name", "country_code", "lat", "lon", "aliases"],
                        "required": ["name", "country_code"], "namecol": "name"},
    "grapes":         {"table": "ref_grapes", "cols": ["name", "color", "aliases"],
                        "required": ["name"], "namecol": "name"},
    "wine_types":     {"table": "ref_wine_types", "cols": ["key", "color", "aliases"],
                        "required": ["key"], "namecol": "key"},
    "bottle_formats": {"table": "ref_bottle_formats", "cols": ["name", "liters"],
                        "required": ["name", "liters"], "namecol": "name"},
    "spirit_types":   {"table": "ref_spirit_types", "cols": ["key", "color", "aliases"],
                        "required": ["key"], "namecol": "key"},
    "cask_types":     {"table": "ref_cask_types", "cols": ["name", "aliases"],
                        "required": ["name"], "namecol": "name"},
}

_FLOAT_COLS = {"lat", "lon", "liters"}


def _coerce(col, value):
    if col == "aliases":
        if isinstance(value, str):
            value = [a.strip() for a in value.split(",") if a.strip()]
        return json.dumps(list(value or []))
    if col in _FLOAT_COLS:
        if value in (None, ""):
            return None
        return float(value)
    if col == "code":
        return str(value).strip().upper()
    return str(value).strip() if value is not None else None


def _norm_value(entity, fields):
    spec = _CRUD[entity]
    return normalize_name(fields.get(spec["namecol"], ""))


def _duplicate_exists(db, entity, norm, fields, exclude_id=None):
    spec = _CRUD[entity]
    table = spec["table"]
    if entity in ("regions", "spirit_regions"):
        sql = "SELECT id FROM %s WHERE norm=? AND country_code=?" % table
        params = [norm, _coerce("country_code", fields.get("country_code"))]
    elif entity == "countries":
        sql = "SELECT id FROM %s WHERE code=?" % table
        params = [_coerce("code", fields.get("code"))]
    else:
        sql = "SELECT id FROM %s WHERE norm=?" % table
        params = [norm]
    if exclude_id:
        sql += " AND id != ?"
        params.append(exclude_id)
    return db.execute(sql, params).fetchone() is not None


def get_entry(db, entity, entry_id):
    if entity not in _CRUD:
        raise UnknownEntity(entity)
    return db.execute(f"SELECT * FROM {_CRUD[entity]['table']} WHERE id=?", (entry_id,)).fetchone()


def create_custom(db, entity, fields):
    if entity not in _CRUD:
        raise UnknownEntity(entity)
    spec = _CRUD[entity]
    for req in spec["required"]:
        if not str(fields.get(req, "")).strip():
            raise ValueError(f"missing_required:{req}")
    norm = _norm_value(entity, fields)
    if _duplicate_exists(db, entity, norm, fields):
        raise ValueError("duplicate")

    cols = ["norm", "is_custom", "sort_order"]
    vals = [norm, 1, 9999]
    for c in spec["cols"]:
        cols.append(c)
        vals.append(_coerce(c, fields.get(c)))
    placeholders = ",".join("?" for _ in cols)
    cur = db.execute(f"INSERT INTO {spec['table']} ({','.join(cols)}) VALUES ({placeholders})", vals)
    return get_entry(db, entity, cur.lastrowid)


def update_custom(db, entity, entry_id, fields):
    if entity not in _CRUD:
        raise UnknownEntity(entity)
    spec = _CRUD[entity]
    row = get_entry(db, entity, entry_id)
    if not row:
        return None
    if row["is_custom"] != 1:
        raise PermissionError("builtin_readonly")
    for req in spec["required"]:
        if req in fields and not str(fields.get(req, "")).strip():
            raise ValueError(f"missing_required:{req}")

    merged = dict(row)
    for c in spec["cols"]:
        if c in fields:
            merged[c] = fields[c]
    norm = _norm_value(entity, merged)
    if _duplicate_exists(db, entity, norm, merged, exclude_id=entry_id):
        raise ValueError("duplicate")

    sets = ["norm=?"]
    vals = [norm]
    for c in spec["cols"]:
        sets.append(f"{c}=?")
        vals.append(_coerce(c, merged.get(c)))
    vals.append(entry_id)
    db.execute(f"UPDATE {spec['table']} SET {','.join(sets)} WHERE id=?", vals)
    return get_entry(db, entity, entry_id)


def delete_custom(db, entity, entry_id):
    if entity not in _CRUD:
        raise UnknownEntity(entity)
    row = get_entry(db, entity, entry_id)
    if not row:
        return False
    if row["is_custom"] != 1:
        raise PermissionError("builtin_readonly")
    db.execute(f"DELETE FROM {_CRUD[entity]['table']} WHERE id=?", (entry_id,))
    return True


# ── Listing (read API) ─────────────────────────────────────────────────────────

_LIST = {
    "countries":      ("ref_countries",      "name"),
    "regions":        ("ref_regions",        "name"),
    "spirit_regions": ("ref_spirit_regions", "name"),
    "grapes":         ("ref_grapes",         "name"),
    "wine_types":     ("ref_wine_types",     "key"),
    "bottle_formats": ("ref_bottle_formats", "sort_order"),
    "spirit_types":   ("ref_spirit_types",   "sort_order"),
    "cask_types":     ("ref_cask_types",     "sort_order"),
}


def list_reference(db, entity, country=None):
    if entity not in _LIST:
        raise UnknownEntity(entity)
    table, name_col = _LIST[entity]
    sql = f"SELECT * FROM {table}"
    params = []
    if entity in ("regions", "spirit_regions") and country:
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
