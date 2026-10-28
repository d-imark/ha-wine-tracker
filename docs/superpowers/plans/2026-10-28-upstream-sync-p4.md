# Upstream-Abgleich P4 (KI-Einstellungen in der App) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Anbieter, API-Keys, Modelle, Chat-Modell und OpenAI-Websuche lassen sich in den Einstellungen ändern, ohne die Add-on-Konfiguration anzufassen; Keys verlassen den Server nie.

**Architecture:** Neue Tabelle `app_settings (key, value)`; `load_options()` legt deren Werte über ENV und `options.json` (Vorrang App > ENV > options.json > Defaults). Vier Endpunkte unter `/api/ai-settings`. Neuer Tab „KI-Anbieter“ im Einstellungs-Modal (Struktur aus P3).

**Tech Stack:** Flask, sqlite3, requests; Vanilla JS; pytest; Playwright/Edge.

**Spec:** `docs/superpowers/specs/2026-10-28-upstream-sync-design.md` (Paket P4)

## Global Constraints

- Branch `feature/upstream-sync`; Commits nur lokal.
- Upstream-Vorlage: 5f0a259, aa1e35d, 0fd153e, b6ece0b (Code in `upstream/main`).
- `AI_SETTING_KEYS` = upstream-Satz **plus** `openai_web_search`.
- `openai_web_search` wird als `"true"`/`"false"` gespeichert; `load_options()` liefert immer ein `bool`.
- Keys (`AI_KEY_FIELDS`) werden nie zurückgegeben, nur `keys: {feld: bool}`.
- Nur nicht-readonly darf lesen/schreiben (403 sonst).
- Tab-Reihenfolge: `appearance`, `ai` (nicht readonly), `sommelier` (nur mit KI), `data`, `about`.
- Übersetzungen in allen 7 Sprachen; die 16 upstream-Schlüssel 1:1 aus `upstream/main:wine-tracker/app/translations.py`.

## Review Focus

1. Anbieter in der App auf „Deaktiviert“, in `options.json` steht ein Anthropic-Key → KI bleibt aus (kein Autodetect). → Task 1, `test_app_none_beats_options_key`.
2. Gespeicherte Keys tauchen nirgends auf: GET-Antwort, Export-ZIP, HTML. → Task 1, `test_keys_never_leave_the_server`.
3. `openai_web_search` in der App ausgeschaltet → `load_options()` liefert `False` (nicht den String `"false"`, der truthy wäre). → Task 1.
4. Überschreibungen zurücksetzen → Werte aus der Add-on-Konfiguration gelten wieder. → Task 1 (`null` löscht) + Task 2 Browser.
5. Leeres Key-Feld beim Speichern behält den gespeicherten Key. → Task 1.

---

### Task 1: Backend — Tabelle, Optionen, Endpunkte, Chat-Modell

**Files:**
- Modify: `wine-tracker/app/app.py` (`load_options` Z. ~75; `init_db`; neue Endpunkte bei den übrigen `/api/*`; `/api/chat` Z. ~4067)
- Test: `wine-tracker/tests/test_routes.py`, `wine-tracker/tests/test_helpers.py`, `wine-tracker/tests/test_database.py`, `wine-tracker/tests/test_api.py`

**Interfaces:**
- Produces: `AI_SETTING_KEYS: set`, `AI_KEY_FIELDS: set`, `AI_PROVIDERS: tuple`, `chat_opts(opts) -> dict`; `GET /api/ai-settings` → `{ok, settings{ai_provider, chat_model, ollama_host, <p>_model…, openai_web_search: bool}, keys{<p>_api_key: bool}, overrides: [key…], configured: bool}`; `POST /api/ai-settings` (JSON; `null` löscht, leerer Key behält, unbekannte Keys ignoriert); `POST /api/ai-settings/test` → `{ok, reply}` | 400/502; `GET /api/ai-settings/models?provider=` → `{ok, models}`.

- [ ] **Step 1: Failing tests** — upstream-Tests übernehmen (`TestAppSettingsTable`, `TestChatOpts`, `TestAiSettings`, `TestAiSettingsAuth`, Modell-Liste aus 0fd153e in `test_api.py`), plus:

