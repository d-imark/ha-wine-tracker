# Rebsorten 1‑n mit Prozenten — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ein Wein trägt 1‑n Rebsorten mit optionalem Prozentanteil, normalisiert in `wine_grapes` (FK auf `ref_grapes`), während `wines.grape` als abgeleiteter Cache-String erhalten bleibt.

**Architecture:** Ansatz **B2**: neue Kind-Tabelle `wine_grapes` ist Source of Truth (name, optionaler pct, position, weicher `grape_id`-FK). Bei jedem Speichern wird `wines.grape` als komma-getrennter Cache neu gebaut, damit Suche/Filter/Sortierung/Export/Chat unverändert weiterlesen. Editor bekommt ein Zeilen-Widget mit Autocomplete gegen `ref_grapes`, Reconcile pro Rebsorte, farbige Chips nach `ref_grapes.color`. KI/Vivino liefern Rebsortenlisten.

**Tech Stack:** Python 3 / Flask, sqlite3, Jinja2, Vanilla-JS-Modals, pytest, Playwright (System-Chrome `channel="chrome"`). Windows/PowerShell; venv `.venv`.

## Global Constraints

- **Nie committen/pushen ohne ausdrückliche Freigabe des Users** — die `git commit`-Schritte unten nur ausführen, wenn der User es für den jeweiligen Punkt freigibt.
- **Vor der vollen pytest-Suite fragen** — gezielte Tests (`pytest tests/test_x.py::test_y`) sind ok.
- **Bei Version-Bump/Release IMMER beide Changelogs** nachführen: `wine-tracker/CHANGELOG.md` (deutsch, von HA angezeigt) UND Root `CHANGELOG.md`, plus `wine-tracker/config.yaml` `version:` und `wine-tracker/app/app.py` `APP_VERSION`. Zielversion dieses Features: **1.14.0**.
- `scripts/run-dev.local.ps1` ist gitignored (echter OpenAI-Key) — **niemals committen**.
- Prozente sind **optional, keine Summenpflicht** (nur nicht-blockierender Hinweis).
- Tests laufen mit `.venv\Scripts\python.exe -m pytest` aus `wine-tracker/`. App-Neustart nach Template/CSS-Änderungen (alle `app.py`-Prozesse beenden, um Stale-Serving zu vermeiden).
- Dev-Server: `./.venv/Scripts/python.exe wine-tracker/app/app.py` (waitress, Port 5050). `INGRESS` ist im Dev leer.

---

## File Structure

- **`wine-tracker/app/grapes.py`** *(neu)* — Kapselt die gesamte `wine_grapes`-Logik: Tabelle, CRUD-Ersatz `set_wine_grapes`, `list_wine_grapes`, `rebuild_cache`, reiner Helfer `split_legacy`. Analog zu `purchases.py`.
- **`wine-tracker/app/app.py`** — init_db-Wiring + Backfill; add/edit-Routen; `wine_json`; index-Context; Datalist-Context; Reconcile-Endpoint; KI-Schema/Prompt; Vivino-Ergebnis.
- **`wine-tracker/app/export_import.py`** — `grapes`-JSON in Export/Import.
- **`wine-tracker/app/templates/_wine_form_fields.html`** — Zeilen-Widget statt Einzelfeld, Datalist-Quelle.
- **`wine-tracker/app/templates/_wine_edit_modal.html`** — JS für Zeilen, Befüllung, Serialisierung, Reconcile, Vivino/AI-Sonderfall.
- **`wine-tracker/app/templates/index.html`** — Karte/Tabelle „+N", Detail-Liste, `data-grape`, `viewChangeQty`.
- **`wine-tracker/app/templates/stats.html`, `chat.html`** — Detail-Blend.
- **`wine-tracker/app/static/filter-advanced.js`** — Datalist-Quelle.
- **`wine-tracker/app/static/style.css`** — Widget + Chips + Farbpunkte.
- **`wine-tracker/app/translations.py`** — neue Keys ×7 Sprachen.
- **`wine-tracker/tests/test_grapes.py`** *(neu)* + Erweiterungen in `test_api.py`, `test_routes.py`, `test_export_import.py`.

---

## Task 1: `grapes.py` — Modul, Tabelle, Kernfunktionen

**Files:**
- Create: `wine-tracker/app/grapes.py`
- Test: `wine-tracker/tests/test_grapes.py`

**Interfaces:**
- Consumes: `reference.match_reference(db, "grape", name)` → Row or None (bestehend in `reference.py`).
- Produces:
  - `create_wine_grapes_table(db) -> None`
  - `split_legacy(text: str) -> list[str]` — Namen in Reihenfolge, dedupliziert (case-insensitiv).
  - `set_wine_grapes(db, wine_id: int, entries: list[dict]) -> None` — `entries` = `[{"name": str, "pct": float|None}]`; ersetzt alle Zeilen, setzt `grape_id`/`position`, ruft `rebuild_cache`. Commit macht der Aufrufer NICHT — diese Funktion committet selbst (wie `purchases.add_purchase`).
  - `list_wine_grapes(db, wine_id: int) -> list[dict]` — `[{"name","pct","color","grape_id","position"}]` nach `position`.
  - `rebuild_cache(db, wine_id: int) -> str|None` — schreibt `wines.grape`, gibt den String zurück.

- [ ] **Step 1: Write the failing test for `split_legacy`**

Create `wine-tracker/tests/test_grapes.py`:

```python
from app import grapes


def test_split_legacy_separators_and_dedup():
    assert grapes.split_legacy("Merlot, Cabernet & Syrah / Merlot") == [
        "Merlot", "Cabernet", "Syrah"
    ]


def test_split_legacy_trims_and_ignores_empty():
    assert grapes.split_legacy("  Merlot ,, /  Cabernet  ") == ["Merlot", "Cabernet"]


def test_split_legacy_empty_input():
    assert grapes.split_legacy("") == []
    assert grapes.split_legacy(None) == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_grapes.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError: module 'app.grapes' has no attribute 'split_legacy'`.

- [ ] **Step 3: Implement `grapes.py` with table + `split_legacy`**

Create `wine-tracker/app/grapes.py`:

```python
"""Grape varieties per wine (1-n, each with an optional percentage).

`wine_grapes` is the source of truth for a wine's blend. The plain-text
`wines.grape` column is kept as an auto-rebuilt cache so existing search,
filter, sort, export and chat paths keep working unchanged.
"""
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
```

- [ ] **Step 4: Run tests to verify `split_legacy` passes**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_grapes.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Write failing tests for set/list/rebuild**

Append to `wine-tracker/tests/test_grapes.py`:

```python
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
```

