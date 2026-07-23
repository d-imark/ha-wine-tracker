#!/usr/bin/env python3
"""Build wine-tracker/app/reference_data.py from public-domain / CC0 sources.

Also (with --vivino-report) reads Vivino's reference lists and writes a coverage
gap report - it never bundles Vivino data, it only measures what our curated seed
is missing so a maintainer can decide what to add.

Data provenance (see also the header written into reference_data.py):
  - Country centroids + ISO codes:
      https://github.com/gavinr/world-countries-centroids  (MIT)
  - Wine-region coordinates / grape varieties + synonyms:
      https://www.wikidata.org  (CC0) + the project's existing REGION_COORDS
  - Wine types / colours / bottle formats: the project's own constants (MIT)

Usage:
  python scripts/build_reference_data.py                # regenerate reference_data.py
  python scripts/build_reference_data.py --vivino-report  # + coverage report vs Vivino
"""
from __future__ import annotations

import argparse
import csv
import io
import os
import unicodedata

GAVINR_CSV = "https://raw.githubusercontent.com/gavinr/world-countries-centroids/master/dist/countries.csv"

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "wine-tracker", "app", "reference_data.py")
REPORT_PATH = os.path.join(os.path.dirname(__file__), "reference_gap_report.md")


def normalize_name(s: str) -> str:
    """lowercase, strip accents, collapse punctuation/whitespace - for matching."""
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    out = []
    for ch in s.lower():
        out.append(ch if ch.isalnum() or ch.isspace() else " ")
    return " ".join("".join(out).split())


# ── Countries (fetched from gavinr CSV, MIT) ─────────────────────────────────

def fetch_countries():
    import requests
    r = requests.get(GAVINR_CSV, timeout=30)
    r.raise_for_status()
    rows = list(csv.DictReader(io.StringIO(r.text)))
    out = []
    for row in rows:
        code = (row.get("ISO") or "").strip().upper()
        name = (row.get("COUNTRY") or "").strip()
        try:
            lat = round(float(row["latitude"]), 4)
            lon = round(float(row["longitude"]), 4)
        except (KeyError, ValueError):
            continue
        if len(code) != 2 or not name:
            continue
        out.append({"code": code, "name": name, "lat": lat, "lon": lon})
    out.sort(key=lambda c: c["name"])
    return out


# German/native aliases for common wine countries, keyed by ISO code.
COUNTRY_ALIASES = {
    "FR": ["Frankreich", "France"], "IT": ["Italien", "Italia", "Italy"],
    "ES": ["Spanien", "España", "Spain"], "DE": ["Deutschland", "Germany"],
    "CH": ["Schweiz", "Suisse", "Svizzera", "Switzerland"], "AT": ["Österreich", "Austria"],
    "PT": ["Portugal"], "US": ["USA", "Vereinigte Staaten", "United States"],
    "AR": ["Argentinien", "Argentina"], "CL": ["Chile"], "AU": ["Australien", "Australia"],
    "NZ": ["Neuseeland", "New Zealand"], "ZA": ["Südafrika", "South Africa"],
    "GR": ["Griechenland", "Greece"], "HU": ["Ungarn", "Hungary"],
    "GE": ["Georgien", "Georgia"], "LB": ["Libanon", "Lebanon"],
    "HR": ["Kroatien", "Croatia"], "SI": ["Slowenien", "Slovenia"], "CA": ["Kanada", "Canada"],
}