```python
def test_app_none_beats_options_key(client, tmp_path, monkeypatch):
    # options.json: anthropic key, no provider; app: ai_provider none -> stays none
def test_web_search_flag_is_a_bool(client):
    client.post("/api/ai-settings", json={"openai_web_search": "false"})
    assert wine_app.load_options()["openai_web_search"] is False
    assert client.get("/api/ai-settings").get_json()["settings"]["openai_web_search"] is False
def test_overrides_are_listed(client):
    client.post("/api/ai-settings", json={"ai_provider": "openai", "openai_model": "gpt-x"})
    assert client.get("/api/ai-settings").get_json()["overrides"] == ["ai_provider", "openai_model"]
def test_keys_never_leave_the_server(client):
    client.post("/api/ai-settings", json={"openai_api_key": "sk-geheim-789"})
    assert "sk-geheim-789" not in client.get("/api/ai-settings").data.decode()
    assert "sk-geheim-789" not in client.get("/").data.decode()
    assert b"sk-geheim-789" not in client.get("/export").data
def test_chat_uses_chat_model(client): # /api/chat with chat_model set -> _call_chat_<p> sees it as <p>_model
```
- [ ] **Step 2:** gezielt laufen lassen → FAIL.
- [ ] **Step 3:** Umsetzen wie upstream (5f0a259, 3b06adb-Teil für DB, 0fd153e), angepasst: `openai_web_search` in `AI_SETTING_KEYS`, nach dem Overlay als Bool parsen (`"1","true","on","yes"` → True); `chat_model` Default `""` + ENV `CHAT_MODEL`; `/api/chat` nutzt `chat_opts(load_options())`.
- [ ] **Step 4:** `pytest tests/test_routes.py tests/test_helpers.py tests/test_database.py tests/test_api.py -q` → PASS.
- [ ] **Step 5:** Commit `Store AI settings in the app, above the add-on options`.

### Task 2: Frontend — Tab „KI-Anbieter“

**Files:**
- Modify: `wine-tracker/app/templates/_settings_modal.html` (Tab + Sektion `data-settings-tab="ai"` + `#aiModelDd`)
- Modify: `wine-tracker/app/static/theme.js` (AI-Block aus upstream, `_apiBase()` = `_ingressPrefix()`; Aufruf `aiSettingsLoad()` im DOMContentLoaded)
- Modify: `wine-tracker/app/static/style.css` (AI-Regeln aus upstream; `--danger`/`--success` mit Fallback `#c0392b`/`#27ae60`)
- Modify: `wine-tracker/app/translations.py` (16 upstream-Schlüssel + `settings_ai_web_search`, `settings_ai_web_search_hint`, `ai_overrides_hint`, `btn_ai_reset`)
- Test: `wine-tracker/tests/test_routes.py`

**Interfaces:** Consumes: Endpunkte aus Task 1. Produces: `aiSettingsLoad()`, `aiSettingsProviderChanged()`, `aiSettingsSave(cb)`, `aiSettingsTest()`, `aiSettingsResetOverrides()`, `toggleModelDd(id, ev)`.

- [ ] **Step 1: Failing tests** — P3-Tab-Tests anpassen: ohne KI `["appearance","ai","data","about"]`, mit KI `["appearance","ai","sommelier","data","about"]`; neu: readonly sieht keinen Tab `ai` und keine `#aiProviderSelect`.
- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** Umsetzen wie upstream (Markup, JS, CSS). Zusätzlich:
  - Schalter „OpenAI-Websuche“ (`#aiWebSearchToggle`), nur sichtbar bei Anbieter `openai`; wird mitgespeichert.
  - Hinweiszeile `#aiOverridesHint` mit `ai_overrides_hint` und Button `btn_ai_reset`, sichtbar wenn `overrides` nicht leer; Reset schickt alle `overrides` als `null` und lädt neu.
  - `_apiBase()` verwendet unser `_ingressPrefix()` (P1).
- [ ] **Step 4:** `pytest tests/test_routes.py -q` → PASS.
- [ ] **Step 5: Browser-Prüfung** (Edge, Port 5051): Anbieter OpenAI + Key + Modell speichern → Reload → Key-Platzhalter „Hinterlegt…“, Websuche-Schalter sichtbar und gespeichert; Anbieter Ollama mit Host `http://127.0.0.1:9` → „Verbindung testen“ zeigt Fehler, keine Hänger; Hinweis „überschreibt Add-on-Konfiguration“ sichtbar → „Zurücksetzen“ → Anbieter wieder „Deaktiviert“, Hinweis weg; Handy-Breite 390 px; keine JS-Fehler; danach `real_data.py`.
- [ ] **Step 6:** Commit `Add an AI provider tab to the settings`.
