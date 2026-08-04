# Spirituosen mit Fokus Whisky — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Neben Wein auch Spirituosen (Whisky im Detail) in derselben App erfassen — eigener Bereich, eigene Felder, offene Flaschen mit Füllstand.

**Architecture:** `wines` bekommt eine `category`-Spalte (`wine` | `whisky` | `spirit`). Alle spirituosenspezifischen Felder liegen in der 1:1-Kindtabelle `spirit_details`, die Fässer als geordnete Liste in `spirit_casks` — beides verwaltet vom neuen Modul `spirits.py` nach dem Muster von `purchases.py`/`grapes.py`. Bilder, Einkäufe, Timeline und Chat hängen an `wines.id` und funktionieren unverändert weiter.

**Tech Stack:** Python 3 / Flask, sqlite3, Jinja2, Vanilla-JS-Modals, pytest, Playwright (System-Chrome `channel="chrome"`). Windows/PowerShell, venv `.venv`.

## Global Constraints

- **Nie committen/pushen ohne ausdrückliche Freigabe des Users.** Die `git commit`-Schritte nur nach seinem Okay ausführen.
- **Volle pytest-Suite nur auf Ansage oder als Gate vor dem Release-Push.** Sonst gezielte Tests (`pytest tests/test_x.py::test_y`).
- **Release-Checkliste (alle vier Dateien in einem Commit):** `wine-tracker/config.yaml` `version:`, `wine-tracker/app/app.py` `APP_VERSION`, `wine-tracker/CHANGELOG.md` (**die zeigt HA an**), `CHANGELOG.md` (Root). Zielversion: **1.15.0**.
- Pfade immer vom **Repo-Root** prüfen — aus `wine-tracker/` heraus schlagen relative Pfade fehl.
- `scripts/run-dev.local.ps1` ist gitignored (echter OpenAI-Key) — niemals committen.
- Tests laufen aus `wine-tracker/`: `../.venv/Scripts/python.exe -m pytest tests/...`
- Dev-Server: `/c/Users/DominikImark/repos/ha-wine-tracker/.venv/Scripts/python.exe /c/Users/DominikImark/repos/ha-wine-tracker/wine-tracker/app/app.py` — **Templates werden gecacht, nach Template-Änderungen neu starten.**
- Kategorie-Werte exakt: `wine`, `whisky`, `spirit`. Default `wine`.
- Fässer werden **nicht** dedupliziert (anders als Rebsorten) — derselbe Fasstyp darf mehrfach vorkommen.

---

## File Structure

- **`wine-tracker/app/spirits.py`** *(neu)* — die gesamte Spirituosen-Logik: beide Tabellen, Details-CRUD, Fässer-Liste, offene Flasche. Analog `purchases.py`/`grapes.py`.
- **`wine-tracker/app/app.py`** — Migrationen, Save-Routen, `wine_json`, Index-Kontext, KI-Schema/Prompts, Typ-Validierung, Routen für Öffnen/Füllstand/Leer.
- **`wine-tracker/app/reference.py` + `reference_data.py`** — `ref_spirit_types`, `ref_cask_types`, Whisky-Regionen, Spirituosen-Flaschengrössen.
- **`wine-tracker/app/templates/_wine_form_fields.html`** — Kategorie-Umschaltung, Whisky-Tab, Fass-Chipfeld.
- **`wine-tracker/app/templates/_wine_edit_modal.html`** — Feldsichtbarkeit, Fässer-Dialog, KI-Abgleich.
- **`wine-tracker/app/templates/index.html`** — Bereichsumschalter, Karte, Detailansicht mit offener Flasche.
- **`wine-tracker/app/templates/stats.html`, `timeline.html`** — Bereichsfilter, neue Aktionen.
- **`wine-tracker/app/static/style.css`, `filter-advanced.js`** — Umschalter, Füllstand, Whisky-Filter.
- **`wine-tracker/app/translations.py`** — neue Schlüssel ×7 Sprachen.
- **`wine-tracker/tests/test_spirits.py`** *(neu)* + Erweiterungen in `test_routes.py`, `test_api.py`, `test_export_import.py`, `test_helpers.py`.

---

## Task 1: `spirits.py` — Tabellen und Details

**Files:**
- Create: `wine-tracker/app/spirits.py`
- Test: `wine-tracker/tests/test_spirits.py`

**Interfaces:**
- Consumes: nichts.
- Produces:
  - `create_spirit_tables(db) -> None`
  - `get_details(db, wine_id) -> dict` — immer ein Dict; fehlende Zeile ergibt `{}`-artige Defaults mit `None`-Werten.
  - `set_details(db, wine_id, data: dict) -> None` — UPSERT, committet selbst.
  - Konstante `DETAIL_FIELDS: list[str]` — die Spaltennamen ohne `wine_id`.

- [ ] **Step 1: Write the failing test**

Create `wine-tracker/tests/test_spirits.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'spirits'`.

- [ ] **Step 3: Create the module**

Create `wine-tracker/app/spirits.py`:

```python
"""Spirits (whisky) details, cask maturation and open-bottle tracking.

`spirit_details` holds the per-bottle facts that only apply to spirits;
`spirit_casks` is the ordered maturation chain (row 0 = initial cask, the
rest are finishes). Wine rows simply have no entry in either table.
"""
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
            cask_id   INTEGER,
            name      TEXT NOT NULL,
            years     REAL,
            position  INTEGER DEFAULT 0,
            FOREIGN KEY (wine_id) REFERENCES wines(id) ON DELETE CASCADE,
            FOREIGN KEY (cask_id) REFERENCES ref_cask_types(id)
        )
    """)
    db.execute("CREATE INDEX IF NOT EXISTS idx_spirit_casks_wine ON spirit_casks(wine_id)")


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
    current = get_details(db, wine_id)
    merged = dict(current)
    for key in DETAIL_FIELDS:
        if key in data:
            merged[key] = data[key]
    cols = ", ".join(DETAIL_FIELDS)
    marks = ", ".join(["?"] * len(DETAIL_FIELDS))
    db.execute(
        f"INSERT INTO spirit_details (wine_id, {cols}) VALUES (?, {marks}) "
        f"ON CONFLICT(wine_id) DO UPDATE SET " +
        ", ".join(f"{c}=excluded.{c}" for c in DETAIL_FIELDS),
        [wine_id] + [merged[f] for f in DETAIL_FIELDS])
    db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/spirits.py wine-tracker/tests/test_spirits.py
git commit -m "feat(spirits): spirit_details/spirit_casks tables + details CRUD"
```

---

## Task 2: Fässer als geordnete Liste

**Files:**
- Modify: `wine-tracker/app/spirits.py`
- Test: `wine-tracker/tests/test_spirits.py`

**Interfaces:**
- Consumes: `create_spirit_tables`, `set_details`, `get_details` (Task 1); `reference.match_reference(db, "cask_type", name)`.
- Produces:
  - `set_casks(db, wine_id, entries: list[dict]) -> None` — `entries` = `[{"name": str, "years": float|None}]`, Reihenfolge = Reifereihenfolge; committet selbst und baut `cask_summary` neu.
  - `list_casks(db, wine_id) -> list[dict]` — `[{"name","years","cask_id","position"}]` nach `position`.
  - `rebuild_cask_summary(db, wine_id) -> str|None` — schreibt `spirit_details.cask_summary`.

**Wichtig:** Die Referenz-Entität heisst `cask_type` und wird erst in Task 5 angelegt. `reference.match_reference` wirft dann `UnknownEntity` — deshalb wird der Aufruf hier defensiv gekapselt, damit Task 2 unabhängig testbar bleibt.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_spirits.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q -k cask`
Expected: FAIL with `AttributeError: module 'spirits' has no attribute 'set_casks'`.

- [ ] **Step 3: Implement the cask functions**

Append to `wine-tracker/app/spirits.py`:

```python
def _coerce_years(value):
    if value in (None, ""):
        return None
    try:
        y = float(value)
    except (TypeError, ValueError):
        return None
    return y if 0 < y <= 100 else None


def _match_cask(db, name):
    """Resolve a cask name against the reference list. Returns the row or None.
    Tolerates the reference entity not existing yet."""
    try:
        return reference.match_reference(db, "cask_type", name)
    except Exception:
        return None


def rebuild_cask_summary(db, wine_id):
    rows = db.execute(
        "SELECT name FROM spirit_casks WHERE wine_id=? ORDER BY position",
        (wine_id,)).fetchall()
    summary = " → ".join(r[0] for r in rows) or None
    set_details(db, wine_id, {"cask_summary": summary})
    return summary