# ── Regions (curated; based on the project's existing REGION_COORDS) ──────────
# (name, country_code, lat, lon, [aliases])
CURATED_REGIONS = [
    ("Bordeaux", "FR", 44.8, -0.6, []),
    ("Bourgogne", "FR", 47.0, 4.8, ["Burgund", "Burgundy"]),
    ("Champagne", "FR", 49.0, 3.9, []),
    ("Alsace", "FR", 48.3, 7.4, ["Elsass"]),
    ("Loire", "FR", 47.4, 0.7, []),
    ("Rhône", "FR", 44.9, 4.8, ["Rhone", "Côtes du Rhône"]),
    ("Provence", "FR", 43.5, 5.9, []),
    ("Languedoc", "FR", 43.3, 3.0, []),
    ("Jura", "FR", 46.7, 5.9, []),
    ("Beaujolais", "FR", 46.1, 4.6, []),
    ("Toscana", "IT", 43.4, 11.2, ["Toskana", "Tuscany"]),
    ("Piemonte", "IT", 44.7, 8.0, ["Piemont", "Piedmont"]),
    ("Veneto", "IT", 45.4, 12.3, ["Venetien"]),
    ("Sicilia", "IT", 37.5, 14.0, ["Sizilien", "Sicily"]),
    ("Sardegna", "IT", 40.1, 9.1, ["Sardinien"]),
    ("Puglia", "IT", 41.1, 16.9, ["Apulien"]),
    ("Abruzzo", "IT", 42.2, 13.8, ["Abruzzen"]),
    ("Alto Adige", "IT", 46.5, 11.3, ["Südtirol"]),
    ("Lombardia", "IT", 45.5, 9.9, ["Lombardei"]),
    ("Campania", "IT", 40.8, 14.3, ["Kampanien"]),
    ("Friuli", "IT", 46.1, 13.2, ["Friaul"]),
    ("Rioja", "ES", 42.5, -2.5, []),
    ("Ribera del Duero", "ES", 41.6, -3.7, []),
    ("Priorat", "ES", 41.2, 0.8, []),
    ("Penedès", "ES", 41.4, 1.7, []),
    ("Cataluña", "ES", 41.6, 1.5, ["Katalonien", "Catalunya"]),
    ("Galicia", "ES", 42.5, -8.0, ["Galizien"]),
    ("Navarra", "ES", 42.7, -1.6, []),
    ("Mosel", "DE", 49.9, 6.9, []),
    ("Rheingau", "DE", 50.0, 8.0, []),
    ("Pfalz", "DE", 49.3, 8.1, []),
    ("Baden", "DE", 48.0, 7.8, []),
    ("Franken", "DE", 49.8, 10.0, []),
    ("Rheinhessen", "DE", 49.8, 8.2, []),
    ("Ahr", "DE", 50.5, 7.1, []),
    ("Nahe", "DE", 49.8, 7.6, []),
    ("Württemberg", "DE", 48.8, 9.2, []),
    ("Wallis", "CH", 46.2, 7.6, ["Valais"]),
    ("Waadt", "CH", 46.5, 6.6, ["Vaud"]),
    ("Genf", "CH", 46.2, 6.1, ["Genève", "Geneva"]),
    ("Ticino", "CH", 46.2, 8.9, ["Tessin"]),
    ("Graubünden", "CH", 46.8, 9.8, ["Grisons"]),
    ("Schaffhausen", "CH", 47.7, 8.6, []),
    ("Zürich", "CH", 47.4, 8.5, []),
    ("Aargau", "CH", 47.4, 8.1, []),
    ("Wachau", "AT", 48.4, 15.4, []),
    ("Burgenland", "AT", 47.5, 16.5, []),
    ("Steiermark", "AT", 46.9, 15.5, ["Styria"]),
    ("Niederösterreich", "AT", 48.2, 15.7, []),
    ("Wien", "AT", 48.2, 16.4, ["Vienna"]),
    ("Douro", "PT", 41.2, -7.8, []),
    ("Alentejo", "PT", 38.5, -7.9, []),
    ("Dão", "PT", 40.5, -7.9, []),
    ("Minho", "PT", 41.8, -8.3, []),
    ("Napa Valley", "US", 38.5, -122.3, ["Napa"]),
    ("Sonoma", "US", 38.3, -122.7, []),
    ("California", "US", 36.8, -119.4, ["Kalifornien"]),
    ("Oregon", "US", 45.2, -122.8, []),
    ("Washington", "US", 46.8, -120.5, []),
    ("Mendoza", "AR", -33.0, -68.8, []),
    ("Maipo", "CL", -33.7, -70.6, []),
    ("Colchagua", "CL", -34.7, -71.2, []),
    ("Casablanca", "CL", -33.3, -71.4, []),
    ("Barossa Valley", "AU", -34.5, 138.9, ["Barossa"]),
    ("McLaren Vale", "AU", -35.2, 138.5, []),
    ("Hunter Valley", "AU", -32.8, 151.2, []),
    ("Margaret River", "AU", -33.9, 115.0, []),
    ("Tokaj", "HU", 48.1, 21.4, []),
    ("Stellenbosch", "ZA", -33.9, 18.8, []),
    ("Marlborough", "NZ", -41.5, 174.0, []),
    ("Hawke's Bay", "NZ", -39.5, 176.8, []),
    # ── additional notable appellations ──────────────────────────────────────
    ("Chablis", "FR", 47.8, 3.8, []),
    ("Sancerre", "FR", 47.3, 2.8, []),
    ("Châteauneuf-du-Pape", "FR", 44.1, 4.8, []),
    ("Sauternes", "FR", 44.5, -0.3, []),
    ("Médoc", "FR", 45.2, -0.8, []),
    ("Saint-Émilion", "FR", 44.9, -0.2, []),
    ("Pomerol", "FR", 44.9, -0.2, []),
    ("Chianti", "IT", 43.5, 11.3, ["Chianti Classico"]),
    ("Barolo", "IT", 44.6, 7.9, []),
    ("Barbaresco", "IT", 44.7, 8.1, []),
    ("Montalcino", "IT", 43.1, 11.5, ["Brunello di Montalcino"]),
    ("Valpolicella", "IT", 45.5, 10.9, []),
    ("Prosecco", "IT", 45.9, 12.2, ["Conegliano Valdobbiadene"]),
    ("Rías Baixas", "ES", 42.4, -8.7, []),
    ("Jerez", "ES", 36.7, -6.1, ["Sherry", "Xérès"]),
    ("Willamette Valley", "US", 45.2, -123.1, []),
    ("Paso Robles", "US", 35.6, -120.7, []),
    ("Coonawarra", "AU", -37.3, 140.8, []),
    ("Yarra Valley", "AU", -37.7, 145.5, []),
    ("Central Otago", "NZ", -45.0, 169.2, []),
    ("Kamptal", "AT", 48.5, 15.7, []),
    ("Kremstal", "AT", 48.4, 15.6, []),
]


