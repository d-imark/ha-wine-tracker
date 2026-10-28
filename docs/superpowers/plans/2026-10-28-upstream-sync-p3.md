# Upstream-Abgleich P3 (Einstellungen mit Tabs) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Das Einstellungs-Modal bekommt Tabs (Darstellung, Sommelier, Daten, Info), eine feste Konto-Fusszeile und ein ruhiges Layout auf Desktop und Handy.

**Architecture:** Reine Frontend-Änderung am geteilten Include `_settings_modal.html` (auf index, stats, timeline, chat, reference), dazu `style.css` und `theme.js`. Sektionen werden Tab-Panels über `data-settings-tab`; ein Tab-Leiste schaltet sie per JS um.

**Tech Stack:** Jinja, Vanilla JS, CSS; pytest, Playwright/Edge.

**Spec:** `docs/superpowers/specs/2026-10-28-upstream-sync-design.md` (Paket P3)

## Global Constraints

- Branch `feature/upstream-sync`; Commits nur lokal.
- Upstream-Vorlage: 4be0106, e4ac873, 03a0daf, 4878727, 33f444a, 26c58ab, 3a412b6.
- Tab-Schlüssel exakt: `appearance`, `sommelier`, `data`, `about`; `ai` kommt erst mit P4 (Reihenfolge dann appearance, ai, sommelier, data, about).
- Gemerkter Tab in `localStorage` unter `wineSettingsTab`.
- Keine neuen Übersetzungen nötig (Tab-Beschriftungen = bestehende Sektionstitel).

## Review Focus

1. Gespeicherter Tab `sommelier`, aber KI inzwischen aus → Modal öffnet auf dem ersten Tab, nicht leer. → Task 1, Browser-Prüfung.
2. Seite `reference.html` hat ein eigenes `openModal` → Tabs funktionieren dort trotzdem. → Task 1, Browser-Prüfung.
3. Handy-Breite (≤ 500 px): Modal vollflächig, Tab-Leiste wischbar ohne Scrollbalken, Schalter-Zeilen einzeilig. → Task 1, Browser-Prüfung bei 390 px.
4. Mit Login: Konto und Abmelden als feste Fusszeile, auf jedem Tab sichtbar. → Task 1, pytest mit DEV_AUTH-Muster falls vorhanden, sonst Browser.
5. Ohne Login: keine leere Fusszeile. → Task 1, pytest.

---

### Task 1: Tabs, Fusszeile, Layout

**Files:**
- Modify: `wine-tracker/app/templates/_settings_modal.html`
- Modify: `wine-tracker/app/static/style.css` (Block „Settings Modal“, ca. Z. 1244–1305)
- Modify: `wine-tracker/app/static/theme.js` (`switchSettingsTab`, `initSettingsTabs`, Aufruf im `DOMContentLoaded`)
- Test: `wine-tracker/tests/test_routes.py`

**Interfaces:** Produces: `switchSettingsTab(name)`, `initSettingsTabs()` global in `theme.js`; Tab-Button `.settings-tab[data-tab]`, Panel `.settings-section[data-settings-tab]`. P4 hängt den Tab `ai` an dieselbe Struktur.

- [ ] **Step 1: Failing tests**

```python
def test_settings_modal_has_tabs(client):
    html = client.get("/").data.decode()
    tabs = re.findall(r'class="settings-tab" data-tab="(\w+)"', html)
    assert tabs == ["appearance", "data", "about"]          # no AI configured
    for t in tabs:
        assert f'data-settings-tab="{t}"' in html

@patch("app.load_options")
def test_sommelier_tab_only_with_ai(mock_opts, client):
    mock_opts.return_value = {**wine_app.HA_OPTIONS, "ai_provider": "anthropic", "anthropic_api_key": "sk"}
    tabs = re.findall(r'class="settings-tab" data-tab="(\w+)"', client.get("/").data.decode())
    assert tabs == ["appearance", "sommelier", "data", "about"]

def test_no_footer_without_login(client):
    assert 'class="settings-footer"' not in client.get("/").data.decode()
```
- [ ] **Step 2:** `pytest tests/test_routes.py -k "settings_modal_has_tabs or sommelier_tab or footer_without" -v` → FAIL.
- [ ] **Step 3:** Umsetzen wie upstream: Tab-Leiste mit Icons (`mdi-palette-outline`, `mdi-chat-outline`, `mdi-database-outline`, `mdi-information-outline`) unter dem Modal-Kopf; `data-settings-tab` an den vier Sektionen; Sektionstitel in Tab-Panels ausblenden; Konto-Zeile → `.settings-footer` unter `.modal-body`, nur `{% if auth_user %}`; Schalter-Zeilen bekommen `settings-row--toggle`; CSS aus 4be0106/e4ac873/4878727/33f444a/26c58ab/3a412b6 (Modal oben verankert `margin-top: 10vh`, `max-height: 80vh`; ≤ 500 px vollflächig; Scrollbalken der Tab-Leiste aus). Alte Regeln `#settingsModal .settings-section:last-child` und `a.btn-cancel[href*="logout"]` entfernen. `initSettingsTabs()` fällt bei unbekanntem gespeichertem Tab auf den ersten Tab zurück.
- [ ] **Step 4:** `pytest tests/test_routes.py -v` → PASS.
- [ ] **Step 5: Browser-Prüfung** (Edge, Desktop 1280 px und Handy 390 px, Seiten `/`, `/stats`, `/timeline`, `/reference`): Tabs wechseln Inhalt; gewählter Tab bleibt nach Reload; `localStorage.wineSettingsTab = 'sommelier'` ohne KI → erster Tab; Modal springt beim Tabwechsel nicht (Oberkante bleibt); Handy: Modal füllt den Bildschirm; keine JS-Fehler. Danach `real_data.py` gegen den echten Export.
- [ ] **Step 6:** Commit `Split the settings modal into tabs`.
