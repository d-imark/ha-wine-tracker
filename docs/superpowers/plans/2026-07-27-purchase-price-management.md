# Einkaufs-Preisverwaltung Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** KI-Preis vom eigenen Preis trennen; eigene Einkäufe (Datum/Menge/Stückpreis/Ort) als Posten verwalten; `wines.price` wird zum gecachten, mengengewichteten Ø dieser Einkäufe.

**Architecture:** Neue Tabelle `wine_purchases` (entkoppelt vom Bestand) + Modul `purchases.py`; REST-CRUD unter `/api/wine/<id>/purchases`; `wines.ai_price` neu (KI/Info); eigener Frontend-Dialog „Einkäufe verwalten" aus Bearbeiten + Detail. Spec: `docs/superpowers/specs/2026-07-27-purchase-price-management-design.md`.

**Tech Stack:** Flask + sqlite3, pytest, Playwright (System-Chrome). Muster wie `wine-tracker/app/images.py`.

## Global Constraints

- Einkäufe sind reine Kostensätze; `wines.quantity` (Bestand) bleibt unberührt.
- `wines.price` = `round(Σ(quantity×unit_price)/Σ(quantity), 2)` oder `NULL`; nach jeder Posten-Änderung serverseitig neu berechnet. Bestehende Statistik-Queries bleiben unverändert.
- `ai_price` ist informativ; **nicht** in Wert-Statistiken.
- Alle neuen Nutzertexte in 7 Sprachen (de,en,fr,it,es,pt,nl).
- Bestehende Tests bleiben grün.
- Kein `git commit` ohne ausdrückliche Freigabe des Nutzers.

---

### Task 1: DB-Migration + `purchases.py` (Modell)

**Files:**
- Create: `wine-tracker/app/purchases.py`
- Modify: `wine-tracker/app/app.py` (`init_db`)
- Test: `wine-tracker/tests/test_purchases.py`

**Interfaces:**
- Produces:
  - `purchases.create_purchases_table(db)`
  - `purchases.weighted_average(db, wine_id) -> dict {avg, total_qty, total_spent}`
  - `purchases.recompute_wine_price(db, wine_id)` (setzt `wines.price`)
  - `purchases.list_purchases(db, wine_id) -> list[dict]`
  - `purchases.add_purchase(db, wine_id, data) -> int` (pid)
  - `purchases.update_purchase(db, pid, data) -> bool`
  - `purchases.delete_purchase(db, pid) -> bool`

- [ ] **Step 1: Failing test (Ø + recompute)**

`wine-tracker/tests/test_purchases.py`:
```python
import os, sys, sqlite3
APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, APP_DIR)
import purchases

def _db():
    db = sqlite3.connect(":memory:"); db.row_factory = sqlite3.Row
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
    assert wa["total_spent"] == 70
    assert wa["avg"] == 16.0
    assert db.execute("SELECT price FROM wines WHERE id=1").fetchone()[0] == 16.0

def test_delete_recomputes_and_nulls():
    db = _db()
    p1 = purchases.add_purchase(db, 1, {"quantity": 1, "unit_price": 5})
    purchases.delete_purchase(db, p1)
    assert db.execute("SELECT price FROM wines WHERE id=1").fetchone()[0] is None
    assert purchases.list_purchases(db, 1) == []
```

- [ ] **Step 2: Run (fail)** — `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_purchases.py -q` → ImportError/fail.

