# Fork-Rebrand „Wine Tracker DI" Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add-on-Identität und funktionale Owner-Referenzen des Forks auf d-imark umstellen, sodass „Wine Tracker DI" parallel zum Original in Home Assistant läuft.

**Architecture:** Config-/Docker-Änderungen für die HA-Add-on-Identität (Slug, Name, Port, `DATA_DIR`-Env für getrennte Daten) + textuelle Ersetzung funktionaler Owner-URLs `xenofex7`→`d-imark`. App-Code unverändert; Urheber-/Copyright-Angaben bleiben beim Original.

**Tech Stack:** HA Add-on (config.yaml/build.yaml/Dockerfile), Markdown/HTML/Shell Docs. Verifikation: YAML-Parse, grep, DATA_DIR-Auflösung, pytest.

## Global Constraints

- Neuer Slug `wine_tracker_di`, Name/panel_title „Wine Tracker DI", Host-Port **5051** (Container bleibt 5050), Ingress bleibt.
- Datenverzeichnis `/share/wine-tracker-di` via `ENV DATA_DIR` — **app.py NICHT ändern**.
- Funktionale URLs → d-imark. **NICHT ändern:** `LICENSE`-Copyright; Autoren-Credit-Strings in `docs/` (Meta-`author`, schema `author/creator` `name`, bare Profil-URL `github.com/xenofex7`, Footer „by xenofex7").
- Ordner `wine-tracker/` und UI-Text „Wine Tracker" bleiben. Kein Versions-Bump.

---

### Task 1: Add-on-Identität, Datenverzeichnis, Repository-Deskriptor

**Files:**
- Modify: `wine-tracker/config.yaml`
- Modify: `wine-tracker/Dockerfile`
- Modify: `repository.yaml`

**Interfaces:**
- Produces: Slug `wine_tracker_di`; Host-Port `5050/tcp: 5051`; `ENV DATA_DIR=/share/wine-tracker-di`; Repo-URL/Maintainer d-imark.

- [ ] **Step 1: `config.yaml` — Name/Slug/URL/Panel**

In `wine-tracker/config.yaml` ersetzen:
```yaml
name: "Wine Tracker DI"
description: "Track and manage your wine cellar"
version: "1.11.0"
slug: "wine_tracker_di"
url: "https://github.com/d-imark/ha-wine-tracker"
```
(nur `name`, `slug`, `url` geändert; `description`/`version` unverändert.)

- [ ] **Step 2: `config.yaml` — Port + panel_title**

Ersetzen:
```yaml
ports:
  5050/tcp: 5051
ports_description:
  5050/tcp: "Wine Tracker DI Web UI (host port 5051)"
```
und weiter unten:
```yaml
panel_title: "Wine Tracker DI"
```
(`ingress: true`, `ingress_port: 5050`, `map: [share:rw]`, `options`, `schema` bleiben unverändert.)

- [ ] **Step 3: `Dockerfile` — eigenes Datenverzeichnis**

In `wine-tracker/Dockerfile` die `EXPOSE`/`CMD`-Zeilen so ergänzen:
```dockerfile
EXPOSE 5050
ENV DATA_DIR=/share/wine-tracker-di
CMD ["python3", "app.py"]
```

- [ ] **Step 4: `repository.yaml`**

Kompletten Inhalt ersetzen durch:
```yaml
name: "Wine Tracker DI for Home Assistant"
url: "https://github.com/d-imark/ha-wine-tracker"
maintainer: "d-imark"
```

- [ ] **Step 5: YAML gültig + Identität korrekt**

Run:
```bash
cd wine-tracker && python -c "import yaml,io; [yaml.safe_load(open(f,encoding='utf-8')) for f in ['config.yaml','build.yaml']]; print('config/build OK')"
cd .. && python -c "import yaml; print(yaml.safe_load(open('repository.yaml',encoding='utf-8')))"
grep -nE 'slug:|ports:|5051|panel_title:|url:' wine-tracker/config.yaml
grep -n 'DATA_DIR' wine-tracker/Dockerfile
```
Expected: `config/build OK`; repository.yaml dict zeigt d-imark; `slug: "wine_tracker_di"`, `5050/tcp: 5051`, `panel_title: "Wine Tracker DI"`, d-imark-URL; Dockerfile enthält `ENV DATA_DIR=/share/wine-tracker-di`.

- [ ] **Step 6: DATA_DIR-Override greift (getrennte Daten)**

App-Modul mit gesetztem `DATA_DIR` importieren und Auflösung prüfen (PowerShell):
```powershell
$env:DATA_DIR = "$env:TEMP\wtdi_verify"
& "C:\Users\DominikImark\repos\ha-wine-tracker\.venv\Scripts\python.exe" -c "import sys; sys.path.insert(0,'wine-tracker/app'); import app; print(app.DATA_DIR); print(app.DB_PATH)"
Remove-Item Env:\DATA_DIR
```
Expected: Ausgabe zeigt `...\wtdi_verify` als `DATA_DIR` und `...\wtdi_verify\wine.db` als `DB_PATH` (bestätigt: Fork nutzt ein eigenes Verzeichnis → getrennte DB).

- [ ] **Step 7: Commit**

```bash
git add wine-tracker/config.yaml wine-tracker/Dockerfile repository.yaml
git commit -m "Rebrand add-on identity to Wine Tracker DI (slug, port 5051, DATA_DIR)"
```

---

### Task 2: Funktionale Owner-Referenzen xenofex7 → d-imark

**Files:**
- Modify: `README.md`, `wine-tracker/DOCS.md`, `wine-tracker/README.md`,
  `docker/docker-compose.yml`, `scripts/deploy.sh`, `scripts/update-ha-dev.sh`,
  `wine-tracker/app/templates/_settings_modal.html`,
  `docs/index.html`, `docs/llms.txt`, `docs/robots.txt`, `docs/sitemap.xml`

**Interfaces:**
- Consumes: nichts aus Task 1.
- Produces: alle funktionalen Repo-/Site-/Image-URLs zeigen auf d-imark; Urheber-Credits unverändert.

- [ ] **Step 1: URL-Ersetzungen anwenden**

Vier gezielte Ersetzungen über die Zieldateien (treffen nur URL-Kontexte, nie
den bloßen Namen `xenofex7` und nie `LICENSE`):
```bash
cd "c:/Users/DominikImark/repos/ha-wine-tracker"
FILES="README.md wine-tracker/DOCS.md wine-tracker/README.md docker/docker-compose.yml scripts/deploy.sh scripts/update-ha-dev.sh wine-tracker/app/templates/_settings_modal.html docs/index.html docs/llms.txt docs/robots.txt docs/sitemap.xml"
sed -i 's#xenofex7/ha-wine-tracker#d-imark/ha-wine-tracker#g' $FILES
sed -i 's#xenofex7\.github\.io#d-imark.github.io#g' $FILES
sed -i 's#ghcr\.io/xenofex7/wine-tracker#ghcr.io/d-imark/wine-tracker#g' $FILES
sed -i 's#%2Fxenofex7%2Fha-wine-tracker#%2Fd-imark%2Fha-wine-tracker#g' $FILES
echo done
```

- [ ] **Step 2: Verifizieren — funktionale URLs sauber, nur Credits verbleiben**

Run:
```bash
cd "c:/Users/DominikImark/repos/ha-wine-tracker"
echo "=== remaining xenofex7 (should be ONLY license + author credits) ==="
grep -rn "xenofex7" README.md wine-tracker docker scripts docs repository.yaml LICENSE 2>/dev/null | grep -v "docs/superpowers"
```
Expected: verbleibende Treffer sind ausschließlich:
- `LICENSE`: `Copyright (c) 2026 xenofex7`
- `docs/index.html`: `<meta name="author" content="xenofex7">`, schema `"name": "xenofex7"` (author + creator), bare `https://github.com/xenofex7` (Autor-Profil, ohne `/ha-wine-tracker`), Footer-Text `>xenofex7</a>`
- `docs/llms.txt`: `Made with 🍷 by xenofex7`

**Keine** verbleibenden Treffer mit `xenofex7/ha-wine-tracker`, `xenofex7.github.io`, `ghcr.io/xenofex7`, `%2Fxenofex7%2F`. Falls doch → per Edit korrigieren.

- [ ] **Step 3: Stichprobe der Kern-URLs**

Run:
```bash
cd "c:/Users/DominikImark/repos/ha-wine-tracker"
grep -n "d-imark/ha-wine-tracker" README.md | head -3
grep -n "image:" docker/docker-compose.yml
grep -n "REPO_URL" scripts/update-ha-dev.sh
grep -n "settings-link" wine-tracker/app/templates/_settings_modal.html | head -1
```
Expected: README Install-/Badge-URLs auf d-imark; docker-compose `image: ghcr.io/d-imark/wine-tracker:latest`; `REPO_URL="https://github.com/d-imark/ha-wine-tracker.git"`; Settings-Link vorhanden.

- [ ] **Step 4: Regression — App unverändert**

Run: `cd wine-tracker && ../.venv/Scripts/python.exe -m pytest -q`
Expected: 418 passed (App-Code nicht berührt).

- [ ] **Step 5: Commit**

```bash
git add README.md wine-tracker/DOCS.md wine-tracker/README.md docker/docker-compose.yml scripts/deploy.sh scripts/update-ha-dev.sh wine-tracker/app/templates/_settings_modal.html docs/index.html docs/llms.txt docs/robots.txt docs/sitemap.xml
git commit -m "Point functional URLs to the d-imark fork (keep original author credit)"
```

---

## Self-Review

**Spec-Abdeckung:**
- config.yaml Identität + Port → Task 1 Steps 1–2. ✓
- Dockerfile DATA_DIR → Task 1 Step 3 + Verifikation Step 6. ✓
- repository.yaml → Task 1 Step 4. ✓
- Funktionale URL-Ersetzung (alle Dateien) → Task 2 Step 1. ✓
- LICENSE + Autoren-Credits bewusst behalten → Task 2 Step 2 (Erwartung listet genau diese). ✓
- Parallel-Betrieb (Slug/Port/Datenpfad getrennt) → Task 1 (slug/port/DATA_DIR) + Step 6 beweist getrennte Daten. ✓
- Verifikation YAML/grep/pytest → Task 1 Step 5–6, Task 2 Step 2–4. ✓

**Placeholder-Scan:** kein TBD/TODO; konkrete Befehle/Inhalte je Step. ✓

**Typ-/Wert-Konsistenz:** Slug `wine_tracker_di`, Host-Port `5051` (Container 5050), Datenpfad `/share/wine-tracker-di`, Owner `d-imark` durchgängig identisch in allen Tasks/Dateien. ✓

**Hinweis:** `docs/robots.txt`/`sitemap.xml` enthalten ggf. nur `xenofex7.github.io`-URLs; Pattern 2 deckt sie ab. Enthält eine Zieldatei wider Erwarten kein `xenofex7`, ist der jeweilige `sed` ein harmloser No-op.
