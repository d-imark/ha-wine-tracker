# Teilprojekt 1: Referenzdaten-Fundament (Datenschicht)

Datum: 2026-07-23
Status: freigegeben
Teil von: Referenzdaten-Paket (TP1 von 4)

## Kontext & Ziel

Heute sind Region/Herkunft und Rebsorte reine Freitextfelder; das Autocomplete
speist sich nur aus den eigenen bisher erfassten Werten. Land ist nicht separat,
sondern im Freitext der Region enthalten. Die Weltkarte nutzt ein hartcodiertes
`REGION_COORDS` (~66 Einträge).

Ziel des Gesamtpakets: strukturierte, gepflegte Referenzdaten (Länder, Regionen,
Rebsorten, Weintypen, Flaschenformate), gebündelt ausgeliefert, um eigene Einträge
erweiterbar, mit Verwaltungs-UI, sauberer Formular-Integration, separatem Land und
einer besseren Weltkarte.

**TP1 liefert nur die Datenschicht:** Referenztabellen, gebündelter Seed, Matching-
Layer, Lese-API, Build-Skript mit Vivino-Abgleich. Kein UI, keine Formular-/`wines`-/
Kartenänderung.

## Nicht in TP1 (spätere Teilprojekte)

- **TP2:** Verwaltungs-UI (neuer Top-Tab, CRUD über die Referenzdaten).
- **TP3:** Formular-Integration (Referenzlisten im Weinformular, **Land als eigenes
  Feld**, kaskadierend Land→Region), `wines`-Verknüpfung (String vs. FK entscheidet
  TP3), Migration bestehender Freitext-Daten, Einbindung des Matchings in den
  Vivino-Import.
- **TP4:** Weltkarte-Upgrade (Region-/Land-Koordinaten aus den Referenzdaten,
  Landes-Zentroid als Fallback; ersetzt `REGION_COORDS`).

Die `wines`-Tabelle bleibt in TP1 unverändert.

## A. Datenmodell (neue Referenztabellen)

Alle Tabellen via bestehende `init_db`-Migration. Gemeinsame Spalten:
`is_custom` (0 = built-in / 1 = eigen), `sort_order` (INTEGER), `norm` (normalisierter
Name fürs Matching).

- `ref_countries(id PK, code TEXT UNIQUE, name TEXT, norm TEXT, lat REAL, lon REAL,
  aliases TEXT[JSON], is_custom INT DEFAULT 0, sort_order INT DEFAULT 0)`
  - `code` = ISO 3166-1 alpha-2 (primärer Join-Key fürs Vivino-Matching);
    `norm`/`aliases` als Fallback für Namens-Matching (z. B. "Frankreich"/"France").
- `ref_regions(id PK, name TEXT, norm TEXT, country_code TEXT, lat REAL NULL,
  lon REAL NULL, is_custom INT DEFAULT 0, sort_order INT DEFAULT 0)`
  - `country_code` referenziert `ref_countries.code` (logisch; kein harter FK-Zwang).
- `ref_grapes(id PK, name TEXT UNIQUE, norm TEXT, color TEXT NULL, aliases TEXT[JSON],
  is_custom INT DEFAULT 0, sort_order INT DEFAULT 0)`
  - `color` ∈ {red, white, rose, other, NULL}.
- `ref_wine_types(id PK, key TEXT UNIQUE, norm TEXT, color TEXT, aliases TEXT[JSON],
  is_custom INT DEFAULT 0, sort_order INT DEFAULT 0)`
  - `key` = der in `wines.type` gespeicherte Wert (z. B. "Rotwein"); Anzeigename für
    built-in über bestehende Übersetzung `wine_type_<key>`, für eigene = `key` selbst.
  - `color` = Hex (Seed aus den `--wine-*`-Werten).
- `ref_bottle_formats(id PK, name TEXT, norm TEXT, liters REAL, is_custom INT DEFAULT 0,
  sort_order INT DEFAULT 0)`

`norm(s)`: lowercase, Akzente/Diakritika entfernt, Satzzeichen/Anführungszeichen und
Mehrfach-Whitespace normalisiert. Wird beim Insert gesetzt.

## B. Gebündelter Seed (`wine-tracker/app/reference_data.py`)

Statisches Python-Modul (Stil wie `translations.py`), einmalig erzeugt und committet.
Kopfkommentar mit Herkunft/Lizenzen.

Inhalte & Quellen:

| Teil | Quelle | Lizenz |
|------|--------|--------|
| Länder + Zentroid-Koordinaten | Natural Earth (Admin-0) | Public Domain |
| (Alternative: fertige ISO+Koordinaten-CSV) | github.com/gavinr/world-countries-centroids | MIT (Hinweis im Header) |
| ISO-Ländercodes/-namen | ISO 3166-1 | Fakten, frei |
| Weinregionen-Koordinaten + Synonyme | Wikidata | CC0 |
| Rebsorten + Farbe + Synonyme | Wikidata + Allgemeinwissen | CC0 |
| Weinregionen-Basis | vorhandenes `REGION_COORDS` | projekteigen (MIT) |
| Weintypen + Farben | `WINE_TYPES` + `--wine-*` | projekteigen |
| Flaschenformate | vorhandene Formatliste | projekteigen |

Umfang: ~195 Länder, kuratierte große Weinregionen (Basis `REGION_COORDS` + Erweiterung),
~100–200 Rebsorten, 7 Weintypen, 10 Flaschenformate. **Keine Vivino-Daten im
ausgelieferten Seed.**

## C. Seeding-Logik

