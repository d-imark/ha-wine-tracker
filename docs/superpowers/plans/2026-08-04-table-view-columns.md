# Table View Columns Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the width-driven column hiding in the table view with an explicit per-area column choice, make wide tables scroll on a phone with type and name pinned, and add own / AI / effective price columns.

**Architecture:** The table view moves out of `index.html` into its own static module `app/static/table-view.js`, mirroring the existing `filter-advanced.js`. The module owns a column catalogue, renders from `card.dataset`, and persists the chosen columns in `localStorage` per area. The effective price is materialised into the dataset (`data-price_effective`) so the existing sort and the advanced filter keep working through plain dataset lookups.

**Tech Stack:** Flask + Jinja2 templates, vanilla JS (no build step), plain CSS, pytest, Playwright.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-04-table-view-columns-design.md`
- `Typ` and `Name` are fixed columns; the other 19 are selectable.
- Storage keys: `wineTableCols.cellar` and `wineTableCols.bar`, JSON array of column keys.
- Column order is catalogue order, never pick order. Reordering is out of scope.
- Statistics and total value must not change: they keep counting only real purchase prices.
- Effective price = own price, else AI price, else empty.
- Every new user-facing string needs all 7 languages: de, en, fr, it, es, pt, nl.
- Never commit `scripts/run-dev.local.ps1` (gitignored, contains a real API key).
- Run targeted tests during work; the full suite only before a release push.
- Restart the dev server after editing `index.html` (Jinja caches templates; CSS and static JS are served fresh).

---

### Task 1: Dataset foundation (ai_price, price_effective, grapes)

The table reads `card.dataset`. Three values it needs are missing today.

**Files:**
- Modify: `wine-tracker/app/templates/index.html` (card attribute block ~line 119; `updateCardData` ~line 1541)
- Test: `wine-tracker/tests/test_routes.py`

**Interfaces:**
- Produces `effective_price(row)` in `app.py` - the single definition of the
  fallback rule; returns the own price if non-empty, else the AI price, else `""`
- Produces `wine_json()["price_effective"]` and a `price_effective` template
  variable (dict keyed by wine id)
- Produces dataset attributes:
  - `data-ai_price` - the AI/market price
  - `data-price_effective` - the computed value, never recomputed client-side
  - `data-grapes` - JSON array of `{name, pct}`, which is what `grapeLead()` expects

- [ ] **Step 1: Write the failing test**

Append to `wine-tracker/tests/test_routes.py`:

```python
class TestCardDatasetPriceFields:
    """The table view reads card.dataset, so the price trio must live there."""

    @staticmethod
    def _card(html, name):
        return [chunk for chunk in html.split('<div class="card') if name in chunk][0]

    def test_own_price_wins(self, client, db):
        client.post("/add", data={"name": "Beide Preise", "quantity": "1",
                                  "price": "60", "ai_price": "65"}, headers=AJAX)
        card = self._card(client.get("/").data.decode(), "Beide Preise")
        assert 'data-price_effective="60' in card
        assert 'data-ai_price="65' in card

    def test_ai_price_fills_in(self, client, db):
        client.post("/add", data={"name": "Nur KI", "quantity": "1",
                                  "ai_price": "42"}, headers=AJAX)
        card = self._card(client.get("/").data.decode(), "Nur KI")
        assert 'data-price_effective="42' in card

    def test_empty_when_neither(self, client, db):
        client.post("/add", data={"name": "Kein Preis", "quantity": "1"}, headers=AJAX)
        card = self._card(client.get("/").data.decode(), "Kein Preis")
        assert 'data-price_effective=""' in card

    def test_structured_grapes_are_exposed(self, client, db):
        import json as J
        client.post("/add", data={
            "name": "Cuvee Dataset", "quantity": "1",
            "grapes": J.dumps([{"name": "Merlot", "pct": 70},
                               {"name": "Syrah", "pct": 30}]),
        }, headers=AJAX)
        card = self._card(client.get("/").data.decode(), "Cuvee Dataset")
        assert "data-grapes=" in card
        assert "Merlot" in card and "Syrah" in card
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_routes.py -q -k CardDatasetPrice`

Expected: FAIL - `data-price_effective` is not in the markup.

- [ ] **Step 3: Compute the effective price in ONE place**

The fallback rule must not be written twice. Put it in `app.py` as a helper and
feed both renderers from it - the server-rendered card list and `wine_json()`,
which is what the JS card updater consumes after a save.

Add near the other small helpers in `wine-tracker/app/app.py`:

```python
def effective_price(row):
    """The price to show: the user's own, else the AI's estimate, else empty.

    One definition, used by the card list and by wine_json(), so the table, the
    sort and the advanced filter can all read a ready-made value.
    """
    return (row["price"] if row["price"] not in (None, "") else row["ai_price"]) or ""
