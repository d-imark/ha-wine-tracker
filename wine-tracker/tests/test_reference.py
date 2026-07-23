"""Tests for the reference-data layer (TP1): tables, seed, matching, read API."""
import os
import sqlite3
import sys
from unittest.mock import patch

import pytest

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, APP_DIR)

import app as wine_app
import reference

AJAX = {"X-Requested-With": "XMLHttpRequest"}

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


class TestSuggestAndAlias:
    def test_suggest_grape_typo_ranks_correct_top(self, db):
        # "Shirazz" (typo of the Shiraz alias) should rank Syrah first.
        out = reference.suggest_matches(db, "grape", "Shirazz", limit=5)
        assert out and out[0]["name"] == "Syrah"

    def test_suggest_region_typo_scoped_to_country(self, db):
        out = reference.suggest_matches(db, "region", "Bordeux", country_code="FR", limit=5)
        assert out and out[0]["name"] == "Bordeaux"
        assert all((r["country_code"] or "").upper() == "FR" for r in out)

    def test_add_alias_makes_future_match(self, db):
        syrah = reference.match_reference(db, "grape", "Syrah")
        assert reference.add_alias(db, "grape", syrah["id"], "Balsamina") is True
        db.commit()
        assert reference.match_reference(db, "grape", "Balsamina")["name"] == "Syrah"

    def test_add_alias_is_idempotent(self, db):
        syrah = reference.match_reference(db, "grape", "Syrah")
        reference.add_alias(db, "grape", syrah["id"], "Sirah")
        reference.add_alias(db, "grape", syrah["id"], "Sirah")
        db.commit()
        import json
        aliases = json.loads(db.execute("SELECT aliases FROM ref_grapes WHERE id=?", (syrah["id"],)).fetchone()[0])
        assert aliases.count("Sirah") == 1


class TestCustomCrud:
    def test_create_custom_grape(self, db):
        row = reference.create_custom(db, "grapes", {"name": "Zibibbo", "color": "white"})
        db.commit()
        assert row["is_custom"] == 1 and row["norm"] == "zibibbo"
        assert db.execute("SELECT COUNT(*) FROM ref_grapes WHERE name='Zibibbo'").fetchone()[0] == 1

    def test_create_requires_required_fields(self, db):
        with pytest.raises(ValueError):
            reference.create_custom(db, "grapes", {"color": "red"})       # no name
        with pytest.raises(ValueError):
            reference.create_custom(db, "regions", {"name": "X"})          # no country_code

    def test_create_rejects_duplicate(self, db):
        with pytest.raises(ValueError):
            reference.create_custom(db, "grapes", {"name": "Merlot"})      # already built-in

    def test_update_custom(self, db):
        row = reference.create_custom(db, "grapes", {"name": "Nerello", "color": "red"})
        db.commit()
        reference.update_custom(db, "grapes", row["id"], {"name": "Nerello", "color": "white"})
        db.commit()
        assert db.execute("SELECT color FROM ref_grapes WHERE id=?", (row["id"],)).fetchone()[0] == "white"

    def test_update_builtin_forbidden(self, db):
        builtin = db.execute("SELECT id FROM ref_grapes WHERE is_custom=0 LIMIT 1").fetchone()[0]
        with pytest.raises(PermissionError):
            reference.update_custom(db, "grapes", builtin, {"name": "Hacked"})

    def test_delete_custom(self, db):
        row = reference.create_custom(db, "grapes", {"name": "Deleteme"})
        db.commit()
        assert reference.delete_custom(db, "grapes", row["id"]) is True
        db.commit()
        assert db.execute("SELECT COUNT(*) FROM ref_grapes WHERE id=?", (row["id"],)).fetchone()[0] == 0

    def test_delete_builtin_forbidden(self, db):
        builtin = db.execute("SELECT id FROM ref_grapes WHERE is_custom=0 LIMIT 1").fetchone()[0]
        with pytest.raises(PermissionError):
            reference.delete_custom(db, "grapes", builtin)


