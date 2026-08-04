# Spirituosen mit Fokus Whisky — Design-Spec

**Datum:** 2026-08-02
**Status:** Entwurf zur Freigabe
**Betrifft:** Wine Tracker DI (`wine-tracker/`)

## Ziel

Neben Wein auch Spirituosen erfassen, mit Whisky als ausgearbeitetem Fall. Beide Bereiche leben in **einer** App und teilen sich die vorhandene Infrastruktur; die fachlichen Felder und die Bedienung sind pro Bereich passend.

## Entscheidungen (aus dem Brainstorming)

1. **Getrennte Bereiche, eine App** — ein Umschalter „Weinkeller | Bar", je eigene Ansicht und Felder. Eine Installation, ein Backup, ein Update.
2. **Whisky im Detail, restliche Spirituosen schlank** — Whisky bekommt den vollen Feldsatz; Gin, Rum, Grappa & Co. teilen sich die Grundfelder. Kein konfigurierbarer Feld-Baukasten.
3. **Versiegelt und offen getrennt, mit Füllstand** — `quantity` zählt ungeöffnete Flaschen, dazu eine offene Flasche mit Öffnungsdatum und Füllstand.
4. **KI-Web-Recherche und Etikett-Scan als Datenquelle, kein Katalog** — whisky.de wurde geprüft und verworfen (Begründung unten).

### Warum kein whisky.de (geprüft am 2026-08-02)

Die `robots.txt` erlaubt zwar `/` generell, sperrt aber genau die benötigten Pfade: `Disallow: /*?q=*` und `Disallow: /*tx_solr*`. Die Flaschensuche liefert ihre Treffer über Solr nach — ohne diese Pfade führt kein Weg zu den Detailseiten. Zusätzlich fehlen strukturierte Daten (kein JSON-LD) und stabile IDs, wie sie die Vivino-Anbindung über Algolia nutzt. Eine Anbindung wäre also regelwidrig **und** dauerhaft fragil. whisky.de bleibt als normale Quelle der KI-Websuche erreichbar.

## Architektur

### Datenmodell

`wines` erhält **eine** neue Spalte:

```sql
ALTER TABLE wines ADD COLUMN category TEXT NOT NULL DEFAULT 'wine';   -- 'wine' | 'whisky' | 'spirit'
```

Alle spirituosenspezifischen Felder liegen in einer 1:1-Kindtabelle, verwaltet vom neuen Modul `spirits.py` (analog zu `purchases.py` und `grapes.py`):

```sql
CREATE TABLE IF NOT EXISTS spirit_details (
    wine_id        INTEGER PRIMARY KEY REFERENCES wines(id) ON DELETE CASCADE,
    abv            REAL,      -- Vol.-%
    age_years      INTEGER,   -- Altersangabe; NULL bei NAS (no age statement)
    distilled_year INTEGER,
    bottled_year   INTEGER,
    cask_summary   TEXT,      -- abgeleiteter Cache aus spirit_casks, z.B. "Ex-Bourbon → PX Sherry"
    bottler        TEXT,      -- Originalabfüllung oder unabhängiger Abfüller
    batch_number   TEXT,      -- Batch-/Chargennummer, z.B. "Batch 003"
    cask_strength  INTEGER DEFAULT 0,   -- 0/1
    single_cask    INTEGER DEFAULT 0,   -- 0/1
    cask_number    TEXT,
    chill_filtered INTEGER,   -- 0/1/NULL (unbekannt)
    peat_ppm       INTEGER,
    opened_at      TEXT,      -- ISO-Datum der offenen Flasche, NULL = keine offen
    fill_level     REAL       -- Prozent 0-100 der offenen Flasche
);
```

### Fässer (1-n, Erstfass und Finishes)

Ein Whisky reift oft in mehreren Fässern nacheinander. Das wird als **geordnete Liste** abgebildet — dasselbe Muster wie die Rebsorten (`wine_grapes`):

```sql
CREATE TABLE IF NOT EXISTS spirit_casks (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    wine_id   INTEGER NOT NULL REFERENCES wines(id) ON DELETE CASCADE,
    cask_id   INTEGER REFERENCES ref_cask_types(id),  -- weicher FK, best-effort
    name      TEXT NOT NULL,     -- autoritativ, z.B. "PX Sherry"
    years     REAL,              -- optionale Reifedauer in diesem Fass
    position  INTEGER DEFAULT 0  -- 0 = Erstfass, 1+ = Finishes in Reihenfolge
);
```

