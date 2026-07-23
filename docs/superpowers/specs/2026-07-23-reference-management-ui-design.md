# Teilprojekt 2: Verwaltungs-UI für Referenzdaten

Datum: 2026-07-23
Status: freigegeben
Teil von: Referenzdaten-Paket (TP2 von 4). Baut auf TP1 (Datenschicht) auf.

## Ziel

Eine Oberfläche, um die in TP1 gebündelten Referenzdaten (Länder, Regionen,
Rebsorten, Weintypen, Flaschenformate) anzusehen und **eigene** Einträge zu
pflegen. Built-in-Einträge sind read-only; eigene (is_custom=1) sind voll
CRUD-fähig.

## Navigation & Seite

- Neuer Top-Nav-Link **„Referenzdaten"** (nur Admin bei aktiver Auth; für
  readonly ausgeblendet/geblockt).
- Eigene Seite `GET /reference` (Muster wie `/stats`, `/timeline`).
- Unter-Tabs je Entität: Länder · Regionen · Rebsorten · Weintypen · Flaschenformate.

## Liste je Entität

- Suchfeld (Client-seitig filtern nach Name; wichtig bei 244 Ländern / 100 Rebsorten).
- Relevante Spalten je Entität:
  - Länder: Code, Name, lat/lon, Aliasse
  - Regionen: Name, Land, lat/lon, Aliasse
  - Rebsorten: Name, Farbe, Aliasse
  - Weintypen: Key, Farbe (Farbfeld), Aliasse
  - Flaschenformate: Name, Liter
- Badge **„Standard"** (built-in, read-only) vs. **„Eigen"** (mit Bearbeiten/Löschen).
- `+ Hinzufügen` je Entität.

## CRUD (nur eigene)

- Anlegen/Bearbeiten über entitätsspezifisches Formular:
  - Region: Land aus Dropdown der Referenzländer (country_code), lat/lon optional.
  - Rebsorte: Name, Farbe (rot/weiß/rosé/other), Aliasse (kommagetrennt).
  - Land: Code (2 Buchstaben), Name, lat/lon, Aliasse.
  - Weintyp: Key, Farbe (Hex), Aliasse.
  - Flaschenformat: Name, Liter.
- Löschen mit Bestätigung.
- Aliasse werden als kommagetrennte Eingabe erfasst und als JSON gespeichert.

## Datenschicht (reference.py)

Verallgemeinerung von `add_custom_entry` zu vollem Custom-CRUD über alle 5 Entitäten:
- `create_custom(db, entity, fields) -> row` (setzt norm, is_custom=1; validiert Pflichtfelder + Eindeutigkeit).
- `update_custom(db, entity, id, fields) -> row` (nur is_custom=1; sonst `PermissionError`).
- `delete_custom(db, entity, id)` (nur is_custom=1; sonst `PermissionError`).
- `get_entry(db, entity, id)`.
- Validierungsfehler → `ValueError`.

## API

- `POST /api/reference/<entity>` → 200 {ok, item} | 400 (Validierung) | 404 (Entität).
- `PUT /api/reference/<entity>/<id>` → 200 | 400 | 403 (built-in) | 404.
- `DELETE /api/reference/<entity>/<id>` → 200 | 403 (built-in) | 404.
- Alle Schreib-Endpunkte durch den bestehenden readonly-Guard geschützt (kein
  Schreiben für readonly-User).

## i18n

Neue Strings (Nav-Label, Entitätsnamen, Spalten-/Feld-Labels, Buttons, Badges,
Bestätigungstexte) in allen 7 Sprachen.

## Wechselwirkung mit Weinen

Weine speichern bis TP3 Freitext und sind nicht mit den Referenzen verknüpft.
Ändern/Löschen eines Referenzeintrags berührt bestehende Weine daher nicht — es
entfernt den Eintrag nur aus den Auswahllisten. Migration/Verknüpfung = TP3.

## Nicht in TP2

- Formular-Integration ins Weinformular, Land-Feld, Migration, Vivino-Matching-
  Einbindung, KI-Abgleich-Dialog (TP3).
- Weltkarte (TP4).
- Bearbeiten/Löschen von built-in-Einträgen (bewusst read-only).

## Testing

Backend test-first:
- `create_custom` legt an (norm/is_custom gesetzt), Pflichtfeld-/Eindeutigkeits-
  Validierung → ValueError.
- `update_custom`/`delete_custom` nur für eigene; built-in → PermissionError.
- API: POST/PUT/DELETE Happy-Path; built-in PUT/DELETE → 403; Validierung → 400;
  unbekannte Entität → 404; readonly-User → geblockt.
UI per Browser-Drive (Tab öffnet, Liste + Suche, eigene anlegen/bearbeiten/löschen,
built-in ohne Buttons).