def set_casks(db, wine_id, entries):
    """Replace the maturation chain. entries: [{"name", "years"}] in order.

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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q`
Expected: PASS (11 passed).

- [ ] **Step 5: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/spirits.py wine-tracker/tests/test_spirits.py
git commit -m "feat(spirits): ordered cask chain with summary cache"
```

---

## Task 3: Offene Flaschen

**Files:**
- Modify: `wine-tracker/app/spirits.py`
- Test: `wine-tracker/tests/test_spirits.py`

**Interfaces:**
- Consumes: `get_details`, `set_details` (Task 1).
- Produces:
  - `open_bottle(db, wine_id, today: str) -> bool` — `False` wenn `quantity == 0` oder bereits offen.
  - `set_fill_level(db, wine_id, percent) -> bool` — `False` bei ungültigem Wert oder wenn keine Flasche offen ist.
  - `finish_bottle(db, wine_id) -> bool` — `False` wenn keine offen.
  - Timeline-Aktionen: `opened`, `refilled`, `consumed`.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_spirits.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q -k "open or fill or finish"`
Expected: FAIL with `AttributeError: module 'spirits' has no attribute 'open_bottle'`.

- [ ] **Step 3: Implement the open-bottle operations**

Append to `wine-tracker/app/spirits.py`:

```python
from datetime import datetime


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
```

Move the `from datetime import datetime` line to the top of the module next to `import reference`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q`
Expected: PASS (19 passed).

- [ ] **Step 5: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/spirits.py wine-tracker/tests/test_spirits.py
git commit -m "feat(spirits): open/fill-level/finish with timeline entries"
```

---

## Task 4: `category`-Spalte und Tabellen in `init_db`

**Files:**
- Modify: `wine-tracker/app/app.py` (Import-Block ~Zeile 13-16; `migrations`-Dict ~Zeile 585-597; Migrationsblock ~Zeile 686-692)
- Test: `wine-tracker/tests/test_spirits.py`

**Interfaces:**
- Consumes: `spirits.create_spirit_tables`.
- Produces: nach `init_db()` existieren `wines.category` (Default `'wine'`), `spirit_details` und `spirit_casks`.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_spirits.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q -k "category_column or created_by_init"`
Expected: FAIL — `category` fehlt in `PRAGMA table_info`.

Hinweis: Die `db`-Fixture kopiert eine Template-DB, die `conftest.py` einmal per `init_db()` baut. Der Test greift also echt auf die Migration zu.

- [ ] **Step 3: Add the import**

In `wine-tracker/app/app.py` neben `import grapes`:

```python
import spirits
```

- [ ] **Step 4: Add the column to the migrations dict**

Im `migrations`-Dict (bei `"ai_price": "REAL",`) ergänzen:

```python
            "category":       "TEXT NOT NULL DEFAULT 'wine'",
```

- [ ] **Step 5: Create the tables in init_db**

Nach dem Rebsorten-Block (`grapes.dedupe_wine_grapes(db)`) und vor `db.commit()`:

```python
        # ── spirits: details + cask chain ──────────────────────────────────
        spirits.create_spirit_tables(db)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_spirits.py -q`
Expected: PASS (21 passed).

- [ ] **Step 7: Regression on the DB tests**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_database.py tests/test_grapes.py -q`
Expected: PASS.

- [ ] **Step 8: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_spirits.py
git commit -m "feat(spirits): category column + spirit tables in init_db"
```

---

## Task 5: Referenzlisten für Spirituosen

**Files:**
- Modify: `wine-tracker/app/reference.py` (`_DDL` ~42-63; `seed_reference_data` ~73-130; `match_reference` ~164-211; `_CRUD` ~288-299; `_LIST` ~413-419)
- Modify: `wine-tracker/app/reference_data.py` (neue Listen + Whisky-Regionen + Flaschengrössen)
- Test: `wine-tracker/tests/test_reference.py`

**Interfaces:**
- Consumes: nichts.
- Produces: Tabellen `ref_spirit_types` (Spalte `key`) und `ref_cask_types` (Spalte `name`), beide mit `norm`, `aliases`, `is_custom`, `sort_order`. `reference.match_reference(db, "spirit_type"|"cask_type", value)` liefert die Zeile oder `None`. Die Referenzseite listet sie unter `spirit_types` und `cask_types`.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_reference.py`:

```python
class TestSpiritReferences:
    def test_spirit_types_seeded(self, db):
        import reference
        for key in ("Single Malt", "Bourbon", "Gin", "Rum"):
            assert reference.match_reference(db, "spirit_type", key), key

    def test_cask_types_seeded(self, db):
        import reference
        for name in ("Ex-Bourbon", "PX Sherry", "Oloroso Sherry", "Virgin Oak"):
            assert reference.match_reference(db, "cask_type", name), name

    def test_cask_alias_resolves(self, db):
        import reference
        assert reference.match_reference(db, "cask_type", "Bourbon")["name"] == "Ex-Bourbon"
        assert reference.match_reference(db, "cask_type", "PX")["name"] == "PX Sherry"

    def test_whisky_regions_seeded(self, db):
        import reference
        for name in ("Islay", "Speyside", "Highlands"):
            assert reference.match_reference(db, "region", name), name

    def test_spirit_bottle_formats_seeded(self, db):
        rows = {r[0] for r in db.execute("SELECT liters FROM ref_bottle_formats")}
        assert 0.7 in rows and 0.5 in rows and 0.05 in rows

    def test_unknown_value_returns_none(self, db):
        import reference
        assert reference.match_reference(db, "cask_type", "Zzz Unknown") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_reference.py -q -k Spirit`
Expected: FAIL mit `UnknownEntity: spirit_type`.

- [ ] **Step 3: Add the seed data**

In `wine-tracker/app/reference_data.py` am Ende ergänzen:

```python
SPIRIT_TYPES = [
    {'key': 'Single Malt', 'color': '#b8860b', 'aliases': ['Single Malt Whisky', 'Single Malt Scotch']},
    {'key': 'Blended Malt', 'color': '#b8860b', 'aliases': ['Vatted Malt']},
    {'key': 'Blended Scotch', 'color': '#b8860b', 'aliases': ['Blend', 'Blended Whisky']},
    {'key': 'Single Grain', 'color': '#b8860b', 'aliases': ['Grain']},
    {'key': 'Bourbon', 'color': '#a0522d', 'aliases': ['Straight Bourbon']},
    {'key': 'Rye', 'color': '#a0522d', 'aliases': ['Rye Whiskey']},
    {'key': 'Tennessee', 'color': '#a0522d', 'aliases': ['Tennessee Whiskey']},
    {'key': 'Irish', 'color': '#b8860b', 'aliases': ['Irish Whiskey']},
    {'key': 'Rum', 'color': '#8b4513', 'aliases': ['Ron', 'Rhum']},
    {'key': 'Gin', 'color': '#5f9ea0', 'aliases': ['London Dry']},
    {'key': 'Cognac', 'color': '#a0522d', 'aliases': []},
    {'key': 'Armagnac', 'color': '#a0522d', 'aliases': []},
    {'key': 'Brandy', 'color': '#a0522d', 'aliases': ['Weinbrand']},
    {'key': 'Grappa', 'color': '#dcdcdc', 'aliases': ['Marc', 'Tresterbrand']},
    {'key': 'Tequila', 'color': '#9acd32', 'aliases': []},
    {'key': 'Mezcal', 'color': '#9acd32', 'aliases': []},
    {'key': 'Wodka', 'color': '#dcdcdc', 'aliases': ['Vodka']},
    {'key': 'Likör', 'color': '#da70d6', 'aliases': ['Liqueur', 'Likoer']},
    {'key': 'Obstbrand', 'color': '#dcdcdc', 'aliases': ['Eau de Vie', 'Schnaps']},
    {'key': 'Anderes', 'color': None, 'aliases': ['Sonstiges']},
]

CASK_TYPES = [
    {'name': 'Ex-Bourbon', 'aliases': ['Bourbon', 'Bourbon Barrel', 'American Oak']},
    {'name': 'Oloroso Sherry', 'aliases': ['Oloroso']},
    {'name': 'PX Sherry', 'aliases': ['PX', 'Pedro Ximenez', 'Pedro Ximénez']},
    {'name': 'Fino Sherry', 'aliases': ['Fino']},
    {'name': 'Amontillado Sherry', 'aliases': ['Amontillado']},
    {'name': 'Sherry', 'aliases': ['Sherry Cask']},
    {'name': 'Port', 'aliases': ['Portwein', 'Port Pipe']},
    {'name': 'Madeira', 'aliases': []},
    {'name': 'Sauternes', 'aliases': []},
    {'name': 'Rotwein', 'aliases': ['Red Wine', 'Wine Cask']},
    {'name': 'Virgin Oak', 'aliases': ['New Oak', 'Neues Holz']},
    {'name': 'Rum', 'aliases': ['Rum Cask']},
    {'name': 'Mizunara', 'aliases': ['Japanese Oak']},
    {'name': 'Refill Hogshead', 'aliases': ['Hogshead', 'Refill']},
    {'name': 'Quarter Cask', 'aliases': []},
    {'name': 'Butt', 'aliases': ['Sherry Butt']},
]

# Whisky regions - appended to REGIONS so the existing region machinery works.
REGIONS += [
    {'name': 'Islay', 'country_code': 'GB', 'lat': 55.75, 'lon': -6.20, 'aliases': []},
    {'name': 'Speyside', 'country_code': 'GB', 'lat': 57.45, 'lon': -3.20, 'aliases': []},
    {'name': 'Highlands', 'country_code': 'GB', 'lat': 57.12, 'lon': -4.71,
     'aliases': ['Highland']},
    {'name': 'Lowlands', 'country_code': 'GB', 'lat': 55.60, 'lon': -3.80,
     'aliases': ['Lowland']},
    {'name': 'Campbeltown', 'country_code': 'GB', 'lat': 55.42, 'lon': -5.60, 'aliases': []},
    {'name': 'Islands', 'country_code': 'GB', 'lat': 57.50, 'lon': -6.20, 'aliases': []},
]

# Spirit bottle sizes - appended to the existing wine formats. Names stay bare
# ("Piccolo", "Demi", "Standard" ...); the UI appends the litre value itself.
BOTTLE_FORMATS += [
    {'name': 'Spirituose', 'liters': 0.7},
    {'name': 'Halbliter', 'liters': 0.5},
    {'name': 'Kleinflasche', 'liters': 0.35},
    {'name': 'Probe', 'liters': 0.2},
    {'name': 'Miniatur', 'liters': 0.05},
]
```

Die Listennamen `REGIONS` und `BOTTLE_FORMATS` sind verifiziert (Zeilen 264 und 494); `BOTTLE_FORMATS`-Einträge haben nur `name` und `liters`, **kein** `aliases`.

Zusätzlich in `index.html` die JS-Konstante `BOTTLE_FORMATS` (die Anzeigenamen wie `0.75: 'Standard (0.75 l)'`) um die neuen Grössen ergänzen — sonst zeigt die Detailansicht bei 0.7 l nur die nackte Zahl.

- [ ] **Step 4: Add the tables**

In `wine-tracker/app/reference.py` in `_DDL` ergänzen:

```python
    """CREATE TABLE IF NOT EXISTS ref_spirit_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        key TEXT UNIQUE, norm TEXT, color TEXT, aliases TEXT,
        is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
    """CREATE TABLE IF NOT EXISTS ref_cask_types (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE, norm TEXT, aliases TEXT,
        is_custom INTEGER DEFAULT 0, sort_order INTEGER DEFAULT 0)""",
