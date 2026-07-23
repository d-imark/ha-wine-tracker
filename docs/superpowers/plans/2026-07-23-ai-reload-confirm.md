# KI-Reload Bestätigungs-Dialog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Der KI-Reload im Bearbeiten-Dialog zeigt vor dem Überschreiben einen Bestätigungs-Dialog mit erkanntem Wein und einer Checkbox-Änderungstabelle (pro Feld wählbar).

**Architecture:** Neuer, eigenständiger Dialog `aiReloadModal` parallel zum bestehenden `vivinoReloadModal`. Reine Frontend-Änderung in `_wine_edit_modal.html` (+ `translations.py`, `style.css`). Das Backend `/api/reanalyze-wine` liefert `fields` bereits und bleibt unverändert. Der Vivino-Flow wird nicht angefasst.

**Tech Stack:** Flask/Jinja Templates, Vanilla JS, CSS. Verifikation per Playwright (System-Chrome, `channel="chrome"`), Backend-Regression per pytest.

## Global Constraints

- Code/Kommentare/Commits auf Englisch; UI-Strings über `translations.py` in allen 7 Sprachen: `de, en, fr, it, es, pt, nl`.
- Der Vivino-Reload-Flow (`vivinoReloadModal`, `vr*`-Funktionen) bleibt unverändert und funktionsfähig.
- Modal-Anzeige über die CSS-Klasse `open` (`.modal-overlay.open { display: flex; }`), analog `vivinoReloadModal`.
- Persönliches Rating nur anbieten, wenn die KI eins liefert UND der Slider aktuell 0 ist; Wert auf 0–5 mit einer Nachkommastelle clampen.
- Enrichment (`maturity_data`, `taste_profile`, `food_pairings`) als eigene Checkbox-Zeilen mit Kurz-Zusammenfassung, kein JSON-Diff.
- Alle bestehenden Tests bleiben grün (`pytest` im Ordner `wine-tracker`).

---

### Task 1: Modal-Markup, CSS und Übersetzungen

**Files:**
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (Modal-Markup direkt nach dem `reconcileModal`-Block einfügen)
- Modify: `wine-tracker/app/static/style.css` (nach dem `Reference reconcile dialog`-Block)
- Modify: `wine-tracker/app/translations.py` (je Sprache 8 Keys nach `"vivino_rating_label"`)

**Interfaces:**
- Produces: DOM-Element `#aiReloadModal` mit Kindern `#aiIdentified`, `#aiChanges` (tbody), Buttons `arCancel()`/`applyAiReload()`. Translation-Keys `ar_title, ar_identified, ar_maturity, ar_taste, ar_pairings, ar_apply, ar_no_changes, ar_hint`. CSS-Klassen `.ar-identified`, `.ar-id-label`, `.ar-changes-table .ar-check`.

- [ ] **Step 1: Modal-Markup einfügen**

In `wine-tracker/app/templates/_wine_edit_modal.html` direkt NACH dem schließenden `</div>` des `reconcileModal`-Blocks (vor `<script src="{{ ingress }}/static/wine-modal.js"></script>`) einfügen:

```html
<!-- ═══════════ AI RELOAD CONFIRM (per-field, KI) ═══════════ -->
<div class="modal-overlay" id="aiReloadModal">
  <div class="modal">
    <div class="modal-header">
      <span>{{ t.ar_title }}</span>
      <button class="modal-close" type="button" onclick="arCancel()">&times;</button>
    </div>
    <div class="modal-body">
      <p class="ar-identified" id="aiIdentified"></p>
      <p class="vr-hint">{{ t.ar_hint }}</p>
      <table class="vr-changes-table ar-changes-table"><tbody id="aiChanges"></tbody></table>
    </div>
    <div class="modal-footer vr-footer">
      <button type="button" class="btn-cancel" onclick="arCancel()">{{ t.btn_cancel }}</button>
      <button type="button" class="btn-submit" onclick="applyAiReload()">{{ t.ar_apply }}</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: CSS einfügen**

In `wine-tracker/app/static/style.css` am Ende des `Reference reconcile dialog (TP3b)`-Blocks anhängen:

```css
/* ── AI reload confirm dialog ──────────────────────────────────────────────── */
#aiReloadModal { z-index: 260; }  /* above the edit modal (200) it opens from */
#aiReloadModal .ar-identified {
  font-size: .9rem; margin: 0 0 .6rem; padding: .5rem .6rem;
  background: var(--surface); border-radius: 6px;
}
#aiReloadModal .ar-identified .ar-id-label { color: var(--muted); margin-right: .3rem; }
.ar-changes-table .ar-check { width: 1%; white-space: nowrap; padding-right: .3rem; }
.ar-changes-table .ar-check input { cursor: pointer; }
```

- [ ] **Step 3: Übersetzungen einfügen (alle 7 Sprachen)**

In `wine-tracker/app/translations.py` in jedem Sprach-Dict direkt NACH der Zeile `"vivino_rating_label": ...,` den passenden Block einfügen:

`de` (nach Zeile ~283):
```python
    "ar_title": "KI-Abgleich",
    "ar_identified": "Die KI hat erkannt:",
    "ar_maturity": "Reifeverlauf",
    "ar_taste": "Geschmacksprofil",
    "ar_pairings": "Food-Pairings",
    "ar_apply": "Übernehmen",
    "ar_no_changes": "Keine neuen Daten",
    "ar_hint": "Wähle, welche Vorschläge übernommen werden:",