```

In `wine_json()`, after `d = dict(row)`:

```python
    d["price_effective"] = effective_price(row)
```

In the index route, the cards come from `SELECT * FROM wines`, which yields
`sqlite3.Row` objects the template cannot extend. Pass a lookup alongside them:

```python
    price_effective = {w["id"]: effective_price(w) for w in wines}
```

and hand `price_effective=price_effective` to `render_template`.

- [ ] **Step 4: Read the computed value in both renderers**

In `wine-tracker/app/templates/index.html`, in the `<div class="card ...">`
attribute block, directly after the existing `data-price="{{ w['price'] or '' }}"`:

```jinja
       data-ai_price="{{ w['ai_price'] or '' }}"
       data-price_effective="{{ price_effective[w['id']] }}"
       data-grapes="{{ (w['grapes'] or []) | tojson | forceescape }}"
```

In `updateCardData(card, w)`, after `card.dataset.price = w.price || '';`:

```javascript
  card.dataset.ai_price = w.ai_price || '';
  // Computed server-side by effective_price() - never recompute the rule here.
  card.dataset.price_effective = w.price_effective || '';
  card.dataset.grapes = JSON.stringify(w.grapes || []);
```

- [ ] **Step 5: Add a unit test for the helper**

Append to `wine-tracker/tests/test_helpers.py`:

```python
class TestEffectivePrice:
    """One definition of the fallback rule, used by both renderers."""

    @pytest.mark.parametrize("own,ai,expected", [
        (60.0, 65.0, 60.0),
        (None, 42.0, 42.0),
        ("",   42.0, 42.0),
        (60.0, None, 60.0),
        (None, None, ""),
        (0.0,  42.0, 42.0),   # a zero own price is not a price
    ])
    def test_rule(self, own, ai, expected):
        assert wine_app.effective_price({"price": own, "ai_price": ai}) == expected
```

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_helpers.py -q -k EffectivePrice`

Expected: PASS, 6 cases.

- [ ] **Step 6: Run the route test to verify it passes**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_routes.py -q -k CardDatasetPrice`

Expected: PASS, 4 tests.

- [ ] **Step 7: Check nothing else broke**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_routes.py tests/test_api.py -q`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add wine-tracker/app/app.py wine-tracker/app/templates/index.html         wine-tracker/tests/test_routes.py wine-tracker/tests/test_helpers.py
git commit -m "Expose ai_price, effective price and structured grapes on the card dataset"
```

---

### Task 2: Extract the table view into its own module

Pure refactor, no behaviour change. `index.html` already carries ~1800 lines of
JS; the table view is a self-contained unit and the next three tasks all touch it.

**Files:**
- Create: `wine-tracker/app/static/table-view.js`
- Modify: `wine-tracker/app/templates/index.html` (delete `renderTableView`/`removeTableView`, lines ~341-460; add the script tag)

**Interfaces:**
- Consumes: `card.dataset` (Task 1); globals `T`, `CURRENCY`, `escapeHtml()`, `grapeLead()`, `viewWineById()`, `window._area`
- Produces: `window.TableView = { render, remove }`

- [ ] **Step 1: Create the module carrying the current behaviour**

Create `wine-tracker/app/static/table-view.js` as an IIFE that assigns
`window.TableView`. Move the bodies of `renderTableView()`, `removeTableView()`
and the nested `sortTableBy()` across verbatim, renaming the two entry points to
`render` and `remove`. Keep the seven hard-coded columns for now: this step must
not change what the user sees.

- [ ] **Step 2: Load the module and delegate to it**

In `index.html`, next to the existing `filter-advanced.js` script tag:

```html
<script src="{{ ingress }}/static/table-view.js"></script>
```

Delete the two moved functions and change `setViewMode()`:

```javascript
  if (mode === 'table') {
    TableView.render();
  } else {
    TableView.remove();
  }
