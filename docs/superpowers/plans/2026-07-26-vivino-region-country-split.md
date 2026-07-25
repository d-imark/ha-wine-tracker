# Vivino Region/Land-Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Vivino-Ergebnisse liefern Region und Land getrennt; Reload-Confirm und Add-Flow füllen beide Formularfelder.

**Architecture:** Backend `vivino_search` gibt `region` (nur Regionsname) + neu `country` zurück (statt „Region, Land"). Frontend: `_VR_FIELDS` bekommt eine country-Zeile; der Add-Flow (`selectVivinoResult`/`populateFormFromAi`) setzt `wine_country`; beide Trefferlisten zeigen das Land.

**Tech Stack:** Flask, Vanilla JS, pytest (gemockte Algolia-Antwort via `_mock_algolia`), Playwright.

## Global Constraints

- Nur künftig; keine Migration bestehender Weine.
- Kein neuer i18n-Key (`label_country` nutzen).
- Bestehende Vivino-Feldübernahme/Bild/`vivino_id`/`vivino_rating` unverändert.
- Vorhandene Tests bleiben grün (418 + neuer Backend-Test).

---

### Task 1: Backend — Region und Land getrennt zurückgeben

**Files:**
- Modify: `wine-tracker/app/app.py` (`vivino_search`, Ergebnis-Dict)
- Test: `wine-tracker/tests/test_api.py` (neuer Test in `TestVivinoSearch`)

**Interfaces:**
- Produces: jedes `/api/vivino-search`-Ergebnis hat `region` (nur Regionsname) und `country` (Klarname oder "").

- [ ] **Step 1: Failing test schreiben**

In `wine-tracker/tests/test_api.py` in der Klasse `TestVivinoSearch` (z.B. nach `test_vivino_search_finds_catalog_producer`) einfügen:
```python
    @patch("requests.Session")
    def test_vivino_search_splits_region_and_country(self, MockSession, monkeypatch, client):
        """Region and country come back as two separate fields, not 'Region, Country'."""
        _mock_algolia(MockSession, monkeypatch, response=_algolia_response([_algolia_hit()]))
        resp = client.get("/api/vivino-search?q=maurice+schueller")
        assert resp.status_code == 200
        r = json.loads(resp.data)["results"][0]
        assert r["region"] == "Alsace Grand Cru 'Goldert'"   # region only, no country
        assert "," not in r["region"]
        assert r["country"] == "France"                       # fr -> France via _COUNTRY_NAMES
```

- [ ] **Step 2: Test laufen lassen (fail)**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_api.py::TestVivinoSearch::test_vivino_search_splits_region_and_country -q`
Expected: FAIL — `region` ist aktuell `"Alsace Grand Cru 'Goldert', France"` (Komma enthalten) und `r["country"]` fehlt (`KeyError`).

- [ ] **Step 3: `vivino_search` anpassen**

Den Block, der `region_str` bildet und im Ergebnis setzt, ändern. Die Zeilen
```python
            region_str = (
                f"{region_name}, {country_name}" if region_name and country_name
                else region_name or country_name
            )
```
**entfernen**. Im `results.append({...})` die Zeile
```python
                "region": region_str,
```
ersetzen durch
```python
                "region": region_name,
                "country": country_name,
```
(`region_name` und `country_name` werden weiter oben unverändert berechnet.)

- [ ] **Step 4: Test grün + volle Suite**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_api.py::TestVivinoSearch -q`
Expected: alle grün (inkl. `test_vivino_search_finds_catalog_producer`, dessen `"Alsace..." in r["region"]` weiterhin gilt).
Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 419 passed (418 + 1 neu).

- [ ] **Step 5: Commit**

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_api.py
git commit -m "Vivino search returns region and country as separate fields"
```

---

### Task 2: Frontend — beide Felder in Reload-Confirm und Add-Flow setzen

**Files:**
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (`_VR_FIELDS`, `vrRenderCandidates`, `renderVivinoResults`, `selectVivinoResult`, `populateFormFromAi`)

**Interfaces:**
- Consumes: `region`+`country` je Vivino-Ergebnis (Task 1); Felder `wine_region`/`wine_country`.

- [ ] **Step 1: `_VR_FIELDS` um Land erweitern**

Den Block ersetzen:
```js
var _VR_FIELDS = [
  { key: 'name',      el: 'wine_name',    labelKey: 'vr_field_name' },
  { key: 'wine_type', el: 'wine_type',    labelKey: 'vr_field_type', type: 'wine_type' },
  { key: 'region',    el: 'wine_region',  labelKey: 'vr_field_region' },
  { key: 'country',   el: 'wine_country', labelKey: 'label_country' },
  { key: 'grape',     el: 'wine_grape',   labelKey: 'vr_field_grape' }
];
```

- [ ] **Step 2: Land in beiden Trefferlisten anzeigen**

In `renderVivinoResults` (Add-Flow) und `vrRenderCandidates` (Reload-Confirm) steht jeweils dieselbe Zeile `    if (item.region) meta.push(item.region);`. In **beiden** direkt danach ergänzen:
```js
    if (item.region) meta.push(item.region);
    if (item.country) meta.push(item.country);
```

- [ ] **Step 3: Add-Flow — country ins fields-Objekt**

In `selectVivinoResult` nach `if (item.region) fields.region = item.region;` einfügen:
```js
  if (item.region) fields.region = item.region;
  if (item.country) fields.country = item.country;
```

- [ ] **Step 4: `populateFormFromAi` — Land-Feld setzen**

In `populateFormFromAi` nach der `wine_region`-Zeile einfügen:
```js
  if (fields.region) document.getElementById('wine_region').value = fields.region;
  if (fields.country) document.getElementById('wine_country').value = fields.country;
```

- [ ] **Step 5: RED/GREEN — Playwright beide Flows**

App neu starten:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*app.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\Users\DominikImark\repos\ha-wine-tracker\scripts\run-dev.local.ps1" -WindowStyle Hidden
Start-Sleep -Seconds 7
```
Skript `scratchpad/vc.py`:
```python
from playwright.sync_api import sync_playwright
BASE="http://localhost:5050"
CAND={"name":"Maurice Schueller","region":"Alsace","country":"France","wine_type":"Weisswein",
      "year":2020,"rating":4.2,"grape":"Gewürztraminer","image_url":"https://images.vivino.com/x.png"}
with sync_playwright() as p:
    b=p.chromium.launch(channel="chrome", headless=True); pg=b.new_page()
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/api/wine/*/images/vivino", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true,"image":{"id":1,"category":"vivino","filename":"v.jpg"}}'))
    pg.route("**/api/vivino-image", lambda r: r.fulfill(status=200, content_type="application/json", body='{"ok":true,"filename":"v.jpg"}'))
    wid=pg.request.post(BASE+"/add", form={"name":"VCsplit","quantity":"1"}, headers={"X-Requested-With":"XMLHttpRequest"}).json()["wine"]["id"]
    pg.goto(BASE+"/", wait_until="load")
    # Reload-confirm flow
    pg.evaluate(f"() => openWineModal('{wid}', {{name:'VCsplit', region:'Alt', country:''}})"); pg.wait_for_timeout(400)
    pg.evaluate("(c)=>openVivinoReload([c], true)", CAND); pg.wait_for_timeout(200)
    pg.evaluate("()=>vrSelectCandidate(0)"); pg.wait_for_timeout(200)
    pg.evaluate("()=>vrConfirm()"); pg.wait_for_timeout(500)
    rc = pg.evaluate("()=>({region:document.getElementById('wine_region').value, country:document.getElementById('wine_country').value})")
    print("reload-confirm:", rc)
    # Add-flow
    pg.evaluate("() => openWineModal(null, {})"); pg.wait_for_timeout(300)
    pg.evaluate("(c)=>{ window._vivinoResults=[c]; selectVivinoResult(0); }", CAND); pg.wait_for_timeout(400)
    af = pg.evaluate("()=>({region:document.getElementById('wine_region').value, country:document.getElementById('wine_country').value})")
    print("add-flow:", af)
    print("errors:", errs if errs else "none"); b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/vc.py`
Expected: beide Zeilen `region: 'Alsace'`, `country: 'France'` (Region und Land getrennt in den jeweiligen Feldern); `errors: none`.
(Vor der Implementierung: `country` leer bzw. `_VR_FIELDS`/fields kennen kein country.)

- [ ] **Step 6: Volle Testsuite**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 419 passed (Frontend-Change berührt Backend nicht).

- [ ] **Step 7: Commit**

```bash
git add wine-tracker/app/templates/_wine_edit_modal.html
git commit -m "Apply Vivino region and country into their separate form fields"
```

---

## Self-Review

**Spec-Abdeckung:**
- Backend region/country getrennt → Task 1 Step 3 + Test Step 1. ✓
- Reload-Confirm `_VR_FIELDS` + Land → Task 2 Step 1 (+ vrComputeChanges/Übernahme automatisch). ✓
- Kandidatenlisten zeigen Land → Task 2 Step 2 (beide). ✓
- Add-Flow setzt beide Felder → Task 2 Steps 3–4. ✓
- `label_country` statt neuem Key → Task 2 Step 1. ✓
- Keine Migration → nicht implementiert (Scope). ✓
- Tests backend (pytest) + frontend (Playwright) → Task 1 Step 4, Task 2 Step 5. ✓

**Placeholder-Scan:** kein TBD/TODO; vollständiger Code je Step. ✓

**Typ-Konsistenz:** Ergebnis-Keys `region`/`country` (Backend) == `item.region`/`item.country` (Frontend) == `fields.region`/`fields.country`; `_VR_FIELDS`-Eintrag el `wine_country`, key `country`; `label_country` existiert. ✓