- [ ] **Step 3: Implement `purchases.py`**
```python
"""Purchase lots per wine (cost records; decoupled from stock quantity)."""
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
    q = int(data.get("quantity") or 0)
    if q <= 0:
        raise ValueError("quantity_must_be_positive")
    up = float(data.get("unit_price") or 0)
    if up < 0:
        raise ValueError("price_must_be_non_negative")
    date = (data.get("purchase_date") or "").strip() or None
    loc = (data.get("location") or "").strip() or None
    note = (data.get("note") or "").strip() or None
    return q, up, date, loc, note


def weighted_average(db, wine_id):
    row = db.execute(
        "SELECT COALESCE(SUM(quantity),0) q, COALESCE(SUM(quantity*unit_price),0) s "
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
        "FROM wine_purchases WHERE wine_id=? ORDER BY COALESCE(purchase_date,''), id", (wine_id,)
    ).fetchall()
    return [dict(r) for r in rows]


def add_purchase(db, wine_id, data):
    q, up, date, loc, note = _coerce(data)
    cur = db.execute(
        "INSERT INTO wine_purchases (wine_id, purchase_date, quantity, unit_price, location, note, created) "
        "VALUES (?,?,?,?,?,?,?)",
        (wine_id, date, q, up, loc, note, datetime.now().isoformat()))
    db.commit()
    recompute_wine_price(db, wine_id); db.commit()
    return cur.lastrowid


def update_purchase(db, pid, data):
    row = db.execute("SELECT wine_id FROM wine_purchases WHERE id=?", (pid,)).fetchone()
    if not row:
        return False
    q, up, date, loc, note = _coerce(data)
    db.execute("UPDATE wine_purchases SET purchase_date=?, quantity=?, unit_price=?, location=?, note=? WHERE id=?",
               (date, q, up, loc, note, pid))
    db.commit()
    recompute_wine_price(db, row[0]); db.commit()
    return True


def delete_purchase(db, pid):
    row = db.execute("SELECT wine_id FROM wine_purchases WHERE id=?", (pid,)).fetchone()
    if not row:
        return False
    db.execute("DELETE FROM wine_purchases WHERE id=?", (pid,))
    db.commit()
    recompute_wine_price(db, row[0]); db.commit()
    return True
```

- [ ] **Step 4: Run (pass)** — `pytest tests/test_purchases.py -q` → 2 passed.

- [ ] **Step 5: init_db — ai_price + Tabelle + Backfill**

In `app.py` `init_db()`: in `migrations`-Dict `"ai_price": "REAL"` ergänzen. Nach `images.migrate_legacy_images(db)` einfügen:
```python
        # ── purchase lots + one-time price backfill ───────────────────────
        purchases.create_purchases_table(db)
        has_purchases = db.execute("SELECT COUNT(*) FROM wine_purchases").fetchone()[0]
        if has_purchases == 0:
            for w in db.execute("SELECT id, price, quantity, purchased_at FROM wines "
                                 "WHERE price IS NOT NULL AND price > 0").fetchall():
                db.execute(
                    "INSERT INTO wine_purchases (wine_id, purchase_date, quantity, unit_price, location, note, created) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (w["id"], None, max(w["quantity"] or 1, 1), w["price"],
                     w["purchased_at"], "Migriert", datetime.now().isoformat()))
```
Und `import purchases` oben bei den anderen Modul-Imports (`import images`, `import reference`).

- [ ] **Step 6: Migration test**
```python
def test_migration_backfill(tmp_path, monkeypatch):
    import app as wine_app
    monkeypatch.setattr(wine_app, "DB_PATH", str(tmp_path / "w.db"))
    db = sqlite3.connect(wine_app.DB_PATH); db.row_factory = sqlite3.Row
    db.execute("CREATE TABLE wines (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price REAL, quantity INTEGER, purchased_at TEXT)")
    db.execute("INSERT INTO wines (name, price, quantity, purchased_at) VALUES ('W', 25.0, 4, 'Shop')")
    db.commit(); db.close()
    wine_app.init_db()
    db = sqlite3.connect(wine_app.DB_PATH); db.row_factory = sqlite3.Row
    lots = db.execute("SELECT * FROM wine_purchases").fetchall()
    assert len(lots) == 1 and lots[0]["unit_price"] == 25.0 and lots[0]["quantity"] == 4
    assert db.execute("SELECT price FROM wines").fetchone()[0] == 25.0
```
(Falls `init_db` weitere Tabellen erwartet, den bestehenden `client`/`db`-Fixture-Ansatz aus `tests/conftest.py` nutzen statt Handroll — an vorhandene Tests anlehnen.)

- [ ] **Step 7: Volle Suite (Regression)** — `pytest -q` (vorher fragen, ob Full-Suite ok).

- [ ] **Step 8: Commit** — nur nach Nutzer-Freigabe.

---

### Task 2: Purchases-REST-API + `wine_json`

**Files:**
- Modify: `wine-tracker/app/app.py`
- Test: `wine-tracker/tests/test_api.py` (Klasse `TestPurchasesApi`)

**Interfaces:**
- Consumes: `purchases.*` (Task 1).
- Produces: `GET/POST/PATCH/DELETE /api/wine/<id>/purchases[/<pid>]`; `wine_json` liefert `ai_price`, `purchase_count`.