```

- [ ] **Step 3: Write the refactor guard**

Create `scratchpad/verify_table_refactor.py`:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5050/", wait_until="networkidle")
    pg.evaluate("setViewMode('table')")
    pg.wait_for_timeout(800)
    cols = pg.evaluate("() => document.querySelectorAll('#wineTable thead th').length")
    rows = pg.evaluate("() => document.querySelectorAll('#wineTable tbody tr').length")
    print("  Spalten:", cols, " Zeilen:", rows, " JS-Fehler:", errs)
    assert cols == 7, cols
    assert rows > 0, rows
    assert not errs, errs
    b.close()
print("RESULT: ALL CHECKS PASSED")
```

- [ ] **Step 4: Restart the dev server and run the guard**

Restart via `scripts/run-dev.local.ps1`, then run the script.

Expected: 7 columns, rows > 0, no JS errors, `RESULT: ALL CHECKS PASSED`.

- [ ] **Step 5: Commit**

```bash
git add wine-tracker/app/static/table-view.js wine-tracker/app/templates/index.html
git commit -m "Extract the table view into app/static/table-view.js"
```

---

### Task 3: Column catalogue, picker dialog, per-area persistence

**Files:**
- Modify: `wine-tracker/app/static/table-view.js`
- Modify: `wine-tracker/app/templates/index.html` (picker dialog markup)
- Modify: `wine-tracker/app/static/style.css` (toolbar + dialog rows)
- Modify: `wine-tracker/app/translations.py` (8 new keys x 7 languages)

**Interfaces:**
- Produces, inside the module:
  - `COLUMNS` - ordered array of `{key, group, label, numeric?, minWidth}`
  - `DEFAULTS` - `{cellar: [keys], bar: [keys]}`
  - `chosenColumns()` returns the selected `COLUMNS` entries in catalogue order
  - `setChosenColumns(keys)` persists and re-renders
  - `window.TableView.openPicker()`, `window.TableView.resetColumns()`

- [ ] **Step 1: Define the catalogue and the defaults**

Near the top of the IIFE. `Typ` and `Name` are deliberately absent: they are
always rendered and are the pinned pair on mobile.

```javascript
  // Catalogue order IS display order. Every key is a card.dataset key.
  var COLUMNS = [
    { key: 'year',            group: 'wine',    label: 'table_col_year',      numeric: true, minWidth: 80 },
    { key: 'region',          group: 'wine',    label: 'table_col_region',                   minWidth: 150 },
    { key: 'country',         group: 'wine',    label: 'label_country',                      minWidth: 130 },
    { key: 'grape',           group: 'wine',    label: 'table_col_grape',                    minWidth: 150 },
    { key: 'winery',          group: 'wine',    label: 'label_winery',                       minWidth: 150 },
    { key: 'drink_until',     group: 'wine',    label: 'label_drink_until',   numeric: true, minWidth: 100 },
    { key: 'age_years',       group: 'spirits', label: 'label_age',           numeric: true, minWidth: 90 },
    { key: 'abv',             group: 'spirits', label: 'label_abv',           numeric: true, minWidth: 90 },
    { key: 'cask',            group: 'spirits', label: 'label_casks',                        minWidth: 170 },
    { key: 'bottler',         group: 'spirits', label: 'label_bottler',                      minWidth: 150 },
    { key: 'price',           group: 'price',   label: 'table_col_price_own', numeric: true, minWidth: 110 },
    { key: 'ai_price',        group: 'price',   label: 'label_ai_price',      numeric: true, minWidth: 110 },
    { key: 'price_effective', group: 'price',   label: 'table_col_price_eff', numeric: true, minWidth: 110 },
    { key: 'quantity',        group: 'general', label: 'table_col_quantity',  numeric: true, minWidth: 70 },
    { key: 'rating',          group: 'general', label: 'label_rating',        numeric: true, minWidth: 90 },
    { key: 'vivino_rating',   group: 'general', label: 'vr_field_rating',     numeric: true, minWidth: 90 },
    { key: 'location',        group: 'general', label: 'label_location',                     minWidth: 130 },
    { key: 'bottle_format',   group: 'general', label: 'label_bottle_format', numeric: true, minWidth: 100 },
    { key: 'purchased_at',    group: 'general', label: 'label_purchased_at',                 minWidth: 120 }
  ];
  var GROUP_ORDER = ['wine', 'spirits', 'price', 'general'];
  var GROUP_LABEL = { wine: 'colgrp_wine', spirits: 'colgrp_spirits',
                      price: 'colgrp_price', general: 'colgrp_general' };

  var DEFAULTS = {
    cellar: ['year', 'region', 'grape', 'price_effective', 'quantity'],
    bar:    ['age_years', 'abv', 'cask', 'price_effective', 'quantity']
  };
```