```

`en`:
```python
    "ar_title": "AI match",
    "ar_identified": "The AI identified:",
    "ar_maturity": "Maturity",
    "ar_taste": "Taste profile",
    "ar_pairings": "Food pairings",
    "ar_apply": "Apply",
    "ar_no_changes": "No new data",
    "ar_hint": "Choose which suggestions to apply:",
```

`fr`:
```python
    "ar_title": "Correspondance IA",
    "ar_identified": "L'IA a identifié :",
    "ar_maturity": "Maturité",
    "ar_taste": "Profil gustatif",
    "ar_pairings": "Accords mets-vins",
    "ar_apply": "Appliquer",
    "ar_no_changes": "Aucune nouvelle donnée",
    "ar_hint": "Choisissez les suggestions à appliquer :",
```

`it`:
```python
    "ar_title": "Confronto IA",
    "ar_identified": "L'IA ha riconosciuto:",
    "ar_maturity": "Maturazione",
    "ar_taste": "Profilo gustativo",
    "ar_pairings": "Abbinamenti",
    "ar_apply": "Applica",
    "ar_no_changes": "Nessun dato nuovo",
    "ar_hint": "Scegli quali suggerimenti applicare:",
```

`es`:
```python
    "ar_title": "Coincidencia IA",
    "ar_identified": "La IA ha identificado:",
    "ar_maturity": "Maduración",
    "ar_taste": "Perfil de sabor",
    "ar_pairings": "Maridajes",
    "ar_apply": "Aplicar",
    "ar_no_changes": "Sin datos nuevos",
    "ar_hint": "Elige qué sugerencias aplicar:",
```

`pt`:
```python
    "ar_title": "Correspondência IA",
    "ar_identified": "A IA identificou:",
    "ar_maturity": "Maturação",
    "ar_taste": "Perfil de sabor",
    "ar_pairings": "Harmonizações",
    "ar_apply": "Aplicar",
    "ar_no_changes": "Sem dados novos",
    "ar_hint": "Escolhe quais sugestões aplicar:",
```

`nl`:
```python
    "ar_title": "AI-match",
    "ar_identified": "De AI herkende:",
    "ar_maturity": "Rijping",
    "ar_taste": "Smaakprofiel",
    "ar_pairings": "Foodpairings",
    "ar_apply": "Toepassen",
    "ar_no_changes": "Geen nieuwe gegevens",
    "ar_hint": "Kies welke suggesties je toepast:",
```

- [ ] **Step 4: Syntax prüfen und bestehende Tests laufen lassen**

Run:
```bash
cd wine-tracker && python -c "import ast; ast.parse(open('app/translations.py',encoding='utf-8').read()); print('OK')"
cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q
```
Expected: `OK`, danach alle Tests grün (390 passed).

- [ ] **Step 5: Playwright-Check — Modal existiert und ist versteckt**

Skript `scratchpad/t1.py` (App muss auf :5050 laufen):
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.goto("http://localhost:5050/", wait_until="load")
    r = pg.evaluate("""() => {
      var m = document.getElementById('aiReloadModal');
      return { exists: !!m, hidden: m ? getComputedStyle(m).display : '??',
               header: !!document.getElementById('aiIdentified'),
               tbody: !!document.getElementById('aiChanges') };
    }""")
    print(r); b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/t1.py`
