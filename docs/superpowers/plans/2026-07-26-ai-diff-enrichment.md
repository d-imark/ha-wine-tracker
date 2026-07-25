# KI-Diff Enrichment vorher→nachher Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Die Enrichment-Zeilen im KI-Abgleich-Diff zeigen eine kompakte, lokalisierte alt→neu-Zusammenfassung statt „✓ (Anzahl)".

**Architecture:** Reine JS-Änderung in `_wine_edit_modal.html`: `arComputeEnrich` liest zusätzlich den alten Wert aus dem versteckten Feld und berechnet alt/neu-Zusammenfassungen; `renderAiReload` rendert Enrichment wie die einfachen Felder (Checkbox · Label · vr-old → vr-new). Neuer Helfer `_arEnrichSummary`.

**Tech Stack:** Vanilla JS, bestehende i18n-Keys (`taste_body/tannin/acidity/sweetness`, `maturity_peak`). Verifikation per Playwright. Backend unverändert.

## Global Constraints

- Nur `_wine_edit_modal.html`; keine Backend-/Schema-/i18n-/CSS-Änderung.
- Zusammenfassungen kompakt + lokalisiert über `T.*`.
- `applyAiReload` (Übernahme) bleibt unverändert; Checkbox-IDs `arEnr_<j>` bleiben.
- Vorhandene Tests bleiben grün (418).

---

### Task 1: Enrichment als alt→neu rendern

**Files:**
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (`arComputeEnrich`, `renderAiReload`; neuer Helfer `_arEnrichSummary`)

**Interfaces:**
- Consumes: `_AR_ENRICH` (`{key, el, labelKey}`), globales `T`, hidden fields `wine_maturity_data/wine_taste_profile/wine_food_pairings`.
- Produces: `_arEnrichSummary(key, value) -> string`; `arComputeEnrich` liefert je Eintrag `{ e, val, oldSummary, newSummary }`.

- [ ] **Step 1: RED-Check-Skript**

App-Neustart (PowerShell):
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*app.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\Users\DominikImark\repos\ha-wine-tracker\scripts\run-dev.local.ps1" -WindowStyle Hidden
Start-Sleep -Seconds 7
```
Skript `scratchpad/e1.py` (stubt KI-Antwort mit Enrichment, Wein hat altes Enrichment):
```python
import json
from playwright.sync_api import sync_playwright
FIELDS = {"name":"X","taste_profile":{"body":5,"tannin":5,"acidity":4,"sweetness":1},
          "maturity_data":{"youth":[2020,2025],"peak":[2030,2040]},
          "food_pairings":["Rind","Wild","Hartkäse"]}
with sync_playwright() as p:
    b=p.chromium.launch(channel="chrome", headless=True); pg=b.new_page()
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(status=200,
        content_type="application/json", body=json.dumps({"ok":True,"fields":FIELDS})))
    pg.goto("http://localhost:5050/", wait_until="load")
    # edit wine with EXISTING enrichment (peak 2028-2035) so we can see old->new
    pg.evaluate("""() => openWineModal('1', {name:'X',
        taste_profile:{body:3,tannin:4,acidity:3,sweetness:2},
        maturity_data:{youth:[2019,2024],peak:[2028,2035]},
        food_pairings:['Fisch']})""")
    pg.wait_for_timeout(400)
    pg.evaluate("() => reloadViaAi()")
    pg.wait_for_timeout(1200)
    r = pg.evaluate("""() => {
      var rows=Array.from(document.querySelectorAll('#aiChanges tr'));
      return rows.map(function(tr){
        var f=tr.querySelector('.vr-field'), o=tr.querySelector('.vr-old'), n=tr.querySelector('.vr-new');
        return {label:f?f.textContent:'', old:o?o.textContent:null, new:n?n.textContent:null,
                colspan:n?n.getAttribute('colspan'):null};
      });
    }""")
    for row in r: print(row)
    print("errors:", errs if errs else "none"); b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/e1.py`
Expected VOR der Implementierung: die Enrichment-Zeilen haben `old: null` und `new` = „✓ (n)" mit `colspan=3` (keine vorher/nachher-Spalten).

- [ ] **Step 2: `_arEnrichSummary`-Helfer einfügen**

In `_wine_edit_modal.html` direkt VOR `function arComputeEnrich` einfügen:
```js
function _arEnrichSummary(key, value) {
  if (value === null || value === undefined) return '—';
  if (key === 'food_pairings') {
    return Array.isArray(value) && value.length ? value.join(', ') : '—';
  }
  if (key === 'maturity_data') {
    var pk = value && value.peak;
    if (Array.isArray(pk) && pk.length === 2 && pk[0] && pk[1]) {
      return (T.maturity_peak || 'Peak') + ' ' + pk[0] + '–' + pk[1];
    }
    var n = value && typeof value === 'object' ? Object.keys(value).length : 0;
    return n ? n + ' ' + (T.maturity_phases || 'phases') : '—';
  }
  if (key === 'taste_profile') {
    var dims = [['body','taste_body'],['tannin','taste_tannin'],
                ['acidity','taste_acidity'],['sweetness','taste_sweetness']];
    var parts = [];
    dims.forEach(function(d) {
      var v = value ? value[d[0]] : undefined;
      if (v !== undefined && v !== null && v !== '') parts.push((T[d[1]] || d[0]) + ' ' + v);
    });
    return parts.length ? parts.join(' · ') : '—';
  }
  return '—';
}
```

- [ ] **Step 3: `arComputeEnrich` — alt-Wert + Zusammenfassungen**

Die Funktion `arComputeEnrich` ersetzen durch:
```js
function arComputeEnrich(fields) {
  var out = [];
  _AR_ENRICH.forEach(function(e) {
    var val = fields[e.key];
    if (val === null || val === undefined) return;
    if (Array.isArray(val) && val.length === 0) return;
    if (typeof val === 'object' && !Array.isArray(val) && Object.keys(val).length === 0) return;
    var oldRaw = null;
    var el = document.getElementById(e.el);
    if (el && el.value) { try { oldRaw = JSON.parse(el.value); } catch (ex) { oldRaw = null; } }
    out.push({
      e: e, val: val,
      oldSummary: _arEnrichSummary(e.key, oldRaw),
      newSummary: _arEnrichSummary(e.key, val)
    });
  });
  return out;
}
```

- [ ] **Step 4: `renderAiReload` — Enrichment-Zeilen als alt→neu**

Den Enrichment-`forEach`-Block in `renderAiReload` ersetzen:
```js
  enrich.forEach(function(en, j) {
    rows += '<tr>' +
      '<td class="ar-check"><input type="checkbox" id="arEnr_' + j + '" checked></td>' +
      '<td class="vr-field">' + (T[en.e.labelKey] || en.e.key) + '</td>' +
      '<td class="vr-old">' + esc(en.oldSummary) + '</td>' +
      '<td class="vr-arrow">→</td>' +
      '<td class="vr-new">' + esc(en.newSummary) + '</td>' +
    '</tr>';
  });
