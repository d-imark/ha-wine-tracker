# Design: Flexible Bilder — BP1 (Datenmodell & Backend-Fundament)

## Kontext

Teil 1 eines größeren Pakets „flexible Bilder". Ziel des Gesamtpakets: pro Wein
mehrere Bilder in Kategorien (scan/vivino/ki/manuell) parallel, Default-Auswahl
für die Anzeige, Bild-Änderungen in den Confirm-Dialogen und ein KI-Bildauswahl-
Schritt. Zerlegt in BP1–BP5; **dieses Spec deckt nur BP1** (Fundament).

Aktuell: eine Spalte `wines.image` (genau ein Dateiname). Bilder liegen in
`UPLOAD_DIR`. `save_image` (Upload, Resize) und `vivino_image`/`ai_image` laden
in denselben Slot. Anzeige (Karte, Detailansicht, `data-image`) liest
`wines.image`.

## Ziel von BP1

Ein sauberes Mehrbild-Datenmodell mit CRUD-Backend schaffen, **ohne die Anzeige
oder den bestehenden Bild-Ablauf zu verändern**. `wines.image` bleibt und
spiegelt immer das Default-Bild, sodass alle bestehenden Anzeige-Stellen
unverändert funktionieren. Spätere Pakete (BP2–BP5) bauen UI/Dialoge darauf auf.

## Nicht-Ziel (BP1)

- Keine UI-Änderungen (kein Mehrbild-Upload-UI, keine Galerie, keine Dialog-
  Änderungen). Kommt in BP2–BP5.
- Kein Label „vorne/hinten" (bewusst weggelassen: nur Kategorie + Reihenfolge).
- Kategorien-spezifische Zuordnung im Add/Edit-Formular (Scan vs. KI vs. Vivino)
  bleibt BP2/BP4/BP5; in BP1 wird das bestehende Einzelbild als `scan` geführt.

## Datenmodell

Neue Tabelle `wine_images`:

| Spalte      | Typ     | Bedeutung                                             |
|-------------|---------|-------------------------------------------------------|
| id          | INTEGER PRIMARY KEY AUTOINCREMENT |                             |
| wine_id     | INTEGER NOT NULL | zugehöriger Wein (Index)                     |
| category    | TEXT NOT NULL | einer von scan / vivino / ki / manuell          |
| filename    | TEXT NOT NULL | Dateiname in UPLOAD_DIR                          |
| is_default  | INTEGER NOT NULL DEFAULT 0 | 1 = Anzeige-Default des Weins      |
| sort_order  | INTEGER NOT NULL DEFAULT 0 | Reihenfolge innerhalb des Weins    |
| created     | TEXT    | ISO-Zeitstempel                                       |

- Index `idx_wine_images_wine` auf `wine_id`.
- **Invariante:** pro `wine_id` genau eine Zeile mit `is_default=1`, solange
  mindestens ein Bild existiert; sonst keine.
- Tabelle in `init_db` via `CREATE TABLE IF NOT EXISTS` erstellt.

Kategorien-Konstante: `CATEGORIES = ("scan", "vivino", "ki", "manuell")`.

## Modul `wine-tracker/app/images.py`

Reine DB-Logik (nimmt eine `sqlite3`-Connection mit `Row`-Factory), analog
`reference.py`. Datei-I/O (Speichern/Löschen der Bilddatei) bleibt in den Routen.

- `create_images_table(db)` — Tabelle + Index anlegen.
- `migrate_legacy_images(db)` — für jeden Wein mit nicht-leerem `wines.image`
  und **ohne** vorhandene Bildzeile: eine Zeile `category='scan'`, `is_default=1`,
  `sort_order=0` anlegen. Idempotent (mehrfach aufrufbar).
- `add_image(db, wine_id, category, filename) -> int` — legt Zeile an; `category`
  muss in `CATEGORIES` sein (sonst `ValueError`). Ist es das erste Bild des Weins,
  wird es automatisch Default. `sort_order` = aktuelle Bildanzahl. Ruft
  `_sync_wine_image`. Gibt die neue `id` zurück.
- `list_images(db, wine_id) -> list[dict]` — nach `sort_order, id` sortiert;
  Felder id, category, filename, is_default, sort_order.
- `get_default_filename(db, wine_id) -> str | None`.
- `set_default(db, wine_id, image_id) -> bool` — setzt `is_default` exklusiv;
  `False`, wenn `image_id` nicht zu diesem Wein gehört; ruft `_sync_wine_image`.
- `remove_image(db, wine_id, image_id) -> str | None` — löscht die Zeile, gibt den
  Dateinamen zurück (für os.remove in der Route). War es das Default, wird das
  Bild mit kleinstem `sort_order` neues Default; ruft `_sync_wine_image`.
- `sync_primary(db, wine_id, old_filename, new_filename)` — hält die Tabelle
  konsistent mit dem Legacy-Einzelbild:
  - `new_filename` gesetzt: existiert bereits eine Zeile mit diesem Namen → zum
    Default machen; sonst als `scan`-Zeile anlegen und zum Default machen.
  - `new_filename` leer/None: die Zeile mit `old_filename` (falls vorhanden)
    entfernen.
  Ruft danach `_sync_wine_image`.
- `_sync_wine_image(db, wine_id)` (intern) — setzt `wines.image` auf den
  Default-Dateinamen bzw. `NULL`, wenn keine Bilder existieren.

