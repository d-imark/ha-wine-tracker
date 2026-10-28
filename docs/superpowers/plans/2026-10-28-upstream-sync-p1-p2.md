# Upstream-Abgleich P1 (Bugfixes) + P2 (Alkoholgehalt) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upstream-Bugfixes übernehmen und den Alkoholgehalt für Wein und Spirituosen in `wines.alcohol_pct` vereinheitlichen, inkl. Migration von `spirit_details.abv`.

**Architecture:** Flask + SQLite, serverseitig gerenderte Templates mit Inline-JS; erweiterter Filter und Tabelle lesen `card.dataset`. Migrationen laufen in `init_db()`; datenverschiebende einmal über `_migration_done`/`_mark_migration_done` (`app_meta`).

**Tech Stack:** Python 3 / Flask / sqlite3, Vanilla JS, pytest, Node (`node --test`), Playwright mit Edge (`channel="msedge"`) für Browser-Prüfungen.

**Spec:** `docs/superpowers/specs/2026-10-28-upstream-sync-design.md` (Pakete P1, P2)

## Global Constraints

- Branch `feature/upstream-sync` (basiert auf `feature/search`). Commits nur lokal, kein Push.
- Spaltenname exakt `alcohol_pct REAL` auf `wines` (wie upstream).
- Formularfeld `name="alcohol_pct"`, `id="wine_alcohol_pct"`, `min="0" max="100" step="0.1"`; Platzhalter Wein `13.5`, Spirituose `46.0`.
- Weingut bleibt `winery`; upstreams `producer` nur beim Import → `winery`, wenn `winery` leer.
- Übersetzungen in allen 7 Sprachen von `translations.py`.
- Tests gezielt laufen lassen; volle Suite erst vor dem Release.
- Pro Task ein Commit; Commit-Messages englisch, im Stil des Repos (Imperativ, ohne Präfix).

## Review Focus

1. Ein Gerät mit gespeicherter Tabellenspalte `abv` (`localStorage wineTableCols.bar`) → Spalte heisst danach `alcohol_pct` und bleibt sichtbar. → Task 7, Browser-Prüfung.
2. Filter-Preset in der DB mit Bedingung auf `abv` → nach dem Start auf `alcohol_pct`, Filter liefert dieselben Flaschen. → Task 4, `test_migration_rewrites_abv_in_filter_presets`.
3. Zweiter App-Start nach der Migration → nichts ändert sich, kein Fehler (Spalte `abv` existiert nicht mehr). → Task 4, `test_alcohol_migration_is_idempotent`.
4. Mengen-Klick (+/−) auf einer Spirituose → `alcohol_pct` bleibt erhalten (Teil-Update ohne Feld). → Task 4, `test_partial_edit_keeps_alcohol_pct`.
5. Import eines alten Fork-Exports (JSON mit `spirit_details.abv`, CSV mit Spalte `abv`) → Wert landet in `alcohol_pct`. → Task 5.

---

## P1 — Bugfixes

### Task 1: `ai_provider: none` bleibt `none`

**Files:**
- Modify: `wine-tracker/app/app.py` (`load_options`, ca. Z. 75–134)
- Test: `wine-tracker/tests/test_helpers.py` (Klasse mit `test_backward_compat_anthropic_autodetect`)

**Interfaces:** Produces: `load_options()` setzt Anthropic nur noch automatisch, wenn keine Quelle `ai_provider` gesetzt hat. Task P4 (spätere Plan) ergänzt die DB-Quelle mit derselben Variable `provider_explicit`.

- [ ] **Step 1: Failing tests**