class TestCrudApi:
    def _first_custom(self, client, entity, create):
        import json
        r = client.post(f"/api/reference/{entity}", data=json.dumps(create),
                        content_type="application/json", headers=AJAX)
        return json.loads(r.data)

    def test_post_creates_custom(self, client):
        import json
        r = client.post("/api/reference/grapes",
                        data=json.dumps({"name": "Xynomavro Test", "color": "red"}),
                        content_type="application/json", headers=AJAX)
        assert r.status_code == 200
        data = json.loads(r.data)
        assert data["ok"] and data["item"]["is_custom"] == 1

    def test_put_builtin_forbidden(self, client, db):
        import json
        bid = db.execute("SELECT id FROM ref_grapes WHERE is_custom=0 LIMIT 1").fetchone()[0]
        r = client.put(f"/api/reference/grapes/{bid}",
                       data=json.dumps({"name": "Nope"}), content_type="application/json", headers=AJAX)
        assert r.status_code == 403

    def test_delete_custom_via_api(self, client):
        import json
        created = json.loads(client.post("/api/reference/grapes",
                             data=json.dumps({"name": "TempGrape"}),
                             content_type="application/json", headers=AJAX).data)
        gid = created["item"]["id"]
        r = client.delete(f"/api/reference/grapes/{gid}", headers=AJAX)
        assert r.status_code == 200

    def test_post_validation_error(self, client):
        import json
        r = client.post("/api/reference/grapes", data=json.dumps({"color": "red"}),
                        content_type="application/json", headers=AJAX)
        assert r.status_code == 400

    def test_post_unknown_entity(self, client):
        import json
        r = client.post("/api/reference/bogus", data=json.dumps({"name": "x"}),
                        content_type="application/json", headers=AJAX)
        assert r.status_code == 404


class TestReconcile:
    """Save-time reconciliation endpoint (TP3b): suggest known matches for
    unknown grape/region values; AI pick when configured; alias learning."""

    def _post(self, client, payload):
        import json
        return json.loads(client.post("/api/reference/reconcile", data=json.dumps(payload),
                                      content_type="application/json", headers=AJAX).data)

    def test_exact_match_yields_no_items(self, client):
        data = self._post(client, {"grape": "Merlot"})
        assert data["ok"] is True
        assert data["items"] == []

    def test_unknown_grape_returns_suggestions(self, client):
        data = self._post(client, {"grape": "Cabernet Savignon"})  # typo
        assert len(data["items"]) == 1
        item = data["items"][0]
        assert item["entity"] == "grape"
        names = [s["name"] for s in item["suggestions"]]
        assert "Cabernet Sauvignon" in names
        assert item["ai_pick"] is None  # no AI configured in tests

    def test_region_scoped_by_country(self, client):
        data = self._post(client, {"region": "Bordeux", "country": "France"})
        item = next(i for i in data["items"] if i["entity"] == "region")
        assert "Bordeaux" in [s["name"] for s in item["suggestions"]]

    def test_alias_endpoint_teaches_match(self, client, db):
        gid = reference.match_reference(db, "grape", "Syrah")["id"]
        import json
        r = client.post(f"/api/reference/grape/{gid}/alias", data=json.dumps({"alias": "Balsamina"}),
                        content_type="application/json", headers=AJAX)
        assert r.status_code == 200
        # a fresh reconcile for "Balsamina" now matches Syrah exactly -> no items
        assert self._post(client, {"grape": "Balsamina"})["items"] == []

    @patch("app._call_chat")
    def test_ai_pick_when_configured(self, mock_chat, client, monkeypatch):
        import app as wine_app
        monkeypatch.setattr(wine_app, "load_options", lambda: {
            "ai_provider": "anthropic", "anthropic_api_key": "k", "anthropic_model": "m"})
        mock_chat.return_value = "Cabernet Sauvignon"
        data = self._post(client, {"grape": "Cab Sauv"})
        assert data["items"][0]["ai_pick"] == "Cabernet Sauvignon"


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
