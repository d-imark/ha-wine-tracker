# Abgleich mit upstream (xenofex7) — Design-Spec

**Datum:** 2026-10-28
**Status:** Entwurf zur Freigabe
**Betrifft:** Wine Tracker DI (`wine-tracker/`)
**Basis:** Branch `feature/search` (69db8ff); upstream `upstream/main` (bea3ce0)

## Ziel

Die brauchbaren Änderungen aus upstream seit dem Fork (Merge-Base `5745a89`, 2026-07-02; 51 Commits bis 2026-10-18) in den Fork holen, ohne dessen eigene Entwicklung (124 Commits: Bildersammlung, Spirituosen, Rebsorten, Käufe, Referenzdaten, Tabellenspalten, Suche …) zu beschädigen.

## Entscheidungen

1. **Kein Merge, sondern paketweise übernehmen.** Ein Probe-Merge ergab Konflikte in 23 Dateien und doppelte Konzepte im Datenmodell. Jedes Paket wird per Cherry-Pick oder — wo der Code zu weit auseinanderliegt — als Nachbau übernommen und an unser Modell angepasst.
2. **Weingut bleibt `winery`.** Upstreams `producer` ist dasselbe Feld und wird nicht übernommen; nur beim Import wird es auf `winery` gemappt.
3. **Alkoholgehalt wird auf upstreams Standard `wines.alcohol_pct` vereinheitlicht** — für Wein *und* Spirituosen. Unser `spirit_details.abv` wird dorthin migriert und entfällt.
4. **Nicht übernommen:** Dev-Add-on-Kanal (`wine-tracker-dev/`, `deploy-dev.sh`, `sync-dev-addon.sh`), Doku-Seite/README/Screenshots, `DESIGN.md` anstelle von `STYLE_GUIDE.md`.
5. **Später, als eigenes Projekt:** Design/Barrierefreiheit (semantische Tokens, WCAG-Kontraste, Fokus-Ring, Tastatur, eigene statt nativer Dialoge, einheitliches Schliessen). Unsere `style.css` hat seit dem Fork +673/−50 Zeilen; die Umstellung muss unsere neuen Komponenten mit abdecken und wird nachgebaut, nicht gepickt.

## Pakete

Reihenfolge = Umsetzungsreihenfolge. Jedes Paket ist für sich testbar und wird einzeln committet.

### P1 — Bugfixes