# ── Grapes (curated common varieties; color + common synonyms) ───────────────
# (name, color, [aliases])
CURATED_GRAPES = [
    ("Cabernet Sauvignon", "red", []),
    ("Merlot", "red", []),
    ("Pinot Noir", "red", ["Spätburgunder", "Blauburgunder", "Pinot Nero"]),
    ("Syrah", "red", ["Shiraz"]),
    ("Grenache", "red", ["Garnacha", "Cannonau"]),
    ("Tempranillo", "red", ["Tinta Roriz", "Aragonez"]),
    ("Sangiovese", "red", ["Brunello", "Nielluccio"]),
    ("Nebbiolo", "red", []),
    ("Malbec", "red", []),
    ("Zinfandel", "red", ["Primitivo"]),
    ("Cabernet Franc", "red", []),
    ("Barbera", "red", []),
    ("Montepulciano", "red", []),
    ("Carménère", "red", []),
    ("Mourvèdre", "red", ["Monastrell", "Mataro"]),
    ("Gamay", "red", []),
    ("Petit Verdot", "red", []),
    ("Pinotage", "red", []),
    ("Touriga Nacional", "red", []),
    ("Dornfelder", "red", []),
    ("Blaufränkisch", "red", ["Lemberger", "Kékfrankos"]),
    ("Zweigelt", "red", []),
    ("Corvina", "red", []),
    ("Aglianico", "red", []),
    ("Tannat", "red", []),
    ("Chardonnay", "white", []),
    ("Sauvignon Blanc", "white", []),
    ("Riesling", "white", []),
    ("Pinot Gris", "white", ["Pinot Grigio", "Grauburgunder"]),
    ("Pinot Blanc", "white", ["Weissburgunder", "Pinot Bianco"]),
    ("Chenin Blanc", "white", []),
    ("Gewürztraminer", "white", ["Traminer"]),
    ("Viognier", "white", []),
    ("Grüner Veltliner", "white", []),
    ("Sémillon", "white", []),
    ("Muscat", "white", ["Muskateller", "Moscato", "Muscatel"]),
    ("Albariño", "white", ["Alvarinho"]),
    ("Verdejo", "white", []),
    ("Vermentino", "white", []),
    ("Garganega", "white", []),
    ("Trebbiano", "white", ["Ugni Blanc"]),
    ("Silvaner", "white", ["Sylvaner"]),
    ("Müller-Thurgau", "white", ["Rivaner"]),
    ("Marsanne", "white", []),
    ("Roussanne", "white", []),
    ("Furmint", "white", []),
    ("Assyrtiko", "white", []),
    ("Glera", "white", ["Prosecco"]),
    ("Chasselas", "white", ["Fendant", "Gutedel"]),
    ("Sylvaner", "white", []),
    ("Palomino", "white", []),
    ("Cortese", "white", ["Gavi"]),
    # ── expanded head of the distribution ────────────────────────────────────
    ("Petite Sirah", "red", ["Durif"]),
    ("Carignan", "red", ["Mazuelo", "Cariñena", "Carignano"]),
    ("Cinsault", "red", ["Cinsaut"]),
    ("Dolcetto", "red", []),
    ("Lagrein", "red", []),
    ("Refosco", "red", []),
    ("Schiava", "red", ["Vernatsch", "Trollinger"]),
    ("Nero d'Avola", "red", []),
    ("Frappato", "red", []),
    ("Sagrantino", "red", []),
    ("Teroldego", "red", []),
    ("Xinomavro", "red", []),
    ("Saperavi", "red", []),
    ("Mencía", "red", ["Jaen"]),
    ("Bobal", "red", []),
    ("Graciano", "red", []),
    ("Touriga Franca", "red", []),
    ("Baga", "red", []),
    ("Castelão", "red", ["Periquita"]),
    ("Bonarda", "red", []),
    ("Pinot Meunier", "red", ["Meunier", "Schwarzriesling"]),
    ("Trousseau", "red", ["Bastardo"]),
    ("Saint Laurent", "red", ["Sankt Laurent"]),
    ("Torrontés", "white", []),
    ("Godello", "white", []),
    ("Verdicchio", "white", []),
    ("Fiano", "white", []),
    ("Falanghina", "white", []),
    ("Greco", "white", ["Greco di Tufo"]),
    ("Kerner", "white", []),
    ("Scheurebe", "white", []),
    ("Aligoté", "white", []),
    ("Melon de Bourgogne", "white", ["Muscadet"]),
    ("Colombard", "white", []),
    ("Picpoul", "white", ["Piquepoul"]),
    ("Malvasia", "white", ["Malvazija"]),
    ("Verdelho", "white", []),
    ("Arinto", "white", []),
    ("Macabeo", "white", ["Viura"]),
    ("Xarel·lo", "white", ["Xarel-lo"]),
    ("Parellada", "white", []),
    ("Airén", "white", []),
    ("Grillo", "white", []),
    ("Catarratto", "white", []),
    ("Rkatsiteli", "white", []),
    ("Moschofilero", "white", []),
    ("Assyrtico", "white", ["Assyrtiko"]),
    ("Welschriesling", "white", ["Riesling Italico", "Graševina"]),
]


