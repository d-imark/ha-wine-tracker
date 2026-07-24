# KI-Begründung ("Quellen") Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die KI liefert eine kurze, ehrliche Begründung ihrer Angaben; sie wird im KI-Abgleich-Dialog angezeigt, optional gespeichert und in der Detailansicht angezeigt.

**Architecture:** Backend: neue Spalte `wines.ai_rationale`, ein zusätzliches Feld im KI-JSON-Schema, Persistenz in `add`/`edit`/`duplicate`. Frontend: Begründungs-Block mit „speichern"-Checkbox im bestehenden `aiReloadModal`, verstecktes Formularfeld, Anzeige in der Detailansicht.

**Tech Stack:** Flask/Jinja, SQLite, Vanilla JS, CSS. Backend-Tests pytest; Frontend-Verifikation Playwright (System-Chrome, `channel="chrome"`).

## Global Constraints

- Code/Kommentare/Commits Englisch; UI-Strings in `translations.py` für 7 Sprachen: `de, en, fr, it, es, pt, nl`.
- Feldname durchgängig `ai_rationale` (DB-Spalte, AI-JSON-Key, Formularfeld-`name`); Formular-Element-ID `wine_ai_rationale`.
- Keine erfundenen URLs/Zitate — die KI-Regel verbietet das ausdrücklich.
- Bestehende KI-Abgleich- und Vivino-Flows bleiben funktionsfähig; volle pytest-Suite bleibt grün.
- App-Tests laufen im Ordner `wine-tracker`: `../.venv/Scripts/python.exe -m pytest`.

---

### Task 1: Backend — Spalte, KI-Schema und Persistenz

**Files:**
- Modify: `wine-tracker/app/app.py` (migrations-Dict; `add`/`edit`/`duplicate` INSERT/UPDATE; `_wine_json_schema`; `_wine_json_rules`)
- Test: `wine-tracker/tests/test_routes.py` (neue Klasse `TestAiRationale`)

**Interfaces:**
- Consumes: bestehende Fixtures `client`, `sample_wine`, Konstante `AJAX = {"X-Requested-With": "XMLHttpRequest"}`, `wine_json`.
- Produces: DB-Spalte `wines.ai_rationale` (TEXT); `add`/`edit`/`duplicate` lesen `request.form["ai_rationale"]` und persistieren es; `wine_json` gibt `ai_rationale` zurück (automatisch via `dict(row)`).

- [ ] **Step 1: Failing tests schreiben**

In `wine-tracker/tests/test_routes.py` ans Ende anfügen:
```python
class TestAiRationale:
    """AI rationale ("Quellen") stored on wines (ai_rationale)."""

    def test_add_stores_ai_rationale(self, client):
        resp = client.post("/add", data={"name": "R", "quantity": "1",
                            "ai_rationale": "Erkannt anhand Label."}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["ai_rationale"] == "Erkannt anhand Label."

    def test_edit_updates_ai_rationale(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(f"/edit/{wine_id}", data={"name": "X", "quantity": "1",
                            "ai_rationale": "Neue Basis."}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["wine"]["ai_rationale"] == "Neue Basis."

    def test_duplicate_copies_ai_rationale(self, client):
        created = json.loads(client.post("/add", data={"name": "Dup", "quantity": "1",
                             "ai_rationale": "Basis."}, headers=AJAX).data)
        wid = created["wine"]["id"]
        resp = client.post(f"/duplicate/{wid}", data={"year": "2021"}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["wine"]["ai_rationale"] == "Basis."

    def test_api_wine_returns_ai_rationale(self, client):
        created = json.loads(client.post("/add", data={"name": "C2", "quantity": "1",
                             "ai_rationale": "Weinführer-Wissen."}, headers=AJAX).data)
        wid = created["wine"]["id"]
        data = json.loads(client.get(f"/api/wine/{wid}").data)
        assert data["wine"]["ai_rationale"] == "Weinführer-Wissen."
```