```

- [ ] **Step 5: GREEN-Check**

App neu starten (Step-1-Befehl), dann `& .venv/Scripts/python.exe scratchpad/e1.py`
Expected: die drei Enrichment-Zeilen haben jetzt `colspan: null` und:
- Geschmacksprofil: `old` ≈ „Körper 3 · Tannin 4 · Säure 3 · Süße 2", `new` ≈ „Körper 5 · Tannin 5 · Säure 4 · Süße 1"
- Reifeverlauf: `old` ≈ „Höhepunkt 2028–2035", `new` ≈ „Höhepunkt 2030–2040"
- Food-Pairings: `old` = „Fisch", `new` = „Rind, Wild, Hartkäse"
- `errors: none`

- [ ] **Step 6: Erstbefüllung (kein alter Wert) prüfen**

Skript `scratchpad/e1b.py` wie e1.py, aber `openWineModal(null, {name:'X'})` (Add-Modus, keine alten Werte):
```python
import json
from playwright.sync_api import sync_playwright
FIELDS = {"name":"X","taste_profile":{"body":5,"tannin":5,"acidity":4,"sweetness":1},
          "maturity_data":{"peak":[2030,2040]},"food_pairings":["Rind","Wild"]}
with sync_playwright() as p:
    b=p.chromium.launch(channel="chrome", headless=True); pg=b.new_page()
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(status=200,
        content_type="application/json", body=json.dumps({"ok":True,"fields":FIELDS})))
    pg.goto("http://localhost:5050/", wait_until="load")
    pg.evaluate("() => openWineModal(null, {name:'X'})")
    pg.wait_for_timeout(300)
    pg.evaluate("() => reloadViaAi()")
    pg.wait_for_timeout(1200)
    r = pg.evaluate("""() => Array.from(document.querySelectorAll('#aiChanges tr')).map(function(tr){
        var f=tr.querySelector('.vr-field'), o=tr.querySelector('.vr-old'), n=tr.querySelector('.vr-new');
        return {label:f?f.textContent:'', old:o?o.textContent:null, new:n?n.textContent:null}; })""")
    for row in r: print(row)
    b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/e1b.py`
Expected: Enrichment-Zeilen zeigen `old: „—"` und rechts die neue Zusammenfassung.

- [ ] **Step 7: Volle Testsuite (Regression)**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 418 passed.

- [ ] **Step 8: Commit**

```bash
git add wine-tracker/app/templates/_wine_edit_modal.html
git commit -m "Show AI-diff enrichment as compact before->after summaries"
```

---

## Self-Review

**Spec-Abdeckung:**
- Enrichment alt→neu statt Haken+Zahl → Task 1 Step 4. ✓
- Kompakte, lokalisierte Zusammenfassungen (maturity peak, taste dims, food list) → Task 1 Step 2 (`_arEnrichSummary`). ✓
- Alt-Wert aus verstecktem Feld, `—` bei leer → Task 1 Step 3. ✓
- Checkbox/Übernahme unverändert → Enrichment behält `arEnr_<j>`; `applyAiReload` nicht angefasst. ✓
- Tests (Playwright: mit/ohne alten Wert; Regression) → Steps 5–7. ✓

**Placeholder-Scan:** kein TBD/TODO; vollständiger Code je Step. ✓

**Typ-Konsistenz:** `_arEnrichSummary(key, value)`, `arComputeEnrich`→`{e,val,oldSummary,newSummary}`, verwendet in `renderAiReload` (en.oldSummary/en.newSummary/en.e.labelKey). `applyAiReload` nutzt weiterhin `en.val` — unverändert vorhanden. i18n-Keys `taste_*`, `maturity_peak`, `maturity_phases` existieren. ✓