Alle mutierenden Funktionen committen NICHT selbst (die Route committet), außer
wo im Bestand üblich; Konsistenz mit vorhandenem Stil (`reference.py` committet
nicht selbst — die Route ruft `db.commit()`).

## HTTP-Endpoints (in `app.py`)

- `GET /api/wine/<int:wine_id>/images` → `{"ok": true, "images": [...], "default": <filename|null>}`.
- `POST /api/wine/<int:wine_id>/images` — multipart: Datei-Feld `image`, Formfeld
  `category` (default `manuell`, muss in CATEGORIES sein). Speichert via
  `save_image`, ruft `add_image`, committet. → `{"ok": true, "image": {...}}`.
  Ungültige Kategorie → 400.
- `POST /api/wine/<int:wine_id>/images/<int:image_id>/default` → `set_default`,
  committet. → `{"ok": true}` bzw. 404 wenn Bild nicht zum Wein gehört.
- `DELETE /api/wine/<int:wine_id>/images/<int:image_id>` → `remove_image`,
  danach `os.remove` der Datei (falls kein anderer Wein sie referenziert — in
  BP1 sind Dateien 1:1, also einfaches Löschen), committet. → `{"ok": true}`.

Alle Endpoints prüfen, dass der Wein existiert (sonst 404).

## Integration bestehender Routen

- **`wine_json`**: zusätzlich `images` (via `list_images`) im Rückgabe-Dict;
  `image` bleibt der Default-Dateiname (unverändert).
- **`add` / `edit` / `duplicate`**: bestehende Bildlogik bleibt (sie setzen
  `wines.image`). Nach dem Ermitteln des neuen Bild-Dateinamens ein Aufruf von
  `images.sync_primary(db, wine_id, old_filename, new_filename)`:
  - `new_filename` gesetzt und ungleich `old_filename` → falls schon eine Zeile
    mit diesem Namen existiert, zum Default machen; sonst als `scan`-Zeile
    anlegen und zum Default machen. (Beim `add`/`duplicate` ist `old_filename`
    leer.)
  - `new_filename` leer (Bild via `delete_image=1` entfernt) → die Zeile mit
    `old_filename` entfernen; `_sync_wine_image` befördert ein verbleibendes Bild
    zum Default bzw. setzt `wines.image = NULL`.
  So bleibt die Tabelle frei von verwaisten Verweisen und immer konsistent mit
  `wines.image`. Kategorie-spezifische Zuordnung (KI/Vivino) im Formular bleibt
  BP4/BP5.
- **Anzeige** (Karte, Detailansicht, `data-image`): **unverändert**.
- **Migration** in `init_db`: nach `create_images_table` einmalig
  `migrate_legacy_images`.

## Datenfluss

1. Beim Start: `create_images_table` + `migrate_legacy_images` → bestehende
   Einzelbilder als `scan`-Default in der Tabelle.
2. Add/Edit/Duplicate: wie bisher + `sync_primary` hält Tabelle & `wines.image`
   konsistent.
3. Neue Endpoints erlauben mehrere Bilder je Kategorie, Default-Wechsel, Löschen;
   `_sync_wine_image` hält `wines.image` = Default → Anzeige bleibt korrekt.
4. `wine_json` liefert `images` (für spätere UI) + `image` (Default, Kompat).

## Tests (pytest)

Modul (`tests/test_images.py`):
- `create_images_table` legt Tabelle an; `add_image` erstes Bild = Default.
- Zweites Bild derselben Kategorie ist nicht Default; `sort_order` inkrementiert.
- Ungültige Kategorie → `ValueError`.
- `set_default` wechselt exklusiv; Default-Invariante bleibt (genau eine).
- `remove_image` gibt Dateinamen zurück; Entfernen des Defaults befördert das
  nächste Bild; `wines.image` wird synchronisiert.
- `remove_image` des letzten Bildes → `wines.image` = NULL.
- `migrate_legacy_images` backfillt genau einmal (idempotent).
- `sync_primary` legt bei neuem Einzelbild eine scan-Default-Zeile an.

Routen (`tests/test_routes.py` bzw. `test_api.py`):
- `add` mit Bild → `GET /api/wine/<id>/images` zeigt eine scan-Default-Zeile;
  `wine_json.image` == Default.
- `POST` neues Bild (category=manuell) → erscheint in der Liste, nicht Default.
- `POST .../default` wechselt Default → `wine_json.image` folgt.
- `DELETE` entfernt Bild; Default-Entfernung befördert das nächste.
- Ungültige Kategorie → 400; unbekannter Wein → 404.

## Kompatibilität / Risiko

- Anzeige unverändert, da `wines.image` immer = Default.
- Reine additive Migration (neue Tabelle, `wines.image` bleibt).
- Bild-Dateien in BP1 weiterhin 1:1 pro Zeile (kein Sharing) → einfaches Löschen.

## Offen für spätere Pakete (nicht BP1)

- BP2: Mehrbild-Upload-/Verwaltungs-UI (Kategorie wählen, Default setzen,
  löschen, Reihenfolge) im Bearbeiten-Dialog.
- BP3: Galerie in der Detailansicht.
- BP4: Bild-Änderungen in Vivino-/KI-Confirm-Dialogen.
- BP5: KI-Bildauswahl-Schritt aus mehreren gefundenen Bildern.
