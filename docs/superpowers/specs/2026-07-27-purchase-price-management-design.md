# Design: Einkaufs-Preisverwaltung (KI-Preis getrennt + gewichteter Ø der eigenen Einkäufe)

## Problem

Es gibt nur **ein** Feld `wines.price`, das sowohl die KI (Label-/Marktschätzung) als
auch der Nutzer (bezahlter Preis) befüllen — nicht unterscheidbar. Gewünscht:

- **KI-Preis** getrennt vom **eigenen Preis**.
- **Eigene Einkäufe** als mehrere Posten erfassen: *wann*, *wie viele Flaschen*,
  *wo*, zu *welchem Stückpreis*.
- Anzeige eines **mengengewichteten Durchschnitts** als „mein Preis".

## Entscheidungen (Brainstorming)

1. **Entkoppelt:** Einkäufe sind reine Kosten-/Herkunftsdatensätze. Der Bestand
   (Flaschenzahl `quantity`) bleibt unverändert separat (Karten-+/-, Timeline).
2. **Eigener Dialog** „Einkäufe verwalten", aufrufbar aus dem Bearbeiten-Dialog
   **und** der Detailansicht.
3. **KI-Preis = nur Info:** `ai_price` wird separat angezeigt und fließt **nicht**
   in Wert-Statistiken.
4. **Wert-Statistik unverändert:** gewichteter Ø × aktueller Bestand (Lagerwert).

## Datenmodell

Neue Tabelle **`wine_purchases`** (ein Datensatz = ein Einkaufs-Posten):

| Spalte         | Typ     | Bemerkung |
|----------------|---------|-----------|
| `id`           | INTEGER PK AUTOINCREMENT | |
| `wine_id`      | INTEGER NOT NULL | FK → `wines.id`, `ON DELETE CASCADE` |
| `purchase_date`| TEXT | ISO `yyyy-mm-dd`, optional |
| `quantity`     | INTEGER NOT NULL DEFAULT 1 | Flaschen dieses Postens (Gewichtung); > 0 |
| `unit_price`   | REAL NOT NULL | Preis pro Flasche |
| `location`     | TEXT | Einkaufsort, optional |
| `note`         | TEXT | optional |
| `created`      | TEXT | ISO-Zeitstempel |

Änderungen an `wines`:

- **`ai_price REAL`** (neu, nullable): KI-/Marktpreis, rein informativ.
- **`price REAL`** (bestehend, umgewidmet): **gecachter, mengengewichteter Ø** der
  Einkäufe: `Σ(quantity × unit_price) / Σ(quantity)`, auf 2 Nachkommastellen
  gerundet, bei jeder Einkaufs-Änderung serverseitig neu berechnet. `NULL`, wenn
  keine Einkäufe. → bestehende Statistik-Queries (`SUM(quantity*price)`,
  teuerster/günstigster) bleiben ohne Umbau gültig.
- `purchased_at` (bestehend): wird nicht mehr im Formular editiert; der Ort lebt
  künftig pro Posten in `wine_purchases.location`. Spalte bleibt (Backward-Compat),
  wird bei der Migration in den ersten Posten übernommen.

## Migration (`init_db`)

- Spalte `ai_price` ergänzen; Tabelle `wine_purchases` anlegen.
- **Backfill (einmalig, wenn `wine_purchases` gesamthaft leer ist** — analog zum
  Timeline-Backfill): für jeden Wein mit `price` > 0 einen Posten anlegen:
  `quantity = max(quantity, 1)`, `unit_price = price`, `location = purchased_at`,
  `purchase_date = NULL`, `note = 'Migriert'`. Danach `price` = gewichteter Ø
  (== alter Wert → unverändert).
- **Annahme/Hinweis:** bestehende `price`-Werte werden als *bezahlter* Preis
  gewertet (Regelfall). War es faktisch eine KI-Schätzung, kann der Nutzer den
  Posten anpassen. `ai_price` startet leer.

## Backend

Neues Modul **`purchases.py`** (Muster wie `images.py`):
- `create_purchases_table(db)`, `list_purchases(db, wine_id)`,
  `add_purchase(db, wine_id, data)`, `update_purchase(db, pid, data)`,
  `delete_purchase(db, pid)`, `weighted_average(db, wine_id) -> (avg, total_qty, total_spent)`,
  `recompute_wine_price(db, wine_id)` (setzt `wines.price`).