```python
def test_explicit_none_is_not_overridden(self, tmp_path, monkeypatch):
    opts_file = tmp_path / "options.json"
    opts_file.write_text(json.dumps({"ai_provider": "none", "anthropic_api_key": "sk-x"}))
    monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
    assert wine_app.load_options()["ai_provider"] == "none"

def test_env_none_is_not_overridden(self, tmp_path, monkeypatch):
    opts_file = tmp_path / "options.json"
    opts_file.write_text(json.dumps({"anthropic_api_key": "sk-x"}))
    monkeypatch.setattr(wine_app, "OPTIONS_PATH", str(opts_file))
    monkeypatch.setenv("AI_PROVIDER", "none")
    assert wine_app.load_options()["ai_provider"] == "none"
```
`test_backward_compat_anthropic_autodetect` (Key ohne `ai_provider` → `anthropic`) muss weiter grün sein.

- [ ] **Step 2:** `pytest tests/test_helpers.py -k "none_is_not_overridden" -v` → FAIL (`'anthropic' != 'none'`).
- [ ] **Step 3:** In `load_options()` `provider_explicit` einführen: `True`, wenn `"ai_provider" in opts` (options.json) oder `AI_PROVIDER` per ENV gesetzt ist; Autodetect nur bei `not provider_explicit` (wie upstream 3b06adb).
- [ ] **Step 4:** `pytest tests/test_helpers.py -v` → PASS.
- [ ] **Step 5:** Commit `Keep an explicit ai_provider "none" instead of autodetecting Anthropic`.

### Task 2: Erweiterter Filter — sieben Fehler + fehlende Felder

**Files:**
- Modify: `wine-tracker/app/static/filter-advanced.js` (FIELDS Z. 23–48, GROUPS Z. ~51–56, `evaluate` Z. ~170, `dwStatus` Z. 276, `closeModal` Z. 585, `overwriteEditingPreset` Z. 720)
- Modify: `wine-tracker/app/templates/index.html` (Card `data-bottle_format`, Overlay-Klick Z. ~745, ESC Z. ~755)
- Modify: `wine-tracker/app/translations.py` (`filter_field_purchased_at`, 7 Sprachen)
- Test: `wine-tracker/tests/test_routes.py` (TestIndex)

**Interfaces:** Produces: FIELDS-Einträge `{ key: 'winery', group: 'text', type: 'text', label: 'label_winery' }` und `{ key: 'country', group: 'text', type: 'text', label: 'label_country' }`; Task 7 hängt `alcohol_pct` an dieselbe Liste.

- [ ] **Step 1: Failing test** (`bottle_format` kanonisch, sonst passen Chips/Presets nach AJAX-Speichern nicht)