- [ ] **Step 1: Failing tests**
```python
class TestPurchasesApi:
    def _wine(self, client):
        client.post("/add", data={"name": "P Wine", "quantity": 6}, content_type="multipart/form-data")
        import sqlite3, app as wine_app
        db = sqlite3.connect(wine_app.DB_PATH)
        return db.execute("SELECT id FROM wines ORDER BY id DESC LIMIT 1").fetchone()[0]

    def test_add_and_average(self, client):
        wid = self._wine(client)
        client.post(f"/api/wine/{wid}/purchases", json={"quantity": 2, "unit_price": 10})
        r = client.post(f"/api/wine/{wid}/purchases", json={"quantity": 3, "unit_price": 20})
        d = r.get_json()
        assert d["ok"] and d["avg"] == 16.0 and d["total_qty"] == 5
        assert wine_json_price(client, wid) == 16.0

    def test_delete_recomputes(self, client):
        wid = self._wine(client)
        pid = client.post(f"/api/wine/{wid}/purchases", json={"quantity": 1, "unit_price": 5}).get_json()["purchases"][-1]["id"]
        r = client.delete(f"/api/wine/{wid}/purchases/{pid}")
        assert r.get_json()["avg"] is None

    def test_bad_quantity_400(self, client):
        wid = self._wine(client)
        r = client.post(f"/api/wine/{wid}/purchases", json={"quantity": 0, "unit_price": 5})
        assert r.status_code == 400
```
Helper `wine_json_price(client, wid)` = `client.get(f"/api/wine/{wid}").get_json()["wine"]["price"]`.

- [ ] **Step 2: Run (fail).**

- [ ] **Step 3: Endpunkte implementieren** (neben `api_wine_images`):
```python
@app.route("/api/wine/<int:wine_id>/purchases", methods=["GET", "POST"])
def api_wine_purchases(wine_id):
    db = get_db()
    if not db.execute("SELECT 1 FROM wines WHERE id=?", (wine_id,)).fetchone():
        return jsonify({"ok": False, "error": "not_found"}), 404
    if request.method == "POST":
        if AUTH_ENABLED and session.get("role") == "readonly":
            return jsonify({"ok": False, "error": "forbidden"}), 403
        try:
            purchases.add_purchase(db, wine_id, request.get_json(silent=True) or {})
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    return jsonify({"ok": True, "purchases": purchases.list_purchases(db, wine_id),
                    **purchases.weighted_average(db, wine_id)})


@app.route("/api/wine/<int:wine_id>/purchases/<int:pid>", methods=["PATCH", "DELETE"])
def api_wine_purchase_detail(wine_id, pid):
    db = get_db()
    if AUTH_ENABLED and session.get("role") == "readonly":
        return jsonify({"ok": False, "error": "forbidden"}), 403
    if request.method == "DELETE":
        ok = purchases.delete_purchase(db, pid)
    else:
        try:
            ok = purchases.update_purchase(db, pid, request.get_json(silent=True) or {})
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
    if not ok:
        return jsonify({"ok": False, "error": "not_found"}), 404
    return jsonify({"ok": True, "purchases": purchases.list_purchases(db, wine_id),
                    **purchases.weighted_average(db, wine_id)})
```
In `wine_json` ergänzen: `d["purchase_count"] = db.execute("SELECT COUNT(*) FROM wine_purchases WHERE wine_id=?", (wine_id,)).fetchone()[0]` (`ai_price` kommt über `SELECT *` automatisch mit).

- [ ] **Step 4: Run (pass) + Regression** (Full-Suite: vorher fragen).

- [ ] **Step 5: Commit** — nur nach Freigabe.

---

### Task 3: KI-Preis → `ai_price`, Formular-Backend

**Files:**
- Modify: `wine-tracker/app/app.py`
- Test: `wine-tracker/tests/test_api.py`

**Interfaces:**
- Produces: KI-Analyse/Reload/Chat schreiben Preis in `ai_price`; `add`/`edit` setzen `price` nicht mehr aus dem Formular (nur Einkäufe), `ai_price` aus Formular.

- [ ] **Step 1: Failing test** — reanalyze/analyze liefert einen Preis; nach Anwenden steht er in `ai_price`, `price` bleibt vom Einkaufs-Ø bestimmt. (Mock-Analyse mit `price` im JSON; prüfen, dass Speicherung `ai_price` füllt.)