**Die Rolle ergibt sich aus der Position** — kein eigenes Rollenfeld, das inkonsistent werden könnte. Die Oberfläche beschriftet Zeile 1 als „Erstfass", die folgenden als „Finish". Beispiel:

```text
Erstfass   Ex-Bourbon     12 Jahre
Finish     PX Sherry       2 Jahre
```

`spirit_details.cask_summary` wird bei jedem Speichern daraus neu gebaut (`"Ex-Bourbon → PX Sherry"`) und dient Karte, Suche und Filter — genau die Rolle, die `wines.grape` für die Rebsorten spielt. Quelle der Wahrheit ist `spirit_casks`.

Bedient wird das über dasselbe Chip-Feld wie die Rebsorten: im Formular eine antippbare Box mit den Fässern als Chips, dahinter ein Dialog mit einer Zeile je Fass (Fasstyp mit Autovervollständigung + Jahre + Entfernen).

**Warum Kindtabelle statt weiterer Spalten an `wines`:** Die Tabelle hat bereits 26 Spalten; 14 weitere wären bei jedem Wein leer. Da die Filterung clientseitig über `card.dataset` läuft (`applyFilters()` in `index.html`, `filter-advanced.js`), kostet die Kindtabelle keine Filterfähigkeit.

**Unverändert nutzbar:** `wine_images`, `wine_purchases`, `timeline`, `chat_*`, `filter_presets` hängen an `wines.id` und funktionieren für Spirituosen ohne Änderung.

### Kategorie-Wiederverwendung vorhandener Felder

| Spalte in `wines` | Wein | Whisky / Spirituose |
|---|---|---|
| `winery` | Winzer | **Destillerie / Marke** (nur Label ändert sich) |
| `type` | Rotwein, Weisswein … | **Single Malt, Blend, Bourbon, Rye, Gin, Rum …** (eigene Referenzliste) |
| `region`, `country` | Bordeaux, Frankreich | Islay, Schottland (gleiche Referenzlisten) |
| `year` | Jahrgang | **ungenutzt** — stattdessen `distilled_year` / `bottled_year` |
| `grape`, `wine_grapes` | Rebsorten | ungenutzt |
| `drink_from/until`, `maturity_data`, `food_pairings` | Trinkfenster, Reife, Food | ungenutzt |
| `vivino_id`, `vivino_rating` | Vivino | ungenutzt |
| `rating`, `notes`, `price`, `ai_price`, `location`, `bottle_format`, `taste_profile`, `image` | wie bisher | wie bisher |

`taste_profile` wird für Whisky mit anderen Achsen beschriftet (Rauch, Süsse, Frucht, Würze) — dieselbe Speicherstruktur, andere Labels.

### Neue Referenzlisten

Zwei Listen im bestehenden Referenzsystem (mit Alias-Auflösung, Custom-Einträgen und der Referenzseite):

- **`ref_spirit_types`** — Single Malt, Blended Malt, Blended Scotch, Bourbon, Rye, Tennessee, Irish, Grain, Gin, Rum, Cognac, Armagnac, Brandy, Grappa, Tequila, Mezcal, Wodka, Likör, Anderes.
- **`ref_cask_types`** — Ex-Bourbon, Oloroso Sherry, PX Sherry, Fino Sherry, Port, Madeira, Sauternes, Rotwein, Virgin Oak, Rum, Mizunara, Refill Hogshead, Quarter Cask.

Whisky-Regionen (Islay, Speyside, Highlands, Lowlands, Campbeltown, Islands) kommen als Einträge in die vorhandene `ref_regions` mit `country_code = 'GB'`.

**Flaschenformate:** `ref_bottle_formats` kennt heute nur Weingrössen. Ergänzt werden 0,7 l (europäischer Standard für Spirituosen), 0,5 l, 0,35 l, 0,2 l und 0,05 l (Miniatur). Der Default eines neuen Eintrags richtet sich nach der Kategorie: 0,75 l für Wein, **0,7 l für Spirituosen**.

**Typ-Validierung:** `analyze_wine` und `_analyze_wine_from_context` prüfen den gelieferten Typ heute gegen die Konstante `WINE_TYPES` und verwerfen alles andere. Diese Prüfung wird kategorieabhängig und nutzt für Spirituosen die Schlüssel aus `ref_spirit_types` — sonst würde „Single Malt" stillschweigend gelöscht.

## Bedienung

### Bereichsumschalter

