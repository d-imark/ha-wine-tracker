# Design: Flexible Bilder — BP3 (Galerie in der Detailansicht)

## Kontext

Teil 3 des Bild-Pakets. BP1 liefert Datenmodell + `wine_json.images`; BP2 die
Verwaltung im Bearbeiten-Dialog. BP3 zeigt in der **Detailansicht** alle Bilder
eines Weins (read-only), statt nur das Default-Bild.

## Ziel

Hat ein Wein mehrere Bilder, zeigt die Detailansicht ein **Hauptbild** (Default)
plus einen **Thumbnail-Streifen** aller Bilder. Klick auf ein Thumbnail tauscht
das Hauptbild; Klick aufs Hauptbild öffnet die bestehende Lightbox mit dem gerade
gezeigten Bild.

## Entscheidungen

- Nur Anzeige (read-only); Verwaltung bleibt BP2.
- Galerie nur bei **> 1 Bild**; bei 0/1 Bild bleibt das heutige Verhalten
  unverändert (einzelnes Foto bzw. Ribbon-only ohne Bild).
- Keine Kategorie-Badges im Detail (schlankes Ansehen, YAGNI).
- Keine Vor/Zurück-Navigation in der Lightbox (nicht gewählt).

## Nur-Frontend

Reine Frontend-Änderung in `index.html` (`openViewModal`) + `style.css`. Keine
Backend-Änderung: `viewFromCard` lädt bereits `wine_json` (inkl. `images`).

## UI / Verhalten

Im `openViewModal`-Foto-Panel:

- **> 1 Bild:** Panel enthält
  - Hauptbild `#viewMainImg` (Quelle = Default-Dateiname; `w.image` ist der
    Default), plus Ribbon (Weintyp) wie bisher.
  - Darunter ein Streifen `#viewThumbs` mit einem `<img>`/Button je Bild
    (`class="vthumb"`, das aktuell gezeigte hat `vthumb-active`).
  - Klick auf Thumbnail: setzt `#viewMainImg`-`src` auf dieses Bild, verschiebt
    `vthumb-active`.
  - Klick auf Hauptbild: `openLightbox(<aktuelle src>)` (bestehende Funktion).
- **1 Bild:** wie heute — Panel mit dem einen Bild, Klick → Lightbox.
- **0 Bilder:** wie heute — `view-no-image` mit Ribbon bzw. nichts.

Die Reihenfolge der Thumbnails folgt `w.images` (nach `sort_order`); das
Default-Bild wird zuerst als Hauptbild gezeigt und im Streifen markiert.

## Implementierung

`openViewModal` (in `index.html`), der Block „Photo panel":

- Neue Hilfsfunktion `viewGalleryHtml(w, ribbonHtml)` liefert das Panel-HTML:
  - `imgs = w.images || []`.
  - `imgs.length > 1`: Hauptbild + Thumb-Streifen (siehe UI). Hauptbild-src =
    `w.image` (Default) oder das erste Bild.
  - `imgs.length === 1` **oder** kein `images`-Array aber `w.image` vorhanden:
    bisheriges Einzel-Panel.
  - sonst: `view-no-image` (mit Ribbon) bzw. leer.
- Neue JS-Funktion `viewSelectThumb(el, url)`: setzt Hauptbild-src, toggelt
  `vthumb-active`.
- Hauptbild-`onclick` ruft `openLightbox(document.getElementById('viewMainImg').src)`.

Alle Pfade über `INGRESS + '/uploads/' + encodeURIComponent(filename)`; alle
Ausgaben HTML-escaped wie im Bestand (`escapeHtml`).

## CSS

`style.css`:
- `.view-thumbs` — Flex-Reihe, `overflow-x:auto`, kleine Lücken.
- `.vthumb` — quadratisch (~52px), `object-fit:cover`, abgerundet, Cursor
  pointer, dezenter Rahmen.
- `.vthumb-active` — Akzent-Rahmen.

## Tests / Verifikation

Backend unverändert → keine neuen pytest-Tests. Playwright (Bilder via BP1-API
vorab angelegt):
- Detailansicht eines Weins mit ≥2 Bildern → Hauptbild sichtbar, `#viewThumbs`
  mit N Thumbnails, eines aktiv.
- Klick auf ein anderes Thumbnail → `#viewMainImg`-`src` wechselt, `vthumb-active`
  wandert.
- Wein mit genau 1 Bild → kein Thumb-Streifen, Einzel-Bild wie bisher.
- Klick aufs Hauptbild öffnet die Lightbox.
- Keine JS-Fehler; bestehende Detailansicht-Elemente (Name, Meta, Rating,
  KI-Basis, Notizen) unverändert.

## Nicht im Scope

- BP4: Bild-Änderungen in den Vivino-/KI-Confirm-Dialogen.
- BP5: KI-Bildauswahl-Schritt.
- Lightbox-Navigation zwischen Bildern.
- Bildverwaltung in der Detailansicht (bleibt BP2/Bearbeiten).