- [ ] **Step 2: Implementierung**
  - In `add()`/`edit()`: `price`-Formularlogik entfernen (nicht mehr in INSERT/UPDATE aus dem Formular; `price` wird nur von `purchases.recompute_wine_price` gesetzt). Beim `add` (neuer Wein) bleibt `price` NULL. `ai_price` aus `request.form.get("ai_price")` (float|None) in INSERT/UPDATE aufnehmen.
  - `duplicate()`: `ai_price` mitkopieren; `price` neu = NULL (Einkäufe werden nicht mitkopiert) — Hinweis im Code.
  - KI-Pfade: wo bisher `price` aus KI-Feldern übernommen wurde, auf `ai_price` mappen. Betroffen: Chat-`_process_chat_add_wine`/`edit` (Feld `price`), sowie die Reanalyze-Anwendung im Frontend (Task 5) — Backend akzeptiert `ai_price`.
  - `_wine_json_schema`/`_wine_json_rules`: KI-Key bleibt `price` (Label-Preis); Doku-Kommentar, dass er ins `ai_price` gespeichert wird.
  - WICHTIG: `add`/`edit` dürfen ein vorhandenes `price` (Ø aus Einkäufen) **nicht** überschreiben/nullen. Sicherstellen, dass `price` in den UPDATE-Spalten **nicht** mehr vorkommt.

- [ ] **Step 3: Run (pass) + Regression.** (Bestehende Tests, die `price` beim Add/Edit erwarten, anpassen: Preis kommt jetzt über Einkäufe. Betroffene Tests in `test_routes.py`/`test_api.py` suchen und umstellen.)

- [ ] **Step 4: Commit** — nur nach Freigabe.

---

### Task 4: Export/Import

**Files:**
- Modify: `wine-tracker/app/export_import.py`
- Test: `wine-tracker/tests/test_export_import.py`

- [ ] **Step 1: Failing test** — Wein mit `ai_price` + zwei Einkäufen → Export-ZIP enthält `purchases.json` + `ai_price`; Re-Import stellt Einkäufe + `ai_price` wieder her und `price` = Ø.

- [ ] **Step 2: Implementierung**
  - `WINE_COLUMNS` + `CSV_COLUMNS`: `"ai_price"` ergänzen; README-Feldtabelle erweitern.
  - `build_export_zip`: `purchases.json` schreiben — `SELECT id, wine_id, purchase_date, quantity, unit_price, location, note FROM wine_purchases`.
  - `parse_import_file` (ZIP): `purchases.json` (optional) einlesen → in `parsed["purchases"]` (Liste, referenziert Original-`wine_id`).
  - `apply_import`: nach dem Einfügen der Weine (id_map original→neu) die Einkäufe je Wein via `purchases.add_purchase` neu anlegen (mit gemappter `wine_id`) und `recompute_wine_price`. `ai_price` wird über `WINE_COLUMNS` bereits gesetzt; danach ggf. `price` neu berechnen (falls Einkäufe vorhanden).
  - CSV bleibt informativ (Ø-`price` + `ai_price`).

- [ ] **Step 3: Run (pass) + Regression.**

- [ ] **Step 4: Commit** — nur nach Freigabe.

---

### Task 5: Frontend — Dialog „Einkäufe verwalten" + Bearbeiten/Detail + i18n + CSS

**Files:**
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (Dialog-Markup + JS)
- Modify: `wine-tracker/app/templates/_wine_form_fields.html` (Preis-Block ersetzen)
- Modify: `wine-tracker/app/templates/index.html` (Detailansicht: „Mein Preis"/„KI-Preis" + Button; Karte unverändert)
- Modify: `wine-tracker/app/static/style.css`
- Modify: `wine-tracker/app/translations.py` (7 Sprachen)
- Verify: Playwright

- [ ] **Step 1: i18n-Keys** (7 Sprachen, per Skript nach vorhandenem Muster einfügen): `label_my_price` („Mein Preis"), `label_ai_price` („KI-Preis"), `purchases_title` („Einkäufe"), `purchases_manage` („Einkäufe verwalten"), `purchase_date`, `purchase_qty` („Menge"), `purchase_unit_price` („Stückpreis"), `purchase_location` („Ort"), `purchase_note` („Notiz"), `purchase_add` („+ Posten"), `purchase_total_spent` („insgesamt ausgegeben"), `purchase_save_first` („zuerst speichern"), `purchase_avg` („gewichteter Ø").

