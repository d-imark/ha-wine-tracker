# KI-Web-Recherche (OpenAI web_search) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Für den OpenAI-Provider recherchiert die KI-Analyse per Responses-API `web_search` die offizielle Winzer-Website + Händler, verbessert die Felder und schreibt die Quellen in `ai_rationale`; ein Add-on-Schalter `openai_web_search` (HA/Docker/lokal) schaltet das um.

**Architecture:** Neue Aufrufe `_call_openai_websearch` (Responses-API + web_search) und `_call_openai_smart` (Web + Fallback auf `_call_openai`); Gate in `_analyze_wine_from_context` über `opts["openai_web_search"]`. Option in `config.yaml` + `load_options` (Default an) + Docker-Env + `run-dev.local.ps1`. Kein Frontend-Umbau (Quellen erscheinen im bestehenden Begründungs-Block).

**Tech Stack:** Flask, OpenAI SDK (Responses API), pytest (OpenAI gemockt). Modell in Tests: `gpt-5.6-luna` (irrelevant, da gemockt).

## Global Constraints

- Nur OpenAI; andere Provider unverändert. Default `openai_web_search=True`.
- Jeder Fehler im Web-Pfad → Fallback auf `_call_openai` (chat.completions).
- Quellen (Winzer-URL + Händler) als Text in `ai_rationale`; kein neues Feld, kein Frontend-Umbau, kein Request-Flag.
- Option in allen Deployment-Varianten via `load_options` (HA options / Docker-Env / lokale Env).
- `scripts/run-dev.local.ps1` ist GITIGNORED → lokal editieren, **nicht** committen.
- Bestehende Tests bleiben grün (419 + neue).

---

### Task 1: Option `openai_web_search` in allen Varianten

**Files:**
- Modify: `wine-tracker/app/app.py` (`load_options`)
- Modify: `wine-tracker/config.yaml` (options + schema)
- Modify: `docker/docker-compose.yml` (Env-Beispiel)
- Modify: `README.md` (Env-Tabelle)
- Modify (lokal, nicht committen): `scripts/run-dev.local.ps1`
- Test: `wine-tracker/tests/test_api.py` (neue Klasse `TestWebSearchOption`)

**Interfaces:**
- Produces: `load_options()["openai_web_search"]` (bool, Default True; via HA-Option, options.json oder Env `OPENAI_WEB_SEARCH`).

- [ ] **Step 1: Failing test schreiben**

In `wine-tracker/tests/test_api.py` ans Ende anfügen:
```python
class TestWebSearchOption:
    def test_default_true(self, monkeypatch):
        import app as wine_app
        monkeypatch.delenv("OPENAI_WEB_SEARCH", raising=False)
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", "/nonexistent/options.json")
        assert wine_app.load_options()["openai_web_search"] is True

    def test_env_false(self, monkeypatch):
        import app as wine_app
        monkeypatch.setenv("OPENAI_WEB_SEARCH", "false")
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", "/nonexistent/options.json")
        assert wine_app.load_options()["openai_web_search"] is False

    def test_env_true(self, monkeypatch):
        import app as wine_app
        monkeypatch.setenv("OPENAI_WEB_SEARCH", "true")
        monkeypatch.setattr(wine_app, "OPTIONS_PATH", "/nonexistent/options.json")
        assert wine_app.load_options()["openai_web_search"] is True
```

- [ ] **Step 2: Test laufen lassen (fail)**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_api.py::TestWebSearchOption -q`
Expected: FAIL — `KeyError: 'openai_web_search'`.

- [ ] **Step 3: `load_options` — Default + Env-Parse**

In `wine-tracker/app/app.py` im `defaults`-Dict nach `"mistral_model": "mistral-medium-latest",` ergänzen:
```python
        "mistral_model": "mistral-medium-latest",
        "openai_web_search": True,
```
Und **nach** der `for env_key, opt_key in env_map.items()`-Schleife (vor dem Backward-compat-Block) einfügen:
```python
    ws = os.environ.get("OPENAI_WEB_SEARCH")
    if ws is not None:
        defaults["openai_web_search"] = ws.strip().lower() not in ("0", "false", "no", "off", "")