Expected: `exists=True, hidden=none, header=True, tbody=True`.

- [ ] **Step 6: Commit**

```bash
git add wine-tracker/app/templates/_wine_edit_modal.html wine-tracker/app/static/style.css wine-tracker/app/translations.py
git commit -m "Add AI reload confirm dialog markup, styles and i18n"
```

---

### Task 2: JS — Änderungsberechnung, Rendering und Verdrahtung

**Files:**
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (JS-Block; `reloadViaAi` anpassen, neue Funktionen ergänzen)

**Interfaces:**
- Consumes: DOM/Keys aus Task 1; Helfer `showReloadToast(msg, success)`, `setReloadLoading(on)`, `updateRatingPreview()`, globales `T` (Übersetzungen), `INGRESS`.
- Produces: `openAiReload(fields)`, `arComputeChanges(fields)`, `arComputeEnrich(fields)`, `renderAiReload(fields, changes, enrich)`, Maps `_AR_FIELDS`/`_AR_ENRICH`, globales `_arPending`. Die Checkboxen erhalten IDs `arChk_<i>` (einfache Felder) und `arEnr_<j>` (Enrichment).

- [ ] **Step 1: Playwright-Test schreiben (RED)**

Skript `scratchpad/t2.py` (App auf :5050). Stubt die KI-Antwort per `page.route`:
```python
import json
from playwright.sync_api import sync_playwright
FIELDS = {"name":"Barolo Riserva","vintage":"2015","wine_type":"red",
          "region":"Piemont","grape":"Nebbiolo","notes":"Kräftig, langer Abgang",
          "taste_profile":{"body":4,"tannin":5},"food_pairings":["Rind","Hartkäse"]}
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "fields": FIELDS})))
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://localhost:5050/", wait_until="load")
    # edit mode with some values already set (name matches -> should NOT be a change row)
    pg.evaluate("""() => openWineModal('1', {name:'Barolo Riserva', region:'Alt'})""")
    pg.wait_for_timeout(400)
    pg.evaluate("() => reloadViaAi()")
    pg.wait_for_timeout(1500)
    r = pg.evaluate("""() => {
      var m = document.getElementById('aiReloadModal');
      var rows = Array.from(document.querySelectorAll('#aiChanges tr'));
      return {
        open: m ? getComputedStyle(m).display : '??',
        identified: document.getElementById('aiIdentified').textContent,
        rowLabels: rows.map(tr => tr.querySelector('.vr-field') ? tr.querySelector('.vr-field').textContent : ''),
        checkboxes: rows.map(tr => { var c = tr.querySelector('input[type=checkbox]'); return c ? c.checked : null; })
      };
    }""")
    print("open:", r["open"])
    print("identified:", r["identified"])
    print("rowLabels:", r["rowLabels"])
    print("checkboxes:", r["checkboxes"])
    print("errors:", errs if errs else "none")
    b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/t2.py`
Expected VOR der Implementierung: FEHLER — `reloadViaAi` ruft noch `populateFormMerge`, `aiReloadModal` bleibt `none` (kein `open`), `identified` leer.

- [ ] **Step 2: Feld-Maps und State ergänzen**

Im JS-Block von `_wine_edit_modal.html` (bei den übrigen `var`-Deklarationen nahe `_reloadMode`) ergänzen:
```js
// ── AI reload confirm (per-field) ────────────────────────────────────────────
var _AR_FIELDS = [
  { key: 'name',        el: 'wine_name',        labelKey: 'label_name' },
  { key: 'vintage',     el: 'wine_year',        labelKey: 'label_vintage' },
  { key: 'wine_type',   el: 'wine_type',        labelKey: 'label_type', type: 'wine_type' },
  { key: 'region',      el: 'wine_region',      labelKey: 'label_region' },
  { key: 'grape',       el: 'wine_grape',       labelKey: 'label_grape' },
  { key: 'price',       el: 'wine_price',       labelKey: 'label_price' },
  { key: 'drink_from',  el: 'wine_drink_from',  labelKey: 'label_drink_from' },
  { key: 'drink_until', el: 'wine_drink_until', labelKey: 'label_drink_until' },
  { key: 'notes',       el: 'wine_notes',       labelKey: 'label_notes' }
];
var _AR_ENRICH = [
  { key: 'maturity_data', el: 'wine_maturity_data', labelKey: 'ar_maturity' },
  { key: 'taste_profile', el: 'wine_taste_profile', labelKey: 'ar_taste' },
  { key: 'food_pairings', el: 'wine_food_pairings', labelKey: 'ar_pairings' }
];
var _arPending = null;
```

