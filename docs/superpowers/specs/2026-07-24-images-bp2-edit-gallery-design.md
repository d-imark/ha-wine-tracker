# Design: Flexible Bilder — BP2 (Bildverwaltung im Bearbeiten-Dialog)

## Kontext

Teil 2 des Bild-Pakets. BP1 hat Datenmodell (`wine_images`), Modul `images.py`
und CRUD-Endpoints geliefert; `wines.image` spiegelt den Default. BP2 baut die
**Verwaltungs-UI** im Bearbeiten-Dialog darauf auf.

## Ziel

Im Bearbeiten-Dialog (existierender Wein) mehrere Bilder je Kategorie
(scan/vivino/ki/manuell) verwalten: anzeigen, hochladen, löschen, Default für die
Anzeige wählen. Aktionen greifen **sofort** über die BP1-Endpoints.

## Entscheidungen (aus dem Brainstorming)

- Nur im **Bearbeiten**-Dialog (Wein hat id). Anlegen behält den bisherigen
  Einzelbild-Upload (wird beim Speichern zum scan-Default); volle Verwaltung nach
  dem ersten Speichern.
- Aktionen **sofort** via API (`/api/wine/<id>/images…`), unabhängig vom
  Formular-Speichern.
- **Kein Rotieren** in BP2 (kein Rotate-Endpoint; YAGNI).

## Nur-Frontend

Reine Frontend-Änderung in `_wine_edit_modal.html` (+ `style.css`,
`translations.py`). Keine Backend-/Schema-Änderung (BP1-Endpoints genügen).

## UI

Im Bearbeiten-Modus wird der bisherige Einzel-Slot im `form-photo-panel` durch
eine **Galerie** ersetzt:

- **Thumbnail-Grid** (`#wineGallery`): pro Bild ein `<div class="gal-item">` mit
  - `<img>` (aus `INGRESS + '/uploads/' + filename`),
  - **Kategorie-Badge** (klein, Text = übersetzte Kategorie),
  - **Default-Stern** oben (gefüllt `mdi-star` beim Default, sonst
    `mdi-star-outline`) → Klick `POST …/<id>/default`,
  - **Löschen-×** (`mdi-close`) → kurze JS-`confirm`-Bestätigung → `DELETE`.
  - Das Default-Item erhält die Klasse `is-default` (hervorgehobener Rahmen).
- **Upload-Zeile** (`#galUpload`) unter dem Grid: verstecktes `<input type=file>`
  + „Hinzufügen"-Button + **Kategorie-Dropdown** (`scan/vivino/ki/manuell`,
  Default `manuell`). Bei Dateiauswahl: `POST …/images` (multipart: `image`,
  `category`), danach Galerie neu laden.
- Im **Anlegen**-Modus wird die Galerie ausgeblendet und der bestehende
  Einzel-Slot (`#winePreview`) wie bisher gezeigt.

## JS-Funktionen (in `_wine_edit_modal.html`)

- `initWineGallery(wineId)` — steuert Sichtbarkeit: bei `wineId` (edit) Galerie
  laden + Einzel-Slot ausblenden; sonst Galerie ausblenden + Einzel-Slot zeigen.
  Aufgerufen aus `openWineModal` (nachdem `_editWineId` gesetzt ist).
- `loadWineGallery()` — `GET /api/wine/<_editWineId>/images` → `renderWineGallery`.
- `renderWineGallery(images)` — baut das Grid; leere Liste → dezenter Hinweis.
- `galSetDefault(imageId)` — `POST …/<imageId>/default` → `loadWineGallery`.
- `galDelete(imageId)` — `confirm` → `DELETE …/<imageId>` → `loadWineGallery`.
- `galUpload(fileInput)` — nimmt `fileInput.files[0]` + gewählte Kategorie,
  `POST …/images` (FormData), bei Erfolg `loadWineGallery` + Input zurücksetzen.
- Alle `fetch` mit Header `X-Requested-With: XMLHttpRequest`; Fehler → dezenter
  Toast (`showReloadToast(T.ref_save_error, false)` o.ä., bestehende Toast-Funktion).

## Konsistenz mit dem Formular-Speichern

Im Bearbeiten-Modus bleibt der Legacy-Einzel-Upload **inert**: das Datei-`input`
im `#winePreview` wird ausgeblendet und nicht befüllt, `deleteImageField` bleibt
leer. Damit gilt beim `edit`-Submit `image == wine["image"]` (aktueller Default),
und `images.sync_primary(db, wine_id, wine["image"], image)` ist ein No-op
(setzt denselben Default erneut). Galerie-Änderungen (Upload/Delete/Default) sind
bereits persistiert und werden vom Formular-Speichern nicht überschrieben.

Die Anzeige (Karte) aktualisiert sich beim nächsten Laden/Speichern über den
gespiegelten `wines.image`. Eine sofortige Kartenaktualisierung ist nicht Teil
von BP2.

## i18n

Neue Keys in 7 Sprachen (`translations.py`):
- `img_add` — „Bild hinzufügen"
- `img_delete_confirm` — „Bild löschen?"
- `img_default` — „Als Anzeige-Bild"
- `img_cat_scan`, `img_cat_vivino`, `img_cat_ki`, `img_cat_manuell` —
  Kategorie-Labels (Scan / Vivino / KI / Manuell).

## CSS

`style.css`: `.wine-gallery` (Grid), `.gal-item` (Thumbnail-Container,
`is-default`-Rahmen), `.gal-badge`, `.gal-star`, `.gal-del`, `.gal-upload`.
Responsiv (Grid mit `auto-fill`/`minmax`), Thumbnails quadratisch mit
`object-fit: cover`.

## Tests / Verifikation

Backend unverändert → keine neuen pytest-Tests. Frontend per Playwright
(System-Chrome, Bilder über die BP1-API vorab angelegt):
- Bearbeiten-Dialog eines Weins mit ≥1 Bild → Galerie zeigt Thumbnails, Default
  markiert; Einzel-Slot ausgeblendet.
- Upload (gestubbte/echte Datei, Kategorie manuell) → neues Thumbnail erscheint.
- Default-Stern auf ein anderes Bild klicken → Stern wandert, `GET` bestätigt
  neuen Default; `wine_json.image` folgt.
- Löschen → Thumbnail verschwindet; war es Default, rückt ein anderes nach.
- Anlegen-Dialog → Galerie ausgeblendet, klassischer Einzel-Slot sichtbar.
- Keine JS-Fehler; bestehende Flows (Reload/Reconcile/Speichern) unverändert.

## Nicht im Scope (spätere Pakete)

- BP3: Galerie in der Detailansicht (Anzeige, nicht Verwaltung).
- BP4: Bild-Änderungen in den Vivino-/KI-Confirm-Dialogen.
- BP5: KI-Bildauswahl-Schritt.
- Rotieren/Zuschneiden von Bildern.
- Mehrbild-Verwaltung im Anlegen-Dialog.