Before continuing, confirm every `label` key already exists in
`translations.py` except the eight added in Step 5:

Run: `cd wine-tracker && grep -c '"label_purchased_at":' app/translations.py`

Expected: `7`. Repeat for `label_drink_until`, `label_rating`, `vr_field_rating`,
`label_location`, `label_bottle_format`, `label_country`, `label_winery`,
`label_age`, `label_abv`, `label_casks`, `label_bottler`, `label_ai_price`,
`table_col_year`, `table_col_region`, `table_col_grape`, `table_col_quantity`.
Any that returns `0` must be added alongside Step 5.

- [ ] **Step 2: Read and write the choice per area**

```javascript
  function areaKey() {
    return (window._area === 'bar') ? 'bar' : 'cellar';
  }

  function chosenColumns() {
    var area = areaKey();
    var stored = null;
    try { stored = JSON.parse(localStorage.getItem('wineTableCols.' + area)); } catch (e) {}
    if (!Array.isArray(stored)) stored = DEFAULTS[area];
    var want = {};
    stored.forEach(function (k) { want[k] = true; });
    // Filtering the catalogue (rather than mapping the stored list) keeps
    // catalogue order and silently drops keys that no longer exist, so removing
    // a column later cannot break someone's stored selection.
    return COLUMNS.filter(function (c) { return want[c.key]; });
  }

  function setChosenColumns(keys) {
    try {
      localStorage.setItem('wineTableCols.' + areaKey(), JSON.stringify(keys));
    } catch (e) {}
    render();
  }

  function resetColumns() {
    try { localStorage.removeItem('wineTableCols.' + areaKey()); } catch (e) {}
    render();
    openPicker();   // re-render the checkboxes to match
  }
```

- [ ] **Step 3: Render header and body from the chosen columns**

Replace the hard-coded `thead`/`tbody` strings. Type and name stay first and
keep the `col-type` / `col-name` classes; the rest is generated.

```javascript
  function drinkIcon(d) {
    if (!d.drink_until) return '';
    var yr = new Date().getFullYear();
    var until = parseInt(d.drink_until, 10);
    if (until < yr) return ' <i class="mdi mdi-alert" style="color:#e74c3c;font-size:.75rem"></i>';
    if (until === yr) return ' <i class="mdi mdi-alert" style="color:#e67e22;font-size:.75rem"></i>';
    return ' <i class="mdi mdi-check-circle" style="color:#27ae60;font-size:.75rem"></i>';
  }

  // Returns {html: string} so the caller never has to guess whether to escape.
  function cellHtml(d, col) {
    if (col.key === 'grape') {
      var list = [];
      try { list = JSON.parse(d.grapes || '[]'); } catch (e) {}
      return escapeHtml(grapeLead(list) || d.grape || '');
    }
    if (col.key === 'drink_until') {
      return escapeHtml(d.drink_until || '') + drinkIcon(d);
    }
    if (col.group === 'price') {
      var v = d[col.key];
      return v ? escapeHtml(CURRENCY + ' ' + Number(v).toFixed(2)) : '';
    }
    return escapeHtml(d[col.key] || '');
  }
```

Header cell per chosen column:

```javascript
      thead += '<th class="wine-table-sortable col-' + col.key
        + (col.numeric ? ' wine-table-right' : '')
        + '" data-sort="' + col.key
        + '" style="min-width:' + col.minWidth + 'px">'
        + escapeHtml(T[col.label] || col.key)
        + ' <i class="mdi mdi-swap-vertical"></i></th>';
```

Body cell per chosen column:

```javascript
      tbody += '<td class="col-' + col.key
        + (col.numeric ? ' wine-table-right' : '') + '">'
        + cellHtml(d, col) + '</td>';
```

- [ ] **Step 4: Add the toolbar and the picker dialog**

In `render()`, before appending the table, add a toolbar into `#wineGrid`. The
view-mode switch lives in the settings modal, so there is no on-page control to
sit next to; this strip is the entry point.