`seed_reference_data(db)` läuft am Ende von `init_db()`:
- Für jeden built-in Eintrag: per natürlichem Schlüssel prüfen, ob vorhanden
  (Land: `code`; Rebsorte/Weintyp: `norm`/`key`; Format: `norm`; Region: `norm` +
  `country_code`). **Nur einfügen, wenn fehlend.**
- Bestehende Zeilen werden **nie überschrieben oder gelöscht** → eigene Einträge und
  manuelle Änderungen an built-ins bleiben erhalten; neue App-Versionen liefern neue
  built-ins nach.
- Idempotent: mehrfaches Ausführen erzeugt keine Duplikate.

## D. Matching-Layer

`reference.py` (oder in `app.py`) mit reiner Logik (testbar, ohne Netz):

- `normalize_name(s) -> str` — die oben beschriebene Normalisierung.
- `match_reference(db, entity, value, country_code=None) -> row | None`:
  - **country:** Match über ISO-Code (exakt), sonst über `norm`/Aliasse.
  - **wine_type:** Vivino `type_id` → `VIVINO_WINE_TYPES` → `key`; bzw. `norm`/Aliasse.
  - **grape:** `norm` exakt, sonst Alias-Treffer.
  - **region:** `norm` **innerhalb `country_code`**; sonst None.
- `add_custom_entry(db, entity, ...) -> row` — legt einen `is_custom=1`-Eintrag an
  (mit `norm`), idempotent gegen Dubletten.

**Kein-Treffer-Politik (für den späteren Import in TP3, hier als Verhalten definiert):**
- unbekannte **Rebsorte** → automatisch als `is_custom=1` anlegen;
- unbekannte **Region** → nicht anlegen (bleibt in TP3 Freitext am Wein, Karte nutzt
  Landes-Fallback);
- **Land/Weintyp** → immer über Code/Mapping gematcht.

## E. Lese-API

`GET /api/reference/<entity>` mit `entity ∈ {countries, regions, grapes, wine_types,
bottle_formats}` → JSON-Liste, nach `sort_order`, dann Name sortiert.
- `regions` akzeptiert `?country=<code>` zum Filtern.
- Liefert `is_custom` mit, damit TP2 built-in vs. eigen unterscheiden kann.
- Unbekannte Entität → 404.

## F. Build-Skript mit Vivino-Abgleich (`scripts/build_reference_data.py`)

Maintainer-Werkzeug, **nicht Runtime**. Zwei Funktionen:

1. **Generieren:** erzeugt `reference_data.py` aus den PD/CC0-Quellen + projekteigenen
   Konstanten. Committet wird nur die fertige statische Datei.
2. **Vivino-Abgleich (`--vivino-report`):** liest Vivinos Referenzdaten
   (`/api/regions` ~4184, `/api/grapes`, Länder aus den Regionen) und erzeugt einen
   **Lücken-Report** — legt **nichts** automatisch an:
   - **Länder:** Vivino-Codes ohne Entsprechung im Bundle (erwartet ~0).
   - **Rebsorten:** Vivino-Sorten, die per `match_reference` (norm + Aliasse) nicht
     matchen → Liste (Kurationskandidaten).
   - **Regionen:** ungematchte Vivino-Regionen, **gruppiert nach Land** mit Anzahl +
     Beispielen (Volltext optional).
   - **Deckungs-Kennzahlen** (z. B. % gematchte Rebsorten, Anzahl ungematchter Regionen).
   - Nutzt **dieselbe** `match_reference`-Logik wie der Runtime-Import → realistische
     Vorschau, was der spätere Import nicht zuordnen könnte.
   - Ausgabe: `scripts/reference_gap_report.md` (generiertes Artefakt; gitignored,
     optional als Snapshot committbar).
   - Verhalten bei Rate-Limit (Vivino liefert intermittierend 403): Drosselung,
     Retries mit Backoff, lokaler Cache der Rohantworten; klarer Abbruchhinweis statt
     stiller Teilergebnisse.

**ToS-Einordnung:** gleiche Kategorie wie die bestehende Vivino-Suche (automatisierter
Zugriff, ToS-grau), aber es werden **keine Vivino-Daten verteilt** — der Report ist ein
lokales QA-Artefakt; das ausgelieferte `reference_data.py` bleibt PD/CC0 + projekteigen.

## G. Testing

Backend test-first (`pytest`), Vivino-I/O gemockt:
- Migration legt alle 5 Tabellen an (auch auf bestehender DB ohne die Tabellen).
- Seed füllt built-ins (Stichproben: Land "fr" mit Koordinaten, Weintyp "Rotwein" mit
  Farbe, Format "Magnum" = 1.5 l).
- Re-Seed ist idempotent (keine Duplikate; Anzahl bleibt gleich).
- Eine `is_custom=1`-Zeile und eine geänderte built-in-Zeile überleben einen Re-Seed.
- `normalize_name`: Akzente/Anführungszeichen/Case (z. B. "Gewürztraminer" ↔
  "gewurztraminer").
- `match_reference`: Land per Code, Rebsorte per norm + Alias (Syrah↔Shiraz),
  Region landgebunden, Nicht-Treffer → None.
- `add_custom_entry`: legt an, ist idempotent.
- Lese-API: liefert Listen, `?country=` filtert, unbekannte Entität → 404.
- Gap-Report-Diff-Logik: mit gemockten Vivino-Daten werden ungematchte Einträge
  korrekt als „fehlend" erkannt.

## Offene Punkte (bewusst später)

- String-vs-FK-Verknüpfung `wines` ↔ Referenz: TP3.
- Mehrsprachige Anzeige der Ländernamen: zunächst kanonisch englisch + Code; das
  Matching läuft über den Code, daher unkritisch. Lokalisierung ggf. TP2/Display.
- Ob ein Gap-Report-Snapshot committet wird: Maintainer-Entscheidung.