Note: the `db` fixture comes from `conftest.py`. Verify it exposes a connection with `ref_grapes` seeded (it calls `init_db`); if `ref_grapes` is empty in the fixture DB, this test's ref assertions will fail — in that case seed is already handled by `init_db` in conftest.

- [ ] **Step 6: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_grapes.py -v`
Expected: FAIL with `AttributeError: module 'app.grapes' has no attribute 'set_wine_grapes'`.

- [ ] **Step 7: Implement set/list/rebuild**

Append to `wine-tracker/app/grapes.py`:

```python
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
    """Replace all grape rows for a wine. entries: [{"name", "pct"}]."""
    db.execute("DELETE FROM wine_grapes WHERE wine_id=?", (wine_id,))
    pos = 0
    seen = set()
    for e in entries or []:
        name = (str(e.get("name") or "")).strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        ref = reference.match_reference(db, "grape", name)
        grape_id = ref["id"] if ref else None
        db.execute(
            "INSERT INTO wine_grapes (wine_id, grape_id, name, pct, position) VALUES (?,?,?,?,?)",
            (wine_id, grape_id, name, _coerce_pct(e.get("pct")), pos))
        pos += 1
    rebuild_cache(db, wine_id)
    db.commit()


def list_wine_grapes(db, wine_id):
    rows = db.execute(
        """SELECT wg.name, wg.pct, wg.grape_id, wg.position, rg.color AS color
             FROM wine_grapes wg
             LEFT JOIN ref_grapes rg ON rg.id = wg.grape_id
            WHERE wg.wine_id=? ORDER BY wg.position""",
        (wine_id,)).fetchall()
    return [dict(r) for r in rows]
```

- [ ] **Step 8: Run tests to verify all pass**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_grapes.py -v`
Expected: PASS (all).

- [ ] **Step 9: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/grapes.py wine-tracker/tests/test_grapes.py
git commit -m "feat(grapes): wine_grapes module (table, set/list/rebuild, split_legacy)"
```

---

## Task 2: init_db-Wiring + einmaliges Backfill

**Files:**
- Modify: `wine-tracker/app/app.py:628-642` (init_db, nach dem purchases-Block)
- Modify: `wine-tracker/app/app.py` (Import-Block oben, `import grapes`)
- Test: `wine-tracker/tests/test_grapes.py`

**Interfaces:**
- Consumes: `grapes.create_wine_grapes_table`, `grapes.split_legacy`, `grapes.set_wine_grapes`, `reference.match_reference`.
- Produces: nach `init_db()` existiert `wine_grapes`, und jeder Alt-Wein mit `grape`-Text hat entsprechende Zeilen (pct NULL).

- [ ] **Step 1: Write the failing backfill test**

Append to `wine-tracker/tests/test_grapes.py`:

```python
def test_backfill_from_legacy_grape(db):
    # Insert a wine with a legacy blend string but no wine_grapes rows
    wid = _insert_wine(db, grape="Cabernet Sauvignon, Merlot")
    db.execute("DELETE FROM wine_grapes WHERE wine_id=?", (wid,))
    db.commit()
    from app import app as wine_app
    wine_app.backfill_wine_grapes(db)
    rows = grapes.list_wine_grapes(db, wid)
    assert [r["name"] for r in rows] == ["Cabernet Sauvignon", "Merlot"]
    assert all(r["pct"] is None for r in rows)


def test_backfill_is_idempotent(db):
    wid = _insert_wine(db, grape="Merlot")
    from app import app as wine_app
    wine_app.backfill_wine_grapes(db)
    wine_app.backfill_wine_grapes(db)  # second run must not duplicate
    assert len(grapes.list_wine_grapes(db, wid)) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_grapes.py -k backfill -v`
Expected: FAIL with `AttributeError: module 'app.app' has no attribute 'backfill_wine_grapes'`.

- [ ] **Step 3: Add `import grapes` and the backfill function**

In `wine-tracker/app/app.py`, add `import grapes` alongside `import purchases` (top import block).

Add this function just above `def init_db():` (near line 510):

```python
def backfill_wine_grapes(db):
    """One-time: populate wine_grapes from the legacy free-text grape column.

    Only touches wines that have no wine_grapes rows yet, so it is safe to run
    on every startup. Percentages are unknown for legacy data (left NULL).
    """
    wines = db.execute(
        "SELECT id, grape FROM wines WHERE grape IS NOT NULL AND grape != ''"
    ).fetchall()
    for w in wines:
        has = db.execute(
            "SELECT 1 FROM wine_grapes WHERE wine_id=? LIMIT 1", (w["id"],)).fetchone()
        if has:
            continue
        entries = [{"name": n, "pct": None} for n in grapes.split_legacy(w["grape"])]
        if entries:
            grapes.set_wine_grapes(db, w["id"], entries)
```

- [ ] **Step 4: Wire into init_db**

In `wine-tracker/app/app.py`, after the purchases block (after line 640, before `db.commit()` at 642), add:

```python
        # ── grape varieties (1-n + pct) + one-time backfill ────────────────
        grapes.create_wine_grapes_table(db)
        backfill_wine_grapes(db)
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_grapes.py -v`
Expected: PASS (all).

- [ ] **Step 6: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_grapes.py
git commit -m "feat(grapes): create table + one-time legacy backfill in init_db"
```

---

## Task 3: Save-Routen (add/edit) verarbeiten `grapes`-JSON

**Files:**
- Modify: `wine-tracker/app/app.py:959-995` (add-Route) und `:1090-1120` (edit-Route)
- Test: `wine-tracker/tests/test_routes.py`

**Interfaces:**
- Consumes: `grapes.set_wine_grapes`. Formfeld `grapes` = JSON-String `[{"name","pct"}]`.
- Produces: nach POST `/add` bzw. `/edit/<id>` sind die `wine_grapes`-Zeilen gesetzt und `wines.grape` ist der Cache. Wenn `grapes` fehlt/leer/unparsebar, aber das alte `grape`-Feld gesendet wird, fällt die Route auf `split_legacy(grape)` zurück (Abwärtskompatibilität für Alt-Clients/Tests).

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_routes.py`:

```python
import json


def test_add_wine_with_grapes_json(client, db):
    resp = client.post("/add", data={
        "name": "Blend Test", "type": "red", "region": "Bordeaux", "quantity": "1",
        "grapes": json.dumps([{"name": "Merlot", "pct": 70},
                              {"name": "Cabernet Franc", "pct": 30}]),
    }, follow_redirects=True)
    assert resp.status_code == 200
    wid = db.execute("SELECT id FROM wines WHERE name='Blend Test'").fetchone()[0]
    from app import grapes
    rows = grapes.list_wine_grapes(db, wid)
    assert [(r["name"], r["pct"]) for r in rows] == [("Merlot", 70), ("Cabernet Franc", 30)]
    # cache string kept in sync
    assert db.execute("SELECT grape FROM wines WHERE id=?", (wid,)).fetchone()[0] \
        == "Merlot, Cabernet Franc"