- [ ] **Step 3: Berechnungs- und Anzeige-Funktionen ergänzen**

Im JS-Block (z.B. direkt vor dem `AJAX form submit`-Kommentar) einfügen:
```js
function _arDisplay(f, val) {
  if (val === '' || val === null || val === undefined) return '—';
  if (f.type === 'wine_type') return T['wine_type_' + val] || val;
  return String(val);
}

function arComputeChanges(fields) {
  var changes = [];
  _AR_FIELDS.forEach(function(f) {
    var raw = fields[f.key];
    if (raw === null || raw === undefined) return;
    var nv = String(raw).trim();
    if (!nv) return;
    var el = document.getElementById(f.el);
    var cur = el ? (el.value || '').trim() : '';
    if (nv === cur) return;                       // unchanged -> skip
    changes.push({ f: f, cur: cur, nv: nv });
  });
  // Personal rating: only when the AI supplies one and the slider is still unset.
  if (fields.rating) {
    var slider = document.getElementById('wine_rating');
    var curRating = slider ? (parseFloat(slider.value) || 0) : 0;
    if (curRating === 0) {
      var rv = Math.max(0, Math.min(5, Math.round(Number(fields.rating) * 10) / 10));
      if (rv > 0) {
        changes.push({ f: { el: 'wine_rating', labelKey: 'label_rating', rating: true },
                       cur: '', nv: String(rv) });
      }
    }
  }
  return changes;
}

function arComputeEnrich(fields) {
  var out = [];
  _AR_ENRICH.forEach(function(e) {
    var val = fields[e.key];
    if (val === null || val === undefined) return;
    if (Array.isArray(val)) { if (val.length === 0) return; out.push({ e: e, val: val, count: val.length }); return; }
    if (typeof val === 'object') { var n = Object.keys(val).length; if (n === 0) return; out.push({ e: e, val: val, count: n }); return; }
  });
  return out;
}

function renderAiReload(fields, changes, enrich) {
  var esc = function(s) { return (s == null ? '' : String(s)).replace(/</g, '&lt;'); };
  var idParts = [];
  ['name','vintage','wine_type','region','grape'].forEach(function(k) {
    var v = fields[k];
    if (!v) return;
    if (k === 'wine_type') v = T['wine_type_' + v] || v;
    idParts.push(esc(v));
  });
  document.getElementById('aiIdentified').innerHTML =
    '<span class="ar-id-label">' + (T.ar_identified || '') + '</span>' +
    (idParts.length ? idParts.join(' · ') : '—');

  var rows = '';
  changes.forEach(function(c, i) {
    rows += '<tr>' +
      '<td class="ar-check"><input type="checkbox" id="arChk_' + i + '" checked></td>' +
      '<td class="vr-field">' + (T[c.f.labelKey] || c.f.el) + '</td>' +
      '<td class="vr-old">' + esc(_arDisplay(c.f, c.cur)) + '</td>' +
      '<td class="vr-arrow">→</td>' +
      '<td class="vr-new">' + esc(_arDisplay(c.f, c.nv)) + '</td>' +
    '</tr>';
  });
  enrich.forEach(function(en, j) {
    rows += '<tr>' +
      '<td class="ar-check"><input type="checkbox" id="arEnr_' + j + '" checked></td>' +
      '<td class="vr-field">' + (T[en.e.labelKey] || en.e.key) + '</td>' +
      '<td class="vr-new" colspan="3"><i class="mdi mdi-check"></i>' +
        (en.count ? ' (' + en.count + ')' : '') + '</td>' +
    '</tr>';
  });
  document.getElementById('aiChanges').innerHTML = rows;
}

function openAiReload(fields) {
  var changes = arComputeChanges(fields);
  var enrich = arComputeEnrich(fields);
  if (changes.length === 0 && enrich.length === 0) {
    showReloadToast(T.ar_no_changes || T.reload_nothing, false);
    return;
  }
  _arPending = { fields: fields, changes: changes, enrich: enrich };
  renderAiReload(fields, changes, enrich);
  document.getElementById('aiReloadModal').classList.add('open');
}

function closeAiReload() {
  document.getElementById('aiReloadModal').classList.remove('open');
  _arPending = null;
}
function arCancel() { closeAiReload(); }
```

