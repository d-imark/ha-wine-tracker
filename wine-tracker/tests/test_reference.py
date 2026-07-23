"""Tests for the reference-data layer (TP1): tables, seed, matching, read API."""
import os
import sqlite3
import sys

import pytest

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, APP_DIR)

import app as wine_app
import reference


REF_TABLES = ["ref_countries", "ref_regions", "ref_grapes", "ref_wine_types", "ref_bottle_formats"]


class TestNormalize:
    def test_strips_accents_and_case(self):
        assert reference.normalize_name("Gewürztraminer") == reference.normalize_name("gewurztraminer")

    def test_strips_punctuation_and_quotes(self):
        assert reference.normalize_name("Alsace Grand Cru 'Goldert'") == "alsace grand cru goldert"

    def test_empty(self):
        assert reference.normalize_name("") == ""
        assert reference.normalize_name(None) == ""


class TestSchemaAndSeed:
    def test_all_tables_exist(self, db):
        names = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for t in REF_TABLES:
            assert t in names, t

    def test_seed_populates_builtins(self, db):
        fr = db.execute("SELECT * FROM ref_countries WHERE code='FR'").fetchone()
        assert fr is not None and fr["lat"] and fr["lon"]
        rot = db.execute("SELECT * FROM ref_wine_types WHERE key='Rotwein'").fetchone()
        assert rot is not None and rot["color"] == "#803039"
        mag = db.execute("SELECT * FROM ref_bottle_formats WHERE name='Magnum'").fetchone()
        assert mag is not None and mag["liters"] == 1.5
        # grapes + regions non-empty
        assert db.execute("SELECT COUNT(*) FROM ref_grapes").fetchone()[0] > 0
        assert db.execute("SELECT COUNT(*) FROM ref_regions").fetchone()[0] > 0

    def test_seed_is_idempotent(self, db):
        before = db.execute("SELECT COUNT(*) FROM ref_countries").fetchone()[0]
        reference.seed_reference_data(db)
        db.commit()
        after = db.execute("SELECT COUNT(*) FROM ref_countries").fetchone()[0]
        assert after == before

    def test_custom_and_edits_survive_reseed(self, db):
        # A custom grape and an edited built-in country must survive re-seeding.
        db.execute("INSERT INTO ref_grapes (name, norm, color, aliases, is_custom, sort_order) "
                   "VALUES ('MyGrape','mygrape','red','[]',1,0)")
        db.execute("UPDATE ref_countries SET lat=1.234 WHERE code='FR'")
        db.commit()
        reference.seed_reference_data(db)
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM ref_grapes WHERE name='MyGrape'").fetchone()[0] == 1
        assert db.execute("SELECT lat FROM ref_countries WHERE code='FR'").fetchone()[0] == 1.234


class TestMatching:
    def test_country_by_code(self, db):
        row = reference.match_reference(db, "country", "fr")
        assert row and row["code"] == "FR"

    def test_grape_by_alias(self, db):
        row = reference.match_reference(db, "grape", "Shiraz")
        assert row and row["name"] == "Syrah"

    def test_grape_by_normalized_name(self, db):
        row = reference.match_reference(db, "grape", "  gewürztraminer ")
        assert row and row["name"] == "Gewürztraminer"

    def test_region_within_country(self, db):
        row = reference.match_reference(db, "region", "Bordeaux", country_code="FR")
        assert row and row["name"] == "Bordeaux"

    def test_no_match_returns_none(self, db):
        assert reference.match_reference(db, "grape", "TotallyUnknownGrape123") is None
        assert reference.match_reference(db, "region", "Nowhereville", country_code="FR") is None

    def test_add_custom_entry_idempotent(self, db):
        r1 = reference.add_custom_entry(db, "grape", name="Zibibbo")
        db.commit()
        r2 = reference.add_custom_entry(db, "grape", name="Zibibbo")
        db.commit()
        assert r1["id"] == r2["id"]
        assert db.execute("SELECT COUNT(*) FROM ref_grapes WHERE name='Zibibbo'").fetchone()[0] == 1


class TestReadApi:
    def test_list_countries(self, client):
        resp = client.get("/api/reference/countries")
        assert resp.status_code == 200
        import json
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert any(c["code"] == "FR" for c in data["items"])

    def test_regions_filtered_by_country(self, client):
        import json
        resp = client.get("/api/reference/regions?country=FR")
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["items"]
        assert all(r["country_code"] == "FR" for r in data["items"])

    def test_unknown_entity_404(self, client):
        resp = client.get("/api/reference/bogus")
        assert resp.status_code == 404