# ── Wine types + colours (project's WINE_TYPES + --wine-* CSS vars) ───────────
WINE_TYPES = [
    ("Rotwein", "#803039"),
    ("Weisswein", "#f4ca4f"),
    ("Rosé", "#ffd1d8"),
    ("Schaumwein", "#f3efaf"),
    ("Dessertwein", "#eb7a17"),
    ("Likörwein", "#800f1c"),
    ("Anderes", "#6c3461"),
]

# ── Bottle formats (project's existing list) ─────────────────────────────────
BOTTLE_FORMATS = [
    ("Piccolo", 0.1875), ("Demi", 0.375), ("Standard", 0.75), ("Magnum", 1.5),
    ("Double Magnum", 3.0), ("Jeroboam", 4.5), ("Imperial", 6.0),
    ("Salmanazar", 9.0), ("Balthazar", 12.0), ("Nebuchadnezzar", 15.0),
]


HEADER = '''# ── Wine Tracker - bundled reference data ──────────────────────────────────────
# AUTO-GENERATED by scripts/build_reference_data.py - do not edit by hand.
#
# Provenance / licences:
#   countries  : github.com/gavinr/world-countries-centroids (MIT), ISO 3166-1
#   regions    : project REGION_COORDS + Wikidata (CC0)
#   grapes     : Wikidata (CC0) + general knowledge
#   wine_types : project WINE_TYPES + --wine-* colours (MIT)
#   formats    : project bottle-format list (MIT)
# No Vivino data is bundled here.
'''


