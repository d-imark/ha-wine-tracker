# Design: KI-Web-Recherche (Winzer-Website + Händler) via OpenAI web_search

## Problem

Die KI-Analyse (`/api/reanalyze-wine`) arbeitet aus Trainingswissen und kann das
Web nicht abfragen. Der Nutzer möchte, dass die KI **immer** prüft, ob die
**offizielle Winzer-Website** (mit Detailinfos) gefunden werden kann, danach
**Händler** — als Prozess, dessen Ergebnis sichtbar ist, und die gefundenen
Detailinfos sollen die Wein-Felder verbessern.

## Ansatz

Für den **OpenAI-Provider** nutzt die Analyse die **Responses-API mit dem
`web_search`-Tool** (ein Aufruf, das Modell recherchiert intern). Andere Provider
und der Fehler-Fallback nutzen unverändert `chat.completions` ohne Web. Die
gefundenen Quellen (Winzer-Website + Händler) werden als Prozess-Info in die
bestehende **`ai_rationale`** geschrieben (kein neues Feld); die verbesserten
Felder laufen durch den bestehenden KI-Abgleich-Dialog.

## Entscheidungen (aus dem Brainstorming)

- **Nur OpenAI** (web_search ist OpenAI-spezifisch); läuft **immer** beim
  KI-Reload, wenn Provider = openai.
- **Zweck:** Info **und** Feld-Verbesserung (Winzer-Details fließen in die Felder).
- **Ein Aufruf**, Ergebnis als Prozess-Info (kein Live-Status, keine 2 Calls).
- **Quellen in die Begründung** integriert (kein eigenes Feld, keine klickbaren
  Links) → erscheinen im Begründungs-Block des Dialogs und als „KI-Basis" im
  Detail.
- **Modell-agnostisch:** nutzt das konfigurierte `openai_model` (Default
  `gpt-5.5`; der Nutzer kann z.B. `gpt-5.6-luna` eintragen). In Tests wird der
  OpenAI-Aufruf gemockt → Modell-String `gpt-5.6-luna` (irrelevant fürs Ergebnis).

## Backend (`wine-tracker/app/app.py`)

### Neuer Aufruf `_call_openai_websearch(image_b64, media_type, prompt, opts)`
- OpenAI-SDK, **Responses-API**:
  `client.responses.create(model=<openai_model>, tools=[{"type": "web_search"}], input=<messages>)`.
- `input` enthält den Prompt als `input_text`; bei vorhandenem Bild zusätzlich
  ein `input_image` (`data:`-URL).
- Rückgabe: der finale Text (`response.output_text`) — enthält das JSON (wie beim
  bestehenden Pfad; gleiche Parse-Logik in `_analyze_wine_from_context`).
- Wirft bei API-/Tool-Fehler eine Exception (wird vom Dispatcher gefangen).

### Dispatch mit Fallback
- Die Provider-Zuordnung für `openai` zeigt auf einen Wrapper
  `_call_openai_smart(...)`: versucht `_call_openai_websearch`; bei **jeder**
  Exception → `app.logger.warning(...)` + Rückgabe von `_call_openai(...)`
  (bestehender `chat.completions`-Pfad, ohne Web). So bricht nichts, wenn das
  Modell/Tool die Websuche nicht unterstützt.
- `_call_openai` bleibt unverändert (Fallback + weiterhin für nicht-web Zwecke).

### Prompt / Regeln (`_wine_json_rules`)
Für OpenAI wird der Prompt um einen Recherche-Block erweitert (die übrigen
Provider bekommen ihn nicht, da ohne Web wirkungslos — Umsetzung: der Web-Prompt
wird nur im `_call_openai_websearch`-Pfad angehängt, das JSON-Schema bleibt
gleich):
1. Finde und **verifiziere** die **offizielle Website des Winzers/Guts**; nutze
   deren Detailinfos, um `region`, `grape`, `drink_from/until`, `notes` etc.
   genauer zu bestimmen.
2. Finde **Händler/Bezugsquellen** (Online-Shops), an denen der Wein kaufbar ist.
3. Schreibe in `ai_rationale` eine **kurze Prozess-Zusammenfassung** in der
   aktiven Sprache: „Offizielle Website: <URL> (gefunden/nicht gefunden). Basis
   der Angaben: … Händler: <URL1>, <URL2>." Keine erfundenen URLs — nur, was die
   Suche wirklich geliefert hat; sonst „nicht gefunden".
Das JSON-Schema (`_wine_json_schema`) bleibt **unverändert** (Felder + `ai_rationale`).

## Frontend

**Kein/kaum Umbau.** Die verbesserten Felder erscheinen wie gehabt pro Feld im
KI-Abgleich-Dialog; die Recherche-Info steht in `ai_rationale` und wird im
Begründungs-Block sowie als „KI-Basis" in der Detailansicht angezeigt (beides
existiert bereits). Ggf. minimal: Begründungs-Block bleibt `white-space`/Wrap-fest
(bereits via `overflow-wrap`).

## Robustheit / Kosten

- Web-Recherche ist langsamer + teurer pro Reload; läuft „immer" bei OpenAI
  (bewusst so gewünscht). Kein Toggle (später leicht als Option ergänzbar).
- Jeder Fehler im Web-Pfad → transparenter Fallback auf die bisherige Analyse.
- Timeouts/`max_output_tokens` moderat setzen, damit der Reload nicht hängt.

## Tests / Verifikation

Backend (pytest, OpenAI gemockt):
- `_call_openai_websearch`: `openai.OpenAI` gemockt, `client.responses.create`
  liefert ein Objekt mit `output_text` = JSON (Felder + `ai_rationale` inkl.
  Winzer-URL + Händler). `_analyze_wine_from_context` (Provider openai, Modell
  `gpt-5.6-luna`) liefert die Felder inkl. `ai_rationale` mit den Quellen.
- **Fallback:** `client.responses.create` wirft → `_call_openai_smart` ruft
  `_call_openai` (gemockt) und liefert dessen Ergebnis; kein Fehler nach außen.
- Nicht-OpenAI-Provider unverändert (kein Web-Pfad).

Frontend (Playwright): gestubbte `/api/reanalyze-wine` mit `ai_rationale`, die
Winzer-URL + Händler enthält → Begründungs-Block zeigt den Recherche-Text;
Felder wie gehabt übernehmbar. (Deckt die Anzeige ab; die echte Websuche ist
nicht Teil des automatisierten Tests.)

## Spike zuerst

Vor der Umsetzung ein kurzer manueller Spike: `client.responses.create` mit
`tools=[{"type":"web_search"}]` und dem konfigurierten Modell gegen den echten
Key testen (Tool-Name/`output_text`-Form bestätigen). Ergebnis fließt in die
genaue Aufruf-Syntax; der Fallback deckt Abweichungen ab.

## Nicht im Scope

- Andere Provider (nur OpenAI).
- Klickbare Quell-Links / eigenes Quellen-Feld (Quellen bleiben Text in der
  Begründung).
- Kosten-Toggle, Live-Fortschrittsanzeige, zweistufiger Aufruf.
