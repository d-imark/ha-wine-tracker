# Upstream-Abgleich P5 (Einstellungen auf dem Server) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** UI-Einstellungen (Theme, Ansicht, Sortierung, Spalten, Bereich …) überleben gelöschte Browserdaten und folgen dem Benutzer auf andere Geräte.

**Architecture:** Tabelle `user_prefs (user, key, value)`; `POST /api/prefs` speichert einen Schnappschuss der erlaubten `localStorage`-Schlüssel; jede Seite füllt `localStorage` im `<head>` aus den Server-Werten, bevor das Theme angewendet wird; `theme.js` meldet Änderungen gebündelt zurück.

**Tech Stack:** Flask, sqlite3, Vanilla JS; pytest; Playwright/Edge.

**Spec:** `docs/superpowers/specs/2026-10-28-upstream-sync-design.md` (Paket P5)

## Global Constraints

- Branch `feature/upstream-sync`; Commits nur lokal. Upstream-Vorlage: d8faa05, a2a9e97.
- Erlaubte Schlüssel: upstream-Satz (`wine-theme`, `wine-theme-name`, `wineViewMode`, `wineTableSortCol`, `wineTableSortAsc`, `wine-show-empty`, `wine-advanced-filter-default`, `chatEditWines`, `chatRecording`) **plus** `wt_area`, `statsPriceBasis`, `wineSettingsTab` und das Präfix `wineTableCols.`.
- **Abweichung vom Spec:** `wine-advanced-filter` (aktiver Filter) wird nicht synchronisiert – Arbeitszustand, kein Einstellungswert; Presets liegen bereits auf dem Server.
- Werte über 4000 Zeichen werden weggelassen, nicht abgeschnitten (abgeschnittenes JSON wäre kaputt).
- Readonly-Benutzer dürfen ihre eigenen Einstellungen speichern; ohne Login (bei Auth) 401.
- Alle fünf Seiten mit Theme-Skript werden vorbefüllt: index, stats, timeline, chat, reference.

## Review Focus

1. Ein Wert in `localStorage`, der noch nicht auf dem Server liegt (erster Start nach dem Update) → wird einmalig hochgeladen, nicht verworfen. → Browser.
2. Die `localStorage`-Methoden werden nicht durch einen Eintrag namens `setItem` verschattet (Patch am `Storage.prototype`, nur für `localStorage`). → Browser.
3. Spaltenauswahl `wineTableCols.bar` (JSON) kommt vollständig auf einem zweiten „Gerät“ (neuer Browser-Kontext) an. → Browser.
4. POST ohne JSON-Body löscht nichts (400). → pytest.
5. Aktiver Filter `wine-advanced-filter` wird nicht übertragen. → pytest + Browser.

---

### Task 1: Server-Einstellungen

**Files:**
- Modify: `wine-tracker/app/app.py` (`init_db`: Tabelle `user_prefs`; `check_readonly` allowed + `api_prefs_save`; `inject_globals`: `user_prefs`; `PREF_KEYS`, `PREF_PREFIXES`, `prefs_user()`, `load_user_prefs()`, `POST /api/prefs`)
- Modify: `wine-tracker/app/templates/{index,stats,timeline,chat,reference}.html` (Head-Skript: Vorbefüllung + `window._serverPrefsEmpty`)
- Modify: `wine-tracker/app/static/theme.js` (Sync: `_isPrefKey`, `_collectPrefs`, `_schedulePrefSync`, Patch `Storage.prototype.setItem/removeItem` nur für `localStorage`)
- Test: `wine-tracker/tests/test_routes.py`, `wine-tracker/tests/test_database.py`

- [ ] **Step 1: Failing tests** — upstream `TestUserPrefsTable`, `TestUserPrefs`, `TestUserPrefsAuth` übernehmen, plus:
  `test_prefix_keys_and_our_keys_are_stored` (`wineTableCols.bar`, `wt_area`, `statsPriceBasis`, `wineSettingsTab`), `test_active_filter_is_not_synced` (`wine-advanced-filter` nicht gespeichert), `test_overlong_values_are_dropped_not_cut`, `test_missing_json_body_keeps_prefs` (400, nichts gelöscht), `test_every_page_seeds_prefs` (`/`, `/stats`, `/timeline`, `/reference` enthalten den gespeicherten Wert im Head-Skript).
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** Umsetzen wie upstream mit den Abweichungen aus den Global Constraints.
- [ ] **Step 4:** `pytest tests/test_routes.py tests/test_database.py -q` → PASS.
- [ ] **Step 5: Browser-Prüfung** (Edge, Port 5051): Theme + Ansicht + Spalten in Kontext A setzen → Kontext B (leerer Speicher) zeigt dieselben Werte; `localStorage.getItem('setItem')` ist `null`; Altwert nur in `localStorage` wird beim ersten Laden hochgeladen; aktiver Filter in A erscheint nicht in B; keine JS-Fehler; danach `real_data.py`.
- [ ] **Step 6:** Commit `Keep UI preferences on the server`.