- [ ] **Step 2: Tests laufen lassen (fail)**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_routes.py::TestAiRationale -q`
Expected: FAIL (Spalte/Feld fehlt → `KeyError`/`None`).

- [ ] **Step 3: Migrations-Spalte ergänzen**

In `wine-tracker/app/app.py` im `migrations`-Dict die Zeile nach `"country": "TEXT",` einfügen:
```python
            "country":        "TEXT",
            "ai_rationale":   "TEXT",
```

- [ ] **Step 4: `add`-Route INSERT erweitern**

Spaltenliste (aktuell endet mit `food_pairings, country)`):
```python
            maturity_data, taste_profile, food_pairings, country, ai_rationale)
```
Platzhalter-Zeile ersetzen:
```python
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
```
Wert nach `request.form.get("country", "").strip() or None,` ergänzen:
```python
            request.form.get("country", "").strip() or None,
            request.form.get("ai_rationale", "").strip() or None,
```

- [ ] **Step 5: `edit`-Route UPDATE erweitern**

Nach dem `country_val`-Block (`if "country" in request.form: ... else: country_val = wine["country"]`) einfügen:
```python
    if "ai_rationale" in request.form:
        ai_rationale_val = request.form.get("ai_rationale", "").strip() or None
    else:
        ai_rationale_val = wine["ai_rationale"]
```
SET-Klausel (aktuell `... food_pairings=?, country=?`) ersetzen:
```python
           maturity_data=?, taste_profile=?, food_pairings=?, country=?, ai_rationale=?
```
Wert nach `country_val,` (vor `wine_id,`) ergänzen:
```python
            country_val,
            ai_rationale_val,
            wine_id,
```

- [ ] **Step 6: `duplicate`-Route INSERT erweitern**

Spaltenliste (aktuell `... food_pairings, country)`) ersetzen:
```python
           maturity_data, taste_profile, food_pairings, country, ai_rationale)
```
Platzhalter-Zeile ersetzen:
```python
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
```
Wert nach `wine["country"],` ergänzen:
```python
            wine["country"],
            wine["ai_rationale"],