```python
def test_bottle_format_rendered_canonically(self, client):
    client.post("/add", data={"name": "Magnum", "quantity": "1", "bottle_format": "1.5"}, headers=AJAX)
    client.post("/add", data={"name": "Doppelmagnum", "quantity": "1", "bottle_format": "3"}, headers=AJAX)
    html = client.get("/").data.decode()
    assert 'data-bottle_format="1.5"' in html
    assert 'data-bottle_format="3"' in html
    assert 'data-bottle_format="3.0"' not in html
```
- [ ] **Step 2:** `pytest tests/test_routes.py -k bottle_format_rendered -v` → FAIL.
- [ ] **Step 3:** Umsetzen, jeweils wie upstream 29bc4a6/449dbf2:
  - Card: `data-bottle_format="{{ '%g'|format(w['bottle_format'] or 0.75) }}"`.
  - `evaluate`: nach `if (!rule || !rule.op) continue;` zusätzlich `if (!isRuleActive(rule)) continue;`.
  - `dwStatus`: ohne `until` → `'future'`, wenn `from > aktuelles Jahr`, sonst `null`.
  - `closeModal`: nach dem Zurücksetzen des Edit-Modus `state.rules = {}; load(); updateBadge();`.
  - `overwriteEditingPreset`: leerer Name → `tr('filter_preset_save_prompt')` statt `filter_preset_name_exists`.
  - `index.html`: Overlay-Klick und ESC auf `advancedFilterModal` rufen `AdvancedFilter.closeModal()` statt nur `classList.remove('open')`.
  - `purchased_at` wandert in die Gruppe `text` (Typ `text`); Datumsgruppe `date` samt Eintrag in GROUPS entfällt. Übersetzung DE „Gekauft bei", EN „Purchased at", FR „Acheté chez", IT „Acquistato presso", ES „Comprado en", NL „Gekocht bij", PT analog („Comprado em").
  - FIELDS: `winery` nach `name`, `country` nach `region` (Text).
- [ ] **Step 4:** `pytest tests/test_routes.py tests/test_filter_presets.py -v` → PASS.
- [ ] **Step 5: Browser-Prüfung** (Edge, Testdaten im Scratchpad wie bei der Suche): Bedingung „Jahr >" ohne Wert → alle Weine sichtbar; Bedingung setzen, Modal mit ESC schliessen → Filter greift nicht; Filter „Weingut enthält Gaja" → nur Gaja; „Gekauft bei enthält" auf einen Händlernamen → Treffer.
- [ ] **Step 6:** Commit `Fix advanced filter bugs and add winery and country fields`.

### Task 3: Kleine UI-Fixes (Ingress, Export, Chat, Touch-Hover)

**Files:**
- Modify: `wine-tracker/app/templates/{index,stats,timeline,chat,reference}.html` (`<body>`)
- Modify: `wine-tracker/app/static/style.css` (Z. ~367/388 Tab-Bar/Body, ~808 FAB, ~2184 Chat, ~2758–2765 Filter-Footer)
- Modify: `wine-tracker/app/templates/_settings_modal.html` (Export-Link Z. 160), `wine-tracker/app/static/theme.js` (neu `exportBackup()`)
- Modify: `wine-tracker/app/templates/chat.html` (Fokus-Handler um `KB_INSET_PX`, Z. ~629)
- Test: `wine-tracker/tests/test_routes.py`

**Interfaces:** Produces: Body-Klasse `embedded`, wenn `X-Ingress-Path` gesetzt ist; `exportBackup()` global in `theme.js`.

- [ ] **Step 1: Failing tests**

```python
@pytest.mark.parametrize("path", ["/", "/stats", "/timeline", "/reference"])
def test_body_marked_embedded_under_ingress(self, client, path):
    html = client.get(path, headers={"X-Ingress-Path": "/api/hassio_ingress/x"}).data.decode()
    assert 'class="embedded"' in html or 'embedded"' in html

def test_body_not_embedded_without_ingress(self, client):
    assert "embedded" not in client.get("/").data.decode().split("<body", 1)[1].split(">", 1)[0]

def test_export_is_a_button_with_share_fallback(self, client):
    html = client.get("/").data.decode()
    assert 'id="exportBackupBtn"' in html and "exportBackup()" in html
```
(`/chat` leitet ohne KI um und wird daher nicht parametrisiert.)
- [ ] **Step 2:** `pytest tests/test_routes.py -k "embedded or exportBackup or export_is" -v` → FAIL.
- [ ] **Step 3:** Umsetzen wie upstream 0a5b485, 4d426ff, d5243bb, 3dbf37f: `<body{% if ingress %} class="embedded"{% endif %}>` (chat: `class="chat-page{% if ingress %} embedded{% endif %}"`, auch `reference.html`); CSS-Regeln `body.embedded …` ohne `env(safe-area-inset-bottom)`; Export-`<a>` → `<button type="button" id="exportBackupBtn" … onclick="exportBackup()">` mit `exportBackup()` (fetch → Share-Sheet bei `embedded` + `navigator.canShare`, sonst Blob-Download, bei Fehler `location.href`); Chat `resetWindowScroll()` auf `scroll`, nach Fokus (100/350 ms) und Blur (100 ms); Filter-Footer-Hover in `@media (hover: hover)`.
- [ ] **Step 4:** `pytest tests/test_routes.py -v` → PASS.
- [ ] **Step 5: Browser-Prüfung:** Export-Button in den Einstellungen lädt eine ZIP herunter (Edge, Download-Event).
- [ ] **Step 6:** Commit `Fix export, safe-area and chat scrolling inside the HA app`.

---

## P2 — Alkoholgehalt vereinheitlichen

### Task 4: Spalte, Migration, Speichern

**Files:**
- Modify: `wine-tracker/app/app.py` (`init_db` migrations-Dict Z. ~704; neue Funktion bei den One-shot-Migrationen Z. ~933; Aufruf nach `spirits.create_spirit_tables(db)` Z. ~833; `_spirit_payload_from_form` Z. 616; `add` Z. 1231, `edit` Z. 1301, `duplicate` Z. 1447)
- Modify: `wine-tracker/app/spirits.py` (`DETAIL_FIELDS`, `CREATE TABLE spirit_details`)
- Test: `wine-tracker/tests/test_database.py`, `wine-tracker/tests/test_spirits.py`, `wine-tracker/tests/test_routes.py`

**Interfaces:**
- Produces: `wines.alcohol_pct REAL`; `migrate_abv_to_alcohol_pct(db) -> int` (Anzahl übernommener Werte); `spirits.DETAIL_FIELDS` ohne `"abv"`; `wine_json()` liefert `alcohol_pct` (kommt automatisch aus `SELECT *`).

- [ ] **Step 1: Failing tests**

```python
# test_database.py
def test_alcohol_migration_moves_abv(self, tmp_path, monkeypatch):
    # alte DB: spirit_details mit Spalte abv, Whisky mit abv=46.3, Wein ohne
    ...  # DB im Altformat anlegen, init_db() laufen lassen
    assert row("SELECT alcohol_pct FROM wines WHERE name='Lagavulin'") == 46.3
    assert "abv" not in columns("spirit_details")

def test_alcohol_migration_is_idempotent(...):
    # init_db() zweimal → kein Fehler, Wert unverändert 46.3

def test_migration_rewrites_abv_in_filter_presets(...):
    # Preset {"abv": {"op": "gte", "value": 40}} → {"alcohol_pct": {"op": "gte", "value": 40}}

def test_migration_keeps_existing_alcohol_pct(...):
    # alcohol_pct schon 43.0, abv 46.3 → bleibt 43.0

# test_routes.py
def test_add_and_edit_store_alcohol_pct(self, client, db):
    # /add Wein mit alcohol_pct=13.5 → 13.5; /add whisky mit alcohol_pct=46 → 46.0
def test_partial_edit_keeps_alcohol_pct(self, client, db):
    # /edit nur name+quantity → alcohol_pct unverändert
def test_duplicate_copies_alcohol_pct(self, client, db): ...

# test_spirits.py
def test_details_no_longer_carry_abv(): assert "abv" not in spirits.DETAIL_FIELDS
```
Das Altformat legt der Test mit `CREATE TABLE spirit_details (wine_id INTEGER PRIMARY KEY, abv REAL, …)` vor `init_db()` an; Hilfsfunktionen `row`/`columns` lokal im Test.
- [ ] **Step 2:** Gezielt laufen lassen → FAIL.
- [ ] **Step 3: Umsetzen**
  - `"alcohol_pct": "REAL"` ins migrations-Dict.
  - `migrate_abv_to_alcohol_pct(db)`: läuft nur, wenn `spirit_details` die Spalte `abv` hat (`PRAGMA table_info`), dadurch idempotent ohne `app_meta`. Reihenfolge: (1) `UPDATE wines SET alcohol_pct = (SELECT abv …) WHERE alcohol_pct IS NULL AND EXISTS (… abv IS NOT NULL)`; (2) `filter_presets.conditions` JSON laden, Schlüssel `abv` → `alcohol_pct` (nur wenn `alcohol_pct` noch nicht vorhanden), zurückschreiben; (3) `ALTER TABLE spirit_details DROP COLUMN abv` in `try/except sqlite3.OperationalError` (Fallback: Spalte bleibt, wird nicht mehr gelesen). Aufruf direkt nach `spirits.create_spirit_tables(db)`.
  - `spirits.py`: `"abv"` aus `DETAIL_FIELDS` und aus dem `CREATE TABLE` (neue DBs bekommen die Spalte nicht mehr).
  - `_spirit_payload_from_form`: `"abv"` aus `numeric`.
  - `add`: `alcohol_pct` in INSERT (float oder `None`). `edit`: Teil-Update-Muster wie `winery` (`if "alcohol_pct" in request.form … else wine["alcohol_pct"]`). `duplicate`: `wine["alcohol_pct"]` mitkopieren.
- [ ] **Step 4:** `pytest tests/test_database.py tests/test_spirits.py tests/test_routes.py -v` → PASS.
- [ ] **Step 5:** Commit `Store alcohol content on the bottle for wine and spirits`.

### Task 5: Export und Import

**Files:**
- Modify: `wine-tracker/app/export_import.py` (`WINE_COLUMNS` Z. ~30–58, `CSV_COLUMNS` Z. 62–86, README-Tabelle Z. ~138–141, `build_export_zip` Z. 217, `CSV_ALIASES` Z. 281, `_normalize_wine` Z. 341)
- Test: `wine-tracker/tests/test_export_import.py`

**Interfaces:** Consumes: `wines.alcohol_pct` (Task 4). Produces: Export-Feld `alcohol_pct` (JSON + CSV); `spirit_details` im Export ohne `abv`.

- [ ] **Step 1: Failing tests**

```python
def test_export_carries_alcohol_pct(...):  # JSON-Wein hat "alcohol_pct": 46.3; CSV-Header enthält "alcohol_pct", nicht "abv"
def test_import_legacy_fork_json_abv(...):  # {"category":"whisky","spirit_details":{"abv":46.3}} → alcohol_pct 46.3
def test_import_legacy_csv_abv_column(...):  # CSV-Spalte "abv" → alcohol_pct
def test_import_upstream_export(...):        # {"producer":"Gaja","alcohol_pct":14.5} → winery "Gaja", alcohol_pct 14.5
def test_import_producer_does_not_override_winery(...):  # winery "A", producer "B" → winery "A"
```
- [ ] **Step 2:** `pytest tests/test_export_import.py -v` → FAIL.
- [ ] **Step 3: Umsetzen**
  - `"alcohol_pct"` in `WINE_COLUMNS`; in `CSV_COLUMNS` `"abv"` an derselben Position durch `"alcohol_pct"` ersetzen (Spaltenreihenfolge bleibt); Zeile `w["abv"] = …` entfällt.
  - `CSV_ALIASES`: `"alcohol_pct"`, `"alkohol"`, `"abv"`, `"vol"` → `"alcohol_pct"`; `"producer"`, `"produzent"` → `"producer"` (temporär, siehe unten).
  - `_normalize_wine`: `out["alcohol_pct"] = _coerce_float(w.get("alcohol_pct"))`; ist das leer, Fallback auf `w.get("abv")` bzw. `w["spirit_details"].get("abv")`; `abv` danach aus dem kopierten `spirit_details` entfernen. `producer`: wenn `out["winery"]` leer und `w.get("producer")` gesetzt → `winery`.
  - README-Tabelle: Zeile `alcohol_pct`, `abv` aus der `spirit_details`-Beschreibung.
- [ ] **Step 4:** `pytest tests/test_export_import.py -v` → PASS.
- [ ] **Step 5:** Commit `Export and import alcohol content as a bottle field`.

### Task 6: KI-Felder

**Files:**
- Modify: `wine-tracker/app/app.py` (`_SCHEMA_WINE` Z. ~3029, `_SCHEMA_SPIRIT` Z. 3058, Kontext Z. 3275)
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (`_AR_COMMON_FIELDS` Z. 449, `_AR_SPIRIT_FIELDS` Z. 467, `setIfEmpty` Z. ~1544, Kontext Z. 1725)
- Test: `wine-tracker/tests/test_api.py` (oder `test_helpers.py`, wo `_wine_json_schema` schon getestet wird)

**Interfaces:** Consumes: Formularfeld `wine_alcohol_pct` (Task 7). Produces: KI-Antwortfeld `alcohol_pct` für beide Kategorien.

- [ ] **Step 1: Failing tests**

```python
def test_schema_asks_alcohol_for_wine_and_spirit():
    for cat in ("wine", "whisky", "spirit"):
        s = wine_app._wine_json_schema(cat)
        assert '"alcohol_pct"' in s and '"abv"' not in s

def test_profile_scope_does_not_ask_alcohol():
    assert "alcohol_pct" not in wine_app._wine_json_schema("wine", "profile")
```
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3: Umsetzen**
  - `_SCHEMA_WINE`: nach `country` `("alcohol_pct", '"alcohol_pct": alcohol by volume in percent as number or null', "- alcohol_pct: alcohol by volume as a plain number (e.g. 13.5). Only set it when the label or a reliable source states it - do NOT guess.")`.
  - `_SCHEMA_SPIRIT`: Eintrag `abv` → `alcohol_pct` mit derselben Regel (Beispiel 46.3).
  - Kontext: `wine_context.get("alcohol_pct")` → `"ABV: …"`.
  - Edit-Modal: `abv`-Eintrag aus `_AR_SPIRIT_FIELDS` raus, in `_AR_COMMON_FIELDS` `{ key: 'alcohol_pct', el: 'wine_alcohol_pct', labelKey: 'label_alcohol_pct' }`; `setIfEmpty('wine_alcohol_pct', fields.alcohol_pct)` für beide Kategorien (vor der Kategorie-Verzweigung); Kontext `context.alcohol_pct` aus `wine_alcohol_pct`.
- [ ] **Step 4:** → PASS.
- [ ] **Step 5:** Commit `Ask the AI for alcohol content on wine and spirits alike`.

### Task 7: Formular, Anzeige, Tabelle, Filter, gespeicherte Browser-Einstellungen

**Files:**
- Modify: `wine-tracker/app/templates/_wine_form_fields.html` (Basics-Zeile Z. 34–48; Whisky-Tab Z. 219–227)
- Modify: `wine-tracker/app/static/style.css` (neu `.row3`, neben `.row2` Z. 915)
- Modify: `wine-tracker/app/templates/_wine_edit_modal.html` (Befüllen Z. ~995; Platzhalter je Kategorie in `setWineCategory`-Logik Z. ~768–801)
- Modify: `wine-tracker/app/templates/index.html` (Card-Attribut Z. 141, Card-Zeile Z. 184, `renderCard` Z. ~1451, View-Modal Z. ~1090, `updateCardData` Z. ~1528)
- Modify: `wine-tracker/app/templates/{stats,timeline,chat}.html` (View-Detail-Zeile, wo `spirit_details.abv`/`viewRow` für Spirituosen steht)
- Modify: `wine-tracker/app/static/table-view.js` (COLUMNS Z. 19, Default `bar` Z. 43, gespeicherte Auswahl)
- Modify: `wine-tracker/app/static/filter-advanced.js` (FIELDS, gespeicherter Zustand)
- Modify: `wine-tracker/app/translations.py` (`label_alcohol_pct` in 7 Sprachen; `label_abv` entfernen, wenn unbenutzt)
- Test: `wine-tracker/tests/test_routes.py`, `wine-tracker/tests/test_spirits.py`

**Interfaces:** Consumes: `wines.alcohol_pct` (Task 4). Produces: `data-alcohol_pct` auf der Card; Tabellen-/Filter-Schlüssel `alcohol_pct`; Funktion `migrateAbvKey(list)` lokal in `table-view.js` und in `filter-advanced.js` (je eine Stelle, die `'abv'` → `'alcohol_pct'` ersetzt).

- [ ] **Step 1: Failing tests**

```python
def test_form_has_one_alcohol_field(self, client):
    html = client.get("/").data.decode()
    assert html.count('name="alcohol_pct"') == 1
    assert 'name="abv"' not in html

def test_card_carries_alcohol_pct(self, client):
    client.post("/add", data={"name": "Talisker", "category": "whisky", "quantity": "1",
                              "alcohol_pct": "45.8"}, headers=AJAX)
    html = client.get("/?area=bar").data.decode()
    assert 'data-alcohol_pct="45.8"' in html and "data-abv" not in html
    assert "45.8 %" in html     # Karte zeigt den Wert bei Spirituosen weiterhin
```
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3: Umsetzen**
  - Formular: Basics-Zeile wird `.row3` (Jahrgang bzw. Alter | Alkohol % vol | Menge); `.row3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: .75rem; }`. Platzhalter beim Kategoriewechsel `13.5`/`46.0`. Feld im Whisky-Tab entfällt (Abfüller steht dort dann allein in der Zeile).
  - Edit-Modal befüllt `wine_alcohol_pct` aus `w.alcohol_pct`.
  - Card: `data-alcohol_pct="{{ w['alcohol_pct'] if w['alcohol_pct'] is not none else '' }}"`; Spirituosen-Zeile und `renderCard` lesen `alcohol_pct`; `updateCardData`: `card.dataset.alcohol_pct = w.alcohol_pct == null ? '' : w.alcohol_pct`.
  - Detailansicht (index/stats/timeline/chat): Zeile für alle Kategorien `viewRow('mdi-percent-outline', T.label_alcohol_pct, w.alcohol_pct + ' % vol')`, wenn gesetzt; alte `sd.abv`-Zeile weg.
  - Tabelle: Spalte `{ key: 'alcohol_pct', group: 'general', label: 'label_alcohol_pct', numeric: true, minWidth: 90 }`; Default `bar` nutzt `'alcohol_pct'`. Beim Lesen der gespeicherten Auswahl `'abv'` → `'alcohol_pct'` ersetzen und zurückschreiben.
  - Filter: `{ key: 'alcohol_pct', group: 'numbers', type: 'number', label: 'label_alcohol_pct', min: 0 }` ersetzt `abv`; in `load()` eine gespeicherte Regel `abv` auf `alcohol_pct` umhängen und speichern.
  - Übersetzung `label_alcohol_pct`: DE „Alkohol (% vol)", EN „Alcohol (% vol)", FR „Alcool (% vol)", IT „Alcol (% vol)", ES „Alcohol (% vol)", NL „Alcohol (% vol)", PT „Álcool (% vol)".
- [ ] **Step 4:** `pytest tests/test_routes.py tests/test_spirits.py -v` und `node --test tests/js/search.test.js` → PASS.
- [ ] **Step 5: Browser-Prüfung** (Edge, Scratchpad-DB im **Altformat** mit Whisky `abv=46.3` und Filter-Preset auf `abv`; vor dem Laden `localStorage.wineTableCols.bar = '["winery","abv","quantity"]'` und `wine-advanced-filter` mit `abv`-Regel setzen):
  - Bar-Tabelle zeigt Spalte „Alkohol" mit 46.3; Wein im Formular: Feld sichtbar, Platzhalter 13.5; Whisky: Platzhalter 46.0, kein zweites Feld im Whisky-Tab.
  - Filter „Alkohol ≥ 40" findet den Whisky; das migrierte Preset ebenso.
  - Wein mit 13.5 speichern → Detailansicht zeigt „13.5 % vol"; +/− an der Menge → Wert bleibt.
  - Keine JS-Fehler.
- [ ] **Step 6:** Commit `Show and filter alcohol content for every bottle`.

---

## Gefundene, nicht eingeplante Punkte

- `duplicate` kopiert weder `category` noch `spirit_details`/`spirit_casks`/Rebsorten: Ein duplizierter Whisky wird zum Wein ohne Whisky-Daten. Eigener Fix, sobald freigegeben.