def test_add_wine_legacy_grape_fallback(client, db):
    resp = client.post("/add", data={
        "name": "Legacy Grape", "type": "red", "region": "Rioja", "quantity": "1",
        "grape": "Tempranillo, Garnacha",
    }, follow_redirects=True)
    assert resp.status_code == 200
    wid = db.execute("SELECT id FROM wines WHERE name='Legacy Grape'").fetchone()[0]
    from app import grapes
    assert [r["name"] for r in grapes.list_wine_grapes(db, wid)] == ["Tempranillo", "Garnacha"]
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_routes.py -k grapes -v`
Expected: FAIL — grapes rows empty (route ignores `grapes` field).

- [ ] **Step 3: Add a shared parse helper**

In `wine-tracker/app/app.py`, add near `backfill_wine_grapes`:

```python
def _grapes_from_form(form):
    """Return [{"name","pct"}] from the posted 'grapes' JSON, or fall back to
    splitting the legacy 'grape' text field. Bad JSON -> legacy fallback."""
    raw = (form.get("grapes") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [{"name": (e.get("name") or "").strip(), "pct": e.get("pct")}
                        for e in data if isinstance(e, dict)]
        except (json.JSONDecodeError, TypeError):
            pass
    return [{"name": n, "pct": None} for n in grapes.split_legacy(form.get("grape", ""))]
```

- [ ] **Step 4: Call it after insert in the add-route**

In the add-route, after `db.commit()` / `new_id = cur.lastrowid` (line ~993, before or after `images.sync_primary`), add:

```python
    grapes.set_wine_grapes(db, new_id, _grapes_from_form(request.form))
```

Note: `set_wine_grapes` rebuilds `wines.grape`, so the value inserted for the `grape` column in the INSERT statement (line 982) is now just an initial placeholder that gets overwritten. Leave the INSERT as-is (harmless), or pass `None`; overwrite is authoritative.

- [ ] **Step 5: Call it in the edit-route**

In the edit-route (after the `UPDATE wines ... WHERE id=?` executes and commits, around line 1120), add:

```python
    grapes.set_wine_grapes(db, wine_id, _grapes_from_form(request.form))
```

Use the correct wine-id variable name already in that route (verify it is `wine_id`).

- [ ] **Step 6: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_routes.py -k grapes -v`
Expected: PASS.

- [ ] **Step 7: Regression — run existing route tests**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_routes.py -v`
Expected: PASS (existing tests unaffected; legacy `grape` field still works via fallback).

- [ ] **Step 8: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_routes.py
git commit -m "feat(grapes): add/edit routes persist structured grapes + cache"
```

---

## Task 4: `grapes`-Array in `wine_json` und index-Context

**Files:**
- Modify: `wine-tracker/app/app.py:743-755` (`wine_json`)
- Modify: `wine-tracker/app/app.py:895` (index-Route, `wines`-Liste)
- Test: `wine-tracker/tests/test_api.py`

**Interfaces:**
- Consumes: `grapes.list_wine_grapes`.
- Produces: jedes serialisierte Wein-Dict enthält `grapes: [{"name","pct","color","grape_id","position"}]` in `position`-Reihenfolge.

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_api.py`:

```python
import json as _json


def test_wine_json_includes_grapes(client, db):
    client.post("/add", data={
        "name": "Api Blend", "type": "red", "region": "Bordeaux", "quantity": "1",
        "grapes": _json.dumps([{"name": "Merlot", "pct": 60},
                               {"name": "Cabernet Sauvignon", "pct": 40}]),
    }, follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Api Blend'").fetchone()[0]
    resp = client.get(f"/api/wine/{wid}")
    data = resp.get_json()
    grapes_out = data["grapes"]
    assert [(g["name"], g["pct"]) for g in grapes_out] == [("Merlot", 60), ("Cabernet Sauvignon", 40)]
    assert grapes_out[0]["color"] == "red"
```

Note: verify the single-wine API route path. If it is not `/api/wine/<id>`, grep for `wine_json(` callers and use the correct route. Adjust the URL accordingly.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_api.py -k grapes -v`
Expected: FAIL with `KeyError: 'grapes'`.

- [ ] **Step 3: Add grapes to `wine_json`**

In `wine_json` (after line 754, before `return d`):

```python
    d["grapes"] = grapes.list_wine_grapes(db, wine_id)
```

- [ ] **Step 4: Add grapes to the index wine list**

In the index route, after `wines = [dict(row) ...]` (line 895), add:

```python
    for w in wines:
        w["grapes"] = grapes.list_wine_grapes(db, w["id"])
```

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_api.py -k grapes -v`
Expected: PASS.

- [ ] **Step 6: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_api.py
git commit -m "feat(grapes): expose grapes array in wine_json + index context"
```

---

## Task 5: Datalist-Quelle `ref_grapes` + Reconcile akzeptiert Liste

**Files:**
- Modify: `wine-tracker/app/app.py:445-480` (Context-Builder, `used_grapes` → `ref_grape_names`)
- Modify: `wine-tracker/app/app.py:3487-3516` (`api_reference_reconcile`)
- Modify: `wine-tracker/app/templates/_wine_form_fields.html:54-58` (Datalist)
- Modify: `wine-tracker/app/static/filter-advanced.js:16` (Datalist-Referenz, falls nötig)
- Test: `wine-tracker/tests/test_api.py`

**Interfaces:**
- Produces: Context-Var `ref_grape_names` = sortierte Liste aller `ref_grapes.name`. Reconcile-Endpoint akzeptiert zusätzlich `grapes: [str, ...]` und liefert ein Item pro unbekannter Sorte (Feld `entity` = `"grape"`, `value` = die Sorte).

- [ ] **Step 1: Write the failing reconcile-list test**

Append to `wine-tracker/tests/test_api.py`:

```python
def test_reconcile_accepts_grape_list(client, db):
    # "Merlot" is known (built-in), "Zzz Unknown Grape" is not
    resp = client.post("/api/reference/reconcile", json={
        "grapes": ["Merlot", "Zzz Unknown Grape"]})
    data = resp.get_json()
    values = [it["value"] for it in data["items"] if it["entity"] == "grape"]
    assert "Zzz Unknown Grape" in values
    assert "Merlot" not in values  # known -> no reconcile item
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_api.py -k reconcile -v`
Expected: FAIL — only the singular `grape` field is handled, `grapes` list ignored.

- [ ] **Step 3: Extend the reconcile endpoint**

In `api_reference_reconcile` (line 3502 loop), replace the grape handling so both a singular `grape` and a `grapes` list are processed. After computing `country_code`, build the grape value list:

```python
    grape_values = []
    single = (body.get("grape") or "").strip()
    if single:
        grape_values.append(single)
    for g in (body.get("grapes") or []):
        gv = (str(g) or "").strip()
        if gv and gv not in grape_values:
            grape_values.append(gv)
```

Then change the loop to iterate regions (as before) plus each grape value. Concretely, keep the region branch, and replace the grape branch with a loop over `grape_values`:

```python
    for value in grape_values:
        if reference.match_reference(db, "grape", value):
            continue
        suggestions = [
            {"id": r["id"], "name": r["name"], "is_custom": r["is_custom"]}
            for r in reference.suggest_matches(db, "grape", value, None, limit=5)
        ]
        ai_pick = _ai_reconcile_pick(opts, "grape", value, [s["name"] for s in suggestions]) if ai_on else None
        items.append({"entity": "grape", "value": value, "country_code": None,
                      "suggestions": suggestions, "ai_pick": ai_pick})
```

Keep the existing region handling intact (still reads `body.get("region")`).

- [ ] **Step 4: Run reconcile test**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_api.py -k reconcile -v`
Expected: PASS.

- [ ] **Step 5: Add `ref_grape_names` to the context builder**

Find where `used_grapes` is built (line ~449). Add alongside it (do not remove `used_grapes` yet — other code may read it; remove only after confirming no references remain):

```python
        ctx["ref_grape_names"] = [
            r[0] for r in db.execute(
                "SELECT name FROM ref_grapes ORDER BY name").fetchall()
        ]
```

Also add the `setdefault` fallback near line 478:

```python
        ctx.setdefault("ref_grape_names", [])
```

- [ ] **Step 6: Point the form datalist at `ref_grape_names`**

In `wine-tracker/app/templates/_wine_form_fields.html`, change the datalist source (lines 54-58) from `used_grapes` to `ref_grape_names`:

```html
      <datalist id="grapeList">
        {% for g in ref_grape_names %}
        <option value="{{ g }}">
        {% endfor %}
      </datalist>
```

(The `#grapeList` datalist is reused by the row widget in Task 7 and by the advanced filter, so this single change updates all consumers.)

- [ ] **Step 7: Manual verification of datalist + regression**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_api.py wine-tracker/tests/test_routes.py -v`
Expected: PASS. (Datalist itself is visual — confirmed in Task 7's Playwright run.)

- [ ] **Step 8: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/app/templates/_wine_form_fields.html wine-tracker/tests/test_api.py
git commit -m "feat(grapes): ref_grapes datalist source + reconcile accepts grape list"
```

---

## Task 6: KI-Schema/Prompt + Vivino liefern Rebsortenliste

**Files:**
- Modify: `wine-tracker/app/app.py:2084` (`_wine_json_schema`/Prompt-`grape`-Feld) und `:2108-2112` (Prompt-Regeln)
- Modify: `wine-tracker/app/app.py:2215-2241` (Vivino grape-Mapping — Ergebnis als Liste)
- Test: `wine-tracker/tests/test_api.py` (oder `test_helpers.py`)

**Interfaces:**
- Produces: KI-Response-Schema erlaubt `grapes: [{"name", "pct"}]` zusätzlich zum bestehenden `grape`-String. Vivino-Suchergebnis (`vivino_search` result dict) enthält `grapes: [str]` (Namen), zusätzlich zum bestehenden `grape`-String.

- [ ] **Step 1: Write the failing Vivino-grapes test**

Vivino requires network; test the pure mapping helper instead. If the grape-id→names join is inline, extract it into a helper `_grape_names_from_ids(grape_map, ids) -> list[str]` first. Append to `wine-tracker/tests/test_helpers.py`:

```python
def test_grape_names_from_ids():
    from app import app as wine_app
    gmap = {1: "Merlot", 2: "Cabernet Sauvignon"}
    assert wine_app._grape_names_from_ids(gmap, [1, 2, 99]) == ["Merlot", "Cabernet Sauvignon"]
    assert wine_app._grape_names_from_ids(gmap, []) == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_helpers.py -k grape_names -v`
Expected: FAIL with `AttributeError: ... '_grape_names_from_ids'`.

- [ ] **Step 3: Extract/implement the helper and use it in vivino_search**

In `wine-tracker/app/app.py`, add near `_get_grape_map` (line ~2215):

```python
def _grape_names_from_ids(grape_map, ids):
    """Map Vivino grape ids to names, dropping unknown ids, preserving order."""
    out = []
    for gid in ids or []:
        name = grape_map.get(gid)
        if name:
            out.append(name)
    return out
```

In `vivino_search`, where the result dict is assembled (the `results.append({...})` near line 2399 that already includes `wine_name`/`winery`), add:

```python
            "grapes": grape_names,          # list[str]
```

where `grape_names = _grape_names_from_ids(grape_map, grape_ids)` is computed from the record's grape ids (use the existing grape-id extraction; if the code currently joins them into the `grape` string, compute `grape_names` from the same ids). Keep the existing `grape` string field for compatibility.

- [ ] **Step 4: Run the helper test**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_helpers.py -k grape_names -v`
Expected: PASS.

- [ ] **Step 5: Extend the AI JSON schema + prompt for `grapes`**

In `_wine_json_schema()` (line ~2477 area) add a `grapes` array property alongside `grape`:

```python
        "grapes": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "pct": {"type": ["number", "null"]},
                },
                "required": ["name"],
            },
        },