```
(HA/`options.json` liefern echtes Bool über `defaults.update(opts)`; die Env-Variable ist ein String und wird hier explizit zu bool.)

- [ ] **Step 4: Test grün**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_api.py::TestWebSearchOption -q`
Expected: 3 passed.

- [ ] **Step 5: `config.yaml` (HA-Option)**

In `wine-tracker/config.yaml` unter `options:` nach `openai_model: "gpt-5.5"` einfügen:
```yaml
  openai_model: "gpt-5.5"
  openai_web_search: true
```
Und unter `schema:` nach `openai_model: str?` einfügen:
```yaml
  openai_model: str?
  openai_web_search: bool?
```

- [ ] **Step 6: Docker + README**

In `docker/docker-compose.yml` unter `environment:` nach der `# - OPENAI_MODEL=gpt-5.5`-Zeile ergänzen:
```yaml
      # - OPENAI_MODEL=gpt-5.5
      # - OPENAI_WEB_SEARCH=true   # OpenAI: offizielle Winzer-Website + Händler recherchieren (nur OpenAI)
```
In `README.md` in der Env-Variablen-Tabelle nach der `OPENAI_MODEL`-Zeile eine Zeile im selben Format ergänzen:
```markdown
| `OPENAI_WEB_SEARCH` | `true` |
```

- [ ] **Step 7: `run-dev.local.ps1` (lokal, nicht committen)**

In `scripts/run-dev.local.ps1` nach der `$env:OPENAI_MODEL`-Zeile ergänzen:
```powershell
$env:OPENAI_WEB_SEARCH = "true"   # KI-Websuche im Dev aktiv; auf "false" für die alte Methode
```

- [ ] **Step 8: Syntax + volle Suite**

Run:
```bash
cd wine-tracker && python -c "import ast; ast.parse(open('app/app.py',encoding='utf-8').read()); print('OK')"
cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q
```
Expected: `OK`, 422 passed (419 + 3 neu).

- [ ] **Step 9: Commit (ohne run-dev.local.ps1 — gitignored)**

```bash
git add wine-tracker/app/app.py wine-tracker/config.yaml docker/docker-compose.yml README.md wine-tracker/tests/test_api.py
git commit -m "Add openai_web_search option (HA/Docker/local) with default on"
```

---

### Task 2: Web-Recherche-Aufruf + Gate + Fallback

**Files:**
- Modify: `wine-tracker/app/app.py` (`_call_openai_websearch`, `_call_openai_smart`, Gate in `_analyze_wine_from_context`, `_WEB_RESEARCH_PROMPT`)
- Test: `wine-tracker/tests/test_api.py` (Klasse `TestAiWebResearch`)

**Interfaces:**
- Consumes: `_call_openai` (Fallback), `opts["openai_web_search"]` (Task 1).
- Produces: `_call_openai_websearch(image_b64, media_type, prompt, opts) -> str`; `_call_openai_smart(...)` (Web + Fallback); Gate wählt bei openai+Flag `_call_openai_smart`.

- [ ] **Step 1: Failing tests schreiben**

