# Upstream-Abgleich P6 (Mengen-Popover, Rückgängig) + P7 (Löschen rückgängig) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Menge direkt am Flaschen-Badge bzw. in der Tabelle ändern, jede Mengenänderung und jedes Löschen 6 s lang rückgängig machen; Fehler beim Speichern sichtbar machen.

**Architecture:** Eine Funktion `changeQtyCard(card, delta, isUndo)` für Karte, Popover, Tabelle und Detailansicht; `/edit` versteht `qty_undo=1`. Löschen sichert Wein + alle Kind-Zeilen im Speicher und lässt Dateien liegen; `/api/wine/<id>/restore` stellt alles wieder her; ein Aufräum-Job beim Start entfernt nur unreferenzierte, über 24 h alte Upload-Dateien.

**Tech Stack:** Flask, sqlite3, Vanilla JS; pytest; Playwright/Edge.

**Spec:** `docs/superpowers/specs/2026-10-28-upstream-sync-design.md` (Pakete P6, P7)

## Global Constraints

- Branch `feature/upstream-sync`; Commits nur lokal. Upstream-Vorlage: 9469e17, 25ee246 (P6), 3974e7b (P7, nur als Vorlage).
- Undo-Fenster 6 s, Fehler-Toast 4 s; Übersetzungen `btn_undo`, `toast_bottle_removed`, `toast_bottle_added`, `toast_wine_deleted`, `toast_save_failed` aus upstream, 7 Sprachen.
- Readonly: kein Popover, kein Undo-Pfad.
- Mengen-Posts schicken **kein** `grape` mehr (sonst baut `/edit` die Rebsorten ohne Prozente neu auf).
- Wiederherstellung umfasst `wines` + `WINE_CHILD_TABLES` (`wine_grapes`, `wine_purchases`, `wine_images`, `spirit_details`, `spirit_casks`), mit Original-IDs; höchstens 20 gesicherte Löschungen im Speicher.
- Aufräumen zählt als referenziert: `wines.image`, `wine_images.filename`, `chat_messages.image_path`. Nur Dateien älter als 24 h werden gelöscht.

## Review Focus

1. Wein mit Rebsorten-Prozenten, + an der Karte → Prozente bleiben. → Task 1, Browser.
2. Löschen eines Whiskys mit Fässern, Käufen und 3 Bildern → Rückgängig → alles wieder da, inkl. Bilddateien. → Task 2, `test_restore_brings_back_everything`.
3. Aufräumen beim Start löscht kein Bild aus der Bildersammlung. → Task 2, `test_sweep_keeps_gallery_and_chat_files`.
4. Rückgängig nach einem Neustart (Sicherung weg) → klare Fehlermeldung, nichts kaputt. → Task 2, `test_restore_unknown_is_404`.
5. Netzfehler beim +/− → Anzeige springt zurück, Fehler-Toast. → Task 1, Browser (Route abfangen).

---

### Task 1 (P6): Mengen-Popover und Rückgängig

**Files:** `wine-tracker/app/app.py` (`edit`: `qty_undo`), `wine-tracker/app/templates/index.html` (Badge-Klick, Popover, Toast, `changeQtyCard`, `applyQtyUI`, `viewChangeQty` nutzt `changeQtyCard`), `wine-tracker/app/static/table-view.js` (Mengenzelle klickbar, `col-quantity`), `wine-tracker/app/static/style.css`, `wine-tracker/app/translations.py`; Test `wine-tracker/tests/test_routes.py`.

- [ ] **Step 1:** Upstream `TestQtyUndo` übernehmen (3 Tests) + `test_qty_controls_hidden_for_readonly` (kein `openQtyPopover` im HTML).
- [ ] **Step 2:** → FAIL. **Step 3:** umsetzen. **Step 4:** → PASS.
- [ ] **Step 5: Browser:** Badge-Klick öffnet Popover (Karten, Liste, Tabelle); +/− ändert Badge, Tabellenzelle, Zähler; Toast „1 Flasche entnommen“ → Rückgängig → Menge zurück, Timeline ohne Eintrag; Rebsorten-Prozente nach + unverändert; abgefangener POST (500) → Menge springt zurück + Fehler-Toast; keine JS-Fehler.
- [ ] **Step 6:** Commit `Change quantities from the badge and undo them`.

### Task 2 (P7): Löschen rückgängig (Nachbau)

**Files:** `wine-tracker/app/app.py` (`delete`, neu `restore_wine`, `cleanup_orphan_uploads`, Aufruf im `__main__` nach `init_db()`), `wine-tracker/app/templates/index.html` (Lösch-Handler mit Undo/Fehler); Tests `wine-tracker/tests/test_routes.py`, `wine-tracker/tests/test_helpers.py`.

- [ ] **Step 1: Failing tests:** `test_delete_keeps_files_for_undo`, `test_restore_brings_back_everything` (Whisky mit Details, Fässern, Kauf, Rebsorten, 3 Bildern; Timeline-„removed“ wieder weg), `test_restore_unknown_is_404`, `test_restore_twice_is_404`, `test_sweep_keeps_gallery_and_chat_files`, `test_sweep_removes_old_orphans_only` (alt+unreferenziert weg; frisch bleibt).
- [ ] **Step 2:** → FAIL. **Step 3:** umsetzen. **Step 4:** → PASS.
- [ ] **Step 5: Browser:** Löschen → Karte weg, Toast „Wein gelöscht“ → Rückgängig → Karte wieder da mit Bild; Fehlerpfad (abgefangener POST) → Fehler-Toast, Karte bleibt; danach `real_data.py`.
- [ ] **Step 6:** Commit `Undo deleting a wine, with everything attached to it`.
