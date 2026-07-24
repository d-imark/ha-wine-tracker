# Design: Fork-Rebrand „Wine Tracker DI" (parallel-fähig in Home Assistant)

## Kontext

Dieses Repo ist ein Fork von `xenofex7/ha-wine-tracker` (Home-Assistant-Add-on).
Origin = `github.com/d-imark/ha-wine-tracker`, Upstream = `xenofex7`. Ziel:
Add-on-Identität und Pfade auf den eigenen Owner umstellen, sodass der Fork
sauber installiert und **parallel** zum Original in Home Assistant laufen kann.

## Home-Assistant-Grundlagen (warum parallel geht)

HA identifiziert ein Add-on über **Repository + Slug** und gibt jedem Add-on
eigene Optionen (`/data/options.json`), einen eigenen Ingress-Pfad und ein
eigenes Panel. Für echten Parallelbetrieb mit **getrennten Daten** müssen sich
unterscheiden: Slug, Name/panel_title, **Host-Port** (sonst 5050-Kollision) und
das **Datenverzeichnis** — die App speichert DB + Uploads in `/share/wine-tracker`
(nicht im privaten `/data`), daher würde ein gemeinsamer Pfad dieselbe DB teilen.

## Entscheidungen

- Name/panel_title: **„Wine Tracker DI"**; Slug: **`wine_tracker_di`**.
- Host-Port **5051** (Container bleibt 5050); **Ingress bleibt** aktiv.
- Datenverzeichnis **`/share/wine-tracker-di`** via `DATA_DIR`-Env — **App-Code
  bleibt unverändert** (die App liest `DATA_DIR` bereits).
- Umfang: **nur Add-on-Identität** — Ordner `wine-tracker/` und App-Code/UI
  bleiben; Upstream-Merges bleiben einfach.

## Änderungen

### 1. `wine-tracker/config.yaml` (Identität + Port)
- `name`: „Wine Tracker" → „Wine Tracker DI"
- `panel_title`: „Wine Tracker" → „Wine Tracker DI"
- `slug`: `wine_tracker` → `wine_tracker_di`
- `url`: `…/xenofex7/…` → `…/d-imark/…`
- `ports`: `5050/tcp: 5050` → `5050/tcp: 5051`
- `ports_description`: Text auf „… (Host 5051)" o.ä. anpassen
- unverändert: `ingress: true`, `ingress_port: 5050`, `map: [share:rw]`,
  `options`/`schema`, `version`.

### 2. `wine-tracker/Dockerfile` (eigenes Datenverzeichnis)
- Vor `CMD` eine Zeile ergänzen: `ENV DATA_DIR=/share/wine-tracker-di`
- App-Code (`app.py`) bleibt unverändert.

### 3. `repository.yaml`
- `url` → `…/d-imark/…`, `maintainer` → „d-imark", `name` → „Wine Tracker DI
  for Home Assistant".

### 4. Funktionale Owner-Referenzen `xenofex7` → `d-imark`
Ersetzen in allen **funktionalen URLs / Repo-Links / Bild- & Badge-Quellen /
Docker-Image-Referenzen / my.home-assistant-Redirect**:
- `README.md` (Doku-Link, Repo-URL, `ghcr.io/…/wine-tracker`, Badges, my-ha-url)
- `wine-tracker/DOCS.md` (Logo/Screenshot-`raw.githubusercontent`-URLs, GitHub-Link)
- `wine-tracker/README.md` (Badge-/Repo-/Issues-URLs)
- `docker/docker-compose.yml` (`image: ghcr.io/d-imark/wine-tracker:latest`)
- `scripts/deploy.sh` (Releases-/Actions-URLs)
- `scripts/update-ha-dev.sh` (`REPO_URL`, curl-URL)
- `wine-tracker/app/templates/_settings_modal.html` (GitHub-Link, sofern vorhanden)
- `docs/` (Marketing-Seite: `index.html`, `llms.txt`, `robots.txt`, `sitemap.xml`)
  — funktionale URLs (canonical, og:url/-image, codeRepository, Install-Link,
  Badges, Docker-Image) auf d-imark.

### 5. Bewusst NICHT geändert (Urheberschaft)
- **`LICENSE`**: `Copyright (c) 2026 xenofex7` bleibt — ein Fork behält den
  Urheberrechtsvermerk des Originals.
- Urheber-/Credit-Angaben auf der Doku-Seite: schema.org `author`/`creator`
  `name`, `<meta name="author">` und der Footer „Made with 🍷 by xenofex7"
  bleiben als Credit des ursprünglichen Autors bestehen (nur die *Links* zeigen
  weiterhin korrekt; die Namensnennung wird nicht auf d-imark umgeschrieben).
  (Falls der Nutzer dies später anders möchte — z.B. „Fork maintained by
  d-imark" ergänzen — ist das eine bewusste separate Entscheidung.)

## Parallel-Installation in HA (Ergebnis)

Der Nutzer fügt in HA zusätzlich die Fork-Repo-URL
`https://github.com/d-imark/ha-wine-tracker` als Add-on-Repository hinzu.
Da anderes Repo, anderer Slug (`wine_tracker_di`), anderer Host-Port (5051) und
anderes Datenverzeichnis (`/share/wine-tracker-di`), laufen Original und Fork
unabhängig mit **getrennter Datenbank**.

## Verifikation

- `config.yaml`, `repository.yaml`, `build.yaml` bleiben gültiges YAML.
- Keine `xenofex7`-Reste in den Zieldateien (außer LICENSE + den bewusst
  behaltenen Credit-Strings in `docs/`).
- App startet lokal mit `DATA_DIR=<tmp>` und legt `wine.db` dort an (bestätigt
  den getrennten-Daten-Mechanismus).
- Volle pytest-Suite bleibt grün (App-Code unverändert).

## Nicht im Scope

- Kein Umbenennen des Ordners `wine-tracker/`.
- Keine UI-/Code-Umbenennung von „Wine Tracker" innerhalb der App.
- Kein Ändern der Urheberrechts-/Autoren-Angaben (siehe 5).
- Kein Versions-Bump.