In `wine-tracker/tests/test_api.py` ans Ende anfügen:
```python
class TestAiWebResearch:
    @patch("openai.OpenAI")
    def test_websearch_uses_responses_api(self, MockOpenAI):
        import app as wine_app
        inst = MockOpenAI.return_value
        inst.responses.create.return_value = MagicMock(
            output_text='{"name":"X","ai_rationale":"Offizielle Website: winzer.de. Haendler: shop.de"}')
        out = wine_app._call_openai_websearch(None, "image/jpeg", "PROMPT",
                {"openai_api_key": "k", "openai_model": "gpt-5.6-luna"})
        assert "winzer.de" in out
        kwargs = inst.responses.create.call_args.kwargs
        assert kwargs["model"] == "gpt-5.6-luna"
        assert any(t.get("type") == "web_search" for t in kwargs["tools"])

    def test_smart_falls_back_on_error(self, monkeypatch):
        import app as wine_app
        def boom(*a, **k): raise RuntimeError("no web_search on this model")
        monkeypatch.setattr(wine_app, "_call_openai_websearch", boom)
        monkeypatch.setattr(wine_app, "_call_openai", lambda *a, **k: '{"name":"FB"}')
        assert wine_app._call_openai_smart(None, "image/jpeg", "P", {}) == '{"name":"FB"}'

    def test_gate_websearch_when_flag_on(self, monkeypatch):
        import app as wine_app
        calls = {}
        monkeypatch.setattr(wine_app, "_call_openai_smart", lambda *a, **k: calls.setdefault("smart", 0) or calls.update(smart=1) or '{"name":"X"}')
        monkeypatch.setattr(wine_app, "_call_openai", lambda *a, **k: calls.update(plain=1) or '{"name":"X"}')
        opts = {"ai_provider": "openai", "openai_api_key": "k", "openai_model": "gpt-5.6-luna", "openai_web_search": True}
        wine_app._analyze_wine_from_context(opts, None, "image/jpeg", {"name": "X"})
        assert calls.get("smart") == 1 and "plain" not in calls

    def test_gate_plain_when_flag_off(self, monkeypatch):
        import app as wine_app
        calls = {}
        monkeypatch.setattr(wine_app, "_call_openai_smart", lambda *a, **k: calls.update(smart=1) or '{"name":"X"}')
        monkeypatch.setattr(wine_app, "_call_openai", lambda *a, **k: calls.update(plain=1) or '{"name":"X"}')
        opts = {"ai_provider": "openai", "openai_api_key": "k", "openai_model": "gpt-5.6-luna", "openai_web_search": False}
        wine_app._analyze_wine_from_context(opts, None, "image/jpeg", {"name": "X"})
        assert calls.get("plain") == 1 and "smart" not in calls
```

- [ ] **Step 2: Tests laufen lassen (fail)**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_api.py::TestAiWebResearch -q`
Expected: FAIL — `_call_openai_websearch`/`_call_openai_smart` existieren nicht.

- [ ] **Step 3: Web-Aufruf + Smart-Wrapper implementieren**

In `wine-tracker/app/app.py` direkt **nach** `def _call_openai(...)` (vor `_call_openrouter`) einfügen:
```python
_WEB_RESEARCH_PROMPT = (
    "\n\nZusätzlich: Nutze die Websuche, um diesen Wein zu recherchieren.\n"
    "1. Finde und verifiziere die OFFIZIELLE Website des Winzers/Guts; nutze deren "
    "Detailinfos, um region, grape, drink_from/drink_until und notes so genau wie "
    "möglich zu bestimmen.\n"
    "2. Finde Händler/Online-Shops, bei denen der Wein kaufbar ist.\n"
    "Schreibe in \"ai_rationale\" (in derselben Sprache wie die übrigen Textfelder) "
    "eine kurze Zusammenfassung: offizielle Website-URL (oder 'nicht gefunden'), "
    "worauf die Angaben beruhen, und Händler-URLs. Erfinde KEINE URLs — nenne nur, "
    "was die Suche wirklich geliefert hat."
)


def _call_openai_websearch(image_b64, media_type, prompt, opts):
    """Call OpenAI via the Responses API with the web_search tool."""
    from openai import OpenAI
    api_key = opts.get("openai_api_key", "").strip()
    model = opts.get("openai_model", "gpt-5.5").strip() or "gpt-5.5"
    client = OpenAI(api_key=api_key)
    content = [{"type": "input_text", "text": prompt + _WEB_RESEARCH_PROMPT}]
    if image_b64:
        content.append({"type": "input_image",
                        "image_url": f"data:{media_type};base64,{image_b64}"})
    response = client.responses.create(
        model=model,
        tools=[{"type": "web_search"}],
        input=[{"role": "user", "content": content}],
        max_output_tokens=1500,
    )
    return response.output_text


def _call_openai_smart(image_b64, media_type, prompt, opts):
    """OpenAI with web search; fall back to plain chat.completions on any error."""
    try:
        return _call_openai_websearch(image_b64, media_type, prompt, opts)
    except Exception as e:
        app.logger.warning("OpenAI web_search failed, falling back to chat.completions: %s", e)
        return _call_openai(image_b64, media_type, prompt, opts)
```

- [ ] **Step 4: Gate in `_analyze_wine_from_context`**

Den Block
```python
    call_fn = dispatch.get(provider)
    if not call_fn:
        raise ValueError("invalid_provider")

    raw = call_fn(image_b64, media_type, prompt, opts).strip()
