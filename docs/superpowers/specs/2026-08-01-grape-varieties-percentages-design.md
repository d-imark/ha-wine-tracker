# Rebsorten als 1‑n mit Prozenten — Design-Spec

**Datum:** 2026-08-01
**Status:** Entwurf zur Freigabe
**Betrifft:** Wine Tracker DI (`wine-tracker/`)

## Ziel

Ein Wein soll **eine bis mehrere Rebsorten** tragen, jede mit **optionaler Prozentangabe** (Verschnitt). Das heutige einzelne Freitextfeld `wines.grape` wird durch ein strukturiertes, normalisiertes Modell mit Referenz-Anbindung ersetzt — bei minimalem Impact auf bestehende Lese-/Such-/Filter-/Export-Pfade.

## Entscheidungen (aus dem Brainstorming)

1. **Prozente optional, keine Summenpflicht.** Summe wird nur als nicht-blockierender Hinweis angezeigt.
2. **Kompaktanzeige:** führende Rebsorte (höchstes %, sonst Reihenfolge) + `+N`; volle Liste im Detail.
3. **Altdaten:** Freitext automatisch an `,` / `&` / `/` splitten → einzelne Rebsorten ohne %.
4. **Speichermodell B2:** normalisierte Kind-Tabelle `wine_grapes` mit FK auf `ref_grapes` als **Source of Truth**; `wines.grape` bleibt als **automatisch abgeleiteter Cache-String**.
5. **Farbige Chips** nach `ref_grapes.color` (red/white, sonst neutral) im Editor und Detail.

## Architektur

### Datenmodell

Neue Tabelle (verwaltet in neuem Modul `grapes.py`, analog zu `purchases.py`):

```sql
CREATE TABLE IF NOT EXISTS wine_grapes (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id   INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    grape_id  INTEGER REFERENCES ref_grapes(id),   -- weicher FK, best-effort via match_reference
    name      TEXT NOT NULL,                        -- denormalisiert, autoritativ (wie wines.region)
    pct       REAL,                                 -- optional, NULL erlaubt
    position  INTEGER DEFAULT 0                     -- Eingabereihenfolge
);
CREATE INDEX IF NOT EXISTS idx_wine_grapes_wine ON wine_grapes(wine_id);
```

- **`name`** ist autoritativ. Das spiegelt das bestehende Muster (der Code hält `wines.region`/`grape` als Text, obwohl Referenztabellen existieren). Robust für Export/Import und falls ein `ref_grapes`-Eintrag gelöscht wird.
- **`grape_id`** ist der weiche FK: beim Speichern via `reference.match_reference(db, "grape", name)` best‑effort gesetzt; `NULL` wenn keine Referenz matcht. Liefert Farbe (`ref_grapes.color`) und ermöglicht künftige Rebsorten-Statistiken.
- **`pct`** optional. Keine Validierung auf Summe = 100.

### B2 — Cache-Spalte

`wines.grape` **bleibt bestehen** und wird bei **jedem Speichern** aus `wine_grapes` neu erzeugt:

```
grape = ", ".join(g.name for g in wine_grapes ORDER BY position)
```

Damit lesen **unverändert weiter**: Freitextsuche, Advanced-Filter (Substring matcht jede Sorte im Verschnitt), Tabellen-Sortierung nach Rebsorte, Chat-Kontext, Export-Rückwärtskompatibilität und jede Alt-Anzeige.

`wine_grapes` ist Source of Truth; `wines.grape` ist ein abgeleiteter Cache (nie manuell gepflegt).

### Modul `grapes.py` (neu)

Öffentliche Funktionen:

- `create_wine_grapes_table(db)` — DDL + Index.
- `set_wine_grapes(db, wine_id, entries)` — löscht bestehende Zeilen des Weins, fügt `entries` (Liste `{name, pct}`) ein, setzt `grape_id` via `match_reference`, `position` = Indexreihenfolge; danach `rebuild_cache(db, wine_id)`. Leere/whitespace-Namen werden verworfen.
- `list_wine_grapes(db, wine_id)` — Zeilen geordnet nach `position`, inkl. `color` (LEFT JOIN `ref_grapes`).
- `rebuild_cache(db, wine_id)` — baut `wines.grape` aus den Zeilen neu.
- `split_legacy(text)` — teilt Freitext an `,` `&` `/` `+`, trimmt, dedupliziert (case-insensitiv), erhält Reihenfolge. Reiner String-Helfer (unit-testbar).

