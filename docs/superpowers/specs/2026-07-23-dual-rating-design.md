# Zwei Bewertungen: persönlich + Vivino, je 1 Kommastelle

Datum: 2026-07-23
Status: freigegeben

## Problem

Es gibt heute nur eine Bewertung: `rating INTEGER` (1–5, ganzzahlig). Die
Vivino-Community-Note wird nirgends gespeichert - sie erscheint nur flüchtig als
Badge in der Vivino-Trefferliste. Beim Anlegen über Vivino wird die Community-Note
sogar gerundet in das persönliche Sternefeld geschrieben, wodurch beide vermischt
werden. Der Nutzer sieht die Vivino-Note nach dem Speichern nirgends.

Ziel: persönliche Note **und** Vivino-Note getrennt speichern und anzeigen, beide
mit 1 Kommastelle.

## Entscheidungen (freigegeben)

- **Persönliche Note:** Eingabe per **Schieberegler** 0,0–5,0 (Schritt 0,1) mit
  Live-Stern-Vorschau. `0` = keine Bewertung.
- **Vivino-Note:** rein lesend, wird automatisch beim Vivino-Abruf/Anlegen gesetzt
  und gespeichert, nicht von Hand editierbar.
- **Anzeige (Karte + Detail):** persönliche Note als teilgefüllte goldene Sterne +
  Zahl; Vivino-Note als abgesetztes Badge (z. B. „Ⓥ 4.2") mit Tooltip.

## Datenmodell / Migration

- Neue Spalte `vivino_rating REAL` (via bestehende ADD-COLUMN-Migration in
  `init_db` - läuft automatisch beim Update).
- `rating` bleibt formal `INTEGER`, speichert aber Kommawerte. SQLite-Affinität
  legt `4.3` als REAL ab, `4.0` als `4`. Kein Tabellen-Rebuild, bestehende Werte
  bleiben gültig.

## Wiederverwendbare Stern-Darstellung

Reine-CSS-Teilfüllung (kein `range()` auf Float mehr):

```
.star-rating           position:relative; ::before content "★★★★★" in var(--border)
.star-rating .fill      position:absolute; overflow:hidden; width:<pct>%;
                        ::before content "★★★★★" in var(--gold)
```

Jinja-Makro `_stars.html` für Server-Rendering (Karte, Stats) und ein JS-Pendant
für dynamisch gerenderte Karten. Prozent = `rating / 5 * 100`.

## Betroffene Stellen

**Backend (`app.py`)**
- Schema: `vivino_rating REAL` ergänzen.
- `add` / `edit`: `rating` als `float` lesen (statt `int`), `vivino_rating` als
  `float` lesen und speichern.
- `SELECT *`-basierte Wege (`/api/wine`, Index-Karten, View-Modal) liefern
  `vivino_rating` automatisch mit.
- Stats „Top 5" nutzt weiter die persönliche Note.
- Chat-Kontext / Chat-CRUD-Rating bleiben ganzzahlig (Out of Scope).

**Templates**
- `_wine_form_fields.html`: Sterne-Radios → Slider + Live-Stern-Vorschau.
- `_wine_edit_modal.html`:
  - verstecktes Feld `vivino_rating`;
  - `openWineModal` setzt Slider aus `w.rating` und `vivino_rating` aus
    `w.vivino_rating`, aktualisiert Vorschau;
  - Vivino-Treffer (Suche/Anlegen, `selectVivinoResult`) schreiben die Note in
    `vivino_rating` statt in die persönlichen Sterne;
  - Reload-Confirm setzt `vivino_rating` still als Side-Effect (wie Bild/ID);
  - AI-Reload-Vorschlag für die persönliche Note nur, wenn Slider noch 0.
- `index.html`: Karte (`range` → Makro/Teilfüllung) + Vivino-Badge; `renderCard`
  und View-Modal analog; `data-rating` per `parseFloat`; `vivino_rating` ins
  JS-Weinobjekt.
- `stats.html`: Top-Wein-Sterne (`range` → Makro) server- und clientseitig.
- `chat.html`: Mini-Karten-Sterne auf Teilfüllung/Floor (kein Crash, nur Optik).

**CSS (`style.css`)**
- `.star-rating` (+ `.fill`), `.vivino-badge`, Slider-Styling. `.star-input` wird
  durch den Slider ersetzt.

**i18n (`translations.py`)**
- Tooltip „Vivino-Bewertung" + evtl. Label-Anpassung persönliche Note, 7 Sprachen.

## Nicht im Scope (YAGNI)

- Vivino-Note von Hand editierbar.
- Vivino-Badge in Listen-/Tabellen-/Grid-Ansicht (nur Karte + Detail).
- Kommastellen im Advanced-Filter (Filter bleibt ganzzahlig; numerischer Vergleich
  funktioniert weiterhin).
- Chat-CRUD-Rating auf Float umstellen.

## Testing

Backend test-first (`pytest`):
- `add` speichert Komma-`rating` (z. B. 4.3) und `vivino_rating`.
- `edit` aktualisiert beide.
- `/api/wine/<id>` gibt `rating` (float) und `vivino_rating` zurück.

Frontend (kein JS-Test-Harness): manuell + Browser-Drive (Playwright/System-Chrome):
- Slider setzt Wert + Vorschau; Speichern persistiert 4,3.
- Karte/Detail zeigen Teilsterne + Vivino-Badge.
- Vivino-Reload/Anlegen füllt `vivino_rating`, nicht die persönliche Note.
- Stats-Seite lädt mit Komma-Bewertung ohne Fehler.