- [ ] **Step 4: `reloadViaAi` verdrahten**

In `reloadViaAi()` den Erfolgszweig ändern — statt `populateFormMerge(data.fields, null);`:
```js
    if (data.ok && data.fields) {
      openAiReload(data.fields);
    } else {
      showReloadToast(T.ai_error, false);
    }
```
(Die umgebende `.then`/`.catch`-Struktur und `setReloadLoading(false)` bleiben unverändert.)

- [ ] **Step 5: Test laufen lassen (GREEN)**

Run: `& .venv/Scripts/python.exe scratchpad/t2.py`
Expected NACH der Implementierung:
- `open: flex`
- `identified` enthält `Barolo Riserva · 2015 · ... · Piemont · Nebbiolo`
- `rowLabels` enthält Region, Rebsorte, Notizen, Reifeverlauf/Geschmacksprofil/Food-Pairings; **kein** Name-Row (Name identisch), da `name` unverändert
- alle `checkboxes` == `True`
- `errors: none`

- [ ] **Step 6: Commit**

```bash
git add wine-tracker/app/templates/_wine_edit_modal.html
git commit -m "Open AI reload result in a per-field confirm dialog"
```

---

### Task 3: JS — Selektives Übernehmen, „keine Änderungen", Regression

**Files:**
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (Funktion `applyAiReload` ergänzen)

**Interfaces:**
- Consumes: `_arPending`, `updateRatingPreview()`, Checkbox-IDs `arChk_<i>`/`arEnr_<j>` aus Task 2.
- Produces: `applyAiReload()` — übernimmt nur angehakte Zeilen ins Formular, schließt den Dialog, zeigt Erfolgs-Toast.

- [ ] **Step 1: Playwright-Test schreiben (RED)**

Skript `scratchpad/t3.py` (App auf :5050):
```python
import json
from playwright.sync_api import sync_playwright
FIELDS = {"name":"Barolo Riserva","region":"Piemont","grape":"Nebbiolo",
          "notes":"Kräftig","taste_profile":{"body":4}}
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"ok": True, "fields": FIELDS})))
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://localhost:5050/", wait_until="load")
    pg.evaluate("() => openWineModal(null, {})")   # add mode, empty
    pg.wait_for_timeout(300)
    pg.evaluate("() => reloadViaAi()")
    pg.wait_for_timeout(1200)
    # uncheck the region row (find row whose label == label_region text)
    pg.evaluate("""() => {
      var rows = Array.from(document.querySelectorAll('#aiChanges tr'));
      rows.forEach(function(tr){
        var lbl = tr.querySelector('.vr-field'); var chk = tr.querySelector('input[type=checkbox]');
        if (lbl && chk && lbl.textContent === T.label_region) chk.checked = false;
      });
    }""")
    pg.evaluate("() => applyAiReload()")
    pg.wait_for_timeout(400)
    r = pg.evaluate("""() => ({
      modal: getComputedStyle(document.getElementById('aiReloadModal')).display,
      grape: document.getElementById('wine_grape').value,
      region: document.getElementById('wine_region').value,
      notes: document.getElementById('wine_notes').value,
      taste: document.getElementById('wine_taste_profile').value
    })""")
    print(r); print("errors:", errs if errs else "none")
    b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/t3.py`
Expected VOR Implementierung: FEHLER — `applyAiReload is not defined` (pageerror), Felder leer.

- [ ] **Step 2: `applyAiReload` implementieren**