```javascript
    var bar = document.createElement('div');
    bar.id = 'wineTableToolbar';
    bar.className = 'wine-table-toolbar';
    bar.style.gridColumn = '1 / -1';
    bar.innerHTML = '<button type="button" class="wine-table-colbtn" '
      + 'onclick="TableView.openPicker()">'
      + '<i class="mdi mdi-view-column-outline"></i> '
      + escapeHtml(T.table_columns || 'Columns') + '</button>';
    grid.appendChild(bar);
```

`remove()` must remove `#wineTableToolbar` and the scroll wrapper, not only
`#wineTable`.

`openPicker()` fills `#colPickerBody` and opens the modal. Each checkbox applies
immediately, so the effect is visible while choosing:

```javascript
  function openPicker() {
    var chosen = {};
    chosenColumns().forEach(function (c) { chosen[c.key] = true; });
    var html = '';
    GROUP_ORDER.forEach(function (g) {
      html += '<div class="colpick-group"><div class="colpick-group-label">'
        + escapeHtml(T[GROUP_LABEL[g]] || g) + '</div>';
      COLUMNS.filter(function (c) { return c.group === g; }).forEach(function (c) {
        html += '<label class="colpick-opt"><input type="checkbox" value="' + c.key + '"'
          + (chosen[c.key] ? ' checked' : '')
          + ' onchange="TableView.togglePicked()"> '
          + escapeHtml(T[c.label] || c.key) + '</label>';
      });
      html += '</div>';
    });
    document.getElementById('colPickerBody').innerHTML = html;
    openModal('colPickerModal');
  }

  function togglePicked() {
    var keys = [];
    document.querySelectorAll('#colPickerBody input[type=checkbox]').forEach(function (cb) {
      if (cb.checked) keys.push(cb.value);
    });
    setChosenColumns(keys);
  }
```

Add to `index.html` next to the other modals:

```html
<div class="modal-overlay" id="colPickerModal">
  <div class="modal">
    <div class="modal-header">
      <span>{{ t.table_columns }}</span>
      <button class="modal-close" type="button" onclick="closeModal('colPickerModal')">&times;</button>
    </div>
    <div class="modal-body" id="colPickerBody"></div>
    <div class="modal-footer" style="display:flex;justify-content:space-between;gap:.6rem;padding:.75rem 1.25rem 1.25rem;border-top:1px solid var(--border);">
      <button type="button" class="btn-cancel" onclick="TableView.resetColumns()">{{ t.table_columns_reset }}</button>
      <button type="button" class="btn-submit" style="width:auto;padding:0 1.2rem;" onclick="closeModal('colPickerModal')">{{ t.btn_close }}</button>
    </div>
  </div>
</div>
```

Export the new entry points: `window.TableView = { render, remove, openPicker, togglePicked, resetColumns }`.

- [ ] **Step 5: Add CSS for the toolbar and the picker**

```css
.wine-table-toolbar { display: flex; justify-content: flex-end; padding: 0 0 .5rem; }
.wine-table-colbtn {
  display: inline-flex; align-items: center; gap: .35rem;
  background: none; border: 1px solid var(--border); color: var(--muted);
  border-radius: 8px; padding: .3rem .7rem; font-size: .8rem; cursor: pointer;
}
.wine-table-colbtn:hover { color: var(--text); border-color: var(--text); }
.colpick-group { margin-bottom: .9rem; }
.colpick-group-label {
  font-size: .7rem; font-weight: 700; text-transform: uppercase;
  letter-spacing: .05em; color: var(--muted); margin-bottom: .3rem;
}
.colpick-opt {
  display: flex; align-items: center; gap: .5rem;
  padding: .3rem .2rem; font-size: .88rem; cursor: pointer;
}
.colpick-opt:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
```

- [ ] **Step 6: Add the translation keys in all 7 languages**

New keys and German values:

| Key | de |
|---|---|
| `table_columns` | `Spalten` |
| `table_columns_reset` | `Zurücksetzen` |
| `table_col_price_own` | `Mein Preis` |
| `table_col_price_eff` | `Effektiv` |
| `colgrp_wine` | `Wein` |
| `colgrp_spirits` | `Spirituosen` |
| `colgrp_price` | `Preis` |
| `colgrp_general` | `Allgemein` |