- [ ] **Step 2: Preis-Block im Formular** (`_wine_form_fields.html`): das einzelne `price`- und `purchased_at`-Feld ersetzen durch:
  - read-only Anzeige „Mein Preis (Ø)" (`id=myPriceDisplay`),
  - Button „Einkäufe verwalten" (`onclick=openPurchases()`, im Add-Modus disabled + Titel `purchase_save_first`),
  - `ai_price`-Zahlenfeld (`name=ai_price id=wine_ai_price`).

- [ ] **Step 3: Dialog `#purchasesModal`** (in `_wine_edit_modal.html`, neben den anderen Modals): Header (Titel + ×), Body mit Tabelle (`#purchasesTbody`) + „+ Posten"-Zeile (Inputs Datum/Menge/Stückpreis/Ort/Notiz + Hinzufügen), Fußzeile (Ø, Gesamtmenge, insgesamt ausgegeben). `z-index` über Edit/Detail (z.B. 270).

- [ ] **Step 4: JS** (`_wine_edit_modal.html`):
```js
var _purchWineId = null;
function openPurchases(){ if(!_editWineId){ return; } _purchWineId=_editWineId; loadPurchases(); openModal('purchasesModal'); }
function loadPurchases(){ fetch(INGRESS+'/api/wine/'+_purchWineId+'/purchases').then(r=>r.json()).then(renderPurchases); }
function renderPurchases(d){ /* Tabelle bauen; Ø/Summe in Fußzeile; myPriceDisplay = d.avg */ }
function addPurchase(){ /* POST aus den +Posten-Inputs; dann loadPurchases() + myPriceDisplay aktualisieren */ }
function deletePurchase(pid){ fetch(...,{method:'DELETE'}).then(loadPurchases); }
// nach loadPurchases: document.getElementById('myPriceDisplay').textContent = avg
```
`openViewModal` (index.html) + `openWineModal`: „Mein Preis (Ø)" aus `w.price`, „KI-Preis" aus `w.ai_price`, Button „Einkäufe verwalten" (Detail: read/manage). Nach Dialog-Änderungen `myPriceDisplay` live aktualisieren; beim nächsten Laden/Speichern ist `w.price` bereits der Ø.

- [ ] **Step 5: CSS** — `#purchasesModal .modal{max-width:640px}`, Tabellen-/Zeilen-Styling, `.price-block` Layout.

- [ ] **Step 6: Playwright-Verifikation** (App auf dem Feature-Branch neu starten):
  - Wein bearbeiten → „Einkäufe verwalten" → 2 Posten (2×10, 3×20) → Ø 16.00 in Fußzeile + `myPriceDisplay` + nach Reload Karten-/Detail-Preis 16.00.
  - Posten löschen → Ø aktualisiert.
  - `ai_price` separat setzen/anzeigen; keine JS-Fehler.

- [ ] **Step 7: Commit** — nur nach Freigabe.

---

## Self-Review

**Spec-Abdeckung:** `wine_purchases` + Ø-Cache (Task 1) ✓ · CRUD-API (Task 2) ✓ · `ai_price` getrennt + KI-Routing (Task 1/2/3) ✓ · Export/Import inkl. `purchases.json` (Task 4) ✓ · eigener Dialog aus Bearbeiten+Detail, Karte unverändert, i18n (Task 5) ✓ · Statistik unverändert (Ø×Bestand, keine Änderung nötig) ✓ · entkoppelt vom Bestand ✓.

**Placeholder-Scan:** Frontend-JS in Task 5 ist bewusst als Gerüst skizziert (renderPurchases/addPurchase) — beim Umsetzen konkret ausformulieren; keine offenen TBD in Backend-Tasks.

**Typ-Konsistenz:** `weighted_average` liefert `{avg,total_qty,total_spent}`; API spreizt diese Keys in die Antwort (`avg`, `total_qty`, `total_spent`) + `purchases`. `recompute_wine_price` setzt `wines.price`. `ai_price` durchgängig als eigenständige Spalte.

**Migrations-Risiko:** Bestehendes `price` wird als bezahlter Preis interpretiert (ein Migrations-Posten). Dokumentiert; Nutzer kann korrigieren.
