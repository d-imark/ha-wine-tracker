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

    def test_decisive_typo_is_picked_without_ai(self, client):
        """A near-perfect spelling match needs no AI round-trip, and must be
        labelled as a spelling match rather than credited to the AI."""
        item = self._post(client, {"grape": "Cabernet Savignon"})["items"][0]
        assert item["ai_pick"] == "Cabernet Sauvignon"
        assert item["pick_source"] == "fuzzy"

    def test_hopeless_value_gets_no_pick(self, client):
        """Nothing plausible exists, so there is nothing to suggest either -
        and no AI call is worth making (none is configured in tests anyway)."""
        item = self._post(client, {"grape": "Zzzqqx Yyw"})["items"][0]
        assert item["ai_pick"] is None
        assert item["pick_source"] is None

    def test_reconcile_stays_off_the_network_when_ai_is_off(self, client, monkeypatch):
        import app as wine_app

        def boom(*a, **k):
            raise AssertionError("no AI call may happen when no provider is configured")

        monkeypatch.setattr(wine_app, "_call_chat", boom)
        data = self._post(client, {"grapes": ["Merlott", "Zzzqqx Yyw"], "region": "Rioja"})
        assert data["ok"] is True

    def test_ai_picks_run_concurrently(self, client, monkeypatch):
        """Three ambiguous values used to cost three serial round-trips. The
        whole stage must now take about as long as the slowest single call."""
        import time as t
        import app as wine_app

        calls = []

        def slow_pick(opts, entity, value, candidates):
            calls.append(value)
            t.sleep(0.6)
            return candidates[0] if candidates else None

        monkeypatch.setattr(wine_app, "_is_ai_configured", lambda o: True)
        monkeypatch.setattr(wine_app, "_ai_reconcile_pick", slow_pick)

        started = t.monotonic()
        data = self._post(client, {"grapes": ["Sylvaner Blanc", "Rieslinger Weiss",
                                              "Chardonnet Blanc"]})
        elapsed = t.monotonic() - started
        assert len(calls) == 3, calls
        # serial would be >= 1.8s; concurrent stays near a single call
        assert elapsed < 1.5, elapsed
        assert all(i["pick_source"] == "ai" for i in data["items"])

    def test_slow_provider_cannot_block_saving(self, client, monkeypatch):
        import time as t
        import app as wine_app

        monkeypatch.setattr(wine_app, "_is_ai_configured", lambda o: True)
        monkeypatch.setattr(wine_app, "_RC_AI_TIMEOUT", 0.4)
        monkeypatch.setattr(wine_app, "_ai_reconcile_pick",
                            lambda *a, **k: (t.sleep(5), "nope")[1])

        started = t.monotonic()
        data = self._post(client, {"grape": "Sylvaner Blanc"})
        elapsed = t.monotonic() - started
        assert elapsed < 2.0, elapsed          # gave up instead of waiting 5s
        assert data["items"][0]["ai_pick"] is None
        assert data["ok"] is True

    def test_repeated_value_is_answered_from_cache(self, client, monkeypatch):
        import app as wine_app

        calls = []
        monkeypatch.setattr(wine_app, "_is_ai_configured", lambda o: True)
        monkeypatch.setattr(wine_app, "_call_chat",
                            lambda *a, **k: calls.append(1) or "Silvaner")
        wine_app._RC_PICK_CACHE.clear()

        first = self._post(client, {"grape": "Sylvaner Blanc"})["items"][0]
        second = self._post(client, {"grape": "Sylvaner Blanc"})["items"][0]
        assert first["ai_pick"] == second["ai_pick"] == "Silvaner"
        assert len(calls) == 1, "the second save must not ask again"

    def test_failures_are_not_cached(self, client, monkeypatch):
        """A provider outage must not poison the answer for later saves."""
        import app as wine_app

        state = {"fail": True}

        def flaky(*a, **k):
            if state["fail"]:
                raise RuntimeError("provider down")
            return "Silvaner"

        monkeypatch.setattr(wine_app, "_is_ai_configured", lambda o: True)
        monkeypatch.setattr(wine_app, "_call_chat", flaky)
        wine_app._RC_PICK_CACHE.clear()

        assert self._post(client, {"grape": "Sylvaner Blanc"})["items"][0]["ai_pick"] is None
        state["fail"] = False
        assert self._post(client, {"grape": "Sylvaner Blanc"})["items"][0]["ai_pick"] == "Silvaner"

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


