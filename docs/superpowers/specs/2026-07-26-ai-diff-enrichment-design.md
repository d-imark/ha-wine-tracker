# Design: KI-Diff zeigt Enrichment mit vorher→nachher

## Problem

Im KI-Abgleich-Dialog (`aiReloadModal`) zeigen die Enrichment-Zeilen
(Reifeverlauf, Geschmacksprofil, Food-Pairings) nur ein „✓ (Anzahl)" statt der
alt→neu-Darstellung, die die übrigen Felder haben. Der Nutzer sieht nicht, was
sich ändert (vorher/nachher fehlt).

## Ziel

Die Enrichment-Zeilen im Diff zeigen **alt → neu** wie die einfachen Felder,
mit einer **kompakten, lokalisierten Zusammenfassung** je Typ. Checkbox und
Übernahme-Logik bleiben unverändert.

## Nur-Frontend

Reine JS-Änderung in `_wine_edit_modal.html` (`arComputeEnrich`,
`renderAiReload`, neuer Helfer `_arEnrichSummary`). Keine Backend-/i18n-/CSS-
Änderung — die benötigten Labels existieren bereits (`taste_body`,
`taste_tannin`, `taste_acidity`, `taste_sweetness`, `maturity_peak`).

## Zusammenfassungen (kompakt, lokalisiert)

`_arEnrichSummary(key, value)` liefert je Typ einen kurzen String:

- **maturity_data:** Höhepunkt-Bereich aus `value.peak` (`[a, b]`), z.B.
  `Höhepunkt 2030–2040` (`T.maturity_peak + ' ' + a + '–' + b`). Fehlt `peak`
  oder ist kein 2er-Array → Anzahl Phasen (`n Phasen`) bzw. `—` bei leer.
- **taste_profile:** die vorhandenen Dimensionen als
  `Körper 4 · Tannin 5 · Säure 4 · Süße 1`
  (`T.taste_body/…` + Wert, mit ` · ` verbunden; nur gesetzte Werte).
- **food_pairings:** Liste, `Rind, Wild, Hartkäse` (`value.join(', ')`).
- Leerer/fehlender Wert → `—`.

## Datenfluss

- `arComputeEnrich(fields)` liest zusätzlich den **alten** Wert aus dem
  versteckten Formularfeld (`document.getElementById(e.el).value`, JSON-parse
  mit try/catch → `null` bei leer/ungültig) und berechnet `oldSummary` (aus dem
  alten Wert, sonst `—`) und `newSummary` (aus `fields[e.key]`). Rückgabe je
  Eintrag: `{ e, val, oldSummary, newSummary }` (das bisherige `count` entfällt).
- `renderAiReload` rendert die Enrichment-Zeilen wie die einfachen Felder:
  Checkbox `arEnr_<j>` · Label · `vr-old`(oldSummary) · `→` · `vr-new`(newSummary).
- `applyAiReload` unverändert: bei angehakter Zeile wird `en.val` als JSON ins
  versteckte Feld geschrieben.

## Verhalten

- Erstbefüllung (kein alter Wert): `— → Höhepunkt 2030–2040`.
- Aktualisierung: `Höhepunkt 2028–2035 → Höhepunkt 2030–2040`.
- Lange Food-Pairing-Listen brechen dank des bestehenden `overflow-wrap`-Fixes
  in `.vr-changes-table td` sauber um.

## Tests / Verifikation

Backend unverändert → keine neuen pytest-Tests. Playwright (gestubbte KI-Antwort
mit `maturity_data`/`taste_profile`/`food_pairings`):
- Wein **ohne** vorheriges Enrichment → Enrichment-Zeilen zeigen `—` links und
  die Zusammenfassung rechts (nicht mehr „✓ (n)").
- Wein **mit** vorherigem Enrichment (Felder vorbefüllt) → linke Spalte zeigt
  die alte Zusammenfassung, rechte die neue.
- Abwählen einer Enrichment-Checkbox → Feld bleibt beim Übernehmen unverändert
  (bestehendes Verhalten, Regressionscheck).
- Keine JS-Fehler; einfache Feld-Zeilen unverändert.

## Nicht im Scope

- Keine ausführliche Aufschlüsselung je Unter-Größe (kompakt gewählt).
- Kein Backend-/Schema-Change; keine Änderung der Übernahme-Logik.