| Upstream | Inhalt | Anpassung bei uns |
|---|---|---|
| 3b06adb | `ai_provider: none` wird bei vorhandenem Anthropic-Key zu `anthropic` | Bug besteht bei uns (`load_options`), 1:1 |
| 29bc4a6 | Erweiterter Filter: 7 Fehler (halbe Bedingungen blenden alles aus, ungespeicherte Änderungen greifen beim Schliessen, `bottle_format` "3" vs "3.0", „noch nicht" bei nur Startjahr, Zähler, leerer Preset-Name) | Zähler-Teil ist durch die neue Suche erledigt; Rest je Fehler prüfen und nachziehen |
| 449dbf2 | Kaufdatum-Filter: Textvergleich statt Datumsvergleich | prüfen, ob unsere Käufe-Logik dasselbe Feld nutzt |
| 4d426ff | Export-Download in der HA-Companion-App | prüfen, ob noch zutreffend |
| 0a5b485 | Doppelter Safe-Area-Abstand im Ingress-Frame | prüfen |
| d5243bb | Fenster-Scroll auf der mobilen Chat-Seite | prüfen |
| 3dbf37f | Hängender Hover auf Touch im Filter-Footer | prüfen |

Zusätzlich: Weingut (`winery`) und Land (`country`) fehlen im erweiterten Filter und kommen dazu.

### P2 — Alkoholgehalt vereinheitlichen

**Datenmodell:** neue Spalte `wines.alcohol_pct REAL` (Name und Typ wie upstream).

**Migration** (in `init_db`, idempotent):
1. `ALTER TABLE wines ADD COLUMN alcohol_pct REAL`, falls fehlend.
2. `UPDATE wines SET alcohol_pct = (SELECT abv FROM spirit_details WHERE wine_id = wines.id) WHERE alcohol_pct IS NULL AND EXISTS (SELECT 1 FROM spirit_details WHERE wine_id = wines.id AND abv IS NOT NULL)`.
3. `ALTER TABLE spirit_details DROP COLUMN abv`, sobald die Spalte existiert (SQLite ≥ 3.35; lokal 3.49). Scheitert das, bleibt die Spalte ungenutzt stehen.
4. Gespeicherte Verweise auf das Feld `abv` umschreiben:
   - `filter_presets.conditions` (DB): Feld `abv` → `alcohol_pct`.
   - `localStorage` `wine-advanced-filter` und `wineTableCols.*` (Browser): beim Laden einmalig `abv` → `alcohol_pct`.

**Code:** `abv` verschwindet aus `spirits.DETAIL_FIELDS` und `_spirit_payload_from_form`; `alcohol_pct` wird wie die übrigen `wines`-Spalten in add/edit/duplicate gelesen und geschrieben (Teil-Update: fehlt das Feld im Formular, bleibt der Wert).

**Formular:** ein Feld „Alkohol % vol" im allgemeinen Teil, für Wein und Spirituosen; `min=0 max=100 step=0.1`, Platzhalter je Kategorie (13.5 / 46.0). Das Feld im Whisky-Tab entfällt.

**Anzeige:** Karte zeigt den Wert bei Spirituosen wie bisher; Detailansicht zeigt ihn für alle (Zeile wie upstream: `mdi-percent-outline`, „x % vol"). Tabellenspalte und erweiterter Filter heissen `alcohol_pct` und gelten für beide Bereiche (Tabellenspalte wandert von Gruppe „Spirituosen" in „Wein"/allgemein).

**KI:** Ein Prompt-Feld `alcohol_pct` für beide Kategorien („nur setzen, wenn auf dem Etikett sichtbar"). KI-Diff-Bestätigung und Kontext (`_analyze_wine_from_context`) verwenden `alcohol_pct`.

**Export/Import:** Export schreibt `alcohol_pct` als Weinfeld (CSV und JSON), nicht mehr in `spirit_details`. Import akzeptiert `alcohol_pct`, `alkohol` und — für alte Fork-Exporte — `spirit_details.abv` bzw. CSV-Spalte `abv`. Upstream-Exporte: `producer` → `winery`, wenn `winery` leer.

**Chat:** Wein-Kontext und Bearbeitungs-Tools nutzen `alcohol_pct`.

### P3 — Einstellungen mit Tabs

Upstream 4be0106, e4ac873, 03a0daf, 4878727, 33f444a, 26c58ab, 3a412b6. Unser Modal unterscheidet sich nur in den GitHub-Links → weitgehend 1:1. Tabs: Darstellung, (KI-Anbieter aus P4), Sommelier (nur mit KI), Daten, Info. Konto-Zeile als fixer Footer. Letzter Tab wird lokal gemerkt.

### P4 — KI-Einstellungen in der App

Upstream 5f0a259, aa1e35d, 0fd153e, b6ece0b.

- Tabelle `app_settings (key, value)`; Vorrang **App > ENV > options.json > Defaults** in `load_options()`.
- `GET/POST /api/ai-settings`, `POST /api/ai-settings/test`, `GET /api/ai-settings/models`; Keys nur schreibbar, nie zurückgegeben; nur für nicht-readonly.
- `chat_model` (optional, nur Sommelier-Chat) über `chat_opts()`; unsere Chat-Route nutzt `chat_opts()`.
- **Erweiterung bei uns:** `openai_web_search` als Schalter in `AI_SETTING_KEYS`; Speicherung als `"true"`/`"false"`, `load_options()` parst den Wert als Boolean.
- **Hinweis im UI:** Ist ein Wert in der App überschrieben, steht beim Feld, dass die Add-on-Konfiguration dafür nicht mehr greift (Liste `overrides` aus der API), mit Möglichkeit zum Zurücksetzen.
- Keys liegen im Klartext in der DB (gleiches Niveau wie `options.json`, aber auch im HA-Backup). Der Export enthält sie nicht (exportiert nur Weine) — per Test abgesichert.

### P5 — Einstellungen auf dem Server

Upstream d8faa05, a2a9e97. Tabelle `user_prefs` (pro Benutzer bei Auth), `POST /api/prefs`, Seiten füllen `localStorage` vor dem Theme-Start aus den Server-Werten.

**Erweiterung bei uns:** Whitelist um `wt_area`, `statsPriceBasis`, `wine-advanced-filter` und das Präfix `wineTableCols.` (Präfix-Abgleich statt nur exakter Schlüssel). Vorbefüllung auch in `reference.html`.

### P6 — Mengen-Popover und Rückgängig bei der Menge

Upstream 9469e17, 25ee246. Popover am Flaschen-Badge (Karten, Liste, Raster) und an der Mengenzelle der Tabelle — bei uns nur, wenn die Spalte „Menge" gewählt ist. Rückgängig über `qty_undo=1` an `/edit`: löscht den rückgängig gemachten Timeline-Eintrag statt einen Gegeneintrag zu schreiben. Nicht für readonly.

### P7 — Löschen rückgängig (Nachbau)

Upstream 3974e7b dient nur als Vorlage. **Nicht übernommen wird:** die Wiederherstellung nur der `wines`-Zeile und der Aufräum-Job, der nur `wines.image` und Chat-Bilder als verwendet zählt — er würde bei jedem Start alle Zusatzbilder (`wine_images`) löschen, die älter als 24 h sind.

**Nachbau:**
- Beim Löschen werden die `wines`-Zeile **und** alle Zeilen aus `WINE_CHILD_TABLES` (`wine_grapes`, `wine_purchases`, `wine_images`, `spirit_details`, `spirit_casks`) im Speicher gesichert (max. 20 Einträge, wie upstream). Bilddateien bleiben auf der Platte.
- `POST /api/wine/<id>/restore` stellt alles mit den Original-IDs wieder her und entfernt den Timeline-Eintrag „removed".
- Aufräum-Job beim Start: als verwendet gelten `wines.image`, `wine_images.filename` und `chat_messages.image_path`; nur Dateien älter als 24 h werden gelöscht.
- Undo-Toast mit Fehler-Variante (rot, ohne Undo) für fehlgeschlagene Speichervorgänge.

## Tests

- Jedes Paket bringt seine pytest-Tests mit (upstream-Tests wo übernommen, angepasst an unser Modell).
- P2: Migration mit einer DB im alten Format (Spirituose mit `abv`, Filter-Preset mit `abv`) → Wert in `alcohol_pct`, Preset umgeschrieben, Spalte weg; Import alter Fork-Exporte und upstream-Exporte.
- P4: Keys werden nie zurückgegeben; Export enthält keine Keys; `openai_web_search` als Boolean.
- P7: Löschen + Wiederherstellen erhält Rebsorten, Käufe, Bilder, Spirituosen-Details und Fässer; Aufräum-Job lässt `wine_images`-Dateien stehen.
- Browser-Prüfung pro Paket mit UI-Anteil (Edge via Playwright).
- Volle Suite vor dem Release.

## Release

Alle Pakete zusammen als ein Release. Beide Versionsdateien und beide Changelogs (`CHANGELOG.md`, `wine-tracker/CHANGELOG.md`).