English: `Columns`, `Reset`, `My price`, `Effective`, `Wine`, `Spirits`,
`Price`, `General`. French: `Colonnes`, `Réinitialiser`, `Mon prix`, `Effectif`,
`Vin`, `Spiritueux`, `Prix`, `Général`. Italian: `Colonne`, `Ripristina`,
`Il mio prezzo`, `Effettivo`, `Vino`, `Distillati`, `Prezzo`, `Generale`.
Spanish: `Columnas`, `Restablecer`, `Mi precio`, `Efectivo`, `Vino`,
`Destilados`, `Precio`, `General`. Portuguese: `Colunas`, `Restaurar`,
`O meu preço`, `Efetivo`, `Vinho`, `Destilados`, `Preço`, `Geral`.
Dutch: `Kolommen`, `Herstellen`, `Mijn prijs`, `Effectief`, `Wijn`,
`Gedistilleerd`, `Prijs`, `Algemeen`.

Also confirm `btn_close` exists; if `grep -c '"btn_close":' app/translations.py`
returns `0`, add it too (de `Schliessen`, en `Close`, fr `Fermer`, it `Chiudi`,
es `Cerrar`, pt `Fechar`, nl `Sluiten`).

- [ ] **Step 7: Verify the keys are complete**

Run:

```bash
cd wine-tracker && ../.venv/Scripts/python.exe -c "import sys; sys.path.insert(0,'app'); from translations import TRANSLATIONS as T; ks=['table_columns','table_columns_reset','table_col_price_own','table_col_price_eff','colgrp_wine','colgrp_spirits','colgrp_price','colgrp_general','btn_close']; [print(' ', l, [k for k in ks if k not in T[l]] or 'komplett') for l in ('de','en','fr','it','es','pt','nl')]"
```

Expected: `komplett` on all seven lines.

- [ ] **Step 8: Verify the picker in the browser**

Restart the dev server. Check by hand or with a short Playwright snippet: the
dialog lists 19 checkboxes in 4 groups; unchecking `region` removes exactly that
column; the choice survives a reload; switching to the bar shows the bar
defaults, and switching back restores the cellar choice.

- [ ] **Step 9: Commit**

```bash
git add wine-tracker/app/static/table-view.js wine-tracker/app/templates/index.html \
        wine-tracker/app/static/style.css wine-tracker/app/translations.py
git commit -m "Let the user choose table columns, remembered per area"
```

---

### Task 4: Horizontal scrolling with pinned type and name

**Files:**
- Modify: `wine-tracker/app/static/style.css` (delete the hiding block at ~line 698; replace the fixed widths at ~line 630-644)
- Modify: `wine-tracker/app/static/table-view.js` (wrap the table in the scroll container)

**Interfaces:**
- Consumes: the `col-<key>` classes and inline `min-width` from Task 3
- Produces: `.wine-table-scroll` wrapper; sticky `.col-type` / `.col-name`

- [ ] **Step 1: Delete the width-driven hiding**

In `style.css`, remove the entire block introduced by the comment
`/* ── Table: responsive column hiding ── */` - all four media queries
(`max-width: 900px`, `700px`, `500px` and the `.wine-table-type .mdi` rule
inside the last one). The user's choice now applies at every width.

- [ ] **Step 2: Replace fixed layout with min-widths and a scroll container**

Delete the now-unused `.wine-table-col-year`, `-region`, `-grape`, `-price`,
`-qty` width rules. Change `.wine-table` and add the sticky rules:

```css
.wine-table-scroll { grid-column: 1 / -1; overflow-x: auto; }
.wine-table {
  width: 100%; border-collapse: separate; border-spacing: 0;
  background: var(--surface); font-size: .85rem;
  table-layout: auto;   /* per-column min-width decides, not fixed pixels */
}
/* Type and name stay readable while the rest scrolls under them. They need an
   opaque background: a transparent sticky cell shows the row moving through it.

   The name's sticky offset must equal the type column's actual width. With
   table-layout: auto a plain `width` is only a hint the browser may widen, which
   would leave a gap or an overlap - so the width is pinned with min+max and both
   values come from one variable that cannot disagree with itself. */
.wine-table { --col-type-w: 40px; }
.wine-table th.col-type, .wine-table td.col-type {
  position: sticky; left: 0; z-index: 2; background: var(--surface);
  min-width: var(--col-type-w); max-width: var(--col-type-w); width: var(--col-type-w);
}
.wine-table th.col-name, .wine-table td.col-name {
  position: sticky; left: var(--col-type-w); z-index: 2; background: var(--surface);
  min-width: 160px;
}
.wine-table-row:hover td.col-type,
.wine-table-row:hover td.col-name {
  background: color-mix(in srgb, var(--accent) 8%, var(--surface));
}
```

