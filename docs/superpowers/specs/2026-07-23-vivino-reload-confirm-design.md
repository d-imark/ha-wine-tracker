# Bestätigter Vivino-Reload (zwei Dialoge)

Datum: 2026-07-23
Status: freigegeben

## Problem

Der Vivino-Reload im Bearbeiten-Modal übernimmt Daten heute ohne Rückfrage:

- Er füllt über `populateFormMerge` nur **leere** Felder (`setIfEmpty`) - bestehende
  Werte werden also gar nicht korrigiert, obwohl der Nutzer genau das erwartet.
- Die `vivino_id` wird direkt überschrieben.
- Der Nutzer sieht vorher weder, **welcher Wein** ausgewählt wurde, noch **was sich
  ändert**.

Gewünscht: Der Reload soll bestehende Werte überschreiben **dürfen**, aber erst nach
expliziter Bestätigung mit sichtbarem Wein und sichtbarem Änderungs-Diff.

## Lösung: zweistufiger Bestätigungsdialog

Gilt für beide Reload-Pfade (`reloadViaVivino`):

### Dialog 1 - Wein bestätigen / auswählen
- **ID-Pfad** (Wein hat gespeicherte `vivino_id`): Abruf via `?id=` liefert genau
  einen Wein. Anzeige als Karte (Name, Region, ★, Bild). Auswahl per Klick.
- **Namenssuche** (keine `vivino_id`): Abruf via `?q=` liefert mehrere Treffer.
  Anzeige als Trefferliste (bestehende `renderVivinoResults`-Optik). Der Nutzer
  wählt einen aus. Kein automatisches Übernehmen von Treffer #1 mehr.
- Fußzeile: `[Abbrechen]`. Auswahl eines Treffers führt zu Dialog 2.

### Dialog 2 - Änderungen
- Tabelle nur der **tatsächlich abweichenden** Felder: `Feld · aktuell → neu`.
- Fußzeile: `[← Zurück]` (zurück zu Dialog 1), `[Abbrechen]`, `[Übernehmen]`.
- Erst `[Übernehmen]` schreibt - **überschreibend**, nicht nur leere Felder.

## Semantik / Entscheidungen

1. **Überschreiben:** Bei „Übernehmen" werden alle im Diff gezeigten Felder gesetzt,
   auch wenn bereits ausgefüllt.
2. **Betroffene Felder:** `name`, `wine_type`, `region`, `grape`. `year` und `price`
   liefert der Vivino-Katalog bewusst als `null` (jahrgangs-/marktunabhängig) und
   tauchen daher nie im Diff auf.
3. **Bewertung (★):** ausgenommen. Das ist die persönliche Bewertung des Nutzers,
   nicht die Vivino-Community-Note. Wird nie angetastet.
4. **Bild:** wird nur gesetzt, wenn noch keines vorhanden ist (wie bisher).
5. **`vivino_id`:** Nur der Namenssuche-Pfad setzt sie, und nur wenn vorher leer
   (Option B - bestehende ID wird nie überschrieben). Der ID-Pfad lässt sie unverändert.
6. **Keine Änderungen:** Weicht kein Feld ab, wird Dialog 2 übersprungen; ein Toast
   „keine Änderungen" erscheint. Ein evtl. fehlendes Bild wird dabei still nachgeladen.

## Komponenten

- **Neues Modal** `#vivinoReloadModal` in `wine-tracker/app/templates/_wine_edit_modal.html`
  mit zwei Schritt-Containern (`#vrStep1`, `#vrStep2`), Styling nach `STYLE_GUIDE.md`
  (Modal-Radius `var(--radius)`, Body-Padding `1.25rem`, Theme-Variablen).
- **JS** im selben Template:
  - Zustand: `_vrCandidates`, `_vrSelected`, `_vrAllowSetId`.
  - `openVivinoReload(candidates, allowSetId)` - öffnet Dialog 1, rendert Kandidaten.
  - `vrSelectCandidate(idx)` - wählt Wein, berechnet Diff; leer → Toast + still Bild/ID
    anwenden; sonst Dialog 2.
  - `vrRenderChanges()` - Diff-Tabelle (übersetzte Typ-Labels).
  - `vrBack()`, `vrCancel()`, `vrConfirm()` (überschreibendes Anwenden).
  - `reloadViaVivino()` umgeschrieben: ID-Pfad → `?id=` → `openVivinoReload(res,false)`;
    sonst Namenssuche → `?q=` → `openVivinoReload(res,true)`.
- **Backend:** unverändert. `/api/vivino-search?id=` und `?q=` existieren bereits.
- **i18n:** neue UI-Strings in alle 7 Sprachdateien (`translations/*.yaml`), bestehende
  Feld-Labels wo möglich wiederverwenden.

## Nicht im Scope (YAGNI)

- Feldweise Auswahl per Checkbox, welche Änderungen übernommen werden.
- Überschreiben von `rating`, `year`, `price`.
- Backend-Änderungen.

## Testing

Reines Frontend-JS; das Projekt hat keine JS-Test-Infrastruktur. Verifikation manuell
in der laufenden App:

- Wein **mit** gespeicherter `vivino_id`: Dialog 1 zeigt genau diesen Wein; Diff korrekt;
  Übernehmen überschreibt; ID unverändert.
- Wein **ohne** `vivino_id`: Trefferliste; Auswahl; Diff; Übernehmen; ID gesetzt.
- Fall „keine Änderungen": Toast, kein leerer Dialog.
- Abbrechen/Zurück ändern nichts.
- Darstellung in mehreren Themes (Dark + Light).

Bestehende Backend-Tests bleiben grün (`pytest wine-tracker/tests/`).
