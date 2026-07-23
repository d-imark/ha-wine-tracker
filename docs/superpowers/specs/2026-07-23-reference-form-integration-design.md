# Teilprojekt 3a: Formular-Integration + Land-Feld

Datum: 2026-07-23
Status: freigegeben
Teil von: Referenzdaten-Paket (TP3a). Baut auf TP1 (Datenschicht) + TP2 (UI/API) auf.

## Ziel

Das Weinformular nutzt die Referenzdaten als Auswahllisten und bekommt ein
separates Land-Feld. Verknüpfung ist **string-basiert** (Wein speichert den
kanonischen Namen), damit bestehende Daten/Filter/Charts/Export/Chat unverändert
funktionieren.

## Nicht in 3a

- Abgleich-Dialog (Fuzzy/KI „bekannt matchen vs. neu anlegen") → TP3b.
- Migration bestehender Freitext-`region`/Land-Daten → TP3c.
- Weintyp aus Referenz inkl. Custom-Typ-Anzeige (Ribbon-Farben/Übersetzungen/
  Charts/Filter) → späterer Schritt (TP3d). In 3a bleibt der Typ das bestehende
  Dropdown der 7 Standardtypen.

## Datenmodell

- Neue Spalte `wines.country TEXT` (via bestehende ADD-COLUMN-Migration in
  `init_db`). Speichert den Ländernamen (kanonisch aus der Referenz, z. B. „France").
- Alle übrigen Felder bleiben wie sie sind (region/grape/bottle_format als String
  bzw. REAL).

## Formular (`_wine_form_fields.html` + Modal-JS)

- **Land** (neu): Auswahl aus `/api/reference/countries`; angezeigt „Name (Code)",
  gespeichert = Name. Freitext erlaubt (datalist), damit unbekannte Länder möglich
  bleiben.
- **Region**: Freitext-Input mit Datalist; Vorschläge **kaskadierend** aus
  `/api/reference/regions?country=<code>` des gewählten Landes, gemergt mit den
  eigenen bisher genutzten Regionen. Bei Länderwechsel werden die Vorschläge neu
  geladen.
- **Rebsorte**: Datalist-Vorschläge aus `/api/reference/grapes`, gemergt mit
  eigenen bisherigen Werten.
- **Flaschenformat**: `<select>`-Optionen aus `/api/reference/bottle_formats`
  (Wert = Liter, Label = Name) statt der fest kodierten Liste.

Land→Code-Auflösung im Frontend: die Länderliste (mit Code) wird einmal geladen;
beim Land-Wert (Name) wird der Code für den Regions-Filter nachgeschlagen.

## Backend

- `add` / `edit` / `duplicate`: `country` lesen/speichern (bzw. kopieren).
- `wine_json`, Index-Karten, View-Modal liefern `country` über `SELECT *`.
- Bestehender readonly-Schutz greift unverändert.

## Anzeige

- Land im View-Modal (Detail) anzeigen (eigene View-Row).
- `country` als `data-country` an der Karte + im JS-Weinobjekt, damit Edit-
  Formular es vorbefüllt und Re-Render es behält.

## i18n

- `label_country` (+ Platzhalter) in allen 7 Sprachen.

## Tests

Backend test-first:
- `add` speichert `country`; `/api/wine` liefert es zurück.
- `edit` aktualisiert `country`; `duplicate` kopiert es.
- Migration legt die Spalte auf bestehender DB an.
Frontend per Browser-Drive:
- Land-Dropdown gefüllt; Länderwechsel lädt Regions-Vorschläge des Landes;
  Rebsorten-/Format-Listen aus Referenz; Speichern persistiert Land; Edit
  befüllt Land vor.