REST-Endpunkte (analog zu `/api/wine/<id>/images`):
- `GET  /api/wine/<id>/purchases` → `{purchases:[…], avg, total_qty, total_spent}`
- `POST /api/wine/<id>/purchases` → Posten anlegen → recompute → aktualisierte Liste
- `PATCH /api/wine/<id>/purchases/<pid>` → Posten ändern → recompute
- `DELETE /api/wine/<id>/purchases/<pid>` → löschen → recompute
- Validierung: `quantity` int > 0, `unit_price` ≥ 0; Fremd-`wine_id`/`pid` → 404.

Weitere Backend-Anpassungen:
- **`wine_json`**: `price` (Ø) wie gehabt, zusätzlich `ai_price` und `purchase_count`.
- **KI-Analyse/Reload** (`analyze`, `reanalyze`, Chat-Enrichment): geschätzter Preis
  wird in **`ai_price`** geschrieben, nicht mehr in `price`. Der KI-JSON-Key `price`
  bleibt; beim Anwenden landet er in `ai_price`.
- **`add`/`edit`**: kein `price`-Formularfeld mehr; `ai_price` optional editierbar.
  `price` wird nicht mehr direkt aus dem Formular gesetzt (nur über Einkäufe).
- **Export/Import**: `ai_price` in `WINE_COLUMNS` (+ CSV). Einkäufe als eigene
  **`purchases.json`** im Export-ZIP (authoritative Sicherung) + Import wieder
  einspielen; CSV bleibt informativ (Ø-`price` + `ai_price`).

## Frontend

**Dialog „Einkäufe verwalten"** (`#purchasesModal`):
- Aufruf aus Bearbeiten-Dialog (Button im Preis-Block) **und** Detailansicht
  (Button beim Preis). Nur für **bereits gespeicherte** Weine (braucht `wine_id`).
- Tabelle der Posten: Datum · Menge · Stückpreis · Ort · Notiz · Löschen; plus
  „+ Posten"-Zeile zum Hinzufügen, Inline-Bearbeiten.
- Jede Änderung ruft sofort die CRUD-API; Liste + Kennzahlen aktualisieren live.
- Fußzeile: **gewichteter Ø**, Gesamtmenge, insgesamt ausgegeben (Σ).
- In der **Hinzufügen**-Ansicht (neuer Wein, noch keine `id`): Button deaktiviert
  mit Hinweis „zuerst speichern".

**Bearbeiten-Dialog** (Preis-Bereich neu):
- „Mein Preis (Ø)" **read-only** (aus Einkäufen) + Button **„Einkäufe verwalten"**.
- „KI-/Marktpreis" (`ai_price`) als eigenes, editierbares Feld.
- Das bisherige einzelne `price`-Feld und das `purchased_at`-Feld entfallen.

**Karte:** zeigt weiterhin `price` (= Ø) — keine Änderung nötig.

**Detailansicht:** „Mein Preis (Ø)" + separat „KI-Preis"; Button „Einkäufe"
öffnet denselben Dialog (verwalten). Optional Auflistung der Posten.

**i18n:** neue Labels in 7 Sprachen (Einkäufe, Datum, Menge, Stückpreis, Ort,
Notiz, „Mein Preis", „KI-Preis", „insgesamt ausgegeben", „zuerst speichern").

## Statistik

Wert-Übersicht unverändert: gewichteter Ø (`price`) × aktueller Bestand.
`ai_price` bleibt außen vor.

## Tests

Backend (pytest):
- Ø-Berechnung: Posten 2×10 + 3×20 → Ø 16.00, total_qty 5, total_spent 70.
- CRUD: add/patch/delete → `wines.price` wird korrekt neu berechnet; keine Posten → `price` NULL.
- Migration: Wein mit `price`>0 und ohne Posten → genau ein Migrations-Posten, `price` unverändert.
- KI-Analyse schreibt Preis nach `ai_price`, nicht `price`.
- Export/Import: `ai_price` + `purchases.json` round-trip.

Frontend (Playwright):
- Dialog öffnen, 2 Posten anlegen → Ø + Karte/Detail-Preis stimmen; Posten löschen → Neuberechnung; KI-Preis getrennt sichtbar.

## Nicht im Scope (v1)

- Einkäufe steuern den Bestand (bewusst entkoppelt).
- Währung pro Posten (globale Währung).
- Einkäufe im Hinzufügen-Modus vor dem ersten Speichern.
- „Insgesamt ausgegeben" als eigene Statistik-Kennzahl (Entscheidung: Ø×Bestand);
  im Dialog wird die Summe aber angezeigt.