```

- [ ] **Step 7: KI-Schema + Regel erweitern**

In `_wine_json_schema()` die `food_pairings`-Zeile um ein Komma ergänzen und das neue Feld anhängen:
```python
  "food_pairings": ["dish1", "dish2", "dish3"],
  "ai_rationale": "1-2 sentence basis for the identification and estimates, or null"
}"""
```
In `_wine_json_rules()` vor der Zeile `- If a field cannot be determined ...` einfügen:
```python
- ai_rationale: 1-2 short sentences in {lang_name} explaining what the identification and estimates are based on (label text, producer, region/grape typicity). Do NOT invent URLs or citations. Set to null if you have no real basis.
```

- [ ] **Step 8: Tests laufen lassen (pass) + volle Suite**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_routes.py::TestAiRationale -q`
Expected: 4 passed.
Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 394 passed (390 + 4 neue).

- [ ] **Step 9: Commit**

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_routes.py
git commit -m "Store AI rationale on wines (column, schema, add/edit/duplicate)"
```

---

### Task 2: Frontend — Begründungs-Block im KI-Abgleich-Dialog

**Files:**
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (Hidden-Feld, Modal-Markup, `openWineModal`, `openAiReload`, `renderAiReload`, `applyAiReload`)
- Modify: `wine-tracker/app/translations.py` (Keys `ar_rationale_save`, `ai_basis_label` in 7 Sprachen)
- Modify: `wine-tracker/app/static/style.css` (`.ar-rationale*`, `.view-ai-basis`)

**Interfaces:**
- Consumes: `_arPending`, `showReloadToast`, `T`, DOM aus Task 1 (`ai_rationale` in `fields`).
- Produces: Hidden-Feld `#wine_ai_rationale` (name `ai_rationale`); Dialog-Block `#aiRationaleBlock` mit Text `#aiRationaleText` und Checkbox `#arRationaleSave`; `applyAiReload` schreibt bei aktiver Checkbox `#wine_ai_rationale`.

- [ ] **Step 1: Verstecktes Formularfeld ergänzen**

In `_wine_edit_modal.html` nach `<input type="hidden" name="food_pairings" id="wine_food_pairings" value="">` einfügen:
```html
      <input type="hidden" name="ai_rationale" id="wine_ai_rationale" value="">
```

- [ ] **Step 2: `openWineModal` befüllt das Feld**

Bei den anderen Hidden-Feld-Zuweisungen (nach `wine_food_pairings`-Zeile) ergänzen:
```js
  document.getElementById('wine_ai_rationale').value = w.ai_rationale || '';
```

- [ ] **Step 3: Übersetzungen ergänzen (7 Sprachen)**

In `translations.py` in jedem Sprach-Dict nach der jeweiligen `"ar_hint": ...,`-Zeile einfügen:

`de`:
```python
    "ar_rationale_save": "Begründung speichern",
    "ai_basis_label": "KI-Basis",
```
`en`:
```python
    "ar_rationale_save": "Save rationale",
    "ai_basis_label": "AI basis",
```
`fr`:
```python
    "ar_rationale_save": "Enregistrer la justification",
    "ai_basis_label": "Base IA",
```
`it`:
```python
    "ar_rationale_save": "Salva motivazione",
    "ai_basis_label": "Base IA",
```
`es`:
```python
    "ar_rationale_save": "Guardar justificación",
    "ai_basis_label": "Base IA",
```
`pt`:
```python
    "ar_rationale_save": "Guardar justificação",
    "ai_basis_label": "Base IA",
```
`nl`:
```python
    "ar_rationale_save": "Motivering opslaan",
    "ai_basis_label": "AI-basis",
```

- [ ] **Step 4: Dialog-Markup — Begründungs-Block**

In `_wine_edit_modal.html` im `aiReloadModal` die `#aiIdentified`-Zeile so erweitern (Block direkt danach einfügen):
```html
      <p class="ar-identified" id="aiIdentified"></p>
      <div class="ar-rationale" id="aiRationaleBlock" style="display:none">
        <p class="ar-rationale-text" id="aiRationaleText"></p>
        <label class="ar-rationale-save"><input type="checkbox" id="arRationaleSave" checked> {{ t.ar_rationale_save }}</label>
      </div>
```

- [ ] **Step 5: CSS ergänzen**

In `style.css` im `AI reload confirm dialog`-Block anhängen:
```css
#aiReloadModal .ar-rationale {
  font-size: .85rem; margin: 0 0 .8rem; padding: .55rem .65rem;
  background: var(--surface); border-radius: 6px; border-left: 3px solid var(--accent);
}
#aiReloadModal .ar-rationale-text { margin: 0 0 .45rem; line-height: 1.45; overflow-wrap: break-word; }
#aiReloadModal .ar-rationale-save { display: flex; align-items: center; gap: .4rem; font-size: .8rem; color: var(--muted); cursor: pointer; }
```

- [ ] **Step 6: `openAiReload` + `renderAiReload` — Begründung berücksichtigen**

`openAiReload` ersetzen:
```js
function openAiReload(fields) {
  var changes = arComputeChanges(fields);
  var enrich = arComputeEnrich(fields);
  var rationale = (fields.ai_rationale || '').trim();
  if (changes.length === 0 && enrich.length === 0 && !rationale) {
    showReloadToast(T.ar_no_changes || T.reload_nothing, false);
    return;
  }
  _arPending = { fields: fields, changes: changes, enrich: enrich, rationale: rationale };
  renderAiReload(fields, changes, enrich);
  document.getElementById('aiReloadModal').classList.add('open');
}
```
In `renderAiReload` am Ende (nach dem `aiChanges`-innerHTML-Zuweisung) einfügen:
```js
  var rationale = (fields.ai_rationale || '').trim();
  var rblock = document.getElementById('aiRationaleBlock');
  if (rationale) {
    document.getElementById('aiRationaleText').textContent = rationale;
    document.getElementById('arRationaleSave').checked = true;
    rblock.style.display = '';
  } else {
    rblock.style.display = 'none';
  }
```

- [ ] **Step 7: `applyAiReload` — Begründung speichern**

In `applyAiReload` vor `closeAiReload();` einfügen:
```js
  if (_arPending.rationale) {
    var save = document.getElementById('arRationaleSave');
    if (save && save.checked) {
      var rel = document.getElementById('wine_ai_rationale');
      if (rel) rel.value = _arPending.rationale;
    }
  }
```

- [ ] **Step 8: Playwright — Block + Checkbox + Übernehmen**

App neu starten (Task-übergreifend, siehe Task 3 Step 1 für den Neustart-Befehl). Skript `scratchpad/r1.py`:
```python
import json
from playwright.sync_api import sync_playwright
FIELDS = {"name":"X","grape":"Nebbiolo","ai_rationale":"Erkannt anhand des Etiketts; typische Barolo-Reife."}
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(status=200,
        content_type="application/json", body=json.dumps({"ok": True, "fields": FIELDS})))
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://localhost:5050/", wait_until="load")
    pg.evaluate("() => openWineModal(null, {name:'X'})")
    pg.wait_for_timeout(300)
    pg.evaluate("() => reloadViaAi()")
    pg.wait_for_timeout(1200)
    seen = pg.evaluate("""() => ({
      blockShown: getComputedStyle(document.getElementById('aiRationaleBlock')).display,
      text: document.getElementById('aiRationaleText').textContent,
      checked: document.getElementById('arRationaleSave').checked
    })""")
    print("block:", seen)
    pg.evaluate("() => applyAiReload()")
    pg.wait_for_timeout(300)
    val = pg.evaluate("() => document.getElementById('wine_ai_rationale').value")
    print("wine_ai_rationale after apply (checked):", repr(val))
    print("errors:", errs if errs else "none")
    b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/r1.py`
Expected: `blockShown` != `none`, `text` == die Begründung, `checked` True; `wine_ai_rationale` == die Begründung; `errors: none`.

- [ ] **Step 9: Playwright — Checkbox abgewählt → nicht gespeichert**

Skript `scratchpad/r2.py` (wie r1, aber Checkbox vor Apply abwählen):
```python
import json
from playwright.sync_api import sync_playwright
FIELDS = {"name":"X","grape":"Nebbiolo","ai_rationale":"Basis-Text."}
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(status=200,
        content_type="application/json", body=json.dumps({"ok": True, "fields": FIELDS})))
    pg.goto("http://localhost:5050/", wait_until="load")
    pg.evaluate("() => openWineModal(null, {name:'X'})")
    pg.wait_for_timeout(300)
    pg.evaluate("() => reloadViaAi()")
    pg.wait_for_timeout(1200)
    pg.evaluate("() => { document.getElementById('arRationaleSave').checked = false; applyAiReload(); }")
    pg.wait_for_timeout(300)
    print("wine_ai_rationale (unchecked):", repr(pg.evaluate("() => document.getElementById('wine_ai_rationale').value")))
    b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/r2.py`
Expected: leer (`''`).

- [ ] **Step 10: Commit**

```bash
git add wine-tracker/app/templates/_wine_edit_modal.html wine-tracker/app/translations.py wine-tracker/app/static/style.css
git commit -m "Show AI rationale with a save checkbox in the reload dialog"
```

---

### Task 3: Detailansicht + Regression

**Files:**
- Modify: `wine-tracker/app/templates/index.html` (`openViewModal`)
- Modify: `wine-tracker/app/static/style.css` (`.view-ai-basis`)

**Interfaces:**
- Consumes: `w.ai_rationale` aus `wine_json`, `T.ai_basis_label`, `escapeHtml`.
- Produces: Anzeige-Block in der Detailansicht.

- [ ] **Step 1: App auf dieser Branch neu starten**

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*app.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\Users\DominikImark\repos\ha-wine-tracker\scripts\run-dev.local.ps1" -WindowStyle Hidden
Start-Sleep -Seconds 7
```

- [ ] **Step 2: Detailansicht-Block einfügen**

In `index.html` in `openViewModal` direkt nach dem Notes-Block (`if (w.notes) { html += '<div class="view-notes">' ... }`) einfügen:
```js
  // AI rationale ("Quellen")
  if (w.ai_rationale) {
    html += '<div class="view-ai-basis"><span class="view-ai-basis-label">' +
      (T.ai_basis_label || 'AI basis') + '</span> ' + escapeHtml(w.ai_rationale) + '</div>';
  }
```

- [ ] **Step 3: CSS für die Detailansicht**

In `style.css` im `AI reload confirm dialog`-Block anhängen (oder direkt darunter):
```css
.view-ai-basis {
  margin-top: .6rem; font-size: .82rem; color: var(--muted); line-height: 1.45;
  padding: .5rem .6rem; background: var(--surface); border-radius: 6px; overflow-wrap: break-word;
}
.view-ai-basis .view-ai-basis-label { font-weight: 600; margin-right: .3rem; }
```

- [ ] **Step 4: Playwright — End-to-End (speichern → Detailansicht zeigt Basis)**

App neu starten (Step 1). Skript `scratchpad/r3.py`:
```python
from playwright.sync_api import sync_playwright
BASE = "http://localhost:5050"
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    # add a wine with ai_rationale directly via the form endpoint
    pg.request.post(BASE+"/add", form={"name":"BasisWein","quantity":"1",
        "ai_rationale":"Erkannt anhand Etikett; Barolo-typische Reife."},
        headers={"X-Requested-With":"XMLHttpRequest"})
    pg.goto(BASE+"/", wait_until="load")
    # open the view modal for that wine
    pg.evaluate("""() => {
      var c = Array.from(document.querySelectorAll('.card')).find(x => x.dataset.name === 'BasisWein');
      c.click();
    }""")
    pg.wait_for_timeout(1200)
    r = pg.evaluate("""() => {
      var el = document.querySelector('.view-ai-basis');
      return { present: !!el, text: el ? el.textContent : '' };
    }""")
    print(r); b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/r3.py`
Expected: `present: True`, `text` enthält „KI-Basis" und den Begründungstext.

- [ ] **Step 5: Volle Testsuite (Regression)**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 394 passed.

- [ ] **Step 6: Commit**

```bash
git add wine-tracker/app/templates/index.html wine-tracker/app/static/style.css
git commit -m "Show the stored AI rationale in the wine detail view"
```

---

## Self-Review

**Spec-Abdeckung:**
- DB-Spalte `ai_rationale` → Task 1 Step 3. ✓
- KI-Schema + Regel (keine URLs) → Task 1 Step 7. ✓
- Persistenz add/edit/duplicate → Task 1 Steps 4–6 + Tests Step 1/8. ✓
- Dialog-Block + „speichern"-Checkbox + Öffnen auch nur-Begründung → Task 2 Steps 4,6,7. ✓
- Verstecktes Feld + `openWineModal` → Task 2 Steps 1,2. ✓
- Detailansicht „KI-Basis" → Task 3 Step 2. ✓
- i18n 7 Sprachen → Task 2 Step 3. ✓
- CSS Dialog + Detailansicht → Task 2 Step 5, Task 3 Step 3. ✓
- Tests backend (pytest) + frontend (Playwright) → Task 1 Step 1/8, Task 2 Steps 8–9, Task 3 Step 4/5. ✓

**Placeholder-Scan:** kein TBD/TODO; vollständiger Code je Step. ✓

**Typ-Konsistenz:** `ai_rationale` (DB/JSON/Formular-name), `wine_ai_rationale` (Element-ID), `#aiRationaleBlock`/`#aiRationaleText`/`#arRationaleSave`, `_arPending.rationale` durchgängig identisch. Platzhalter add/duplicate 22→23 konsistent mit je einem zusätzlichen Wert. ✓

**Hinweis (Out of Scope):** Der Chat-basierte ADD_WINE-INSERT (`app.py` ~Zeile 2775, 17 Spalten) speichert `ai_rationale` nicht — bewusst außerhalb dieses Plans (Spec deckt den KI-Reload-Flow + add/edit/duplicate ab). Kein Fehler: das zusätzliche Schema-Feld schadet dort nicht.