### Serialisierungsformat

`wine_json` (API/Templates) erhält zusätzlich:

```json
"grapes": [
  {"name": "Merlot", "pct": 60, "color": "red"},
  {"name": "Cabernet Sauvignon", "pct": 40, "color": "red"},
  {"name": "Cabernet Franc", "pct": null, "color": "red"}
]
```

Reihenfolge = `position`. Führende Rebsorte und `+N` werden clientseitig aus diesem Array abgeleitet (höchstes `pct`, bei Gleichstand/NULL die erste Position).

Formular-Submit sendet ein verstecktes Feld `grapes` mit JSON `[{"name": "...", "pct": 60|null}, ...]` (die Route parst es; unparsebar → als leer behandeln).

## Migration / Backfill

Einmalig in `init_db` nach Anlegen der Tabelle: für jeden Wein **ohne** `wine_grapes`-Zeilen und mit nicht-leerem `grape` → `split_legacy(grape)` → Zeilen (pct NULL), `grape_id` best-effort. `wines.grape` wird anschließend als Cache neu gebaut (idempotent, verändert bestehende Werte i. d. R. nur in der Trennzeichen-Normalisierung). Läuft nur, solange keine Zeilen existieren → mehrfach-sicher.

## UI

### Editor (`_wine_form_fields.html`, Tab „Basis")

Einzelfeld ersetzt durch ein **Zeilen-Widget** `#grapeRows`:

- Pro Zeile: Rebsorten-Input (`list="grapeList"`, Autocomplete gegen `ref_grapes`) + `%`-Input (number, 0–100, optional) + Entfernen-Button. Farbpunkt/Chip-Rand nach aufgelöster Farbe.
- Darunter: Button **„+ Rebsorte"** und ein **Summen-Hinweis** (z. B. „Summe: 100 %" / „Summe: 90 %"), rein informativ, nie blockierend.
- Verstecktes `<input name="grapes">` wird beim Submit aus den Zeilen serialisiert.

### Autocomplete-Quelle

`grapeList`-Datalist wird künftig aus **`ref_grapes.name`** gespeist (statt `used_grapes` = distinct `wines.grape`, was bei Verschnitten Kombi-Strings liefern würde). Neue Context-Variable `ref_grape_names` (oder schlanker Endpoint) ersetzt `used_grapes` als Datalist-Quelle in Wein-Formular und Advanced-Filter.

### Anzeige

- **Karte** (`index.html`): führende Rebsorte + `+N` (Chip mit Farbe der führenden Sorte).
- **Tabelle** (`index.html`): führende Rebsorte + `+N`.
- **Detail** (`index.html`, `stats.html`, `chat.html`): volle Liste, je Zeile „Name — pct %" (pct nur wenn gesetzt), Farbpunkt je Zeile.

### Farbige Chips

Farb-Mapping (CSS): `red` → Weinrot, `white` → Gold/Bernstein, sonst/`NULL` → neutrales Grau. Als kleiner Farbpunkt vor dem Namen bzw. Chip-Rand.

## KI / Vivino / Reconcile

- **Reconcile** (`/api/reference/reconcile`): akzeptiert zusätzlich `grapes: ["Merlot", "Cabernet", ...]` (Liste). Für jede unbekannte Sorte ein Reconcile-Item (Vorschläge + KI-Pick). Rückwärtskompatibel: einzelnes `grape` weiter unterstützt. Client (`reconcileThenSubmit`) sammelt alle Grape-Namen aus den Zeilen und mappt jede vor dem Speichern.
- **KI-Scan/Reanalyze**: JSON-Schema erhält `grapes: [{name, pct}]` (pct optional/nullable) zusätzlich zum bisherigen `grape`. Der Prompt weist an, Verschnitte mit Anteilen (falls bekannt) zu liefern. `populateFormFromAi` / `openAiReload` füllen die Editor-Zeilen. Fällt die KI auf einen einzelnen `grape`-String zurück, wird dieser via `split_legacy`-Logik in Zeilen überführt.
- **Vivino**: Grape-IDs → Namen (bereits vorhanden via `_get_grape_map`) → Liste ohne %. Im Vivino-Abgleich (`_VR_FIELDS`) wird `grape` zum Sonderfall „Liste" (überschreibt die Zeilen statt eines Textfelds).