In der Kopfzeile ein Umschalter **Weinkeller | Bar**. Er setzt einen Anzeigemodus (in `localStorage` gemerkt, wie der „leere Flaschen"-Schalter), der:

- die Liste auf die Kategorie filtert (`wine` bzw. `whisky` + `spirit`),
- die Typ-Filterreiter aus der passenden Referenzliste speist,
- bestimmt, welche Kategorie ein neu angelegter Eintrag bekommt.

Statistiken und Timeline zeigen standardmässig den aktiven Bereich, mit einer Option „alles".

### Formular

Das bestehende Tab-Layout bleibt. Der Kategoriewert steuert, welche Felder sichtbar sind:

- **Tab Basis** — Name, Destillerie, Typ, Land/Region, Bewertung, Notizen. Statt Jahrgang: Destilliert, Abgefüllt, Alter.
- **Tab Preis & Lager** — unverändert (Einkäufe, Standort, Flaschenformat, KI-Preis).
- **Tab Whisky** (ersetzt „Reife & Geschmack") — Vol.-%, **Fässer** (Chip-Feld mit eigenem Dialog, s.o.), Abfüller, Batch-Nummer, Fassstärke, Single Cask + Fassnummer, Kühlfiltrierung, Torf (ppm), Geschmacksprofil mit Whisky-Achsen.

Die Kategorie wird beim Anlegen aus dem aktiven Bereich gesetzt und ist im Formular änderbar (Umschalten blendet die Feldsätze um).

### Offene Flaschen

`quantity` = versiegelte Flaschen. Höchstens eine offene Flasche pro Eintrag.

- **Öffnen** — `quantity − 1`, `opened_at = heute`, `fill_level = 100`; Timeline-Eintrag `opened`.
- **Füllstand** — Schieberegler in 5-%-Schritten in der Detailansicht.
- **Leer** — `opened_at`/`fill_level` zurücksetzen; Timeline-Eintrag `consumed` (Menge 1).

Anzeige in der Detailansicht:

```text
Versiegelt   2
Offen seit   12.03.2026   [█████░░░░░]  55 %
```

Die Karte zeigt kompakt `2 + 1 offen`. Der Gesamtbestand für Statistiken ist `quantity + (1 wenn offen)`.

Zwei neue Timeline-Aktionen: `opened` und `refilled` (Füllstandskorrektur nach oben, selten, aber sonst wirkt die Historie falsch).

## KI

`_wine_json_schema()` und `_wine_json_rules()` werden kategorieabhängig:

- **Wein** — unverändert.
- **Whisky/Spirituose** — statt Rebsorten, Trinkfenster, Reifephasen und Food-Pairings: `abv`, `age_years`, `distilled_year`, `bottled_year`, `bottler`, `batch_number`, `cask_strength`, `single_cask`, `peat_ppm` sowie `casks` als **Array** `[{name, years}]` in Reifereihenfolge. Geschmacksprofil mit Whisky-Achsen. `ai_rationale`, Preis in konfigurierter Währung und die Winzer-/Destillerie-Schutzregel gelten unverändert.

Der Etikett-Scan, die Web-Recherche, der Abgleich-Dialog mit Häkchen und die Referenz-Kanonisierung (`_canonicalize_ai_fields`) bleiben mechanisch identisch; letztere bekommt `cask_type` und `spirit_type` als weitere Entitäten. Die Fässer erscheinen im Abgleich als **eine** Zeile mit Häkchen (`Ex-Bourbon → PX Sherry`), genau wie die Rebsorten — nicht als Einzelfelder.

Vivino wird für Spirituosen ausgeblendet (Button und Reload-Pfad).

## Export / Import

`WINE_COLUMNS` erhält `category`. Jeder Eintrag bekommt zusätzlich ein Objekt `spirit_details` und ein Array `casks` (`[{name, years}]`), analog zum bestehenden `grapes`-Array. Beim Import ohne `category` gilt `wine` — alte Archive bleiben also gültig. Die CSV-Ansicht bekommt `category`, `abv` und die Fass-Zusammenfassung; die restlichen Whisky-Felder bleiben der JSON-Datei vorbehalten.

## Fehlerbehandlung und Randfälle

- Kategorie unbekannt oder leer → `wine` (Default der Spalte).
- `spirit_details` fehlt bei einem Whisky → alle Felder gelten als leer, kein Fehler.
- „Öffnen" bei `quantity = 0` → Aktion nicht angeboten.
- `fill_level` ausserhalb 0–100 oder nicht numerisch → verworfen.
- Offene Flasche und `quantity = 0` → gültiger Zustand (letzte Flasche offen).
- Kategoriewechsel eines bestehenden Eintrags → die Felder der anderen Kategorie bleiben in der DB erhalten, werden aber nicht angezeigt; so ist ein versehentlicher Wechsel verlustfrei umkehrbar.
- Löschen eines Eintrags → `ON DELETE CASCADE` räumt `spirit_details` und `spirit_casks`.
- Fass ohne Namen → Zeile wird verworfen; `years` ohne Fassname ergibt keinen Eintrag.
- Nur ein Fass erfasst → gilt als Erstfass, kein Finish; die Zusammenfassung ist schlicht der Fassname.
- Zweimal derselbe Fasstyp hintereinander (z.B. Refill) → **kein** Zusammenlegen; anders als bei Rebsorten ist die Wiederholung hier fachlich sinnvoll. Die Alias-Auflösung (`Bourbon` → `Ex-Bourbon`) greift trotzdem pro Zeile.

## Migration

Beim Start, idempotent wie die bestehenden Migrationen:

1. `category`-Spalte anlegen (Default `wine`) — alle vorhandenen Weine bleiben Wein.
2. `spirit_details` und `spirit_casks` anlegen.
3. `ref_spirit_types` und `ref_cask_types` anlegen und seeden; Whisky-Regionen in `ref_regions` und Spirituosen-Flaschengrössen in `ref_bottle_formats` ergänzen.

Kein Backfill nötig — es gibt noch keine Spirituosen.

## Tests

- **`test_spirits.py`** (neu) — `set_details`/`get_details`-Roundtrip, Fässer-Liste inklusive Reihenfolge, `years` und aufgebauter `cask_summary`, Alias-Auflösung pro Fass, Wiederholung desselben Fasstyps bleibt erhalten, Öffnen/Füllstand/Leeren inklusive Timeline-Einträgen, Cascade-Delete, Randfälle (Öffnen bei 0, ungültiger Füllstand, Fass ohne Namen).
- **`test_routes.py`** — Anlegen mit `category=whisky` speichert `spirit_details`; ein Wein bleibt unberührt.
- **`test_api.py`** — `wine_json` enthält `category` und `spirit_details`.
- **`test_export_import.py`** — Roundtrip mit Whisky; Import eines Alt-Archivs ohne `category`.
- **`test_helpers.py`** — Whisky-Schema enthält `cask_type`/`abv` und **keine** Rebsorten/Trinkfenster.
- Playwright — Bereichsumschalter, Whisky-Formular, Öffnen-Ablauf mit Füllstand.

## Impact-Map

| Datei | Änderung |
|---|---|
| **`spirits.py`** *(neu)* | Tabellen, `get_details`/`set_details`, `set_casks`/`list_casks`/`rebuild_cask_summary`, `open_bottle`/`set_fill_level`/`finish_bottle` |
| `app.py` `init_db` | `category`-Spalte, `spirit_details`, `spirit_casks`, neue Referenzlisten seeden |
| `app.py` add/edit-Routen | `category` und `spirit_details` speichern |
| `app.py` `wine_json`, index-Route | `category` + `spirit_details` mitliefern, Liste nach Bereich filtern |
| `app.py` KI-Schema/Prompts | kategorieabhängige Felder |
| `app.py` neue Routen | Öffnen, Füllstand, Leer |
| `reference.py`, `reference_data.py` | `ref_spirit_types`, `ref_cask_types`, Whisky-Regionen |
| `_wine_form_fields.html` | Kategorie-Umschaltung, Whisky-Tab, Fass-Chipfeld |
| `_wine_edit_modal.html` | Feldsichtbarkeit, Vivino ausblenden, Whisky-Felder im Abgleich, Fässer-Dialog (analog Rebsorten) |
| `index.html` | Bereichsumschalter, Karte mit „offen", Detailaktionen |
| `stats.html`, `timeline.html` | Bereichsfilter, neue Timeline-Aktionen |
| `filter-advanced.js` | Whisky-Filterfelder |
| `style.css` | Umschalter, Füllstandsanzeige |
| `export_import.py` | `category` + `spirit_details` |
| `translations.py` | neue Schlüssel in 7 Sprachen |

## Nicht im Scope

Cocktail-Rezepte, Sammler-/Wertentwicklung, Bewertungen Dritter, eigene Feldsätze für Rum und Gin, mehrere gleichzeitig offene Flaschen desselben Eintrags, Umrechnung Füllstand in Milliliter, Fassgrösse/-volumen als eigenes Feld, Anzahl Flaschen einer limitierten Abfüllung.
