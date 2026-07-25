# Design: Vivino-Abgleich liefert Region und Land getrennt

## Problem

Beim Vivino-Abgleich baut `vivino_search` die Region als kombinierten String
`"Region, Land"` (z.B. „Toro, Spain") und legt ihn ins **Region**-Feld. Es gibt
aber ein separates **Land**-Feld — Region und Land sollen getrennt befüllt werden.

## Ziel

Jedes Vivino-Ergebnis liefert Region und Land **einzeln**; die Übernahme (sowohl
Reload-Confirm als auch Add-Flow) schreibt die Region ins Region-Feld und das
Land ins Land-Feld.

## Scope

- **Nur künftig** — keine Migration bereits gespeicherter Weine (deren Region-Feld
  „Region, Land" enthält, bleibt unberührt).
- Kein neuer i18n-Key (vorhandenes `label_country` wird genutzt).

## Backend (`wine-tracker/app/app.py`, `vivino_search`)

`region_name` und `country_name` liegen bereits getrennt vor (Z. ~2292–2296).
Statt sie zu `region_str = "Region, Land"` zu verketten:
- Ergebnis-Dict: `"region": region_name` (nur die Region),
- **neu**: `"country": country_name` (Klarname aus dem 2-Buchstaben-Code via
  `_COUNTRY_NAMES`, leer wenn kein Land).
- Der bisherige `region_str` entfällt.

## Frontend (`wine-tracker/app/templates/_wine_edit_modal.html`)

### Reload-Confirm (vr-Flow)
- `_VR_FIELDS` um einen Eintrag erweitern:
  `{ key: 'country', el: 'wine_country', labelKey: 'label_country' }`.
  Dadurch erscheint „Land" automatisch in der Änderungstabelle
  (`vrComputeChanges` iteriert `_VR_FIELDS`) und wird beim Übernehmen ins
  `wine_country`-Feld geschrieben; die Region bleibt im `wine_region`-Feld.
- Kandidatenliste Schritt 1 (`vrRenderCandidates`): Land hinter der Region in
  der Meta-Zeile anzeigen (wenn vorhanden).

### Add-Flow (Quelle „Vivino")
- `selectVivinoResult`: zusätzlich `if (item.country) fields.country = item.country;`.
- `populateFormFromAi`: `wine_country` aus `fields.country` setzen (nur wenn
  vorhanden) — analog zu den übrigen Feldern.
- `renderVivinoResults`: Land in der Meta-Zeile mit anzeigen.

## Datenfluss

1. `/api/vivino-search` liefert je Treffer `region` (nur Region) + `country`.
2. Reload-Confirm: Region- und Land-Zeile in der Änderungstabelle; „Übernehmen"
   schreibt beide Felder. Der bestehende `reconcileThenSubmit`-Flow beim Speichern
   nutzt Region **und** Land wie gewohnt (bessere Reconcile-/Karten-Auflösung).
3. Add-Flow: `selectVivinoResult` füllt Region- und Land-Feld direkt.

## Tests / Verifikation

Backend (pytest, gemockte Algolia-Antwort mit `region.name` + `region.country`):
- `vivino_search` liefert `region` == Regionsname **ohne** Land und ein
  separates `country` mit dem Klarnamen.
- Treffer ohne Region (nur Land) → `region` leer, `country` gesetzt.

Frontend (Playwright, gestubbte `/api/vivino-search` mit getrennten Feldern):
- Reload-Confirm: nach „Übernehmen" steht die Region in `wine_region` und das
  Land in `wine_country` (nicht „Region, Land" im Region-Feld).
- Add-Flow: `selectVivinoResult` füllt beide Felder getrennt.
- Keine JS-Fehler; bestehende Vivino-Feldübernahme (Name/Typ/Rebsorte),
  `vivino_id`/`vivino_rating`, Bildübernahme unverändert.

## Nicht im Scope

- Keine Migration bestehender „Region, Land"-Werte.
- Keine Änderung der KI-Analyse (deren Schema liefert weiterhin „wine region";
  separat behandelt).