class TestMapCoords:
    """Map coordinate resolution via reference data + country fallback (TP4)."""

    def test_region_with_coords(self, db):
        c = wine_app.resolve_map_coords(db, "Bordeaux", None)
        assert c and abs(c[0] - 44.8) < 1.5 and abs(c[1] - (-0.6)) < 1.5

    def test_country_centroid_fallback(self, db):
        c = wine_app.resolve_map_coords(db, "Unknownville", "France")
        fr = db.execute("SELECT lat, lon FROM ref_countries WHERE code='FR'").fetchone()
        assert c == [fr["lat"], fr["lon"]]

    def test_country_only(self, db):
        assert wine_app.resolve_map_coords(db, "", "Italy") is not None

    def test_region_country_suffix_legacy(self, db):
        # legacy free-text "Region, Country" with an unknown region still lands via country
        c = wine_app.resolve_map_coords(db, "Kleinstlage, France", None)
        assert c is not None

    def test_unknown_returns_none(self, db):
        assert wine_app.resolve_map_coords(db, "Nowhereland", None) is None
        assert wine_app.resolve_map_coords(db, "", "") is None


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


class TestSpiritReferences:
    def test_spirit_types_seeded(self, db):
        import reference
        for key in ("Single Malt", "Bourbon", "Gin", "Rum"):
            assert reference.match_reference(db, "spirit_type", key), key

    def test_cask_types_seeded(self, db):
        import reference
        for name in ("Ex-Bourbon", "PX Sherry", "Oloroso Sherry", "Virgin Oak"):
            assert reference.match_reference(db, "cask_type", name), name

    def test_cask_alias_resolves(self, db):
        import reference
        assert reference.match_reference(db, "cask_type", "Bourbon")["name"] == "Ex-Bourbon"
        assert reference.match_reference(db, "cask_type", "PX")["name"] == "PX Sherry"

    def test_whisky_regions_seeded(self, db):
        import reference
        for name in ("Islay", "Speyside", "Highlands", "Kentucky", "Jalisco"):
            assert reference.match_reference(db, "spirit_region", name), name

    def test_spirit_regions_are_separate_from_wine_regions(self, db):
        """Islay is not a wine region and Rioja is not a spirit region."""
        import reference
        assert reference.match_reference(db, "region", "Islay") is None
        assert reference.match_reference(db, "region", "Speyside") is None
        assert reference.match_reference(db, "spirit_region", "Rioja") is None
        assert reference.match_reference(db, "region", "Rioja")

    def test_shared_names_stay_in_the_wine_list(self, db):
        """Jerez is a genuine wine region as well - it must exist in both."""
        import reference
        assert reference.match_reference(db, "region", "Jerez")
        assert reference.match_reference(db, "spirit_region", "Jerez")

    def test_spirit_region_aliases(self, db):
        import reference
        assert reference.match_reference(db, "spirit_region", "Orkney")["name"] == "Islands"
        assert reference.match_reference(db, "spirit_region", "Tequila")["name"] == "Jalisco"

    def test_region_entity_follows_category(self):
        import reference
        assert reference.region_entity("whisky") == "spirit_region"
        assert reference.region_entity("spirit") == "spirit_region"
        assert reference.region_entity("wine") == "region"
        assert reference.region_entity(None) == "region"

    def test_spirit_regions_scoped_by_country(self, db):
        import reference
        names = {r["name"] for r in reference.list_reference(db, "spirit_regions", "GB")}
        assert "Islay" in names and "Kentucky" not in names

    def test_migration_moves_stray_regions_but_spares_customs(self, db):
        """An earlier build seeded whisky regions into ref_regions."""
        import reference
        db.execute("INSERT INTO ref_regions (name,norm,country_code,is_custom) VALUES (?,?,?,0)",
                   ("Islay", reference.normalize_name("Islay"), "GB"))
        db.execute("INSERT INTO ref_regions (name,norm,country_code,is_custom) VALUES (?,?,?,1)",
                   ("Campbeltown", reference.normalize_name("Campbeltown"), "GB"))
        removed = reference.migrate_spirit_regions_out_of_regions(db)
        assert removed == 1
        assert reference.match_reference(db, "region", "Islay") is None
        # the user's own entry stays where they put it
        assert reference.match_reference(db, "region", "Campbeltown")
        # and a real wine region is never touched
        assert reference.match_reference(db, "region", "Jerez")

    def test_custom_spirit_region_can_be_added(self, db):
        import reference
        row = reference.add_custom_entry(db, "spirit_region", name="Hanshin",
                                         country_code="JP", lat=34.7, lon=135.5)
        assert row["is_custom"] == 1
        assert reference.match_reference(db, "spirit_region", "Hanshin")["name"] == "Hanshin"
        # idempotent - a second add returns the same row
        assert reference.add_custom_entry(db, "spirit_region", name="Hanshin",
                                          country_code="JP")["id"] == row["id"]
        # and it did not land in the wine list
        assert reference.match_reference(db, "region", "Hanshin") is None

    def test_spirit_bottle_formats_seeded(self, db):
        rows = {r[0] for r in db.execute("SELECT liters FROM ref_bottle_formats")}
        assert 0.7 in rows and 0.5 in rows and 0.05 in rows

    def test_unknown_value_returns_none(self, db):
        import reference
        assert reference.match_reference(db, "cask_type", "Zzz Unknown") is None