```

In the prompt rules (near line 2084 field list and 2108 rules), add a line:

```
- grapes: array of the grape varieties. Each item: name plus pct (0-100) if the
  blend proportions are known, otherwise pct null. For a single-varietal wine,
  return one item. Keep the legacy "grape" field as a comma-joined summary.
```

- [ ] **Step 6: Run the AI schema tests (regression)**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_helpers.py wine-tracker/tests/test_api.py -v`
Expected: PASS. (No live AI call — schema is a dict; existing tests must stay green.)

- [ ] **Step 7: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_helpers.py
git commit -m "feat(grapes): AI schema grapes[] + Vivino grape names list"
```

---

## Task 7: Editor-Zeilen-Widget (Formular + Modal-JS)

**Files:**
- Modify: `wine-tracker/app/templates/_wine_form_fields.html:51-59` (Grape-Feld → Widget)
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (Zeilen-JS, Befüllung, Serialisierung, Reconcile, AI/Vivino-Sonderfall)
- Modify: `wine-tracker/app/static/style.css` (Widget + Chips + Farbpunkte)
- Modify: `wine-tracker/app/translations.py` (neue Keys ×7)
- Verify: Playwright-Skript im Scratchpad

**Interfaces:**
- Consumes: `#grapeList` datalist (Task 5); `wine.grapes` array (Task 4); AI `fields.grapes`; Vivino `item.grapes`; `/api/reference/reconcile` mit `grapes`-Liste (Task 5).
- Produces: verstecktes `<input name="grapes">`, serialisiert aus den Zeilen bei Submit; JS-Funktionen `grapeAddRow(name, pct)`, `grapeClearRows()`, `grapeSetRows(list)`, `grapeCollect()` (→ `[{name,pct}]`), `grapeSerialize()` (schreibt Hidden-Feld), `grapeUpdateSum()` (Hinweis + Chip-Farbe).