- [ ] **Step 3: Keep both classes on the type cell**

The existing markup gives the type cell two classes: `wine-table-type` (padding
and centring, line ~636) and `col-type` (the sticky rules above). The generated
header from Task 3 must keep emitting both, or the type column loses either its
padding or its pinning:

```javascript
    thead += '<th class="wine-table-sortable wine-table-type col-type" data-sort="type">'
      + '<i class="mdi mdi-swap-vertical"></i></th>';
```

Delete the `width: 40px` from the old `.wine-table-type` rule - the variable
above owns the width now, and two sources for it is how they drift apart.

- [ ] **Step 4: Wrap the table in the container**

In `render()`, append the table into a `div.wine-table-scroll` instead of
directly into `#wineGrid`. `remove()` removes the wrapper.

- [ ] **Step 5: Write the mobile verification**

Create `scratchpad/verify_table_mobile.py`:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_context(viewport={"width": 390, "height": 800}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5050/", wait_until="networkidle")
    pg.evaluate("setViewMode('table')")
    pg.wait_for_timeout(800)

    # every chosen column must be present - nothing hidden by width any more
    shown = pg.evaluate(
        "() => Array.from(document.querySelectorAll('#wineTable thead th'))"
        ".filter(th => getComputedStyle(th).display !== 'none').length")
    total = pg.evaluate("() => document.querySelectorAll('#wineTable thead th').length")
    print("  Spalten sichtbar:", shown, "von", total)
    assert shown == total, (shown, total)

    sel = "#wineTable tbody tr:first-child td.col-name"
    before = pg.evaluate("() => document.querySelector('%s').getBoundingClientRect().x" % sel)
    pg.evaluate("() => { document.querySelector('.wine-table-scroll').scrollLeft = 400; }")
    pg.wait_for_timeout(300)
    after = pg.evaluate("() => document.querySelector('%s').getBoundingClientRect().x" % sel)
    over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    print("  Name-x vorher", round(before, 1), "nachher", round(after, 1),
          " Dokument-Ueberlauf", over)
    assert abs(before - after) < 2, "Name bleibt nicht stehen"
    assert over <= 0, "die Seite selbst laeuft seitlich ueber"
    assert not errs, errs
    b.close()
print("RESULT: ALL CHECKS PASSED")
```

- [ ] **Step 6: Run it**

Expected: all columns visible, the name cell keeps its x position, the document
itself does not overflow, `RESULT: ALL CHECKS PASSED`.

- [ ] **Step 7: Commit**

```bash
git add wine-tracker/app/static/style.css wine-tracker/app/static/table-view.js
git commit -m "Scroll wide tables sideways instead of hiding columns by width"
```

---

### Task 5: Sorting and filtering for the new numeric and price fields

**Files:**
- Modify: `wine-tracker/app/static/table-view.js` (sort comparator)
- Modify: `wine-tracker/app/static/filter-advanced.js` (`FIELDS` array, ~line 29-40)

**Interfaces:**
- Consumes: `COLUMNS[].numeric` (Task 3), `data-ai_price` / `data-price_effective` (Task 1)
- Produces: advanced-filter fields `ai_price` and `price_effective`

- [ ] **Step 1: Drive the comparator off the catalogue**

The comparator hard-codes `key === 'year' || key === 'price' || key === 'quantity'`,
so `abv`, `age_years`, `rating` and the two new price keys would sort as text
("9" after "10"). Replace that condition with a catalogue lookup:

```javascript
      var col = COLUMNS.filter(function (c) { return c.key === key; })[0];
      if (col && col.numeric) {
        aVal = parseFloat(aVal) || 0;
        bVal = parseFloat(bVal) || 0;
        return asc ? aVal - bVal : bVal - aVal;
      }
```

- [ ] **Step 2: Add the two price fields to the advanced filter**

In `filter-advanced.js`, in `FIELDS` directly after the existing `price` entry:

```javascript
    { key: 'ai_price',        group: 'numbers', type: 'number', label: 'label_ai_price' },
    { key: 'price_effective', group: 'numbers', type: 'number', label: 'table_col_price_eff' },
```

Nothing else is needed: `cardValue()` is `ds[fieldKey]` and both keys now exist
on the dataset from Task 1.

- [ ] **Step 3: Write the verification**

Create `scratchpad/verify_table_sort_filter.py`:

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_context(viewport={"width": 1400, "height": 1000}).new_page()
    errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto("http://127.0.0.1:5050/", wait_until="networkidle")
    pg.evaluate("setViewMode('table')")
    pg.wait_for_timeout(800)

    pg.evaluate("() => document.querySelector('#wineTable th[data-sort=price_effective]').click()")
    pg.wait_for_timeout(500)
    vals = pg.evaluate(
        "() => Array.from(document.querySelectorAll('#wineTable tbody tr'))"
        ".filter(r => r.style.display !== 'none')"
        ".map(r => { const c = r.querySelector('td.col-price_effective');"
        "  return c ? (parseFloat((c.textContent||'').replace(/[^0-9.]/g,'')) || 0) : 0; })")
    print("  erste Werte:", vals[:6])
    assert vals == sorted(vals), "nicht numerisch sortiert"

    pg.evaluate("AdvancedFilter.openModal()")
    pg.wait_for_selector("#advancedFilterModal.open", timeout=8000)
    pg.wait_for_timeout(500)
    fields = pg.evaluate(
        "() => Array.from(document.querySelectorAll('#advancedFilterModal option'))"
        ".map(o => o.value)")
    assert "ai_price" in fields, fields
    assert "price_effective" in fields, fields
    print("  Filterfelder vorhanden, JS-Fehler:", errs)
    assert not errs, errs
    b.close()
print("RESULT: ALL CHECKS PASSED")
```

- [ ] **Step 4: Run it**

Expected: `RESULT: ALL CHECKS PASSED`.

- [ ] **Step 5: Commit**

```bash
git add wine-tracker/app/static/table-view.js wine-tracker/app/static/filter-advanced.js
git commit -m "Sort every numeric column numerically; filter by AI and effective price"
```

---

### Task 6: Integration verification

**Files:**
- Create: `scratchpad/verify_table_columns.py`

- [ ] **Step 1: Write the consolidated script**

One script covering: the picker lists 19 columns in 4 groups; toggling a column
adds/removes exactly that column; the choice survives a reload; cellar and bar
keep separate choices; at 390px every chosen column is present and type + name
stay pinned while the wrapper scrolls; the three price columns show own / AI /
effective including a row where the AI price fills in; sorting by
`price_effective` is numeric; the advanced filter offers both new fields; no JS
errors. Follow the existing scripts' conventions: ASCII-safe printing, a
`check(cond, msg)` helper, `RESULT: ALL CHECKS PASSED` on success and a non-zero
exit on failure.

Seed the fallback case first, so the effective-price column has a row to prove
itself with:

```python
pg.request.post("http://127.0.0.1:5050/add", form={
    "name": "Nur KI Preis", "quantity": "1", "ai_price": "42"})
```

Remove that bottle again at the end of the script - the dev database holds real
bottles and test rows distort the statistics:

```python
import sqlite3
db = sqlite3.connect("wine-tracker/app/data/wine.db")
db.execute("DELETE FROM wines WHERE name = 'Nur KI Preis'")
db.commit()
```

- [ ] **Step 2: Run it**

Expected: `RESULT: ALL CHECKS PASSED`.

- [ ] **Step 3: Re-run the neighbouring verification scripts**

The card dataset changed, so run at least `verify_description_field.py`,
`verify_stats_area.py`, `verify_ai_spirit_fields.py`.

Expected: all print `RESULT: ALL CHECKS PASSED`.

- [ ] **Step 4: Run the affected pytest modules**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_routes.py tests/test_api.py -q`

Expected: PASS.

- [ ] **Step 5: Report, do not release**

Summarise what changed and what was verified. Do **not** bump versions, edit
changelogs, commit a release or push: the user approves releases separately.

---

## Notes for the implementer

- **Restart the dev server after editing `index.html`** - Jinja caches templates.
  CSS and static JS are served fresh, so those need only a browser reload.
- The dev launcher is `scripts/run-dev.local.ps1` (carries the OpenAI key,
  gitignored, must never be committed).
- Verification scripts must print ASCII-safe output: Windows consoles are cp1252
  and a raw arrow or umlaut inside `print()` raises `UnicodeEncodeError`.
- Never put a blocking `time.sleep` inside a Playwright route handler - it
  freezes the browser event loop, so timers stop and the UI looks broken. Delay
  inside the page instead.
- `wine-tracker/app/data/wine.db` is the dev database with real bottles. Do not
  delete rows you did not create.