## Impact-Map (vollständig)

| Datei | Änderung |
|---|---|
| **`grapes.py`** *(neu)* | Tabelle + `set_wine_grapes` / `list_wine_grapes` / `rebuild_cache` / `split_legacy` |
| **`app.py`** `init_db` (~530/541) | `wine_grapes` anlegen; Backfill aus `grape` |
| **`app.py`** add-Route (~962) | `grapes`-JSON parsen → `set_wine_grapes` → Cache |
| **`app.py`** edit-Route (~1093) | dito |
| **`app.py`** wine_json (~1162) | `grapes`-Array anhängen (via `list_wine_grapes`) |
| **`app.py`** Datalist-Context (~449/478) | `ref_grape_names` statt/zusätzlich zu `used_grapes` |
| **`app.py`** Reconcile (3487) | Grape-Liste unterstützen |
| **`app.py`** KI-Schema/Prompt (~2084/2108) | `grapes`-Array mit `pct` |
| **`app.py`** Vivino-Ergebnis (~2232) | Grape-Namen als Liste im Result |
| **`_wine_form_fields.html`** | Zeilen-Widget, Summen-Hinweis, Datalist-Quelle, verstecktes `grapes` |
| **`_wine_edit_modal.html`** | JS: Zeilen render/add/remove, Befüllung aus Wein/KI/Vivino, Submit-Serialisierung, Reconcile pro Sorte, `_VR_FIELDS`/AR-Grape-Sonderfall |
| **`index.html`** | Karte/Tabelle „+N", Detail-Liste, `data-grape`, `viewChangeQty`-Payload, Suchfelder |
| **`stats.html`, `chat.html`** | Detail-Blend-Anzeige |
| **`static/filter-advanced.js`** | Datalist-Quelle (Filter bleibt Text-Substring) |
| **`static/style.css`** | Zeilen-Widget, Chips, Farbpunkte |
| **`export_import.py`** | `grapes`-JSON exportieren/importieren; `grape` für Alt-Dateien behalten |
| **`translations.py`** | neue Keys ×7 Sprachen (Add/Remove/%, Summen-Hinweis) |

## Export / Import

- **Export:** je Wein zusätzlich `grapes: [{name, pct}]`. `grape`-String bleibt im Export (Rückwärtskompatibilität).
- **Import:** wenn `grapes` vorhanden → `set_wine_grapes`. Sonst Fallback: `grape`-String via `split_legacy`. Alt-Dateien (nur `grape`, auch `rebsorte`-Alias) funktionieren unverändert.

## Fehlerbehandlung / Edge Cases

- Unparsebares `grapes`-JSON → wie leere Liste; `wines.grape` wird auf `NULL` gesetzt.
- Doppelte Rebsorte in der Eingabe → dedupliziert (erste gewinnt, % der ersten).
- `pct` außerhalb 0–100 oder nicht-numerisch → verworfen (Zeile bleibt, pct = NULL).
- Wein ohne Rebsorten → gültig (`grape` = NULL, Anzeige zeigt nichts).
- Löschen eines Weins → `ON DELETE CASCADE` räumt `wine_grapes`.
- `grape_id` NULL (Custom/kein Match) → Chip neutral‑grau; kein Bruch.

## Tests

- **`test_grapes.py`** *(neu)*: `split_legacy` (Trennzeichen, Dedup, Reihenfolge); `set_wine_grapes`/`list_wine_grapes` Roundtrip inkl. pct/position/`grape_id`-Auflösung; `rebuild_cache`; Cascade-Delete; Backfill aus Freitext.
- **`test_api.py`**: `wine_json` enthält `grapes`-Array in korrekter Reihenfolge inkl. Farbe.
- **`test_routes.py`**: Add/Edit mit `grapes`-JSON → Zeilen + Cache; Reconcile mit Grape-Liste liefert Items pro unbekannter Sorte.
- **`test_export_import.py`**: Roundtrip mit Verschnitt + %; Import einer Alt-Datei ohne `grapes`.

## Nicht im Scope (YAGNI)

- Statistik/Charts nach Rebsorte (der FK `grape_id` bereitet es vor, aber keine Aggregation jetzt).
- Erzwungene Summe = 100 %.
- Automatisches Anlegen von `ref_grapes`-Custom-Einträgen beim Wein-Speichern (bleibt wie heute: nur über Reconcile/Vivino/Referenzseite).