- [ ] **Step 1: Add translation keys (7 languages)**

In `wine-tracker/app/translations.py`, add to each language block (near `label_grape`):

```python
    "grapes_add": "+ Rebsorte",            # add-btn (localize per language)
    "grapes_remove": "Entfernen",
    "grapes_pct": "%",
    "grapes_sum": "Summe",                 # prefix for "Summe: 90 %"
```

Localized strings per language:
- de: `+ Rebsorte` / `Entfernen` / `%` / `Summe`
- en: `+ Grape` / `Remove` / `%` / `Sum`
- fr: `+ Cépage` / `Retirer` / `%` / `Somme`
- it: `+ Vitigno` / `Rimuovi` / `%` / `Somma`
- es: `+ Uva` / `Quitar` / `%` / `Suma`
- pt: `+ Casta` / `Remover` / `%` / `Soma`
- nl: `+ Druif` / `Verwijderen` / `%` / `Som`

- [ ] **Step 2: Replace the single grape input with the row widget**

In `wine-tracker/app/templates/_wine_form_fields.html`, replace lines 51-59 (the grape `<div>`) with:

```html
    <div>
      <label>{{ t.label_grape }}</label>
      <div id="grapeRows" class="grape-rows"></div>
      <div class="grape-rows-foot">
        <button type="button" class="btn-cancel grape-add" onclick="grapeAddRow()">{{ t.grapes_add }}</button>
        <span id="grapeSum" class="grape-sum"></span>
      </div>
      <input type="hidden" name="grapes" id="wine_grapes_json">
      <datalist id="grapeList">
        {% for g in ref_grape_names %}
        <option value="{{ g }}">
        {% endfor %}
      </datalist>
    </div>
```

Keep a hidden legacy input so nothing else breaks (some JS still reads `#wine_grape`):

```html
      <input type="hidden" name="grape" id="wine_grape">
```

Place the hidden `#wine_grape` inside the same div. Task 7 JS keeps it in sync (comma-joined) for any legacy reader; the route prefers the `grapes` JSON.

- [ ] **Step 3: Add the row-widget JS**

In `wine-tracker/app/templates/_wine_edit_modal.html`, add a self-contained block (near the other form helpers). Uses `T` (translations) and `INGRESS` already present:

```javascript
// ── Grape rows widget ────────────────────────────────────────────────────────
function _grapeColorClass(name) {
  // resolve color from the ref datalist is not available client-side; color is
  // applied from server data in grapeSetRows. Manual rows default to neutral.
  return 'grape-neutral';
}

function grapeRowHtml(name, pct, colorClass) {
  var esc = function(s){ return (s||'').replace(/"/g,'&quot;'); };
  return '<div class="grape-row ' + (colorClass || 'grape-neutral') + '">' +
    '<span class="grape-dot"></span>' +
    '<input type="text" class="grape-name" list="grapeList" value="' + esc(name) +
      '" oninput="grapeUpdateSum()" autocomplete="off">' +
    '<input type="number" class="grape-pct" min="0" max="100" step="1" value="' +
      (pct === null || pct === undefined ? '' : pct) + '" oninput="grapeUpdateSum()">' +
    '<span class="grape-pct-sign">' + (T.grapes_pct || '%') + '</span>' +
    '<button type="button" class="grape-del" onclick="grapeDelRow(this)">&times;</button>' +
  '</div>';
}

function grapeAddRow(name, pct, colorClass) {
  var box = document.getElementById('grapeRows');
  box.insertAdjacentHTML('beforeend', grapeRowHtml(name || '', pct, colorClass));
  grapeUpdateSum();
}

function grapeDelRow(btn) {
  var row = btn.closest('.grape-row');
  if (row) row.remove();
  grapeUpdateSum();
}

function grapeClearRows() {
  document.getElementById('grapeRows').innerHTML = '';
}

function grapeSetRows(list) {
  grapeClearRows();
  (list || []).forEach(function(g) {
    var cls = g.color === 'red' ? 'grape-red'
            : g.color === 'white' ? 'grape-white' : 'grape-neutral';
    grapeAddRow(g.name, (g.pct === null || g.pct === undefined) ? undefined : g.pct, cls);
  });
  if (!(list && list.length)) grapeUpdateSum();
}

function grapeCollect() {
  var out = [];
  document.querySelectorAll('#grapeRows .grape-row').forEach(function(row) {
    var name = row.querySelector('.grape-name').value.trim();
    if (!name) return;
    var pv = row.querySelector('.grape-pct').value;
    out.push({ name: name, pct: pv === '' ? null : Number(pv) });
  });
  return out;
}

function grapeSerialize() {
  var list = grapeCollect();
  document.getElementById('wine_grapes_json').value = JSON.stringify(list);
  var legacy = document.getElementById('wine_grape');
  if (legacy) legacy.value = list.map(function(g){ return g.name; }).join(', ');
}

function grapeUpdateSum() {
  var list = grapeCollect();
  var sum = list.reduce(function(a, g){ return a + (g.pct || 0); }, 0);
  var el = document.getElementById('grapeSum');
  if (el) el.textContent = list.length ? ((T.grapes_sum || 'Sum') + ': ' + sum + ' %') : '';
}
```

- [ ] **Step 4: Populate rows when opening a wine**

In `openWineModal` (line ~508), where other fields are filled from `wine`/`w`, replace any `wine_grape.value = ...` with:

```javascript
  grapeSetRows(w.grapes || []);
```

If `w.grapes` is absent (e.g. old cached object), fall back:

```javascript
  if (!w.grapes && w.grape) grapeSetRows(grapesFromLegacy(w.grape));
```

Add the tiny helper near the widget:

```javascript
function grapesFromLegacy(text) {
  return (text || '').split(/[,&/+]/).map(function(s){ return s.trim(); })
    .filter(Boolean).map(function(n){ return { name: n, pct: null }; });
}
```

Also ensure "add wine" (empty modal) starts with zero rows: in the code path that resets the form for a new wine, call `grapeClearRows(); grapeUpdateSum();`.

- [ ] **Step 5: Populate rows from AI scan/reanalyze**

In `populateFormFromAi` (line 930), replace the single-grape line (`if (fields.grape) ... wine_grape ...`) with:

```javascript
  if (fields.grapes && fields.grapes.length) {
    grapeSetRows(fields.grapes.map(function(g){ return { name: g.name, pct: g.pct }; }));
  } else if (fields.grape) {
    grapeSetRows(grapesFromLegacy(fields.grape));
  }
```

In the AI reconcile dialog apply path (`applyAiReload`) and the `_AR_FIELDS` handling: grape becomes a list field. Simplest robust approach — when the AI returns `grapes`, treat it like the initial populate (overwrite rows) rather than a single-field diff. Add to `applyAiReload` after the per-field loop:

```javascript
  if (_arPending && _arPending.fields && _arPending.fields.grapes &&
      document.getElementById('arGrapes') && document.getElementById('arGrapes').checked) {
    grapeSetRows(_arPending.fields.grapes.map(function(g){ return {name:g.name, pct:g.pct}; }));
  }
```

And render an `arGrapes` checkbox row in `renderAiReload` when `fields.grapes` differ from current `grapeCollect()` (compare by joined names). Keep it opt-in like other AI changes.

- [ ] **Step 6: Populate rows from Vivino reconcile**

In `_VR_FIELDS` (line 1174) remove the plain `grape` text entry and handle grapes as a list side-effect. In `vrConfirm` (after applying the checkbox field changes, before `_vrApplySideEffects`), add:

```javascript
  if (_vrSelected && _vrSelected.grapes && _vrSelected.grapes.length) {
    var vgChk = document.getElementById('vrGrapesChk');
    if (!vgChk || vgChk.checked) {
      grapeSetRows(_vrSelected.grapes.map(function(n){ return { name: n, pct: null }; }));
    }
  }
```

In `vrComputeChanges`/`vrSelectCandidate` step-2 rendering, add a "Rebsorten"-row with checkbox `vrGrapesChk` (checked) when `item.grapes` differ from the current `grapeCollect()` names. Show old (current joined) → new (Vivino joined).

- [ ] **Step 7: Serialize + reconcile on submit**

In `reconcileThenSubmit` (line 1661), before building the reconcile request, call `grapeSerialize()` so the hidden field is current, and include all grape names in the reconcile payload:

```javascript
  grapeSerialize();
  var grapeNames = grapeCollect().map(function(g){ return g.name; });
```

Add `grapes: grapeNames` to the JSON body sent to `/api/reference/reconcile` (alongside the existing region/country). The existing reconcile UI loop already renders one entry per returned item; grape items now include each unknown blend member.

Ensure the plain form-submit handler (line 1631) also calls `grapeSerialize()` before submit (add it at the top of the submit listener) so the hidden `grapes` field is always populated even when reconcile finds nothing.

- [ ] **Step 8: Add CSS**

In `wine-tracker/app/static/style.css`, add:

```css
.grape-rows { display: flex; flex-direction: column; gap: 6px; }
.grape-row { display: flex; align-items: center; gap: 6px; }
.grape-row .grape-name { flex: 1 1 auto; }
.grape-row .grape-pct { width: 64px; }
.grape-pct-sign { opacity: .6; }
.grape-del { background: none; border: none; cursor: pointer; font-size: 1.1rem; opacity: .6; }
.grape-del:hover { opacity: 1; }
.grape-rows-foot { display: flex; align-items: center; justify-content: space-between; margin-top: 6px; }
.grape-sum { font-size: .85rem; opacity: .7; }
.grape-dot { width: 10px; height: 10px; border-radius: 50%; background: var(--border, #ccc); flex: 0 0 auto; }
.grape-red   .grape-dot { background: #7b1e2b; }
.grape-white .grape-dot { background: #d9b44a; }
.grape-neutral .grape-dot { background: #9aa0a6; }
```

- [ ] **Step 9: Playwright verification (widget behaviour)**

Kill stale servers on 5050, start a fresh server, then run a scratchpad script that:
1. Opens the add-wine modal, adds two grape rows (`grapeAddRow('Merlot',60)`, `grapeAddRow('Cabernet',40)`), asserts `#grapeSum` shows `100 %`.
2. Calls `grapeSerialize()` and asserts `#wine_grapes_json` value parses to the two entries and `#wine_grape` = `"Merlot, Cabernet"`.
3. Calls `grapeSetRows([{name:'Syrah',pct:null,color:'red'}])` and asserts one row, red dot class present.
4. Asserts no `pageerror`.

Server prep (PowerShell): stop any process on 5050, then `./.venv/Scripts/python.exe wine-tracker/app/app.py` in background; wait for HTTP 200.

Expected: all asserts pass, no JS errors. Stop the server afterwards.

- [ ] **Step 10: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/templates/_wine_form_fields.html wine-tracker/app/templates/_wine_edit_modal.html wine-tracker/app/static/style.css wine-tracker/app/translations.py
git commit -m "feat(grapes): multi-row grape editor with pct, reconcile, AI/Vivino population"
```

---

## Task 8: Anzeige — Karte/Tabelle „+N" + Detail-Liste

**Files:**
- Modify: `wine-tracker/app/templates/index.html` (Zeilen 112, 151, 327/354, 463/538, 783, 1054, 1189, 1310, 1371, 1441)
- Modify: `wine-tracker/app/templates/stats.html:571`, `chat.html:243` (Detail)
- Verify: Playwright-Skript im Scratchpad

**Interfaces:**
- Consumes: `w.grapes` / `d.grapes` array (Task 4); `wine.grapes` in JS objects.
- Produces: kompakte „führende + N"-Anzeige und volle Detail-Liste. Helper `grapeLead(grapes)` (JS) und ein Jinja-Makro für server-seitige Karten.

- [ ] **Step 1: Add a JS lead/label helper**

In `wine-tracker/app/templates/index.html` (script section, near other helpers), add:

```javascript
function grapeLead(list) {
  // list: [{name, pct}]. Returns "Merlot +2" (lead by pct, then order).
  if (!list || !list.length) return '';
  var sorted = list.slice().sort(function(a, b) {
    return (b.pct || 0) - (a.pct || 0);
  });
  var lead = sorted[0].name;
  return list.length > 1 ? (lead + ' +' + (list.length - 1)) : lead;
}