def emit(countries):
    def lit(v):
        return repr(v)
    lines = [HEADER, "", "COUNTRIES = ["]
    for c in countries:
        lines.append(f"    {{'code': {lit(c['code'])}, 'name': {lit(c['name'])}, "
                     f"'lat': {c['lat']}, 'lon': {c['lon']}, "
                     f"'aliases': {lit(COUNTRY_ALIASES.get(c['code'], []))}}},")
    lines.append("]")
    lines.append("")
    lines.append("REGIONS = [")
    for name, cc, lat, lon, aliases in CURATED_REGIONS:
        lines.append(f"    {{'name': {lit(name)}, 'country_code': {lit(cc)}, "
                     f"'lat': {lat}, 'lon': {lon}, 'aliases': {lit(aliases)}}},")
    lines.append("]")
    lines.append("")
    lines.append("GRAPES = [")
    for name, color, aliases in CURATED_GRAPES:
        lines.append(f"    {{'name': {lit(name)}, 'color': {lit(color)}, 'aliases': {lit(aliases)}}},")
    lines.append("]")
    lines.append("")
    lines.append("WINE_TYPES = [")
    for key, color in WINE_TYPES:
        lines.append(f"    {{'key': {lit(key)}, 'color': {lit(color)}, 'aliases': []}},")
    lines.append("]")
    lines.append("")
    lines.append("BOTTLE_FORMATS = [")
    for name, liters in BOTTLE_FORMATS:
        lines.append(f"    {{'name': {lit(name)}, 'liters': {liters}}},")
    lines.append("]")
    lines.append("")
    with open(os.path.abspath(OUT_PATH), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(countries)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vivino-report", action="store_true",
                    help="also fetch Vivino reference lists and write a coverage gap report")
    args = ap.parse_args()

    print("Fetching country centroids (gavinr, MIT)...")
    countries = fetch_countries()
    n = emit(countries)
    print(f"Wrote {os.path.abspath(OUT_PATH)}: {n} countries, "
          f"{len(CURATED_REGIONS)} regions, {len(CURATED_GRAPES)} grapes, "
          f"{len(WINE_TYPES)} types, {len(BOTTLE_FORMATS)} formats.")

    if args.vivino_report:
        from vivino_gap import write_gap_report  # local helper, added alongside
        write_gap_report(countries, CURATED_REGIONS, CURATED_GRAPES, REPORT_PATH, normalize_name)


if __name__ == "__main__":
    main()