```

- [ ] **Step 5: Seed them**

In `seed_reference_data` nach dem Rebsorten-Block ergänzen:

```python
    # spirit types - natural key: key
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

    # cask types - natural key: norm
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
```

- [ ] **Step 6: Teach match_reference the new entities**

In `match_reference` vor `raise UnknownEntity(entity)` ergänzen:

```python
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
```

- [ ] **Step 7: Expose them on the reference page**

In `_CRUD` ergänzen:

```python
    "spirit_types":   {"table": "ref_spirit_types", "cols": ["key", "color", "aliases"],
                        "required": ["key"], "namecol": "key"},
    "cask_types":     {"table": "ref_cask_types", "cols": ["name", "aliases"],
                        "required": ["name"], "namecol": "name"},
```

In `_LIST` ergänzen:

```python
    "spirit_types":   ("ref_spirit_types",   "sort_order"),
    "cask_types":     ("ref_cask_types",     "sort_order"),
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_reference.py tests/test_reference_gap.py -q`
Expected: PASS.

- [ ] **Step 9: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/reference.py wine-tracker/app/reference_data.py wine-tracker/tests/test_reference.py
git commit -m "feat(spirits): spirit type + cask type reference lists, whisky regions"
```

---

## Task 6: Save-Routen speichern Kategorie, Details und Fässer

**Files:**
- Modify: `wine-tracker/app/app.py` (add-Route ~1005-1060; edit-Route ~1100-1195)
- Test: `wine-tracker/tests/test_routes.py`

**Interfaces:**
- Consumes: `spirits.set_details`, `spirits.set_casks`, `spirits.DETAIL_FIELDS`.
- Produces: Helfer `_spirit_payload_from_form(form) -> tuple[dict, list[dict]]` — `(details, casks)`. `category` wird aus `form["category"]` gelesen, unbekannte Werte fallen auf `wine` zurück.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_routes.py`:

```python
# ── spirits: category, details, casks ─────────────────────────────────────────

def test_add_whisky_stores_details_and_casks(client, db):
    resp = client.post("/add", data={
        "name": "Lagavulin 16", "category": "whisky", "type": "Single Malt",
        "region": "Islay", "quantity": "2", "abv": "43", "age_years": "16",
        "bottler": "Original", "batch_number": "Batch 003", "peat_ppm": "35",
        "cask_strength": "0",
        "casks": json.dumps([{"name": "Ex-Bourbon", "years": 14},
                             {"name": "PX Sherry", "years": 2}]),
    }, follow_redirects=True)
    assert resp.status_code == 200
    wid = db.execute("SELECT id FROM wines WHERE name='Lagavulin 16'").fetchone()[0]
    assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "whisky"

    import spirits
    d = spirits.get_details(db, wid)
    assert d["abv"] == 43 and d["age_years"] == 16 and d["batch_number"] == "Batch 003"
    assert [c["name"] for c in spirits.list_casks(db, wid)] == ["Ex-Bourbon", "PX Sherry"]
    assert d["cask_summary"] == "Ex-Bourbon → PX Sherry"