function grapeDetailHtml(list) {
  if (!list || !list.length) return '';
  return list.map(function(g) {
    var cls = g.color === 'red' ? 'grape-red' : g.color === 'white' ? 'grape-white' : 'grape-neutral';
    var pct = (g.pct === null || g.pct === undefined) ? '' : ' ' + g.pct + ' %';
    return '<span class="grape-chip ' + cls + '"><span class="grape-dot"></span>' +
      escapeHtml(g.name) + pct + '</span>';
  }).join(' ');
}
```

- [ ] **Step 2: Update JS card render (renderCard)**

At line 1310, replace the single-grape span with the lead label using `w.grapes`:

```javascript
  var lead = grapeLead(w.grapes);
  if (lead) extra += '<span><i class="mdi mdi-fruit-grapes"></i> ' + escapeHtml(lead) + '</span>';
```

At line 1371 keep `card.dataset.grape = w.grape || '';` (cache string powers search). At line 783 keep `grape: d.grape` and add `grapes: d.grapes || []` to the JS wine object built from server data so re-rendered cards have the array.

- [ ] **Step 3: Update the server-side Jinja card (initial render)**

At line 151, replace the single-grape span with a lead computation. Add a Jinja helper macro at the top of `index.html`:

```jinja
{% macro grape_lead(gs) %}{% if gs %}{{ gs[0].name }}{% if gs|length > 1 %} +{{ gs|length - 1 }}{% endif %}{% endif %}{% endmacro %}
```

Then line 151 becomes:

```jinja
        {% if w['grapes'] %}<span><i class="mdi mdi-fruit-grapes"></i> {{ grape_lead(w['grapes']) }}</span>{% endif %}
```

(For the server macro, lead = first by `position`; the JS path sorts by pct. Acceptable minor difference; both show lead + N. If exact parity is wanted, sort `w['grapes']` by pct in the index context in Task 4 — note this in Task 8 Step 6 verification.)

Keep `data-grape="{{ w['grape'] or '' }}"` at line 112 (search).

- [ ] **Step 4: Update the table column**

At line 327 keep the header. At line 354 replace the cell to show the lead:

```javascript
      + '<td class="col-grape">' + escapeHtml(grapeLead(d.grapes) || (d.grape || '')) + '</td>'
```

Ensure the table row objects include `grapes` (they come from the same `d` used for cards — verify `d.grapes` is present; if the table uses a separate data source, add `grapes` there too).

- [ ] **Step 5: Update detail views (index/stats/chat)**

At `index.html:1054`, replace:

```javascript
  if (w.grapes && w.grapes.length) details += viewRow('mdi-fruit-grapes', T.label_grape || 'Grape', grapeDetailHtml(w.grapes));
  else if (w.grape) details += viewRow('mdi-fruit-grapes', T.label_grape || 'Grape', w.grape);
```

Do the same at `stats.html:571` and `chat.html:243`. Both templates need the `grapeDetailHtml` helper — add it to each (or a shared script include). If `viewRow` HTML-escapes its value, pass a variant that allows the chip HTML (check `viewRow`'s implementation; if it escapes, add a `viewRowHtml` that does not, used only for grapes).

- [ ] **Step 6: Keep viewChangeQty payload intact**

At line 1189 and 1441, the quantity-change POST sends `['grape', w.grape]`. Since `grape` is now a derived cache, sending it back would be overwritten by `set_wine_grapes` fallback — but `viewChangeQty` must NOT change grapes. Ensure the quantity POST does NOT include a `grapes` field (so the edit route, when `grapes` is absent AND `grape` present, would fall back and rebuild from the cache string — which is lossless for names but DROPS percentages).

To avoid losing percentages on a quantity change, the edit route must skip grape processing when the request omits BOTH `grapes` and an explicit grape edit. Implement: in Task 3's edit-route call, guard it:

```python
    if "grapes" in request.form or "grape" in request.form:
        grapes.set_wine_grapes(db, wine_id, _grapes_from_form(request.form))
