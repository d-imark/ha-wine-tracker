# Design: KI-Reload mit Bestätigungs-Dialog

## Problem

Der KI-Reload im Bearbeiten-Dialog ("Fehlende Daten von der KI laden",
`reloadViaAi`) schreibt das Analyse-Ergebnis sofort und ohne Rückfrage ins
Formular (`populateFormMerge`, nur leere Felder). Der Nutzer sieht weder, ob die
KI den **richtigen Wein** identifiziert hat, noch welche Felder betroffen sind.

Der Vivino-Abruf hat bereits einen zweistufigen Bestätigungs-Flow
(Treffer bestätigen → Änderungstabelle alt→neu → Übernehmen). Der KI-Reload soll
analog eine Bestätigung bekommen — mit dem Zusatz, dass der Nutzer **pro Feld**
entscheidet, was übernommen wird.

## Ziel

Nach dem KI-Call öffnet ein Bestätigungs-Dialog, der
1. zeigt, welchen Wein die KI erkannt hat (Kontext zur Beurteilung der Treffer-
   qualität), und
2. jede vorgeschlagene Änderung einzeln ankreuzbar macht, bevor überschrieben
   wird.

## Ansatz

**Eigener KI-Bestätigungs-Dialog** parallel zum Vivino-Flow (Ansatz A). Der
funktionierende Vivino-Flow bleibt unangetastet; bewährte Muster (Änderungs-
berechnung alt→neu, Toast, "keine Änderungen"-Fall, Bild-Seiteneffekt) werden
nachgebildet, aber um KI-spezifische Teile (Kopfzeile, Checkbox pro Zeile,
Enrichment-Zeilen) ergänzt. Alle Änderungen liegen in
`wine-tracker/app/templates/_wine_edit_modal.html` (+ Translations + CSS).
Das Backend (`/api/reanalyze-wine`) bleibt unverändert.

## UI / Ablauf

Neues Modal `aiReloadModal` (z-index über dem Edit-Modal, wie `vivinoReloadModal`).

1. Klick auf "Daten von der KI laden" → `reloadViaAi()` sammelt Kontext + Bild,
   ruft `/api/reanalyze-wine`, zeigt den bestehenden Ladeindikator.
