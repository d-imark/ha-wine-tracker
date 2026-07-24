# Design: KI-Begründung ("Quellen") speichern

## Problem

Die KI-Aktualisierung (`/api/reanalyze-wine` + KI-Abgleich-Dialog) füllt Felder,
gibt aber keinen Hinweis, worauf die Identifikation und die Schätzungen beruhen.
Der Nutzer kann die Trefferqualität nur an den Werten selbst beurteilen.

## Ziel

Die KI liefert eine kurze, ehrliche **Begründung** ihrer Identifikation und
Schätzungen. Diese wird im Bestätigungs-Dialog angezeigt und kann optional beim
Wein gespeichert und später in der Detailansicht eingesehen werden.

## Nicht-Ziel / Einschränkung

Echte, überprüfbare Web-Quellen (URLs) sind mit einem reinen LLM (gpt-4o-mini)
nicht zuverlässig möglich — es halluziniert Links. Daher bewusst **nur eine
Begründung/Basis in Prosa**, keine erfundenen URLs oder Zitate.

## Ansatz

Die Begründung wird im **bestehenden** KI-Call miterzeugt (ein zusätzliches
JSON-Feld), im Dialog als eigener Block mit „speichern"-Checkbox angezeigt,
optional in einer neuen Spalte `wines.ai_rationale` gespeichert und in der
Detailansicht dargestellt.

## Komponenten

### 1. Datenbank
Neue Spalte `ai_rationale TEXT` auf `wines`, ergänzt im `migrations`-Dict in
`init_db` (additive Migration, wie `country`/`vivino_rating`). `wine_json`
liefert sie automatisch mit (macht `dict(row)`).

### 2. Backend / KI
- `_wine_json_schema()` um `"ai_rationale": "brief basis for the identification and estimates (1-2 sentences)"` erweitern.
- `_wine_json_rules()` um eine Regel ergänzen: Begründung kurz (1–2 Sätze), in
  der aktiven Sprache, nur auf tatsächlichem Wissen basierend, **keine erfundenen
  URLs/Zitate**; `null`, wenn keine sinnvolle Basis.
- `/api/reanalyze-wine` gibt `ai_rationale` dadurch im `fields`-Objekt zurück.
  Keine Änderung an der Route selbst nötig.

### 3. KI-Abgleich-Dialog (`_wine_edit_modal.html`)
- Unter der „Die KI hat erkannt"-Kopfzeile ein Begründungs-Block
  `#aiRationaleBlock` (Fließtext), sichtbar nur wenn `fields.ai_rationale`
  vorhanden. Nicht in der Änderungstabelle (zu lang).
- Darin eine Checkbox `#arRationaleSave` („Begründung speichern"), standardmäßig
  aktiv.
- `openAiReload` öffnet den Dialog künftig auch, wenn *nur* eine Begründung
  vorliegt (Bedingung: `changes.length || enrich.length || ai_rationale`).
- `applyAiReload`: bei angehakter Checkbox `wine_ai_rationale`-Feld auf
  `fields.ai_rationale` setzen; sonst unverändert lassen.
- `_arPending` trägt zusätzlich `rationale` (den Text).

### 4. Persistenz (Formular)
- Verstecktes Feld `<input type="hidden" id="wine_ai_rationale" name="ai_rationale">`
  im Edit-Modal (bei den anderen Hidden-Feldern `wine_maturity_data` etc.).
- `openWineModal` setzt `wine_ai_rationale` aus `w.ai_rationale` (leer im
  Add-Modus).
- `add`- und `edit`-Route: `ai_rationale` in INSERT/UPDATE aufnehmen
  (`request.form.get("ai_rationale", "").strip() or None`).
- `duplicate`-Route: `ai_rationale` mitkopieren (`wine["ai_rationale"]`).

### 5. Detailansicht (`index.html`, `openViewModal`)
- Nach dem Notizen-Block: wenn `w.ai_rationale` vorhanden, ein Block
  `<div class="view-ai-basis">` mit Label `T.ai_basis_label` und dem Text
  (HTML-escaped). Dezent gestylt (kleiner, `--muted`), damit es sich klar von
  eigenen Notizen abhebt.

### 6. i18n (`translations.py`, 7 Sprachen: de, en, fr, it, es, pt, nl)
- `ar_rationale_save` — Dialog-Checkbox „Begründung speichern".
- `ai_basis_label` — Detailansicht-Label „KI-Basis".

### 7. CSS (`style.css`)
- `#aiReloadModal .ar-rationale` — Begründungs-Block (Hintergrund, Padding,
  `line-height`, `overflow-wrap`).
- `.view-ai-basis` — dezenter Block in der Detailansicht.

## Datenfluss

1. `reloadViaAi` → `/api/reanalyze-wine` → `fields` (inkl. `ai_rationale`).
2. `openAiReload(fields)` rendert Kopfzeile, Änderungstabelle, Enrichment und
   — falls vorhanden — den Begründungs-Block mit Checkbox.
3. „Übernehmen" (`applyAiReload`): angehakte Felder/Enrichment ins Formular;
   bei angehakter Begründung `wine_ai_rationale` setzen.
4. Speichern (`add`/`edit`) persistiert `ai_rationale` in die DB.
5. Detailansicht liest `w.ai_rationale` aus `wine_json` und zeigt „KI-Basis: …".

## Tests / Verifikation

Backend (pytest):
- Migration legt Spalte `ai_rationale` an.
- `add` mit `ai_rationale` speichert und `wine_json` gibt den Wert zurück.
- `edit` aktualisiert `ai_rationale`.
- `duplicate` kopiert `ai_rationale`.

Frontend (Playwright, System-Chrome):
- Gestubbte KI-Antwort mit `ai_rationale` → Begründungs-Block sichtbar,
  Checkbox aktiv.
- „Übernehmen" mit aktiver Checkbox → `wine_ai_rationale` gesetzt; nach Save in
  der Detailansicht sichtbar.
- „Übernehmen" mit abgewählter Checkbox → `wine_ai_rationale` bleibt leer.
- KI-Antwort ohne `ai_rationale` → kein Block; Antwort mit nur Begründung
  (sonst keine Änderungen) → Dialog öffnet trotzdem.
- Regression: bestehende KI-Abgleich- und Vivino-Flows unverändert; volle
  pytest-Suite grün.

## Nicht im Scope (YAGNI)

- Keine echten Web-Quellen / Websuche / Vivino-Zitate.
- Keine Historie mehrerer Begründungen (nur der zuletzt übernommene Stand).
- Kein separater KI-Call nur für die Begründung.