```

And in `viewChangeQty` (index.html:1189) remove `['grape', w.grape]` from the payload so neither key is sent. Add this change here in Task 8.

- [ ] **Step 7: Add chip CSS**

In `style.css`:

```css
.grape-chip { display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px;
  border-radius: 12px; background: var(--surface, #f2f2f2); font-size: .85rem; margin: 2px 2px 0 0; }
```

- [ ] **Step 8: Playwright verification (display)**

Fresh server; scratchpad script:
1. Seed a wine via `/add` with `grapes` = Merlot 60 / Cabernet 40 (POST).
2. Load `/`, assert the card shows `Merlot +1`.
3. Open the detail view for that wine, assert two `.grape-chip` elements with `60 %` and `40 %`.
4. Trigger `viewChangeQty(+1)`, reload, assert grapes unchanged (still 60/40, percentages preserved).
5. No `pageerror`.

Expected: all pass. Stop server afterwards.

- [ ] **Step 9: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/templates/index.html wine-tracker/app/templates/stats.html wine-tracker/app/templates/chat.html wine-tracker/app/static/style.css wine-tracker/app/app.py
git commit -m "feat(grapes): lead+N cards/table, chip detail view, preserve pct on qty change"
```

---

## Task 9: Export / Import mit `grapes`

**Files:**
- Modify: `wine-tracker/app/export_import.py` (Export-Serialisierung + Import-Anwendung)
- Test: `wine-tracker/tests/test_export_import.py`

**Interfaces:**
- Consumes: `grapes.list_wine_grapes`, `grapes.set_wine_grapes`.
- Produces: Export enthält je Wein `grapes: [{"name","pct"}]`; Import ruft `set_wine_grapes`, sonst Fallback auf `grape`-String (Alt-Dateien).

- [ ] **Step 1: Write the failing roundtrip test**

Append to `wine-tracker/tests/test_export_import.py`:

```python
import json


def test_export_import_grapes_roundtrip(client, db, tmp_path):
    client.post("/add", data={
        "name": "RT Blend", "type": "red", "region": "Bordeaux", "quantity": "1",
        "grapes": json.dumps([{"name": "Merlot", "pct": 60}, {"name": "Cabernet Sauvignon", "pct": 40}]),
    }, follow_redirects=True)

    from app import export_import, grapes
    payload = export_import.build_export(db)          # verify actual export fn name
    wine = next(w for w in payload["wines"] if w["name"] == "RT Blend")
    assert [(g["name"], g["pct"]) for g in wine["grapes"]] == [("Merlot", 60), ("Cabernet Sauvignon", 40)]

    # wipe grapes, re-import
    db.execute("DELETE FROM wine_grapes"); db.commit()
    export_import.apply_import(db, payload)            # verify actual import fn name/signature
    wid = db.execute("SELECT id FROM wines WHERE name='RT Blend'").fetchone()[0]
    assert [(g["name"], g["pct"]) for g in grapes.list_wine_grapes(db, wid)] \
        == [("Merlot", 60), ("Cabernet Sauvignon", 40)]


def test_import_legacy_without_grapes(client, db):
    from app import export_import, grapes
    payload = {"wines": [{"name": "Legacy Imp", "type": "red", "region": "Rioja",
                          "quantity": 1, "grape": "Tempranillo, Garnacha"}]}
    export_import.apply_import(db, payload)
    wid = db.execute("SELECT id FROM wines WHERE name='Legacy Imp'").fetchone()[0]
    assert [g["name"] for g in grapes.list_wine_grapes(db, wid)] == ["Tempranillo", "Garnacha"]
```

Note: read `export_import.py` first and replace `build_export`/`apply_import` with the real function names/signatures.

- [ ] **Step 2: Run to verify failure**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_export_import.py -k grapes -v`
Expected: FAIL — export lacks `grapes`; import ignores it.

- [ ] **Step 3: Add grapes to export**

In `export_import.py`, where each wine dict is serialized for export, add:

```python
        wine_dict["grapes"] = grapes.list_wine_grapes(db, wine_row["id"])
```

Add `import grapes` at the top. Keep `grape` in `WINE_COLUMNS` (the cache string still exports).

- [ ] **Step 4: Add grapes to import apply**

In `apply_import`, after a wine row is inserted and its new id is known, add:

```python
        if isinstance(w.get("grapes"), list) and w["grapes"]:
            grapes.set_wine_grapes(db, new_wine_id, w["grapes"])
        elif w.get("grape"):
            grapes.set_wine_grapes(
                db, new_wine_id, [{"name": n, "pct": None} for n in grapes.split_legacy(w["grape"])])
```

Use the correct new-id variable from the surrounding code.

- [ ] **Step 5: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_export_import.py -k grapes -v`
Expected: PASS.

- [ ] **Step 6: Regression — export/import suite**

Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests/test_export_import.py -v`
Expected: PASS.

- [ ] **Step 7: Commit** *(only with user go-ahead)*

```bash
git add wine-tracker/app/export_import.py wine-tracker/tests/test_export_import.py
git commit -m "feat(grapes): export/import structured grapes with legacy fallback"
```

---

## Task 10: Release 1.14.0

**Files:**
- Modify: `wine-tracker/config.yaml:3` (`version: "1.14.0"`)
- Modify: `wine-tracker/app/app.py` (`APP_VERSION = "1.14.0"`)
- Modify: `wine-tracker/CHANGELOG.md` (deutsch) und Root `CHANGELOG.md`

**Interfaces:** keine Code-Schnittstellen; reiner Release-Schritt.

- [ ] **Step 1: Ask before the full test suite, then run it**

Ask the user for go-ahead to run the full suite (per Global Constraints). On approval:
Run: `.venv\Scripts\python.exe -m pytest wine-tracker/tests -q`
Expected: all green (existing ~441 + new grape tests).

- [ ] **Step 2: Bump version in two code locations**

Set `wine-tracker/config.yaml` line 3 to `version: "1.14.0"` and `APP_VERSION = "1.14.0"` in `app.py`.

- [ ] **Step 3: Update BOTH changelogs**

Add a `1.14.0` entry to `wine-tracker/CHANGELOG.md` (deutsch) and root `CHANGELOG.md`, describing: Rebsorten als 1‑n mit optionalen Prozenten, farbige Chips, KI/Vivino-Rebsortenlisten, Reconcile pro Sorte, Export/Import, automatische Migration bestehender Rebsorten.

- [ ] **Step 4: Commit + push** *(only with explicit user go-ahead)*

```bash
git add wine-tracker/config.yaml wine-tracker/app/app.py wine-tracker/CHANGELOG.md CHANGELOG.md
git commit -m "Release 1.14.0: grape varieties 1-n with percentages"
git push origin <branch>
```

---

## Self-Review

**1. Spec coverage:**
- Datenmodell `wine_grapes` + FK → Task 1. B2-Cache → Task 1 (`rebuild_cache`) + Task 3. ✅
- Migration/Backfill → Task 2. ✅
- Save-Routen → Task 3. ✅
- `grapes`-Array in wine_json/Context → Task 4. ✅
- Datalist-Quelle `ref_grapes` → Task 5. Reconcile-Liste → Task 5. ✅
- KI-Schema/Prompt + Vivino-Liste → Task 6. ✅
- Editor-Widget + Farb-Chips + Reconcile pro Sorte + AI/Vivino-Befüllung → Task 7. ✅
- Anzeige Karte/Tabelle „+N" + Detail-Liste (index/stats/chat) → Task 8. ✅
- pct-Erhalt bei Mengenänderung → Task 8 Step 6 (+ edit-route Guard). ✅
- Export/Import → Task 9. ✅
- translations ×7 → Task 7 Step 1. ✅
- CSS → Task 7 Step 8 + Task 8 Step 7. ✅
- Edge Cases (unparsebares JSON, Dedup, pct-Range, leere Liste, Cascade, grape_id NULL) → `_grapes_from_form` (Task 3), `set_wine_grapes`/`_coerce_pct` (Task 1), Cascade (Task 1 DDL). ✅
- Release 1.14.0 + beide Changelogs → Task 10. ✅

**2. Placeholder scan:** Keine TBD/TODO. Alle Code-Schritte enthalten echten Code. Stellen, an denen Funktionsnamen/-signaturen zu verifizieren sind (`export_import.build_export`/`apply_import`, single-wine API-Route, Vivino grape-id-Extraktion, edit-route wine-id-Variable), sind explizit als „verify" markiert statt geraten — bewusst, weil diese Namen vor Ort geprüft werden müssen.

**3. Type consistency:**
- `set_wine_grapes(db, wine_id, entries=[{name, pct}])` — konsistent in Task 1/2/3/9. ✅
- `list_wine_grapes` → `[{name, pct, color, grape_id, position}]` — konsistent in Task 4/7/8/9. ✅
- JS: `grapeAddRow/grapeSetRows/grapeCollect/grapeSerialize/grapeUpdateSum/grapeLead/grapeDetailHtml/grapesFromLegacy` — konsistent zwischen Task 7 und 8. ✅
- Hidden field `#wine_grapes_json` (name `grapes`) + Legacy `#wine_grape` (name `grape`) — konsistent Task 5/7. ✅
- `_grapes_from_form` liest `grapes` dann `grape` — konsistent mit Editor-Serialisierung. ✅
```