2. Bei Erfolg: statt `populateFormMerge(...)` → `openAiReload(data.fields)`.
3. Der Dialog zeigt:
   - **Kopfzeile:** "Die KI hat erkannt:" + Zusammenfassung aus den KI-Feldern
     (Name · Jahr · Typ · Region · Rebsorte), rein informativ (kein Checkbox).
     Wird immer angezeigt, auch wenn diese Felder unverändert bleiben — so ist die
     Identifikation stets sichtbar.
   - **Änderungstabelle mit Checkboxen:** eine Zeile je einfaches Feld, dessen
     KI-Wert vom aktuellen Formularwert abweicht: `Feld | alt → neu | ☑`.
     Alle Checkboxen sind standardmäßig aktiv.
   - **Enrichment-Zeilen:** je eine ankreuzbare Zeile für `maturity_data`,
     `taste_profile`, `food_pairings`, sofern die KI dazu Daten liefert, mit
     Kurz-Zusammenfassung statt JSON-Diff (z.B. "Geschmacksprofil: wird
     aktualisiert").
   - **Footer:** Abbrechen · Übernehmen.
4. "Übernehmen" schreibt **nur die angehakten Zeilen** ins Formular, wendet
   Seiteneffekte an, schließt den Dialog und zeigt einen Erfolgs-Toast.
5. **Keine Änderungen:** Liefert die Analyse keine abweichenden einfachen Felder
   und kein Enrichment → Dialog gar nicht öffnen, nur Toast "Keine neuen Daten".

## Datenfluss & Feld-Mapping

KI-Antwort: `{ ok: true, fields: {...} }`. Relevante Keys (wie heute von
`populateFormMerge` konsumiert):

Einfache Felder (Map `_AR_FIELDS`, KI-Key → Formular-Element-ID; optional Typ):
- `name` → `wine_name`
- `vintage` → `wine_year`
- `wine_type` → `wine_type` (Anzeige über `T['wine_type_' + val]`)
- `region` → `wine_region`
- `grape` → `wine_grape`
- `price` → `wine_price`
- `drink_from` → `wine_drink_from`
- `drink_until` → `wine_drink_until`
- `notes` → `wine_notes`
- `bottle_format` → `wine_bottle_format`

Enrichment (Map `_AR_ENRICH`, KI-Key → verstecktes JSON-Feld + Summary-Funktion):
- `maturity_data` → `wine_maturity_data`
- `taste_profile` → `wine_taste_profile`
- `food_pairings` → `wine_food_pairings`

Sonderfälle:
- **Bild:** stiller Seiteneffekt — nur setzen, wenn noch kein Bild vorhanden
  (analog `_vrApplySideEffects`). Keine Checkbox-Zeile.
- **Persönliches Rating (`rating`):** nur als Checkbox-Zeile anbieten, wenn die
  KI eins liefert **und** der Rating-Slider aktuell 0 ist. So wird eine vom
  Nutzer gesetzte Wertung nie ohne dessen Zutun angeboten/überschrieben. Wert
  wird auf 0–5 mit einer Nachkommastelle geclamped (wie bisher).
- **Vivino-Community-Rating:** vom KI-Flow unberührt.

## Funktionen (in `_wine_edit_modal.html`)

- `reloadViaAi()`: Erfolgszweig ruft `openAiReload(fields)` statt
  `populateFormMerge`.
- `_AR_FIELDS`, `_AR_ENRICH`: Konfigurations-Maps.
- `arComputeChanges(fields)`: liefert Liste `{key, el, labelKey, cur, nv, display}`
  für einfache Felder mit nicht-leerem, abweichendem KI-Wert.
- `arComputeEnrich(fields)`: liefert Liste vorhandener Enrichment-Gruppen mit
  Summary-Text.
- `openAiReload(fields)`: berechnet Changes+Enrichment; bei leer → Toast + return;
  sonst Kopfzeile + Tabelle rendern, Modal öffnen.
- `renderAiReload(identified, changes, enrich)`: baut Kopfzeile und Tabelle
  (Checkbox-Spalte).
- `applyAiReload()`: iteriert Zeilen, übernimmt nur angehakte einfache Felder und
  Enrichment-JSON; Bild-Seiteneffekt; Toast; schließen.
- `arCancel()`: Modal schließen ohne Änderung.

Wiederverwendete Helfer: `setReloadLoading`, `showReloadToast`,
`download/​persist image`-Seiteneffekt, `updateRatingPreview`.

## Interaktion mit Save/Reconcile

Unverändert. Nach dem Übernehmen kann der Nutzer weiter editieren und speichern;
der bestehende `reconcileThenSubmit`-Flow (TP3b) prüft Region/Rebsorte beim
Speichern wie gehabt. Der KI-Reload greift nicht in den Submit ein.

## i18n

Neue Keys in allen 7 Sprachen (`translations.py`):
`ar_title`, `ar_identified`, `ar_maturity`, `ar_taste`, `ar_pairings`,
`ar_apply`, `ar_no_changes`, `ar_hint`.

## CSS

`.vr-changes-table` wiederverwenden; schmale Checkbox-Spalte + Kopfzeilen-Stil
als minimale `.ar-*`-Ergänzungen in `style.css`.

## Tests / Verifikation

Backend unverändert → keine neuen pytest-Tests. Der reine JS-Flow wird per
Playwright verifiziert (System-Chrome, `channel="chrome"`):
- KI-Reload mit gestubbtem/echtem Ergebnis öffnet den Dialog.
- Kopfzeile zeigt die erkannten Werte.
- Nur abweichende Felder erscheinen als Zeilen; alle Checkboxen initial aktiv.
- Abwählen einer Zeile → Feld bleibt beim Übernehmen unverändert.
- Enrichment-Zeilen erscheinen nur bei vorhandenen Daten und schreiben das
  versteckte JSON-Feld.
- "Keine Änderungen" → kein Dialog, Toast erscheint.
- Vivino-Flow weiterhin unverändert funktionsfähig (Regressionscheck).

## Nicht im Scope (YAGNI)

- Keine Konsolidierung des Vivino-Flows in eine gemeinsame Komponente (spätere
  Option B).
- Keine Kandidatenauswahl für die KI (die Analyse liefert genau ein Ergebnis).
- Kein voller JSON-Diff für Enrichment (nur Kurz-Zusammenfassung).