Im JS-Block (direkt nach `arCancel`) einfügen:
```js
function applyAiReload() {
  if (!_arPending) { closeAiReload(); return; }
  var changes = _arPending.changes, enrich = _arPending.enrich;
  changes.forEach(function(c, i) {
    var chk = document.getElementById('arChk_' + i);
    if (!chk || !chk.checked) return;
    if (c.f.rating) {
      var slider = document.getElementById('wine_rating');
      if (slider) { slider.value = c.nv; updateRatingPreview(); }
      return;
    }
    var el = document.getElementById(c.f.el);
    if (el) el.value = c.nv;
  });
  enrich.forEach(function(en, j) {
    var chk = document.getElementById('arEnr_' + j);
    if (!chk || !chk.checked) return;
    var el = document.getElementById(en.e.el);
    if (el) el.value = JSON.stringify(en.val);
  });
  closeAiReload();
  showReloadToast(T.vr_applied || T.reload_filled, true);
}
```

- [ ] **Step 3: Test laufen lassen (GREEN)**

Run: `& .venv/Scripts/python.exe scratchpad/t3.py`
Expected:
- `modal: none` (Dialog geschlossen)
- `grape: Nebbiolo` (angehakt → übernommen)
- `region:` **leer** (abgewählt → nicht übernommen)
- `notes: Kräftig`
- `taste:` enthält `{"body":4}` (Enrichment übernommen)
- `errors: none`

- [ ] **Step 4: „Keine Änderungen"-Fall prüfen**

Skript `scratchpad/t3b.py`: KI-Antwort = bereits vorhandene Werte, kein Enrichment → Dialog darf NICHT öffnen, Toast erscheint.
```python
import json
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(status=200,
        content_type="application/json",
        body=json.dumps({"ok": True, "fields": {"name":"Same","region":"Rioja"}})))
    pg.goto("http://localhost:5050/", wait_until="load")
    pg.evaluate("() => openWineModal('1', {name:'Same', region:'Rioja'})")
    pg.wait_for_timeout(400)
    pg.evaluate("() => reloadViaAi()")
    pg.wait_for_timeout(1200)
    r = pg.evaluate("""() => ({
      modal: getComputedStyle(document.getElementById('aiReloadModal')).display,
      toast: (document.getElementById('reloadToast')||{}).textContent || ''
    })""")
    print(r); b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/t3b.py`
Expected: `modal: none`, `toast` == "Keine neuen Daten" (bzw. Sprache).

- [ ] **Step 5: Vivino-Regression + volle Testsuite**

Skript `scratchpad/t3c.py`: prüft dass der Vivino-Flow unverändert existiert:
```python
from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True); pg = b.new_page()
    pg.goto("http://localhost:5050/", wait_until="load")
    r = pg.evaluate("""() => ({
      vivinoModal: !!document.getElementById('vivinoReloadModal'),
      vrConfirm: typeof vrConfirm === 'function',
      reloadViaVivino: typeof reloadViaVivino === 'function'
    })""")
    print(r); b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/t3c.py`
Expected: alle `True`.

Dann volle Suite:
Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 390 passed.

- [ ] **Step 6: Commit**

```bash
git add wine-tracker/app/templates/_wine_edit_modal.html
git commit -m "Apply only the checked AI reload suggestions"
```

---

## Self-Review

**Spec-Abdeckung:**
- „Kopfzeile was die KI erkannt hat" → Task 2 `renderAiReload` (`#aiIdentified`). ✓
- „Checkbox-Änderungstabelle nur mit Änderungen" → Task 2 `arComputeChanges`/`renderAiReload`. ✓
- „Enrichment als eigene Checkbox-Zeilen mit Summary" → Task 2 `arComputeEnrich` + Enrichment-Rows. ✓
- „pro Feld wählbar, nur angehaktes übernehmen" → Task 3 `applyAiReload`. ✓
- „keine Änderungen → kein Dialog, Toast" → Task 2 `openAiReload` early-return, verifiziert Task 3 Step 4. ✓
- „Rating nur wenn Slider 0" → Task 2 `arComputeChanges` Rating-Zweig. ✓
- „Vivino-Flow unverändert" → Task 3 Step 5 Regressionscheck. ✓
- i18n 7 Sprachen → Task 1 Step 3. ✓

**Placeholder-Scan:** keine TBD/TODO; vollständiger Code in jedem Code-Step. ✓

**Typ-Konsistenz:** `_AR_FIELDS`/`_AR_ENRICH`/`_arPending`, Checkbox-IDs `arChk_<i>`/`arEnr_<j>`, Funktionsnamen `openAiReload/arComputeChanges/arComputeEnrich/renderAiReload/applyAiReload/closeAiReload/arCancel` durchgängig identisch verwendet. ✓
