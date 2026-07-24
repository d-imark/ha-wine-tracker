# Design: Flexible Bilder — BP4 (Bild im Vivino-Confirm)

## Kontext

Teil 4 des Bild-Pakets. BP1–BP3 liefern Datenmodell, Bearbeiten-Galerie und
Detail-Galerie. BP4 integriert das **Vivino-Bild** in den Reload-Confirm-Flow:
Vorschau im Dialog und Aufnahme als `vivino`-Bild in `wine_images` beim
Übernehmen.

## Befund / Scope

- **Vivino** liefert ein echtes Bild (`item.image_url`); der SSRF-geschützte
  Endpoint `/api/vivino-image` lädt es bereits.
- Die **KI** liefert kein Bild (das hochgeladene Foto ist nur Eingabe). Eine
  „KI-Bildsuche" bräuchte echte Bildersuche (nicht gpt-4o-mini) → **separates,
  späteres Paket**, nicht Teil von BP4.
- BP4 betrifft nur den **Vivino-Reload-Confirm** (`vivinoReloadModal`), der im
  **Bearbeiten**-Modus läuft → der Wein hat eine id, die BP1-Endpoints sind
  nutzbar. Der Add-Flow-Vivino (Source-Step) bleibt unverändert.

## Entscheidungen

- Das übernommene Vivino-Bild wird als `vivino`-Bild ergänzt und **nur dann
  Default**, wenn der Wein noch kein Bild hat (`add_image`-Standardverhalten).
  Ein vorhandenes Default (z.B. Scan) bleibt unangetastet.
- Der Legacy-Einzel-Slot wird für diesen Pfad nicht mehr genutzt (`aiImageField`
  bleibt unberührt → kein versehentliches Scan-Doppel beim Speichern).

## Backend

- **Refactor:** Die Download-Logik aus `vivino_image` in einen Helfer auslagern:
  `_download_vivino_image(url) -> str | None` — Protokoll-relative URLs ergänzen,
  SSRF-Check (nur `images.vivino.com`/`pictures.vivino.com`), Download, Downscale,
  Rückgabe des Dateinamens; `None` bei ungültigem Host/Fehler. Der bestehende
  Endpoint `POST /api/vivino-image` nutzt den Helfer weiter (Verhalten unverändert:
  `{ok, filename}` bzw. Fehlerstatus).
- **Neuer Endpoint:** `POST /api/wine/<int:wine_id>/images/vivino`, Body `{url}`.
  - Wein unbekannt → 404.
  - `_download_vivino_image(url)` → `None` → 400 (`download_failed`/`invalid_host`).
  - sonst `images.add_image(wine_id, 'vivino', filename)` (Default nur wenn erstes
    Bild), `db.commit()` → `{"ok": true, "image": {"id", "category": "vivino", "filename"}}`.

## Frontend (`_wine_edit_modal.html`)

- **Schritt 2 des Vivino-Confirm** (`vrSelectCandidate` rendert die Änderungs-
  tabelle): darunter einen Bild-Vorschau-Block einfügen, wenn `_vrSelected.image_url`
  vorhanden ist:
  - kleines Thumbnail (`<img class="vr-image-preview" src="image_url">`),
  - Label `t.vr_image_add` („Bild wird hinzugefügt (Vivino)").
- **`_vrApplySideEffects(item)`** ändern:
  - Bisher: bei fehlendem Bild `downloadVivinoImage(item.image_url)` (Legacy-Slot).
  - Neu: wenn `item.image_url` → `POST /api/wine/<_editWineId>/images/vivino`
    mit `{url: item.image_url}`; bei Erfolg `loadWineGallery()` (BP2-Galerie
    aktualisieren). `aiImageField`/Preview werden nicht mehr gesetzt.
  - `vivino_id` (nur name-search-Pfad, nur wenn leer) und `wine_vivino_rating`
    bleiben wie bisher.
- `downloadVivinoImage` bleibt bestehen (wird ggf. noch vom Add-Flow genutzt);
  nur der Reload-Confirm-Pfad wird umgestellt.

## i18n

Neuer Key `vr_image_add` in 7 Sprachen (de/en/fr/it/es/pt/nl), z.B.
DE „Bild wird hinzugefügt (Vivino)", EN „Image will be added (Vivino)".

## CSS

`.vr-image-preview` — kleines Thumbnail (~72px, `object-fit: cover`, abgerundet)
im Confirm-Schritt 2.

## Tests / Verifikation

Backend (pytest):
- `_download_vivino_image` gemockt (gibt festen Dateinamen zurück): `POST
  /api/wine/<id>/images/vivino` legt ein `vivino`-Bild an; erstes Bild wird
  Default; `wine_json.images` enthält es.
- Zweiter Aufruf bei vorhandenem Default → neues vivino-Bild ist **nicht** Default.
- Unbekannter Wein → 404; Helfer gibt `None` → 400.
- `POST /api/vivino-image` funktioniert unverändert (Helfer-Refactor bricht nichts).

Frontend (Playwright, Bearbeiten-Modus, `image_url` eines Kandidaten gestubbt):
- Vivino-Confirm Schritt 2 zeigt die Bild-Vorschau + Label.
- „Übernehmen" ruft den neuen Endpoint (gemockter Download) → ein Vivino-Bild
  erscheint in der BP2-Galerie; kein `aiImageField` gesetzt.
- Keine JS-Fehler; bestehende Vivino-Feld-Übernahme (Name/Typ/Region/Rebsorte),
  `vivino_id`/`vivino_rating` unverändert.

## Nicht im Scope

- KI-Bildsuche (separates späteres Paket).
- BP5: KI-Bildauswahl-Schritt.
- Änderungen am Add-Flow-Vivino (Source-Step).
- Bild-Vorschau im KI-Confirm (die KI liefert kein Bild).