```
ersetzen durch:
```python
    call_fn = dispatch.get(provider)
    if not call_fn:
        raise ValueError("invalid_provider")
    if provider == "openai" and opts.get("openai_web_search", True):
        call_fn = _call_openai_smart

    raw = call_fn(image_b64, media_type, prompt, opts).strip()
```

- [ ] **Step 5: Tests grün + volle Suite**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest tests/test_api.py::TestAiWebResearch -q`
Expected: 4 passed.
Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 426 passed (422 + 4).

- [ ] **Step 6: Playwright — Anzeige der Recherche-Info (kein Frontend-Umbau)**

App neu starten:
```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*app.py*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop } catch {} }
Start-Process -FilePath "powershell.exe" -ArgumentList "-NoProfile","-ExecutionPolicy","Bypass","-File","C:\Users\DominikImark\repos\ha-wine-tracker\scripts\run-dev.local.ps1" -WindowStyle Hidden
Start-Sleep -Seconds 7
```
Skript `scratchpad/ws.py` (stubt reanalyze mit Recherche-Text in ai_rationale):
```python
import json
from playwright.sync_api import sync_playwright
FIELDS={"name":"X","region":"Piemont","ai_rationale":"Offizielle Website: https://winzer.de (gefunden). Händler: https://shop.de"}
with sync_playwright() as p:
    b=p.chromium.launch(channel="chrome", headless=True); pg=b.new_page()
    errs=[]; pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.route("**/api/reanalyze-wine", lambda r: r.fulfill(status=200, content_type="application/json", body=json.dumps({"ok":True,"fields":FIELDS})))
    pg.goto("http://localhost:5050/", wait_until="load")
    pg.evaluate("() => openWineModal(null,{name:'X'})"); pg.wait_for_timeout(300)
    pg.evaluate("() => reloadViaAi()"); pg.wait_for_timeout(1200)
    r = pg.evaluate("""() => ({shown:getComputedStyle(document.getElementById('aiRationaleBlock')).display, text:document.getElementById('aiRationaleText').textContent})""")
    print(r); print("errors:", errs if errs else "none"); b.close()
```
Run: `& .venv/Scripts/python.exe scratchpad/ws.py`
Expected: Block sichtbar, `text` enthält „winzer.de" und „shop.de"; `errors: none`.

- [ ] **Step 7: Commit**

```bash
git add wine-tracker/app/app.py wine-tracker/tests/test_api.py
git commit -m "Add OpenAI web_search research path with graceful fallback"
```

---

## Self-Review

**Spec-Abdeckung:**
- Responses-API `web_search`-Aufruf → Task 2 Step 3 (`_call_openai_websearch`). ✓
- Fallback bei Fehler → `_call_openai_smart` (Task 2) + Test. ✓
- Gate über Option → Task 2 Step 4 + Tests (on/off). ✓
- Recherche-Prompt (Winzer-Site → Händler → Quellen in ai_rationale) → `_WEB_RESEARCH_PROMPT` (Task 2 Step 3). ✓
- Option `openai_web_search` HA/Docker/lokal/run-dev + load_options Default+Env → Task 1. ✓
- Kein Frontend-Umbau; Anzeige über bestehenden Begründungs-Block → Task 2 Step 6 (Playwright bestätigt). ✓
- Nur OpenAI; andere Provider unverändert → Gate prüft `provider == "openai"`. ✓

**Placeholder-Scan:** kein TBD/TODO; vollständiger Code je Step. ✓

**Typ-Konsistenz:** `_call_openai_websearch`/`_call_openai_smart`(image_b64, media_type, prompt, opts); Gate nutzt `opts.get("openai_web_search", True)`; Option-Key `openai_web_search` in config.yaml/load_options/Env identisch. ✓

**Live-Hinweis:** Die exakte Responses-API-Syntax (Tool-Name `web_search`, `input_image`-Form, `output_text`) kann je nach OpenAI-SDK/Modell abweichen; Tests sind gemockt. **Nach dem Merge ein echter Live-Reload mit OpenAI-Key nötig** — bei Abweichung greift der Fallback (alte Methode), ohne dass etwas bricht.