def test_add_wine_stays_wine_and_has_no_spirit_row(client, db):
    client.post("/add", data={"name": "Barolo Cat", "type": "red", "quantity": "1"},
                follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Barolo Cat'").fetchone()[0]
    assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "wine"
    assert db.execute("SELECT COUNT(*) FROM spirit_details WHERE wine_id=?",
                      (wid,)).fetchone()[0] == 0


def test_edit_without_spirit_fields_keeps_them(client, db):
    """A quantity-only edit must not wipe the whisky details."""
    client.post("/add", data={
        "name": "Keep Details", "category": "whisky", "type": "Single Malt",
        "quantity": "1", "abv": "46",
    }, follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Keep Details'").fetchone()[0]
    client.post(f"/edit/{wid}", data={
        "name": "Keep Details", "type": "Single Malt", "quantity": "3", "rating": "0",
    }, follow_redirects=True)
    import spirits
    assert spirits.get_details(db, wid)["abv"] == 46


def test_unknown_category_falls_back_to_wine(client, db):
    client.post("/add", data={"name": "Weird Cat", "type": "red", "quantity": "1",
                              "category": "bogus"}, follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Weird Cat'").fetchone()[0]
    assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "wine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_routes.py -q -k "whisky or category or spirit"`
Expected: FAIL — `category` wird nicht gespeichert.

- [ ] **Step 3: Add the form helper**

In `wine-tracker/app/app.py` neben `_grapes_from_form`:

```python
CATEGORIES = ("wine", "whisky", "spirit")


def _category_from_form(form):
    value = (form.get("category") or "").strip().lower()
    return value if value in CATEGORIES else "wine"


def _spirit_payload_from_form(form):
    """Return (details, casks) from the posted form.

    Only keys actually present are put into `details`, so a partial post (e.g.
    a quantity-only edit) leaves the other whisky fields untouched.
    """
    numeric = {"abv": float, "age_years": int, "distilled_year": int,
               "bottled_year": int, "peat_ppm": int}
    flags = ("cask_strength", "single_cask", "chill_filtered")
    text = ("bottler", "batch_number", "cask_number")

    details = {}
    for key, cast in numeric.items():
        if key in form:
            raw = (form.get(key) or "").strip()
            try:
                details[key] = cast(float(raw)) if raw else None
            except (TypeError, ValueError):
                details[key] = None
    for key in flags:
        if key in form:
            details[key] = 1 if (form.get(key) or "").strip() in ("1", "on", "true") else 0
    for key in text:
        if key in form:
            details[key] = (form.get(key) or "").strip() or None

    casks = None
    if "casks" in form:
        casks = []
        try:
            data = json.loads((form.get("casks") or "").strip() or "[]")
            if isinstance(data, list):
                casks = [{"name": (e.get("name") or "").strip(), "years": e.get("years")}
                         for e in data if isinstance(e, dict)]
        except (json.JSONDecodeError, TypeError):
            casks = []
    return details, casks
```

- [ ] **Step 4: Wire the add-route**

Im INSERT der add-Route die Spaltenliste um `category` und die Werteliste um `_category_from_form(request.form)` erweitern. Danach, direkt nach `grapes.set_wine_grapes(db, new_id, ...)`:

```python
    _details, _casks = _spirit_payload_from_form(request.form)
    if _details:
        spirits.set_details(db, new_id, _details)
    if _casks is not None:
        spirits.set_casks(db, new_id, _casks)
```

- [ ] **Step 5: Wire the edit-route**

Im UPDATE `category=?` ergänzen (Wert `_category_from_form(request.form)`) — aber **nur wenn** `category` gepostet wurde, sonst bleibt der bestehende Wert. Praktikabel: vor dem UPDATE

```python
    category_val = (_category_from_form(request.form)
                    if "category" in request.form else wine["category"])
```

und `category_val` in die Werteliste aufnehmen. Nach dem UPDATE, neben dem Rebsorten-Block:

```python
    _details, _casks = _spirit_payload_from_form(request.form)
    if _details:
        spirits.set_details(db, wine_id, _details)
    if _casks is not None:
        spirits.set_casks(db, wine_id, _casks)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_routes.py -q -k "whisky or category or spirit"`
Expected: PASS (4 passed).

- [ ] **Step 7: Regression**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_routes.py -q`
Expected: PASS.

- [ ] **Step 8: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_routes.py
git commit -m "feat(spirits): add/edit routes persist category, details and casks"
```

---

## Task 7: Serialisierung und Bereichsfilter

**Files:**
- Modify: `wine-tracker/app/app.py` (`wine_json` ~776-806; Index-Route ~940-975)
- Test: `wine-tracker/tests/test_api.py`

**Interfaces:**
- Consumes: `spirits.get_details`, `spirits.list_casks`.
- Produces: `wine_json` enthält `category`, `spirit_details` (Dict) und `casks` (Liste). Die Index-Route akzeptiert `?area=bar|cellar` und filtert entsprechend; ohne Parameter kommt alles.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_api.py`:

```python
def test_wine_json_includes_spirit_data(client, db):
    import json as J
    client.post("/add", data={
        "name": "Api Whisky", "category": "whisky", "type": "Single Malt",
        "quantity": "1", "abv": "46",
        "casks": J.dumps([{"name": "Ex-Bourbon", "years": 10}]),
    }, follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Api Whisky'").fetchone()[0]
    w = client.get(f"/api/wine/{wid}").get_json()["wine"]
    assert w["category"] == "whisky"
    assert w["spirit_details"]["abv"] == 46
    assert [c["name"] for c in w["casks"]] == ["Ex-Bourbon"]


def test_index_area_filter(client, db):
    client.post("/add", data={"name": "Area Wine", "type": "red", "quantity": "1"},
                follow_redirects=True)
    client.post("/add", data={"name": "Area Whisky", "category": "whisky",
                              "type": "Single Malt", "quantity": "1"},
                follow_redirects=True)
    cellar = client.get("/?area=cellar").get_data(as_text=True)
    assert "Area Wine" in cellar and "Area Whisky" not in cellar
    bar = client.get("/?area=bar").get_data(as_text=True)
    assert "Area Whisky" in bar and "Area Wine" not in bar
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_api.py -q -k "spirit_data or area_filter"`
Expected: FAIL mit `KeyError: 'category'` bzw. beide Weine in beiden Ansichten.

- [ ] **Step 3: Extend wine_json**

In `wine_json`, nach `d["grapes"] = grapes.list_wine_grapes(db, wine_id)`:

```python
    d["spirit_details"] = spirits.get_details(db, wine_id)
    d["casks"] = spirits.list_casks(db, wine_id)
```

- [ ] **Step 4: Add the area filter to the index route**

In der Index-Route, wo `q`/`t`/`show_empty` gelesen werden:

```python
    area = (request.args.get("area") or "").strip().lower()
    if area == "cellar":
        sql += " AND category = 'wine'"
    elif area == "bar":
        sql += " AND category != 'wine'"
```

Und nach dem Zusammenbauen der `wines`-Liste, neben dem Rebsorten-Loop:

```python
    for w in wines:
        w["spirit_details"] = spirits.get_details(db, w["id"])
        w["casks"] = spirits.list_casks(db, w["id"])
```

`area` zusätzlich an `render_template(...)` übergeben (`area=area`), damit das Template den aktiven Bereich kennt.

- [ ] **Step 5: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_api.py -q -k "spirit_data or area_filter"`
Expected: PASS.

- [ ] **Step 6: Regression**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_api.py -q`
Expected: PASS.

- [ ] **Step 7: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_api.py
git commit -m "feat(spirits): expose category/details/casks + area filter"
```

---

## Task 8: Routen für offene Flaschen

**Files:**
- Modify: `wine-tracker/app/app.py` (bei den anderen `/api/wine/<id>/...`-Routen ~3640-3700)
- Test: `wine-tracker/tests/test_api.py`

**Interfaces:**
- Consumes: `spirits.open_bottle`, `spirits.set_fill_level`, `spirits.finish_bottle`.
- Produces: `POST /api/wine/<id>/open`, `POST /api/wine/<id>/fill` (JSON `{"percent": 55}`), `POST /api/wine/<id>/finish`. Antwort jeweils `{"ok": bool, "wine": <wine_json>}`, bei abgelehnter Aktion `{"ok": false, "error": "not_possible"}` mit Status 400.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_api.py`:

```python
class TestOpenBottleRoutes:
    def _whisky(self, client, db, qty=2):
        client.post("/add", data={"name": "Route Whisky", "category": "whisky",
                                  "type": "Single Malt", "quantity": str(qty)},
                    follow_redirects=True)
        return db.execute("SELECT id FROM wines WHERE name='Route Whisky'").fetchone()[0]

    def test_open_then_fill_then_finish(self, client, db):
        wid = self._whisky(client, db)
        r = client.post(f"/api/wine/{wid}/open")
        assert r.status_code == 200 and r.get_json()["ok"] is True
        assert r.get_json()["wine"]["spirit_details"]["fill_level"] == 100
        assert r.get_json()["wine"]["quantity"] == 1

        r = client.post(f"/api/wine/{wid}/fill", json={"percent": 55})
        assert r.get_json()["wine"]["spirit_details"]["fill_level"] == 55

        r = client.post(f"/api/wine/{wid}/finish")
        assert r.get_json()["wine"]["spirit_details"]["opened_at"] is None

    def test_open_without_stock_is_rejected(self, client, db):
        wid = self._whisky(client, db, qty=0)
        r = client.post(f"/api/wine/{wid}/open")
        assert r.status_code == 400 and r.get_json()["error"] == "not_possible"

    def test_fill_with_bad_value_is_rejected(self, client, db):
        wid = self._whisky(client, db)
        client.post(f"/api/wine/{wid}/open")
        r = client.post(f"/api/wine/{wid}/fill", json={"percent": 500})
        assert r.status_code == 400

    def test_unknown_wine_is_404(self, client):
        assert client.post("/api/wine/999999/open").status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_api.py -q -k OpenBottle`
Expected: FAIL mit 404 für alle Routen.

- [ ] **Step 3: Implement the routes**

In `wine-tracker/app/app.py` bei den anderen Wein-API-Routen:

```python
def _spirit_action(wine_id, fn):
    """Shared plumbing for the open-bottle actions."""
    db = get_db()
    if not db.execute("SELECT 1 FROM wines WHERE id=?", (wine_id,)).fetchone():
        return jsonify({"ok": False, "error": "not_found"}), 404
    if not fn(db):
        return jsonify({"ok": False, "error": "not_possible"}), 400
    return jsonify({"ok": True, "wine": wine_json(wine_id), "stats": stats_json()})


@app.route("/api/wine/<int:wine_id>/open", methods=["POST"])
def api_wine_open(wine_id):
    return _spirit_action(
        wine_id, lambda db: spirits.open_bottle(db, wine_id, str(date.today())))


@app.route("/api/wine/<int:wine_id>/fill", methods=["POST"])
def api_wine_fill(wine_id):
    percent = (request.get_json(silent=True) or {}).get("percent")
    return _spirit_action(wine_id, lambda db: spirits.set_fill_level(db, wine_id, percent))


@app.route("/api/wine/<int:wine_id>/finish", methods=["POST"])
def api_wine_finish(wine_id):
    return _spirit_action(wine_id, lambda db: spirits.finish_bottle(db, wine_id))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_api.py -q -k OpenBottle`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_api.py
git commit -m "feat(spirits): open/fill/finish API routes"
```

---

## Task 9: KI kategorieabhängig

**Files:**
- Modify: `wine-tracker/app/app.py` (`_wine_json_schema` ~2660; `_wine_json_rules` ~2671; Scan-Prompt ~2240-2280; `_canonicalize_ai_fields` ~1840; Typ-Validierung an beiden Parse-Stellen)
- Test: `wine-tracker/tests/test_helpers.py`

**Interfaces:**
- Consumes: `reference.match_reference(db, "cask_type"|"spirit_type", …)`.
- Produces: `_wine_json_schema(category="wine")` und `_wine_json_rules(lang, currency, category="wine")`. `_canonicalize_ai_fields(db, fields, category="wine")` kanonisiert bei Spirituosen `casks[].name` über `cask_type` und `wine_type` über `spirit_type`. `_valid_types(db, category) -> set[str]` ersetzt die harte `WINE_TYPES`-Prüfung.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_helpers.py`:

```python
class TestSpiritAiSchema:
    def test_whisky_schema_has_spirit_fields(self):
        import app as wine_app
        s = wine_app._wine_json_schema("whisky")
        for f in ("abv", "age_years", "cask", "bottler", "batch_number", "peat_ppm"):
            assert f in s, f

    def test_whisky_schema_drops_wine_fields(self):
        import app as wine_app
        s = wine_app._wine_json_schema("whisky")
        for f in ("grapes", "maturity_data", "food_pairings", "drink_from"):
            assert f not in s, f

    def test_wine_schema_unchanged(self):
        import app as wine_app
        s = wine_app._wine_json_schema("wine")
        assert "grapes" in s and "abv" not in s

    def test_valid_types_are_category_aware(self, db):
        import app as wine_app
        assert "Rotwein" in wine_app._valid_types(db, "wine")
        assert "Single Malt" in wine_app._valid_types(db, "whisky")
        assert "Single Malt" not in wine_app._valid_types(db, "wine")

    def test_cask_alias_is_canonicalized(self, db):
        import app as wine_app
        out = wine_app._canonicalize_ai_fields(
            db, {"casks": [{"name": "PX", "years": 2}]}, "whisky")
        assert out["casks"][0]["name"] == "PX Sherry"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_helpers.py -q -k SpiritAi`
Expected: FAIL — `_wine_json_schema()` nimmt kein Argument.

- [ ] **Step 3: Make the schema category-aware**

`_wine_json_schema()` bekommt einen Parameter und liefert für Spirituosen ein eigenes Schema:

```python
def _wine_json_schema(category="wine"):
    if category in ("whisky", "spirit"):
        return """{
  "name": "bottling name (without the distillery)",
  "winery": "distillery or brand, or empty string",
  "wine_type": "one of: Single Malt, Blended Malt, Blended Scotch, Single Grain, Bourbon, Rye, Tennessee, Irish, Rum, Gin, Cognac, Armagnac, Brandy, Grappa, Tequila, Mezcal, Wodka, Likör, Obstbrand, Anderes",
  "region": "region, e.g. Islay, Speyside, Kentucky",
  "abv": alcohol by volume as number or null,
  "age_years": age statement in years as number, or null for NAS,
  "distilled_year": year as integer or null,
  "bottled_year": year as integer or null,
  "casks": [{"name": "cask type", "years": years in that cask as number or null}],
  "bottler": "Original bottling or the independent bottler's name",
  "batch_number": "batch or lot number as printed, or null",
  "cask_strength": true or false,
  "single_cask": true or false,
  "peat_ppm": phenol ppm as number or null,
  "price": number or null,
  "notes": "brief tasting notes",
  "taste_profile": {"smoke": 1-5, "sweetness": 1-5, "fruit": 1-5, "spice": 1-5},
  "ai_rationale": "1-2 sentence basis for the identification and estimates, or null"
}"""
    return """{
  "name": "wine name (without the producer)",
  ... (bestehendes Wein-Schema unverändert) ...
}"""
```

Das Wein-Schema bleibt exakt wie es ist — nur eingerückt in den `return` am Ende.

- [ ] **Step 4: Make the rules category-aware**

`_wine_json_rules(lang="en", currency=None, category="wine")`. Die gemeinsamen Regeln (Winzer-Schutz, Jahrgang-Schutz, Preis/Währung, Sprache, „nur JSON") bleiben für beide. Für Spirituosen ersetzt dieser Block die weinspezifischen Regeln:

```
- casks: the maturation chain in order. First entry = initial cask, any further entries are finishes. Each item has a name (cask type) plus years in that cask when known, otherwise null.
- abv: alcohol by volume as a plain number (e.g. 46.3), null if unknown.
- age_years: only the official age statement. Return null for NAS bottlings - do NOT compute it from distilled/bottled years.
- cask_strength / single_cask: true only when the label or a reliable source states it.
- peat_ppm: only for peated whisky and only when a source states the phenol level.
- taste_profile: estimate smoke, sweetness, fruit and spice from 1 to 5.
```

- [ ] **Step 5: Replace the hard type validation**

Neue Funktion neben `_canonicalize_ai_fields`:

```python
def _valid_types(db, category):
    """Allowed `type` values for a category - wine types or spirit types."""
    if category in ("whisky", "spirit"):
        return {r[0] for r in db.execute("SELECT key FROM ref_spirit_types")}
    return set(WINE_TYPES)
```

An beiden Stellen `if fields.get("wine_type") and fields["wine_type"] not in WINE_TYPES:` ersetzen durch:

```python
        if fields.get("wine_type") and fields["wine_type"] not in _valid_types(db, category):
            fields["wine_type"] = ""
```

`category` muss dort verfügbar sein: im Scan aus `request.form.get("category")`, in der Reanalyse aus `wine_context.get("category")` — beide über `_category_from_form`-Logik bzw. mit Default `wine`.

- [ ] **Step 6: Extend the canonicalization**

`_canonicalize_ai_fields(db, fields, category="wine")`; für Spirituosen zusätzlich:

```python
    if category in ("whisky", "spirit"):
        if fields.get("wine_type"):
            row = reference.match_reference(db, "spirit_type", fields["wine_type"])
            if row:
                fields["wine_type"] = row["key"]
        if isinstance(fields.get("casks"), list):
            for c in fields["casks"]:
                if isinstance(c, dict) and c.get("name"):
                    row = reference.match_reference(db, "cask_type", c["name"])
                    if row:
                        c["name"] = row["name"]
```

Die Rebsorten-Kanonisierung wird für Spirituosen übersprungen.

- [ ] **Step 7: Pass the category through**

Client und Server reichen `category` mit: `reloadViaAi()` legt `context.category` an (Task 11), `_analyze_wine_from_context` liest `wine_context.get("category")` und gibt sie an Schema, Regeln und Kanonisierung weiter. Die Scan-Route liest `request.form.get("category")`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_helpers.py tests/test_api.py -q`
Expected: PASS.

- [ ] **Step 9: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_helpers.py
git commit -m "feat(spirits): category-aware AI schema, rules, type validation"
```

---

## Task 10: Übersetzungen

**Files:**
- Modify: `wine-tracker/app/translations.py` (7 Sprachblöcke)

**Interfaces:**
- Produces: die unten gelisteten Schlüssel in allen sieben Sprachen. Sie werden von Task 11-13 verwendet.

- [ ] **Step 1: Add the keys to all seven language blocks**

Je Sprachblock nach `"label_grape": …` einfügen. Anker je Block: `"label_grape": "Rebsorte",` (de), `"Grape variety",` (en), `"Cépage",` (fr), `"Vitigno",` (it), `"Variedad de uva",` (es), `"Casta",` (pt), `"Druivenras",` (nl).

| Schlüssel | de | en | fr | it | es | pt | nl |
|---|---|---|---|---|---|---|---|
| `area_cellar` | Weinkeller | Cellar | Cave | Cantina | Bodega | Adega | Kelder |
| `area_bar` | Bar | Bar | Bar | Bar | Bar | Bar | Bar |
| `label_category` | Kategorie | Category | Catégorie | Categoria | Categoría | Categoria | Categorie |
| `cat_wine` | Wein | Wine | Vin | Vino | Vino | Vinho | Wijn |
| `cat_whisky` | Whisky | Whisky | Whisky | Whisky | Whisky | Whisky | Whisky |
| `cat_spirit` | Spirituose | Spirit | Spiritueux | Distillato | Destilado | Destilado | Gedistilleerd |
| `label_distillery` | Destillerie | Distillery | Distillerie | Distilleria | Destilería | Destilaria | Distilleerderij |
| `label_abv` | Vol.-% | ABV | Vol. % | Vol. % | Vol. % | Vol. % | Vol. % |
| `label_age` | Alter (Jahre) | Age (years) | Âge (ans) | Età (anni) | Edad (años) | Idade (anos) | Leeftijd (jaar) |
| `label_distilled` | Destilliert | Distilled | Distillé | Distillato | Destilado | Destilado | Gedistilleerd |
| `label_bottled` | Abgefüllt | Bottled | Embouteillé | Imbottigliato | Embotellado | Engarrafado | Gebotteld |
| `label_bottler` | Abfüller | Bottler | Embouteilleur | Imbottigliatore | Embotellador | Engarrafador | Bottelaar |
| `label_batch` | Batch-Nr. | Batch no. | N° de lot | N. lotto | N.º de lote | N.º de lote | Batchnr. |
| `label_cask_strength` | Fassstärke | Cask strength | Brut de fût | Cask strength | Cask strength | Cask strength | Cask strength |
| `label_single_cask` | Single Cask | Single cask | Fût unique | Single cask | Barril único | Barril único | Single cask |
| `label_cask_number` | Fassnummer | Cask number | N° de fût | N. botte | N.º de barril | N.º de barril | Vatnummer |
| `label_chill_filtered` | Kühlfiltriert | Chill filtered | Filtré à froid | Filtrato a freddo | Filtrado en frío | Filtrado a frio | Koudgefilterd |
| `label_peat` | Torf (ppm) | Peat (ppm) | Tourbe (ppm) | Torba (ppm) | Turba (ppm) | Turfa (ppm) | Turf (ppm) |
| `label_casks` | Fässer | Casks | Fûts | Botti | Barriles | Barris | Vaten |
| `casks_manage` | Fässer bearbeiten | Edit casks | Modifier les fûts | Modifica botti | Editar barriles | Editar barris | Vaten bewerken |
| `casks_title` | Fässer | Casks | Fûts | Botti | Barriles | Barris | Vaten |
| `casks_hint` | Erstfass zuerst, danach die Finishes. | Initial cask first, then the finishes. | Fût initial d'abord, puis les finitions. | Prima la botte iniziale, poi i finish. | Primero el barril inicial, luego los acabados. | Primeiro o barril inicial, depois os acabamentos. | Eerst het eerste vat, daarna de finishes. |
| `casks_add` | + Fass | + Cask | + Fût | + Botte | + Barril | + Barril | + Vat |
| `casks_years` | Jahre | Years | Ans | Anni | Años | Anos | Jaar |
| `cask_role_first` | Erstfass | Initial cask | Fût initial | Botte iniziale | Barril inicial | Barril inicial | Eerste vat |
| `cask_role_finish` | Finish | Finish | Finition | Finish | Acabado | Acabamento | Finish |
| `label_sealed` | Versiegelt | Sealed | Scellées | Sigillate | Selladas | Seladas | Verzegeld |
| `label_opened_at` | Offen seit | Open since | Ouverte depuis | Aperta dal | Abierta desde | Aberta desde | Open sinds |
| `label_fill_level` | Füllstand | Fill level | Niveau | Livello | Nivel | Nível | Niveau |
| `btn_open_bottle` | Öffnen | Open | Ouvrir | Apri | Abrir | Abrir | Openen |
| `btn_finish_bottle` | Leer | Empty | Vide | Vuota | Vacía | Vazia | Leeg |
| `tab_whisky` | Whisky | Whisky | Whisky | Whisky | Whisky | Whisky | Whisky |
| `taste_smoke` | Rauch | Smoke | Fumé | Affumicato | Humo | Fumo | Rook |
| `taste_fruit` | Frucht | Fruit | Fruit | Frutta | Fruta | Fruta | Fruit |
| `taste_spice` | Würze | Spice | Épices | Spezie | Especias | Especiarias | Kruidigheid |
| `timeline_opened` | geöffnet | opened | ouverte | aperta | abierta | aberta | geopend |
| `timeline_refilled` | Füllstand korrigiert | fill level corrected | niveau corrigé | livello corretto | nivel corregido | nível corrigido | niveau gecorrigeerd |
| `ref_spirit_types` | Spirituosen-Typen | Spirit types | Types de spiritueux | Tipi di distillato | Tipos de destilado | Tipos de destilado | Gedistilleerd-types |
| `ref_cask_types` | Fasstypen | Cask types | Types de fûts | Tipi di botte | Tipos de barril | Tipos de barril | Vattypes |

- [ ] **Step 2: Verify the file still parses and every key exists in all languages**

Run:

```bash
cd wine-tracker && ../.venv/Scripts/python.exe -c "
import sys; sys.path.insert(0,'app')
import translations as t
langs = [k for k in dir(t) if k.isupper() and isinstance(getattr(t,k), dict)]
keys = ['area_cellar','label_distillery','label_abv','casks_add','cask_role_first',
        'label_sealed','btn_open_bottle','tab_whisky','taste_smoke','ref_cask_types']
for name in langs:
    d = getattr(t, name)
    if 'label_grape' not in d: continue
    missing = [k for k in keys if k not in d]
    print(name, 'OK' if not missing else 'FEHLT: %s' % missing)
"
```

Expected: für jeden Sprachblock `OK`.

- [ ] **Step 3: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/translations.py
git commit -m "feat(spirits): translation keys for spirits/whisky in 7 languages"
```

---

## Task 11: Formular — Kategorie, Whisky-Tab, Fässer-Feld

**Files:**
- Modify: `wine-tracker/app/templates/_wine_form_fields.html`
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html`
- Modify: `wine-tracker/app/static/style.css`
- Verify: Playwright-Skript im Scratchpad

**Interfaces:**
- Consumes: Übersetzungsschlüssel aus Task 10; `wine.category`, `wine.spirit_details`, `wine.casks` aus Task 7.
- Produces:
  - Verstecktes `<input name="category" id="wine_category">`; JS `setWineCategory(cat)` blendet die Feldsätze um.
  - Whisky-Tab mit `data-panel="whisky"`.
  - Fass-Chipfeld `#caskField` + Dialog `#casksModal`, JS `caskAddRow/caskSetRows/caskCollect/caskSerialize/openCasksDialog/closeCasksDialog` — 1:1 nach dem Muster der Rebsorten (`grapeAddRow` etc.), aber **ohne** Dedup und mit Zeilenbeschriftung `cask_role_first` / `cask_role_finish`.

- [ ] **Step 1: Add the category field and whisky tab to the form**

In `_wine_form_fields.html` in der Tab-Leiste einen vierten Button ergänzen:

```html
  <button type="button" class="wine-tab" data-tab="whisky" data-cat="spirits"
          onclick="switchWineTab('whisky')">{{ t.tab_whisky }}</button>
```

und ein Panel:

```html
<div class="wine-tab-panel" data-panel="whisky" hidden>
  <div class="row2">
    <div><label>{{ t.label_abv }}</label>
      <input type="number" name="abv" id="wine_abv" min="0" max="100" step="0.1"></div>
    <div><label>{{ t.label_age }}</label>
      <input type="number" name="age_years" id="wine_age_years" min="0" max="100"></div>
  </div>
  <div class="row2">
    <div><label>{{ t.label_distilled }}</label>
      <input type="number" name="distilled_year" id="wine_distilled_year" min="1800" max="2099"></div>
    <div><label>{{ t.label_bottled }}</label>
      <input type="number" name="bottled_year" id="wine_bottled_year" min="1800" max="2099"></div>
  </div>
  <div>
    <label>{{ t.label_casks }}</label>
    <button type="button" class="grape-field" id="caskField" onclick="openCasksDialog()"
            title="{{ t.casks_manage }}" aria-label="{{ t.casks_manage }}">
      <span class="grape-field-chips" id="caskSummary"></span>
      <i class="mdi mdi-chevron-right grape-field-arrow"></i>
    </button>
    <input type="hidden" name="casks" id="wine_casks_json">
  </div>
  <div class="row2">
    <div><label>{{ t.label_bottler }}</label>
      <input type="text" name="bottler" id="wine_bottler" list="wineryList" autocomplete="off"></div>
    <div><label>{{ t.label_batch }}</label>
      <input type="text" name="batch_number" id="wine_batch_number"></div>
  </div>
  <div class="row2">
    <div><label>{{ t.label_cask_number }}</label>
      <input type="text" name="cask_number" id="wine_cask_number"></div>
    <div><label>{{ t.label_peat }}</label>
      <input type="number" name="peat_ppm" id="wine_peat_ppm" min="0" max="200"></div>
  </div>
  <div class="spirit-flags">
    <label><input type="checkbox" name="cask_strength" id="wine_cask_strength" value="1">
      {{ t.label_cask_strength }}</label>
    <label><input type="checkbox" name="single_cask" id="wine_single_cask" value="1">
      {{ t.label_single_cask }}</label>
    <label><input type="checkbox" name="chill_filtered" id="wine_chill_filtered" value="1">
      {{ t.label_chill_filtered }}</label>
  </div>
</div>
```

Ausserdem das versteckte Kategoriefeld neben `#wine_grapes_json`:

```html
      <input type="hidden" name="category" id="wine_category" value="wine">
```

Wein-spezifische Blöcke bekommen `data-cat="wine"`, spirituosenspezifische `data-cat="spirits"` — daran hängt die Sichtbarkeitslogik. Betroffen sind: das Rebsorten-Feld, Jahrgang, Trinkfenster, der Reife-&-Geschmack-Tab und der Vivino-Block (`data-cat="wine"`).

- [ ] **Step 2: Add the category switching JS**

In `_wine_edit_modal.html` neben `switchWineTab`:

```javascript
// Category drives which field sets are visible. 'whisky' and 'spirit' share
// the same UI; only 'wine' differs.
function setWineCategory(cat) {
  cat = (cat === 'whisky' || cat === 'spirit') ? cat : 'wine';
  var el = document.getElementById('wine_category');
  if (el) el.value = cat;
  var isWine = (cat === 'wine');
  document.querySelectorAll('#wineModal [data-cat]').forEach(function(node) {
    var want = node.getAttribute('data-cat');
    var show = isWine ? (want === 'wine') : (want === 'spirits');
    node.hidden = !show;
    if (node.classList.contains('wine-tab')) node.style.display = show ? '' : 'none';
  });
  // never leave the user on a hidden tab
  var active = document.querySelector('#formStep .wine-tab.active');
  if (active && active.style.display === 'none') switchWineTab('basics');
}

function currentWineCategory() {
  var el = document.getElementById('wine_category');
  return el ? (el.value || 'wine') : 'wine';
}
```

`openWineModal` ruft am Ende `setWineCategory(w.category || _defaultCategory())` auf, wobei `_defaultCategory()` den aktiven Bereich liefert (`window._area === 'bar' ? 'whisky' : 'wine'`).

- [ ] **Step 3: Fill and read the whisky fields**

In `openWineModal` nach den bestehenden Feldern:

```javascript
  var sd = w.spirit_details || {};
  var setv = function(id, v) { var e = document.getElementById(id); if (e) e.value = (v == null ? '' : v); };
  setv('wine_abv', sd.abv); setv('wine_age_years', sd.age_years);
  setv('wine_distilled_year', sd.distilled_year); setv('wine_bottled_year', sd.bottled_year);
  setv('wine_bottler', sd.bottler); setv('wine_batch_number', sd.batch_number);
  setv('wine_cask_number', sd.cask_number); setv('wine_peat_ppm', sd.peat_ppm);
  ['cask_strength', 'single_cask', 'chill_filtered'].forEach(function(k) {
    var e = document.getElementById('wine_' + k);
    if (e) e.checked = !!sd[k];
  });
  caskSetRows(w.casks || []);
```

- [ ] **Step 4: Add the cask rows widget**

Nach dem Vorbild des Rebsorten-Widgets (`grapeRowHtml`, `grapeAddRow`, `grapeSetRows`, `grapeCollect`, `grapeSerialize`, `grapeUpdateSummary`, `openGrapesDialog`, `closeGrapesDialog`) ein identisch aufgebautes Cask-Widget ergänzen. Unterschiede:

- Zweites Feld ist `years` (nicht `pct`), Beschriftung `T.casks_years`.
- Jede Zeile trägt links ein Rollen-Label: Index 0 → `T.cask_role_first`, sonst `T.cask_role_finish`. Nach `caskAddRow`/`caskDelRow` müssen die Labels neu vergeben werden (`caskRelabel()`).
- **Kein** Dedup und keine Summenanzeige.
- Zusammenfassung im Chipfeld: Chips in Reihenfolge, verbunden durch `→`.
- Autocomplete-Datalist `caskList`, gespeist aus einer neuen Context-Variable `ref_cask_names` (in `app.py` analog zu `ref_grape_names` ergänzen: `SELECT name FROM ref_cask_types ORDER BY sort_order`).

Der Dialog `#casksModal` wird direkt neben `#grapesModal` angelegt, mit `{{ t.casks_title }}`, `{{ t.casks_hint }}`, `{{ t.casks_add }}` und dem Fertig-Button `{{ t.grapes_done }}`.

- [ ] **Step 5: Serialize on submit**

In `reconcileThenSubmit` neben `grapeSerialize()`:

```javascript
  caskSerialize();
```

- [ ] **Step 6: Add the CSS**

In `style.css` ergänzen:

```css
.spirit-flags { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; }
.spirit-flags label { display: inline-flex; align-items: center; gap: 6px;
  font-size: .9rem; color: var(--text); margin: 0; }
.cask-row { display: flex; align-items: center; gap: 6px; }
.cask-role { flex: 0 0 68px; font-size: .78rem; color: var(--muted); }
.cask-row .cask-name { flex: 1 1 auto; min-width: 0; }
.cask-row .cask-years { flex: 0 0 auto; width: 56px; text-align: right;
  -moz-appearance: textfield; appearance: textfield; }
.cask-row .cask-years::-webkit-outer-spin-button,
.cask-row .cask-years::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }

@media (max-width: 600px) {
  .cask-role { flex-basis: 100%; }
  .cask-row { flex-wrap: wrap; }
}
```

- [ ] **Step 7: Verify with Playwright**

Server neu starten (Templates sind gecacht), dann ein Scratchpad-Skript, das prüft:
1. `openWineModal(null)` + `setWineCategory('whisky')` → Whisky-Tab sichtbar, Rebsorten-Feld `hidden`.
2. `setWineCategory('wine')` → umgekehrt.
3. `caskAddRow('Ex-Bourbon', 12)`, `caskAddRow('PX Sherry', 2)` → zwei Zeilen, Rollen-Labels „Erstfass"/„Finish".
4. `caskSerialize()` → `#wine_casks_json` enthält beide Einträge in Reihenfolge.
5. `#caskSummary` zeigt `Ex-Bourbon → PX Sherry`.
6. Keine `pageerror`.

Expected: alle Checks grün.

- [ ] **Step 8: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/templates/_wine_form_fields.html wine-tracker/app/templates/_wine_edit_modal.html wine-tracker/app/static/style.css wine-tracker/app/app.py
git commit -m "feat(spirits): whisky tab, category switching, cask chip field"
```

---

## Task 12: Bereichsumschalter, Karte und Detailansicht

**Files:**
- Modify: `wine-tracker/app/templates/index.html`
- Modify: `wine-tracker/app/static/style.css`
- Verify: Playwright-Skript im Scratchpad

**Interfaces:**
- Consumes: `area` aus Task 7, `wine.spirit_details`, `wine.casks`, Übersetzungen aus Task 10, Routen aus Task 8.
- Produces: Umschalter `#areaSwitch`, JS `setArea(area)` (merkt sich in `localStorage` unter `wt_area` und lädt `/?area=…`), Detailaktionen `openBottle(id)`, `setFill(id, percent)`, `finishBottle(id)`.

- [ ] **Step 1: Add the area switch**

In der Kopfzeile von `index.html`:

```html
<div class="area-switch" id="areaSwitch">
  <button type="button" class="area-btn{% if area != 'bar' %} active{% endif %}"
          onclick="setArea('cellar')">{{ t.area_cellar }}</button>
  <button type="button" class="area-btn{% if area == 'bar' %} active{% endif %}"
          onclick="setArea('bar')">{{ t.area_bar }}</button>
</div>
```

```javascript
window._area = {{ (area or 'cellar')|tojson }};
function setArea(area) {
  try { localStorage.setItem('wt_area', area); } catch (e) {}
  window.location.href = INGRESS + '/?area=' + encodeURIComponent(area);
}
// Restore the remembered area on a plain visit (no explicit ?area= given).
(function() {
  if (window.location.search.indexOf('area=') !== -1) return;
  var saved = null;
  try { saved = localStorage.getItem('wt_area'); } catch (e) {}
  if (saved && saved !== 'cellar') setArea(saved);
})();
```

- [ ] **Step 2: Show the open bottle on the card**

Im Karten-Markup (Jinja) und in `renderCard` (JS) neben der Mengenanzeige:

```javascript
  var sd = w.spirit_details || {};
  if (sd.opened_at) {
    extra += '<span class="card-open"><i class="mdi mdi-bottle-tonic"></i> ' +
      Math.round(sd.fill_level == null ? 100 : sd.fill_level) + ' %</span>';
  }
```

Analog im server-gerenderten Kartenblock über `w['spirit_details']`.

- [ ] **Step 3: Show casks and whisky facts in the detail view**

In `openViewModal` neben den bestehenden Zeilen:

```javascript
  var sd = w.spirit_details || {};
  if (w.category && w.category !== 'wine') {
    if (sd.abv != null) details += viewRow('mdi-percent', T.label_abv, sd.abv);
    if (sd.age_years != null) details += viewRow('mdi-timer-sand', T.label_age, sd.age_years);
    if (w.casks && w.casks.length) {
      details += viewRowHtml('mdi-barrel', T.label_casks, w.casks.map(function(c) {
        return '<span class="grape-chip">' + escapeHtml(c.name) +
          (c.years == null ? '' : ' ' + c.years + ' J.') + '</span>';
      }).join(' '));
    }
    if (sd.bottler) details += viewRow('mdi-factory', T.label_bottler, sd.bottler);
    if (sd.batch_number) details += viewRow('mdi-numeric', T.label_batch, sd.batch_number);
    if (sd.opened_at) {
      details += viewRow('mdi-calendar-clock', T.label_opened_at, sd.opened_at);
      details += viewRowHtml('mdi-cup', T.label_fill_level, fillBarHtml(sd.fill_level));
    }
  }
```

Hilfsfunktion:

```javascript
function fillBarHtml(pct) {
  var p = Math.max(0, Math.min(100, pct == null ? 100 : pct));
  return '<span class="fill-bar"><span class="fill-bar-in" style="width:' + p + '%"></span></span>' +
         '<span class="fill-pct">' + Math.round(p) + ' %</span>';
}
```

Hinweis: `viewRowHtml` existiert bereits in `index.html` (nicht escapender Zwilling von `viewRow`).

- [ ] **Step 4: Add the open-bottle actions**

In den `view-actions` der Detailansicht, nur für Spirituosen sichtbar:

```javascript
function openBottle(id) {
  fetch(INGRESS + '/api/wine/' + id + '/open', {
    method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }
  }).then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) { closeModal('viewModal'); window.location.reload(); } });
}

function setFill(id, percent) {
  fetch(INGRESS + '/api/wine/' + id + '/fill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
    body: JSON.stringify({ percent: Number(percent) })
  }).then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) openViewModal(d.wine.id, d.wine); });
}

function finishBottle(id) {
  fetch(INGRESS + '/api/wine/' + id + '/finish', {
    method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }
  }).then(function(r) { return r.json(); })
    .then(function(d) { if (d.ok) { closeModal('viewModal'); window.location.reload(); } });
}
```

Der Füllstand wird über einen `<input type="range" min="0" max="100" step="5" onchange="setFill(...)">` in der Detailansicht bedient.

- [ ] **Step 5: Add the CSS**

```css
.area-switch { display: inline-flex; border: 1px solid var(--border); border-radius: 999px;
  overflow: hidden; }
.area-btn { background: none; border: none; padding: 6px 14px; cursor: pointer;
  color: var(--muted); font-size: .85rem; }
.area-btn.active { background: var(--accent); color: #fff; }
.fill-bar { display: inline-block; width: 90px; height: 8px; border-radius: 4px;
  background: var(--border); overflow: hidden; vertical-align: middle; margin-right: 6px; }
.fill-bar-in { display: block; height: 100%; background: var(--accent); }
.fill-pct { font-size: .85rem; }
.card-open { opacity: .85; }
```

- [ ] **Step 6: Verify with Playwright**

Server neu starten, dann prüfen:
1. Whisky anlegen (POST `/add` mit `category=whisky`, `quantity=2`).
2. `/?area=bar` zeigt ihn, `/?area=cellar` nicht.
3. Detailansicht öffnen → „Öffnen" klicken → Bestand 1, Füllstand 100 %.
4. `setFill(id, 55)` → Balken und Prozentwert zeigen 55.
5. „Leer" → offene Flasche verschwindet.
6. Keine `pageerror`.

- [ ] **Step 7: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/templates/index.html wine-tracker/app/static/style.css
git commit -m "feat(spirits): area switch, open-bottle display and actions"
```

---

## Task 13: Statistiken, Timeline und Filter

**Files:**
- Modify: `wine-tracker/app/templates/stats.html`, `timeline.html`
- Modify: `wine-tracker/app/static/filter-advanced.js`
- Modify: `wine-tracker/app/app.py` (Statistik-Abfragen, Timeline-Labels)

**Interfaces:**
- Consumes: `category`, `spirit_details`, Übersetzungen `timeline_opened` / `timeline_refilled`.
- Produces: Statistiken und Timeline respektieren den Bereich; die Advanced-Filter kennen Whisky-Felder.

- [ ] **Step 1: Timeline labels for the new actions**

Dort, wo die Timeline-Aktionen auf Texte gemappt werden (`timeline.html`), ergänzen:

```javascript
  opened:   T.timeline_opened,
  refilled: T.timeline_refilled,
```

Unbekannte Aktionen dürfen nicht als leerer Text erscheinen — Fallback auf den rohen Aktionsnamen.

- [ ] **Step 2: Count the open bottle in the totals**

Die Bestandsabfragen zählen heute `SUM(quantity)`. Für Spirituosen zählt die offene Flasche mit:

```sql
SELECT SUM(w.quantity + CASE WHEN sd.opened_at IS NOT NULL THEN 1 ELSE 0 END)
  FROM wines w LEFT JOIN spirit_details sd ON sd.wine_id = w.id
```

Betroffen sind `stats_json()` und die Statistikseite. Der Liter-Wert (`SUM(quantity * bottle_format)`) bleibt unverändert — der Teilinhalt einer offenen Flasche wird bewusst nicht anteilig gerechnet (siehe Spec, nicht im Scope).

- [ ] **Step 3: Area filter on the stats page**

`stats.html` bekommt denselben Umschalter wie die Hauptseite und hängt `?area=` an die Datenabfrage. Ohne Parameter: alles.

- [ ] **Step 4: Whisky fields in the advanced filter**

In `filter-advanced.js` in der Feldliste ergänzen:

```javascript
    { key: 'abv',       group: 'numbers', type: 'number', label: 'label_abv' },
    { key: 'age_years', group: 'numbers', type: 'number', label: 'label_age', integer: true },
    { key: 'cask',      group: 'text',    type: 'text',   label: 'label_casks' },
    { key: 'bottler',   group: 'text',    type: 'text',   label: 'label_bottler' },
```

Damit sie clientseitig greifen, müssen die Karten die Werte als `data-`Attribute tragen: `data-abv`, `data-age_years`, `data-cask` (die Zusammenfassung), `data-bottler`. Ergänze sie im Karten-Markup (Jinja **und** `renderCard`) und in `getCardData`.

- [ ] **Step 5: Verify**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_routes.py -q`
Expected: PASS.

Playwright: Bar-Ansicht öffnen, Filter „Vol.-% > 45" setzen, prüfen dass nur passende Karten sichtbar bleiben.

- [ ] **Step 6: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/templates/stats.html wine-tracker/app/templates/timeline.html wine-tracker/app/static/filter-advanced.js wine-tracker/app/app.py
git commit -m "feat(spirits): stats/timeline area awareness, whisky filters"
```

---

## Task 14: Export und Import

**Files:**
- Modify: `wine-tracker/app/export_import.py`
- Test: `wine-tracker/tests/test_export_import.py`

**Interfaces:**
- Consumes: `spirits.get_details`, `spirits.set_details`, `spirits.list_casks`, `spirits.set_casks`.
- Produces: Export enthält je Eintrag `category`, `spirit_details` und `casks`; Import stellt sie wieder her, Alt-Archive ohne diese Felder bleiben gültig.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_export_import.py`:

```python
class TestSpiritsExportImport:
    def test_export_contains_spirit_data(self, client, db):
        import json as J
        client.post("/add", data={
            "name": "Exp Whisky", "category": "whisky", "type": "Single Malt",
            "quantity": "1", "abv": "46",
            "casks": J.dumps([{"name": "Ex-Bourbon", "years": 10}]),
        }, follow_redirects=True)
        zf = zipfile.ZipFile(io.BytesIO(client.get("/export").data))
        w = next(x for x in json.loads(zf.read("wines.json")) if x["name"] == "Exp Whisky")
        assert w["category"] == "whisky"
        assert w["spirit_details"]["abv"] == 46
        assert [c["name"] for c in w["casks"]] == ["Ex-Bourbon"]

    def test_import_restores_spirit_data(self, client, db, upload_dir):
        from export_import import match_wines, apply_import
        import spirits
        parsed = {
            "wines": [{"name": "Imp Whisky", "category": "whisky", "type": "Single Malt",
                       "quantity": 1,
                       "spirit_details": {"abv": 43, "age_years": 12},
                       "casks": [{"name": "Oloroso Sherry", "years": 12}]}],
            "timeline": [], "purchases": [], "images": {}, "original_ids": [None],
        }
        apply_import(parsed, match_wines(parsed["wines"], db), db, upload_dir, strategy="skip")
        wid = db.execute("SELECT id FROM wines WHERE name='Imp Whisky'").fetchone()[0]
        assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "whisky"
        assert spirits.get_details(db, wid)["abv"] == 43
        assert [c["name"] for c in spirits.list_casks(db, wid)] == ["Oloroso Sherry"]

    def test_legacy_archive_without_category_imports_as_wine(self, client, db, upload_dir):
        from export_import import match_wines, apply_import
        parsed = {"wines": [{"name": "Legacy Cat", "type": "red", "quantity": 1}],
                  "timeline": [], "purchases": [], "images": {}, "original_ids": [None]}
        apply_import(parsed, match_wines(parsed["wines"], db), db, upload_dir, strategy="skip")
        wid = db.execute("SELECT id FROM wines WHERE name='Legacy Cat'").fetchone()[0]
        assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "wine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_export_import.py -q -k Spirits`
Expected: FAIL — `category` fehlt im Export.

- [ ] **Step 3: Add category to the exported columns**

In `export_import.py` `WINE_COLUMNS` um `"category"` erweitern (nach `"name"`), und in `CSV_COLUMNS` `"category"` sowie `"abv"` ergänzen.

- [ ] **Step 4: Attach details and casks on export**

In `build_export_zip` neben dem Rebsorten-Loop:

```python
    import spirits as spirit_model
    for w in wines:
        w["spirit_details"] = spirit_model.get_details(db, w["id"])
        w["casks"] = [{"name": c["name"], "years": c["years"]}
                      for c in spirit_model.list_casks(db, w["id"])]
        w["abv"] = w["spirit_details"].get("abv")     # for the CSV view
```

- [ ] **Step 5: Preserve them through normalization and apply them on import**

In `_normalize_wine` nach dem Rebsorten-Block:

```python
    if isinstance(w.get("spirit_details"), dict):
        out["spirit_details"] = w["spirit_details"]
    if isinstance(w.get("casks"), list):
        out["casks"] = w["casks"]
    out["category"] = (w.get("category") or "wine")
```

In `apply_import` neben dem Rebsorten-Block:

```python
        sd = wine.get("spirit_details")
        if isinstance(sd, dict) and any(v is not None for v in sd.values()):
            spirit_model.set_details(db, target_id, sd)
        if isinstance(wine.get("casks"), list) and wine["casks"]:
            spirit_model.set_casks(db, target_id, wine["casks"])
```

- [ ] **Step 6: Document the new fields in the README**

In `_build_readme` in der Feldreferenz ergänzen (Achtung: f-String, geschweifte Klammern verdoppeln):

```
| `category` | string | `wine`, `whisky` oder `spirit` |
| `spirit_details` | object | Whisky-Felder (abv, age_years, cask_summary, bottler, batch_number, …) |
| `casks` | array | Reifekette: Liste von `{{name, years}}`, Reihenfolge = Erstfass zuerst |
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `../.venv/Scripts/python.exe -m pytest tests/test_export_import.py -q`
Expected: PASS.

- [ ] **Step 8: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/export_import.py wine-tracker/tests/test_export_import.py
git commit -m "feat(spirits): export/import category, details and casks"
```

---

## Task 15: Release 1.15.0

**Files:**
- Modify: `wine-tracker/config.yaml`, `wine-tracker/app/app.py`, `wine-tracker/CHANGELOG.md`, `CHANGELOG.md`

- [ ] **Step 1: Run the full suite (release gate, no need to ask)**

Run: `../.venv/Scripts/python.exe -m pytest tests -q`
Expected: alles grün.

- [ ] **Step 2: Bump both version files**

`wine-tracker/config.yaml` → `version: "1.15.0"`, `wine-tracker/app/app.py` → `APP_VERSION = "1.15.0"`.

- [ ] **Step 3: Write the entry into BOTH changelogs**

Identischer `## 1.15.0`-Abschnitt (deutsch) oben in `wine-tracker/CHANGELOG.md` **und** `CHANGELOG.md`. Inhalt: Bereichsumschalter Weinkeller/Bar, Whisky-Felder inkl. Fasskette mit Erstfass und Finishes, Batch-Nummer, offene Flaschen mit Füllstand, kategorieabhängige KI, neue Referenzlisten (Spirituosen-Typen, Fasstypen, Whisky-Regionen, Spirituosen-Flaschengrössen), Export/Import.

- [ ] **Step 4: Verify the checklist on the commit**

```bash
git show HEAD:wine-tracker/config.yaml | grep '^version:'
git show HEAD:wine-tracker/app/app.py | grep '^APP_VERSION'
git show HEAD:wine-tracker/CHANGELOG.md | grep -m1 '^## '
git show HEAD:CHANGELOG.md | grep -m1 '^## '
```

Alle vier müssen `1.15.0` zeigen.

- [ ] **Step 5: Commit and push** *(only with explicit user go-ahead)*

```bash
git add wine-tracker/config.yaml wine-tracker/app/app.py wine-tracker/CHANGELOG.md CHANGELOG.md
git commit -m "Release 1.15.0: spirits and whisky tracking"
git push origin main
```

---

## Self-Review

**1. Spec coverage**

- Kategorie-Spalte + `spirit_details` → Task 1, 4 ✅
- Fässer 1-n mit Reihenfolge, `years`, `cask_summary`, keine Dedup → Task 2 ✅
- Offene Flaschen (Öffnen/Füllstand/Leer, Timeline `opened`/`refilled`) → Task 3, 8, 12 ✅
- Referenzlisten `ref_spirit_types`, `ref_cask_types`, Whisky-Regionen, Flaschengrössen → Task 5 ✅
- Batch-Nummer → Task 1 (Spalte), 6 (Speichern), 11 (Formular), 12 (Detailansicht) ✅
- Save-Routen mit Kategorie + Teil-Posts, die Details erhalten → Task 6 ✅
- `wine_json` + Bereichsfilter → Task 7 ✅
- KI kategorieabhängig, Typ-Validierung, Kanonisierung Fass/Typ → Task 9 ✅
- Vivino für Spirituosen ausblenden → Task 11 Step 1 (`data-cat="wine"` am Vivino-Block) ✅
- Bereichsumschalter mit localStorage → Task 12 ✅
- Statistiken/Timeline/Filter → Task 13 ✅
- Export/Import inkl. Alt-Archive → Task 14 ✅
- Übersetzungen ×7 → Task 10 ✅
- Release mit beiden Changelogs → Task 15 ✅
- Randfälle: unbekannte Kategorie (T6), fehlende `spirit_details` (T1), Öffnen bei 0 (T3), ungültiger Füllstand (T3), Fass ohne Namen (T2), wiederholter Fasstyp (T2), Cascade (T1) ✅

**2. Placeholder scan:** Keine TBD/TODO. Task 11 Step 4 und Task 13 Step 3 beschreiben die Umsetzung anhand eines konkreten, im Repo vorhandenen Vorbilds statt vollständigen Codes — das ist bewusst, weil das Rebsorten-Widget 1:1 als Vorlage dient und ein Duplikat hier nur Abweichungsrisiko schaffen würde. Alle Signaturen, IDs, CSS-Klassen und Übersetzungsschlüssel sind benannt.

**3. Type consistency**

- `spirits.set_details(db, wine_id, dict)` / `get_details -> dict` — Task 1, 6, 7, 12, 14 konsistent ✅
- `spirits.set_casks(db, wine_id, [{"name","years"}])` / `list_casks -> [{"name","years","cask_id","position"}]` — Task 2, 6, 7, 12, 14 konsistent ✅
- `open_bottle(db, wine_id, today) -> bool`, `set_fill_level(db, wine_id, percent) -> bool`, `finish_bottle(db, wine_id) -> bool` — Task 3, 8 konsistent ✅
- Kategoriewerte `wine`/`whisky`/`spirit` und `area`-Werte `cellar`/`bar` durchgängig ✅
- JS: `setWineCategory`, `currentWineCategory`, `caskSetRows/caskCollect/caskSerialize/openCasksDialog`, `setArea`, `openBottle/setFill/finishBottle`, `fillBarHtml` — Task 11, 12 konsistent ✅
- Formularfeld-IDs (`wine_category`, `wine_abv`, `wine_casks_json`, …) stimmen zwischen Task 11 (Markup) und Task 6 (Server-Parsing über die `name`-Attribute) überein ✅
