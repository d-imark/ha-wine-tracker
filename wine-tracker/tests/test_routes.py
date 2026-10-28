"""
Tests for Flask routes - CRUD operations on wines.
All requests use AJAX headers to get JSON responses.
"""
import io
import json
import os
import sys

import pytest
from unittest.mock import patch
from werkzeug.security import generate_password_hash

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
sys.path.insert(0, APP_DIR)

AJAX = {"X-Requested-With": "XMLHttpRequest"}


# ── GET / (index) ─────────────────────────────────────────────────────────────

class TestIndex:
    def test_index_loads(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_index_contains_wine_tracker(self, client):
        resp = client.get("/")
        assert b"Wine Tracker" in resp.data or b"wine" in resp.data.lower()

    def test_cards_carry_every_searched_field(self, client, sample_wine):
        """The search runs client-side on data-* attributes (static/search.js);
        every field it scores has to be on the card."""
        html = client.get("/").data.decode()
        assert "static/search.js" in html
        for key in ("name", "winery", "year", "region", "country", "grape",
                    "grapes", "location", "bottler", "cask", "notes",
                    "description"):
            assert f'data-{key}="' in html, key

    @staticmethod
    def _body_tag(html):
        return html.split("<body", 1)[1].split(">", 1)[0]

    @pytest.mark.parametrize("path", ["/", "/stats", "/timeline", "/reference"])
    def test_body_marked_embedded_under_ingress(self, client, path):
        """HA ingress already clears the iOS home indicator; pages flag
        themselves so the CSS skips its own safe-area inset."""
        html = client.get(path, headers={"X-Ingress-Path": "/api/hassio_ingress/x"}).data.decode()
        assert "embedded" in self._body_tag(html)

    def test_body_not_embedded_without_ingress(self, client):
        assert "embedded" not in self._body_tag(client.get("/").data.decode())

    def test_export_is_a_button_with_share_fallback(self, client):
        """A plain link renders the ZIP as text inside the HA companion app."""
        html = client.get("/").data.decode()
        assert 'id="exportBackupBtn"' in html and "exportBackup()" in html

    @pytest.mark.parametrize("path", ["/", "/stats", "/timeline", "/reference"])
    def test_settings_modal_carries_the_ingress_base(self, client, path):
        """Export and import build their URLs from the button's data-base.
        They used to read it off the export link, which is now a button."""
        html = client.get(path, headers={"X-Ingress-Path": "/api/hassio_ingress/x"}).data.decode()
        assert 'data-base="/api/hassio_ingress/x"' in html

    def test_bottle_format_rendered_canonically(self, client):
        """Server-rendered cards must match the AJAX-rendered form ("3", not
        "3.0"), or filter chips and presets stop matching after a save."""
        client.post("/add", data={"name": "Magnum", "quantity": "1", "bottle_format": "1.5"}, headers=AJAX)
        client.post("/add", data={"name": "Doppelmagnum", "quantity": "1", "bottle_format": "3"}, headers=AJAX)
        html = client.get("/").data.decode()
        assert 'data-bottle_format="1.5"' in html
        assert 'data-bottle_format="3"' in html
        assert 'data-bottle_format="3.0"' not in html

    def test_query_params_no_longer_filter_on_the_server(self, client):
        """Search, type and empty filters moved to the browser; the server
        ignores the old ?q=, ?type= and ?show_empty= parameters."""
        client.post("/add", data={"name": "Leer", "quantity": "0"}, headers=AJAX)
        html = client.get("/?q=Zzzgibtsnicht&type=Rotwein&show_empty=0").data
        assert b'data-name="Leer"' in html

    def test_edit_param_loads(self, client, sample_wine):
        """Index with ?edit=ID should load successfully (JS opens modal client-side)."""
        wine_id = sample_wine["wine"]["id"]
        resp = client.get(f"/?edit={wine_id}")
        assert resp.status_code == 200
        # The wine card should be present for JS to find
        assert str(wine_id).encode() in resp.data

    def test_view_modal_opens_in_place(self, client, sample_wine):
        """View modal JS (openViewModal) should be present on index page."""
        resp = client.get("/")
        assert b'openViewModal' in resp.data

    def test_advanced_filter_modal_rendered(self, client, sample_wine):
        """Advanced filter modal markup and its JS bundle should be on the page."""
        resp = client.get("/")
        assert b'id="advancedFilterModal"' in resp.data
        assert b'filter-advanced.js' in resp.data
        # Popover entry point is present so users can reach the modal
        assert b'openAdvancedFilter' in resp.data
        # Settings toggle for the "advanced-as-default" preference
        assert b'advancedFilterDefaultToggle' in resp.data

    def test_filter_preset_name_dialog_rendered(self, client, sample_wine):
        """Inline name-prompt dialog must be present.

        Regression test: window.prompt() is silently blocked in the HA Ingress
        iframe on iOS Safari, so the Save / Save-as-new flow needs an in-page
        dialog instead. Without this markup, tapping "Save preset" on mobile
        does nothing.
        """
        resp = client.get("/")
        assert b'id="advFilterNameDialog"' in resp.data
        assert b'id="advFilterNameInput"' in resp.data
        # The JS-exposed handlers wired to the dialog's buttons:
        assert b'AdvancedFilter.closeNameDialog' in resp.data
        assert b'AdvancedFilter.confirmNameDialog' in resp.data

    def test_drink_window_filter_labels_rendered(self, client, sample_wine):
        """Drink-window filter radios must render their translated labels.

        Regression test for a bug where {{ t.filter_all }}, {{ t.filter_dw_in }}
        and {{ t.filter_dw_last }} had lost their `t.` prefix, causing the
        labels to render as empty strings and leaving only the counts visible
        in the filter dropdown (see commit 051b5cf).
        """
        resp = client.get("/")
        html = resp.data.decode()
        # Default language is German; the three previously-broken labels:
        assert "Im Trinkfenster" in html
        assert "Letztes Jahr" in html
        # And the one that was always correct (sanity check):
        assert "Ausserhalb" in html
        # The buggy raw Jinja variable names must NOT leak into the output:
        assert "{{ filter_all }}" not in html
        assert "{{ filter_dw_in }}" not in html
        assert "{{ filter_dw_last }}" not in html

    def test_about_section_with_version(self, client):
        """Settings modal should contain About section with app version."""
        import app as wine_app
        resp = client.get("/")
        html = resp.data.decode()
        assert "v" + wine_app.APP_VERSION in html
        assert "settings_about" in html or "Über" in html

    def test_view_modal_present(self, client):
        """Index page should contain the viewModal overlay."""
        resp = client.get("/")
        assert b'id="viewModal"' in resp.data

    def test_card_body_calls_view(self, client, sample_wine):
        """Card body onclick should call viewFromCard."""
        resp = client.get("/")
        assert b'viewFromCard(this)' in resp.data

    def test_pencil_still_calls_edit(self, client, sample_wine):
        """Pencil button should still call editFromCard."""
        resp = client.get("/")
        assert b'editFromCard(this)' in resp.data

    def test_view_toggle_buttons_present(self, client):
        """Settings modal should contain view mode radio buttons for all 4 view modes."""
        resp = client.get("/")
        html = resp.data.decode()
        assert 'view-mode-radios' in html
        assert 'value="cards"' in html
        assert 'value="list"' in html
        assert 'value="grid"' in html
        assert 'value="table"' in html
        assert 'mdi-view-module' in html
        assert 'mdi-view-list' in html
        assert 'mdi-view-grid' in html
        assert 'mdi-table' in html

    def test_view_mode_js_functions_present(self, client):
        """Index page should contain JS functions for view mode switching."""
        resp = client.get("/")
        html = resp.data.decode()
        assert 'setViewMode' in html
        assert 'TableView.render' in html
        assert 'static/table-view.js' in html
        assert 'wineViewMode' in html

    def test_table_view_js_loads_before_view_mode_restore(self, client):
        """Regression guard: the saved-view-mode restore block calls
        TableView.render() (via setViewMode) when the saved mode is 'table',
        so it must run after static/table-view.js has loaded. If the script
        tag is ever moved back below the restore block, every user whose
        saved view mode is 'table' hits a ReferenceError and sees a blank
        grid."""
        resp = client.get("/")
        html = resp.data.decode()
        # "localStorage.getItem('wineViewMode')" also appears earlier, in the
        # unrelated initial `currentViewMode` assignment, so anchor on the
        # restore block's own call to setViewMode(saved) instead.
        assert html.index("static/table-view.js") < html.index("setViewMode(saved)")

    def test_wine_grid_has_view_class(self, client):
        """Wine grid container should have view-cards class and id."""
        resp = client.get("/")
        html = resp.data.decode()
        assert 'id="wineGrid"' in html
        assert 'view-cards' in html


# ── POST /add ─────────────────────────────────────────────────────────────────

class TestAddWine:
    def test_add_wine_ajax(self, client):
        resp = client.post(
            "/add",
            data={"name": "Testvin", "year": "2021", "type": "Weisswein", "quantity": "2"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["name"] == "Testvin"
        assert data["wine"]["year"] == 2021
        assert data["wine"]["type"] == "Weisswein"
        assert data["wine"]["quantity"] == 2

    def test_add_wine_redirect(self, client):
        """Non-AJAX add should redirect."""
        resp = client.post(
            "/add",
            data={"name": "Redirect Wine", "quantity": "1"},
        )
        assert resp.status_code == 302

    def test_add_wine_minimal(self, client):
        """Only name is required."""
        resp = client.post("/add", data={"name": "Minimal"}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["name"] == "Minimal"
        assert data["wine"]["quantity"] == 1  # default

    def test_add_wine_with_ai_price(self, client):
        # The own price comes from purchase lots; the form only sets the AI price.
        resp = client.post(
            "/add",
            data={"name": "Priced Wine", "ai_price": "49.50"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["ai_price"] == 49.50
        assert data["wine"]["price"] is None

    def test_add_wine_with_bottle_format(self, client):
        resp = client.post(
            "/add",
            data={"name": "Magnum", "bottle_format": "1.5", "quantity": "1"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["bottle_format"] == 1.5

    def test_add_wine_default_bottle_format(self, client):
        resp = client.post(
            "/add",
            data={"name": "Standard Bottle"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["bottle_format"] == 0.75

    def test_add_wine_with_vivino_id(self, client):
        resp = client.post(
            "/add",
            data={"name": "Vivino Wine", "vivino_id": "12345"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["vivino_id"] == 12345

    def test_add_wine_updates_stats(self, client):
        resp = client.post(
            "/add",
            data={"name": "Stats Wine", "quantity": "5"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["stats"]["total"] == 5

    def test_add_wine_with_image(self, client, upload_dir):
        """Upload a fake image file."""
        fake_image = (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100), "label.png")
        resp = client.post(
            "/add",
            data={"name": "Photo Wine", "image": fake_image},
            headers=AJAX,
            content_type="multipart/form-data",
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["image"] is not None
        assert data["wine"]["image"].endswith(".png")
        # File should exist on disk
        assert os.path.isfile(os.path.join(upload_dir, data["wine"]["image"]))

    def test_add_wine_ai_image_adopted(self, client, upload_dir):
        """A bare ai_image filename already in the upload dir is adopted."""
        fname = "aabbccdd.jpg"
        with open(os.path.join(upload_dir, fname), "wb") as f:
            f.write(b"fake")
        resp = client.post(
            "/add", data={"name": "AI Wine", "ai_image": fname}, headers=AJAX
        )
        data = json.loads(resp.data)
        assert data["wine"]["image"] == fname

    def test_add_wine_ai_image_path_traversal_rejected(self, client):
        """ai_image with path components must not be adopted (would later
        end up in os.remove when the image is replaced or deleted)."""
        import app as wine_app
        outside = os.path.join(wine_app.DATA_DIR, "evil.jpg")
        with open(outside, "wb") as f:
            f.write(b"fake")
        resp = client.post(
            "/add", data={"name": "Evil Wine", "ai_image": "../evil.jpg"}, headers=AJAX
        )
        data = json.loads(resp.data)
        assert data["wine"]["image"] is None
        assert os.path.isfile(outside)


# ── POST /edit/<id> ───────────────────────────────────────────────────────────

class TestDualRating:
    """Personal rating (decimal) and a separate, Vivino-sourced rating."""

    def test_add_stores_decimal_personal_rating(self, client):
        resp = client.post("/add", data={"name": "Deci", "quantity": "1", "rating": "4.3"}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["rating"] == 4.3

    def test_add_stores_vivino_rating_separately(self, client):
        resp = client.post(
            "/add",
            data={"name": "Viv", "quantity": "1", "rating": "3", "vivino_rating": "4.2"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["rating"] == 3          # personal, untouched
        assert data["wine"]["vivino_rating"] == 4.2  # Vivino, stored separately

    def test_edit_updates_both_ratings(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(
            f"/edit/{wine_id}",
            data={"name": "R", "quantity": "1", "rating": "2.5", "vivino_rating": "4.7"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["rating"] == 2.5
        assert data["wine"]["vivino_rating"] == 4.7

    def test_rating_clamped_and_rounded(self, client):
        resp = client.post("/add", data={"name": "Clamp", "quantity": "1", "rating": "9.87"}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["wine"]["rating"] == 5  # clamped to 5.0, stored as int 5

    def test_api_wine_returns_vivino_rating(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        client.post(f"/edit/{wine_id}", data={"name": "R", "quantity": "1", "vivino_rating": "3.8"}, headers=AJAX)
        resp = client.get(f"/api/wine/{wine_id}")
        data = json.loads(resp.data)
        assert data["wine"]["vivino_rating"] == 3.8


class TestCountryMigration:
    """Backfill wines.country from existing free-text region (TP3c)."""

    def _add(self, client, **extra):
        data = {"name": "M", "quantity": "1"}
        data.update(extra)
        return json.loads(client.post("/add", data=data, headers=AJAX).data)["wine"]["id"]

    def test_derives_country_from_known_region(self, client, db):
        import app as wine_app
        wid = self._add(client, region="Bordeaux")
        wine_app.migrate_country_from_region(db)
        db.commit()
        assert db.execute("SELECT country FROM wines WHERE id=?", (wid,)).fetchone()[0] == "France"

    def test_derives_country_from_region_country_suffix(self, client, db):
        import app as wine_app
        wid = self._add(client, region="Toscana, Italien")
        wine_app.migrate_country_from_region(db)
        db.commit()
        assert db.execute("SELECT country FROM wines WHERE id=?", (wid,)).fetchone()[0] == "Italy"

    def test_unknown_region_leaves_country_empty(self, client, db):
        import app as wine_app
        wid = self._add(client, region="Nowhereland")
        wine_app.migrate_country_from_region(db)
        db.commit()
        assert not db.execute("SELECT country FROM wines WHERE id=?", (wid,)).fetchone()[0]

    def test_does_not_overwrite_existing_country(self, client, db):
        import app as wine_app
        wid = self._add(client, region="Bordeaux", country="Neverland")
        wine_app.migrate_country_from_region(db)
        db.commit()
        assert db.execute("SELECT country FROM wines WHERE id=?", (wid,)).fetchone()[0] == "Neverland"


class TestCountryField:
    """Separate country field on wines (TP3a), stored as a string."""

    def test_add_stores_country(self, client):
        resp = client.post("/add", data={"name": "Ctry", "quantity": "1", "country": "France"}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["country"] == "France"

    def test_edit_updates_country(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(
            f"/edit/{wine_id}",
            data={"name": "X", "quantity": "1", "country": "Italy"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["country"] == "Italy"

    def test_duplicate_copies_country(self, client):
        created = json.loads(client.post(
            "/add", data={"name": "Dup", "quantity": "1", "country": "Spain"}, headers=AJAX).data)
        wid = created["wine"]["id"]
        resp = client.post(f"/duplicate/{wid}", data={"year": "2021"}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["country"] == "Spain"

    def test_api_wine_returns_country(self, client):
        created = json.loads(client.post(
            "/add", data={"name": "C2", "quantity": "1", "country": "Portugal"}, headers=AJAX).data)
        wid = created["wine"]["id"]
        data = json.loads(client.get(f"/api/wine/{wid}").data)
        assert data["wine"]["country"] == "Portugal"


class TestEditWine:
    def test_edit_wine(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(
            f"/edit/{wine_id}",
            data={
                "name": "Château Edited",
                "year": "2021",
                "type": "Weisswein",
                "quantity": "10",
                "rating": "5",
                "region": "Loire, FR",
                "notes": "Updated",
                "grape": "Chardonnay",
                "bottle_format": "1.5",
            },
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["name"] == "Château Edited"
        assert data["wine"]["year"] == 2021
        assert data["wine"]["type"] == "Weisswein"
        assert data["wine"]["quantity"] == 10
        assert data["wine"]["rating"] == 5
        assert data["wine"]["grape"] == "Chardonnay"
        assert data["wine"]["bottle_format"] == 1.5

    def test_edit_ai_image_path_traversal_rejected(self, client, sample_wine):
        """ai_image with path components must not be adopted on edit."""
        import app as wine_app
        wine_id = sample_wine["wine"]["id"]
        outside = os.path.join(wine_app.DATA_DIR, "evil.jpg")
        with open(outside, "wb") as f:
            f.write(b"fake")
        resp = client.post(
            f"/edit/{wine_id}",
            data={"name": "Still Safe", "quantity": "3", "ai_image": "../evil.jpg"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["image"] is None
        assert os.path.isfile(outside)

    def test_edit_nonexistent_wine(self, client):
        resp = client.post(
            "/edit/99999",
            data={"name": "Ghost"},
            headers=AJAX,
        )
        # Should redirect (wine not found)
        assert resp.status_code == 302

    def test_edit_preserves_enrichment_on_minimal_form(self, client, sample_wine):
        """Minimal FormData (as sent by the quantity +/- buttons) must not wipe
        maturity_data, taste_profile or food_pairings."""
        wine_id = sample_wine["wine"]["id"]
        # First, seed enrichment via a full form submission (edit modal style)
        client.post(
            f"/edit/{wine_id}",
            data={
                "name": "Château Test",
                "year": "2020",
                "type": "Rotwein",
                "region": "Bordeaux",
                "quantity": "3",
                "rating": "4",
                "notes": "",
                "grape": "Merlot",
                "bottle_format": "0.75",
                "maturity_data": '{"youth":[2020,2022],"maturity":[2022,2025],"peak":[2025,2028],"decline":[2028,2032]}',
                "taste_profile": '{"body":4,"tannin":3,"acidity":3,"sweetness":1}',
                "food_pairings": '["Steak","Cheese"]',
            },
            headers=AJAX,
        )
        # Sanity check
        row = client.get(f"/api/wine/{wine_id}").get_json()
        assert row["wine"]["maturity_data"]["peak"] == [2025, 2028]
        assert row["wine"]["taste_profile"]["body"] == 4
        assert row["wine"]["food_pairings"] == ["Steak", "Cheese"]

        # Now simulate a quantity +1 click - minimal FormData without the
        # enrichment fields (as built by changeQty in index.html).
        resp = client.post(
            f"/edit/{wine_id}",
            data={
                "name": "Château Test",
                "year": "2020",
                "type": "Rotwein",
                "region": "Bordeaux",
                "quantity": "4",
                "rating": "4",
                "notes": "",
                "grape": "Merlot",
                "bottle_format": "0.75",
            },
            headers=AJAX,
        )
        assert resp.status_code == 200
        row = client.get(f"/api/wine/{wine_id}").get_json()
        w = row["wine"]
        # Quantity was updated
        assert w["quantity"] == 4
        # Enrichment MUST still be there
        assert w["maturity_data"]["peak"] == [2025, 2028]
        assert w["taste_profile"]["body"] == 4
        assert w["food_pairings"] == ["Steak", "Cheese"]

    def test_edit_explicit_empty_clears_enrichment(self, client, sample_wine):
        """When the edit modal explicitly submits empty enrichment hidden
        inputs, the values should be cleared (explicit intent)."""
        wine_id = sample_wine["wine"]["id"]
        # Seed enrichment
        client.post(
            f"/edit/{wine_id}",
            data={
                "name": "Château Test",
                "type": "Rotwein",
                "quantity": "3",
                "maturity_data": '{"youth":[2020,2022],"maturity":[2022,2025],"peak":[2025,2028],"decline":[2028,2032]}',
                "taste_profile": '{"body":4,"tannin":3,"acidity":3,"sweetness":1}',
                "food_pairings": '["Steak"]',
            },
            headers=AJAX,
        )
        # Now submit with explicit empty strings (edit modal default)
        client.post(
            f"/edit/{wine_id}",
            data={
                "name": "Château Test",
                "type": "Rotwein",
                "quantity": "3",
                "maturity_data": "",
                "taste_profile": "",
                "food_pairings": "",
            },
            headers=AJAX,
        )
        row = client.get(f"/api/wine/{wine_id}").get_json()
        assert row["wine"]["maturity_data"] is None
        assert row["wine"]["taste_profile"] is None
        assert row["wine"]["food_pairings"] is None

    def test_edit_updates_stats(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(
            f"/edit/{wine_id}",
            data={"name": "Stats Edit", "quantity": "20"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["stats"]["total"] == 20

    def test_edit_delete_image(self, client, upload_dir):
        """Editing with delete_image=1 should remove the image."""
        # First add wine with image
        fake_image = (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100), "label.png")
        resp = client.post(
            "/add",
            data={"name": "Delete Image Wine", "image": fake_image},
            headers=AJAX,
            content_type="multipart/form-data",
        )
        wine = json.loads(resp.data)["wine"]
        assert wine["image"] is not None
        img_path = os.path.join(upload_dir, wine["image"])
        assert os.path.isfile(img_path)

        # Now edit with delete_image
        resp = client.post(
            f"/edit/{wine['id']}",
            data={"name": "Delete Image Wine", "delete_image": "1"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["wine"]["image"] is None
        assert not os.path.isfile(img_path)


# ── POST /duplicate/<id> ─────────────────────────────────────────────────────

class TestDuplicateWine:
    def test_duplicate_wine(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(
            f"/duplicate/{wine_id}",
            data={"new_year": "2021", "quantity": "6"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        assert data["ok"] is True
        new_wine = data["wine"]
        assert new_wine["name"] == "Château Test"
        assert new_wine["year"] == 2021  # changed
        assert new_wine["quantity"] == 6  # changed
        assert new_wine["region"] == "Bordeaux, FR"  # copied
        assert new_wine["grape"] == "Merlot"  # copied
        assert new_wine["id"] != wine_id  # new ID

    def test_duplicate_nonexistent_wine(self, client):
        resp = client.post("/duplicate/99999", data={}, headers=AJAX)
        assert resp.status_code == 302

    def test_duplicate_preserves_bottle_format(self, client):
        """Duplicated wine should keep the bottle format."""
        # Add magnum
        resp = client.post(
            "/add",
            data={"name": "Magnum", "bottle_format": "1.5", "quantity": "1"},
            headers=AJAX,
        )
        wine_id = json.loads(resp.data)["wine"]["id"]

        # Duplicate
        resp = client.post(f"/duplicate/{wine_id}", data={}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["wine"]["bottle_format"] == 1.5


# ── POST /delete/<id> ────────────────────────────────────────────────────────

class TestDeleteWine:
    def test_delete_wine(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(f"/delete/{wine_id}", headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["deleted"] == wine_id
        assert data["stats"]["total"] == 0

    def test_delete_nonexistent_wine(self, client):
        resp = client.post("/delete/99999", headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True  # Still returns ok (idempotent)

    def test_delete_keeps_image_until_the_sweep(self, client, upload_dir):
        """The image stays for the undo; the start-up sweep removes it once no
        wine refers to it any more."""
        fake_image = (io.BytesIO(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100), "label.png")
        resp = client.post(
            "/add",
            data={"name": "Delete Me", "image": fake_image},
            headers=AJAX,
            content_type="multipart/form-data",
        )
        wine = json.loads(resp.data)["wine"]
        img_path = os.path.join(upload_dir, wine["image"])
        assert os.path.isfile(img_path)

        client.post(f"/delete/{wine['id']}", headers=AJAX)
        assert os.path.isfile(img_path)
        import app as wine_app
        wine_app.cleanup_orphan_uploads(max_age_hours=0)
        assert not os.path.isfile(img_path)


# ── GET /stats ────────────────────────────────────────────────────────────────

class TestStatsPage:
    def test_stats_loads_empty(self, client):
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_stats_with_data(self, client, sample_wine):
        resp = client.get("/stats")
        assert resp.status_code == 200
        # Should contain stat labels
        assert b"Rotwein" in resp.data or b"Red" in resp.data

    def test_stats_total_liters(self, client):
        """Total liters should be calculated from quantity * bottle_format."""
        # Add 2x standard (0.75L) + 1x magnum (1.5L)
        client.post("/add", data={"name": "Standard", "quantity": "2", "bottle_format": "0.75"}, headers=AJAX)
        client.post("/add", data={"name": "Magnum", "quantity": "1", "bottle_format": "1.5"}, headers=AJAX)

        resp = client.get("/stats")
        assert resp.status_code == 200
        # 2*0.75 + 1*1.5 = 3.0 liters
        assert b"3.0" in resp.data

    def _seed_both_areas(self, client):
        import json as J
        client.post("/add", data={"name": "Stat Barolo", "type": "Rotwein",
                                  "quantity": "4", "region": "Piemont",
                                  "price": "60"}, headers=AJAX)
        client.post("/add", data={"name": "Stat Lagavulin", "category": "whisky",
                                  "type": "Single Malt", "quantity": "2",
                                  "region": "Islay", "price": "90", "alcohol_pct": "43",
                                  "age_years": "16",
                                  "casks": J.dumps([{"name": "Ex-Bourbon", "years": 16}])},
                    headers=AJAX)

    def test_stats_counts_are_area_scoped(self, client):
        """Mixing 4 bottles of Barolo into the bar's totals means nothing."""
        self._seed_both_areas(client)
        cellar = client.get("/stats?area=cellar").data.decode()
        bar = client.get("/stats?area=bar").data.decode()
        assert "Stat Barolo" in cellar and "Stat Lagavulin" not in cellar
        assert "Stat Lagavulin" in bar and "Stat Barolo" not in bar

    def test_stats_defaults_to_the_cellar(self, client):
        self._seed_both_areas(client)
        html = client.get("/stats").data.decode()
        assert "Stat Barolo" in html and "Stat Lagavulin" not in html

    def test_stats_unknown_area_falls_back_to_cellar(self, client):
        self._seed_both_areas(client)
        html = client.get("/stats?area=garage").data.decode()
        assert "Stat Barolo" in html and "Stat Lagavulin" not in html

    @staticmethod
    def _chart_keys(html):
        """The types the donut/bar charts actually plot.

        Deliberately not a plain substring search over the page: the shared edit
        modal and the colour palette mention every type name regardless of area.
        """
        import re
        return set(re.findall(r'data-key="([^"]+)"', html))

    @staticmethod
    def _globe_regions(html):
        import re
        block = re.search(r'class="globe-legend".*?</div>\s*</div>', html, re.S)
        return set(re.findall(r"<span>([^<]+)</span>", block.group(0))) if block else set()

    def test_stats_types_do_not_leak_between_areas(self, client):
        self._seed_both_areas(client)
        cellar = self._chart_keys(client.get("/stats?area=cellar").data.decode())
        bar = self._chart_keys(client.get("/stats?area=bar").data.decode())
        assert "Rotwein" in cellar and "Single Malt" not in cellar
        assert "Single Malt" in bar and "Rotwein" not in bar

    def test_stats_regions_do_not_leak_between_areas(self, client):
        self._seed_both_areas(client)
        cellar = self._globe_regions(client.get("/stats?area=cellar").data.decode())
        bar = self._globe_regions(client.get("/stats?area=bar").data.decode())
        assert "Piemont" in cellar and "Islay" not in cellar
        assert "Islay" in bar and "Piemont" not in bar

    def test_stats_bar_uses_the_age_statement(self, client):
        """A 16 year old whisky is 16 years old, regardless of the vintage
        field - the cellar's "current year minus vintage" makes no sense here."""
        self._seed_both_areas(client)
        html = client.get("/stats?area=bar").data.decode()
        assert "~16" in html

    def test_stats_area_switch_present(self, client, sample_wine):
        html = client.get("/stats").data.decode()
        assert 'class="area-switch"' in html
        assert "setArea('bar')" in html

    def test_stats_wording_follows_the_area(self, client):
        self._seed_both_areas(client)
        # a second entry per area so both sides use the plural wording
        client.post("/add", data={"name": "Stat Ardbeg", "category": "whisky",
                                  "type": "Single Malt", "quantity": "1"}, headers=AJAX)
        client.post("/add", data={"name": "Stat Chianti", "type": "Rotwein",
                                  "quantity": "1"}, headers=AJAX)
        import re

        def rendered(html):
            """Only the visible labels. The page also embeds the whole
            translation dict for JS, which naturally holds both wordings."""
            return (set(re.findall(r'class="label">([^<]+)<', html))
                    | set(re.findall(r'class="map-card">\s*<h2>.*?</i>\s*([^<]+)<',
                                     html, re.S)))

        cellar = rendered(client.get("/stats?area=cellar").data.decode())
        bar = rendered(client.get("/stats?area=bar").data.decode())
        assert "Verschiedene Weine" in cellar
        assert "Herkunft Deiner Weine" in " ".join(cellar)
        assert "Verschiedene Abfüllungen" in bar
        assert "Herkunft Deiner Spirituosen" in " ".join(bar)
        assert "Verschiedene Weine" not in bar

    def test_nav_no_longer_says_wine_cellar(self, client):
        """The first nav item covers both areas now, so "Weinkeller" was wrong.

        "Weinkeller" still legitimately labels the cellar side of the area
        switch - only the nav entry had to change.
        """
        import re
        for path in ("/", "/stats", "/timeline", "/reference"):
            html = client.get(path).data.decode()
            nav = [n.strip() for n in
                   re.findall(r'class="nav-link[^"]*"[^>]*>([^<]*)<', html) if n.strip()]
            assert nav, path
            assert nav[0] == "Sammlung", (path, nav)
            assert not any("Weinkeller" in n for n in nav), (path, nav)

    def test_stats_tooltip_data_contains_wine_id(self, client, sample_wine):
        """WINE_DATA in stats page should include wine IDs for clickable tooltips."""
        wine_id = sample_wine["wine"]["id"]
        resp = client.get("/stats")
        html = resp.data.decode()

        # wines_by_type should contain the wine ID
        assert f'"id": {wine_id}' in html or f'"id":{wine_id}' in html

    def test_stats_tooltip_links_to_edit(self, client, sample_wine):
        """Tooltip items should use inline editWine() calls."""
        resp = client.get("/stats")
        html = resp.data.decode()
        # The JS template builds <a href="#" onclick="editWine(ID); return false;" class="chart-tooltip-item">
        assert "editWine(" in html
        assert "chart-tooltip-item" in html

    def test_stats_editwine_opens_view_modal(self, client, sample_wine):
        """Stats editWine() function should fetch wine data and open view modal in-place."""
        resp = client.get("/stats")
        html = resp.data.decode()
        assert "openViewModal" in html
        assert "/api/wine/" in html
        assert 'id="viewModal"' in html

    def test_stats_has_lightbox(self, client, sample_wine):
        """Stats page should contain the lightbox overlay for wine image viewing."""
        resp = client.get("/stats")
        html = resp.data.decode()
        assert 'id="lightbox"' in html
        assert "openLightbox" in html

    def test_stats_no_from_stats_links(self, client, sample_wine):
        """Stats page should not contain from=stats links (edit is inline now)."""
        resp = client.get("/stats")
        html = resp.data.decode()
        assert "from=stats" not in html

    def test_stats_has_edit_modal(self, client, sample_wine):
        """Stats page should contain the inline wine edit modal."""
        resp = client.get("/stats")
        html = resp.data.decode()
        assert 'id="wineModal"' in html
        assert 'id="wineForm"' in html

    def test_stats_stock_chart_with_timeline(self, client, sample_wine, db):
        """Stats page should include stock chart data when timeline entries exist."""
        resp = client.get("/stats")
        html = resp.data.decode()
        # sample_wine creates a timeline entry via /add, so the chart should render
        assert "stock-chart-svg" in html
        assert "Bestandsverlauf" in html  # translated title (de)

    def test_stats_stock_chart_shows_correct_stock(self, client, db):
        """Stock chart final value should match current total bottles."""
        client.post("/add", data={"name": "Wine A", "quantity": "5"}, headers=AJAX)
        client.post("/add", data={"name": "Wine B", "quantity": "3"}, headers=AJAX)
        resp = client.get("/stats")
        html = resp.data.decode()
        # Current stock is 8, chart should contain data-stock="8"
        assert 'data-stock="8"' in html

    def test_stats_stock_chart_empty_db(self, client):
        """Stats page with no wines should not render stock chart."""
        resp = client.get("/stats")
        html = resp.data.decode()
        assert "stock-chart-svg" not in html

    def test_stats_stock_chart_tracks_consumption(self, client, db):
        """Stock chart should reflect consumption changes."""
        # Add wine with qty=10
        resp = client.post("/add", data={"name": "Consumed Wine", "quantity": "10"}, headers=AJAX)
        import json
        wine_id = json.loads(resp.data)["wine"]["id"]
        # Consume 4 bottles via edit
        client.post(f"/edit/{wine_id}", data={
            "name": "Consumed Wine", "quantity": "6",
        }, headers=AJAX)
        resp = client.get("/stats")
        html = resp.data.decode()
        # Final stock should be 6
        assert 'data-stock="6"' in html


# ── GET /api/wine/<id> ────────────────────────────────────────────────────────

class TestApiGetWine:
    def test_get_existing_wine(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.get(f"/api/wine/{wine_id}")
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["id"] == wine_id
        assert data["wine"]["name"] == "Château Test"

    def test_get_nonexistent_wine(self, client):
        resp = client.get("/api/wine/99999")
        assert resp.status_code == 404
        data = json.loads(resp.data)
        assert data["ok"] is False

    def test_get_wine_includes_all_fields(self, client):
        """API response should include all wine fields."""
        resp = client.post(
            "/add",
            data={
                "name": "Full Wine",
                "year": "2020",
                "type": "Rotwein",
                "quantity": "5",
                "region": "Toscana, IT",
                "grape": "Sangiovese",
                "ai_price": "25.00",
                "bottle_format": "0.75",
            },
            headers=AJAX,
        )
        wine_id = json.loads(resp.data)["wine"]["id"]

        resp = client.get(f"/api/wine/{wine_id}")
        data = json.loads(resp.data)
        wine = data["wine"]
        assert wine["name"] == "Full Wine"
        assert wine["year"] == 2020
        assert wine["type"] == "Rotwein"
        assert wine["quantity"] == 5
        assert wine["region"] == "Toscana, IT"
        assert wine["grape"] == "Sangiovese"
        assert wine["ai_price"] == 25.00
        assert wine["bottle_format"] == 0.75


# ── GET /api/summary ──────────────────────────────────────────────────────────

class TestApiSummary:
    def test_empty_cellar(self, client):
        resp = client.get("/api/summary")
        data = json.loads(resp.data)
        assert data["total_bottles"] == 0
        assert data["by_type"] == []

    def test_with_wines(self, client, sample_wine):
        resp = client.get("/api/summary")
        data = json.loads(resp.data)
        assert data["total_bottles"] == 3
        assert len(data["by_type"]) == 1
        assert data["by_type"][0]["type"] == "Rotwein"

    def test_multiple_types(self, client):
        client.post("/add", data={"name": "Red", "type": "Rotwein", "quantity": "2"}, headers=AJAX)
        client.post("/add", data={"name": "White", "type": "Weisswein", "quantity": "3"}, headers=AJAX)
        resp = client.get("/api/summary")
        data = json.loads(resp.data)
        assert data["total_bottles"] == 5
        assert len(data["by_type"]) == 2


# ── GET /timeline ─────────────────────────────────────────────────────────────

class TestTimelinePage:
    def test_timeline_loads(self, client):
        resp = client.get("/timeline")
        assert resp.status_code == 200
        assert b"timeline" in resp.data.lower() or b"Zeitverlauf" in resp.data


# ── Wine log integration ─────────────────────────────────────────────────────

class TestWineLog:
    def test_add_creates_log_entry(self, client, db):
        """Adding a wine should create an 'added' log entry."""
        resp = client.post(
            "/add",
            data={"name": "Log Wine", "quantity": "3"},
            headers=AJAX,
        )
        data = json.loads(resp.data)
        wine_id = data["wine"]["id"]
        log = db.execute(
            "SELECT * FROM timeline WHERE wine_id=? AND action='added'", (wine_id,)
        ).fetchone()
        assert log is not None
        assert log["quantity"] == 3

    def test_edit_quantity_down_creates_consumed_log(self, client, sample_wine, db):
        """Reducing quantity via edit should log 'consumed'."""
        wine_id = sample_wine["wine"]["id"]
        client.post(
            f"/edit/{wine_id}",
            data={"name": "Château Test", "quantity": "1"},
            headers=AJAX,
        )
        log = db.execute(
            "SELECT * FROM timeline WHERE wine_id=? AND action='consumed'", (wine_id,)
        ).fetchone()
        assert log is not None
        assert log["quantity"] == 2  # 3 - 1 = 2

    def test_edit_quantity_up_creates_restocked_log(self, client, sample_wine, db):
        """Increasing quantity via edit should log 'restocked'."""
        wine_id = sample_wine["wine"]["id"]
        client.post(
            f"/edit/{wine_id}",
            data={"name": "Château Test", "quantity": "7"},
            headers=AJAX,
        )
        log = db.execute(
            "SELECT * FROM timeline WHERE wine_id=? AND action='restocked'", (wine_id,)
        ).fetchone()
        assert log is not None
        assert log["quantity"] == 4  # 7 - 3 = 4

    def test_edit_same_quantity_no_log(self, client, sample_wine, db):
        """No log entry when quantity stays the same."""
        wine_id = sample_wine["wine"]["id"]
        client.post(
            f"/edit/{wine_id}",
            data={"name": "Château Test", "quantity": "3"},
            headers=AJAX,
        )
        consumed = db.execute(
            "SELECT * FROM timeline WHERE wine_id=? AND action='consumed'", (wine_id,)
        ).fetchone()
        restocked = db.execute(
            "SELECT * FROM timeline WHERE wine_id=? AND action='restocked'", (wine_id,)
        ).fetchone()
        assert consumed is None
        assert restocked is None

    def test_delete_creates_removed_log(self, client, sample_wine, db):
        """Deleting a wine should create a 'removed' log entry."""
        wine_id = sample_wine["wine"]["id"]
        client.post(f"/delete/{wine_id}", headers=AJAX)
        log = db.execute(
            "SELECT * FROM timeline WHERE wine_id=? AND action='removed'", (wine_id,)
        ).fetchone()
        assert log is not None
        assert log["quantity"] == 3

    def test_api_timeline_returns_data(self, client, sample_wine):
        """GET /api/timeline should return log entries."""
        resp = client.get("/api/timeline")
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert isinstance(data["entries"], list)
        assert len(data["entries"]) >= 1
        entry = data["entries"][0]
        assert "wine_name" in entry
        assert "action" in entry
        assert "timestamp" in entry

    def test_api_timeline_with_months_filter(self, client, sample_wine):
        """GET /api/timeline?months=1 should work without error."""
        resp = client.get("/api/timeline?months=1")
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert isinstance(data["entries"], list)


# ── GET /chat ────────────────────────────────────────────────────────────────

class TestChatPage:
    """Tests for the /chat page route."""

    @patch("app.load_options")
    def test_chat_page_with_ai(self, mock_opts, client):
        mock_opts.return_value = {
            "currency": "CHF", "language": "en",
            "ai_provider": "anthropic", "anthropic_api_key": "sk-test",
            "anthropic_model": "claude-sonnet-4-20250514",
            "openai_api_key": "", "openrouter_api_key": "",
            "ollama_host": "", "ollama_model": "",
        }
        response = client.get("/chat")
        assert response.status_code == 200
        assert b"chatMessages" in response.data
        assert b"chatInput" in response.data

    @patch("app.load_options")
    def test_chat_page_without_ai_redirects(self, mock_opts, client):
        mock_opts.return_value = {
            "currency": "CHF", "language": "en",
            "ai_provider": "none", "anthropic_api_key": "",
            "openai_api_key": "", "openrouter_api_key": "",
            "ollama_host": "", "ollama_model": "",
        }
        response = client.get("/chat")
        assert response.status_code == 302

    @patch("app.load_options")
    def test_chat_wine_links_open_view_modal(self, mock_opts, client):
        """Chat page wine: link handler should open view modal in-place (not redirect)."""
        mock_opts.return_value = {
            "currency": "CHF", "language": "en",
            "ai_provider": "anthropic", "anthropic_api_key": "sk-test",
            "anthropic_model": "claude-sonnet-4-20250514",
            "openai_api_key": "", "openrouter_api_key": "",
            "ollama_host": "", "ollama_model": "",
        }
        response = client.get("/chat")
        html = response.data.decode()
        assert "openViewModal" in html
        assert "/api/wine/" in html
        assert 'id="viewModal"' in html

    @patch("app.load_options")
    def test_chat_page_sanitizes_markdown(self, mock_opts, client):
        """Chat markdown must be sanitized with DOMPurify (XSS via AI response),
        and stored messages must be escaped before innerHTML on session load."""
        mock_opts.return_value = {
            "currency": "CHF", "language": "en",
            "ai_provider": "anthropic", "anthropic_api_key": "sk-test",
            "anthropic_model": "claude-sonnet-4-20250514",
            "openai_api_key": "", "openrouter_api_key": "",
            "ollama_host": "", "ollama_model": "",
        }
        response = client.get("/chat")
        html = response.data.decode()
        assert "dompurify" in html.lower()
        assert "DOMPurify.sanitize" in html
        assert "escapeHtmlChat(msg.content)" in html

    @patch("app.load_options")
    def test_chat_panel_sanitizes_markdown(self, mock_opts, client):
        """Same XSS protection in the embedded chat panel (index page)."""
        mock_opts.return_value = {
            "currency": "CHF", "language": "en",
            "ai_provider": "anthropic", "anthropic_api_key": "sk-test",
            "anthropic_model": "claude-sonnet-4-20250514",
            "openai_api_key": "", "openrouter_api_key": "",
            "ollama_host": "", "ollama_model": "",
        }
        response = client.get("/")
        html = response.data.decode()
        assert "dompurify" in html.lower()
        assert "DOMPurify.sanitize" in html
        assert "escapeHtmlChat(msg.content)" in html

    @patch("app.load_options")
    def test_chat_new_button_closes_history_sidebar_on_mobile(self, mock_opts, client):
        """The 'new chat' button must close the history sidebar on narrow viewports,
        otherwise the new (empty) chat stays hidden behind the open sidebar."""
        mock_opts.return_value = {
            "currency": "CHF", "language": "en",
            "ai_provider": "anthropic", "anthropic_api_key": "sk-test",
            "anthropic_model": "claude-sonnet-4-20250514",
            "openai_api_key": "", "openrouter_api_key": "",
            "ollama_host": "", "ollama_model": "",
        }
        response = client.get("/chat")
        html = response.data.decode()
        # Locate the startNewChatSession function body
        start = html.find("function startNewChatSession()")
        assert start != -1, "startNewChatSession function not found in chat.html"
        end = html.find("}", start)
        body = html[start:end]
        # It must contain the same mobile-close idiom used by loadChatSession
        assert "window.innerWidth <= 768" in body
        assert "toggleChatSidebar" in body


# ── Authentication ────────────────────────────────────────────────────────────

class TestAuth:
    """Tests for the optional authentication system (standalone Docker)."""

    def _make_auth_app(self, extra_users=None):
        """Create a test client with authentication enabled."""
        import app as wine_app

        wine_app.AUTH_ENABLED = True
        wine_app._USERS = {
            "admin": {"hash": generate_password_hash("secret", method="pbkdf2:sha256"), "role": "admin"},
            "user1": {"hash": generate_password_hash("pass123", method="pbkdf2:sha256"), "role": "admin"},
        }
        if extra_users:
            wine_app._USERS.update(extra_users)
        wine_app.app.config["TESTING"] = True
        wine_app.app.secret_key = "test-secret"
        wine_app.init_db()
        return wine_app.app.test_client()

    def teardown_method(self):
        """Reset auth state after each test."""
        import app as wine_app

        wine_app.AUTH_ENABLED = False
        wine_app._USERS = {}

    def test_no_auth_by_default(self, client):
        """With AUTH_ENABLED=false (default), all routes should be open."""
        resp = client.get("/")
        assert resp.status_code == 200

    def test_auth_redirects_to_login(self):
        """With AUTH_ENABLED=true, unauthenticated requests redirect to /login."""
        client = self._make_auth_app()
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_login_page_loads(self):
        """The /login page should render successfully."""
        client = self._make_auth_app()
        resp = client.get("/login")
        assert resp.status_code == 200
        assert b"Wine Tracker" in resp.data
        assert b"username" in resp.data

    def test_login_success(self):
        """Correct credentials should log the user in and redirect."""
        client = self._make_auth_app()
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "secret"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/login" not in resp.headers.get("Location", "")

    def test_login_wrong_password(self):
        """Wrong password should re-render login page with error."""
        client = self._make_auth_app()
        resp = client.post(
            "/login",
            data={"username": "admin", "password": "wrong"},
        )
        assert resp.status_code == 200
        assert b"Invalid" in resp.data or b"error" in resp.data.lower()

    def test_login_unknown_user(self):
        """Unknown user should re-render login page."""
        client = self._make_auth_app()
        resp = client.post(
            "/login",
            data={"username": "nobody", "password": "test"},
        )
        assert resp.status_code == 200

    def test_logout(self):
        """Logout should clear the session and redirect to login."""
        client = self._make_auth_app()
        # Login first
        client.post("/login", data={"username": "admin", "password": "secret"})
        # Then logout
        resp = client.get("/logout")
        assert resp.status_code == 302
        # Verify logged out - next request should redirect to login
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]

    def test_static_accessible_without_login(self):
        """Static files (CSS, JS) should be accessible without authentication."""
        client = self._make_auth_app()
        resp = client.get("/static/style.css")
        assert resp.status_code == 200

    def test_api_requires_auth(self):
        """API endpoints should return 401 when not authenticated."""
        client = self._make_auth_app()
        resp = client.get("/api/summary")
        assert resp.status_code == 401
        data = json.loads(resp.data)
        assert data["ok"] is False

    def test_authenticated_access(self):
        """After login, all routes should be accessible."""
        client = self._make_auth_app()
        client.post("/login", data={"username": "admin", "password": "secret"})
        resp = client.get("/")
        assert resp.status_code == 200

    def test_login_disabled_redirects_to_index(self, client):
        """/login should redirect to / when auth is disabled."""
        resp = client.get("/login")
        assert resp.status_code == 302
        assert resp.headers["Location"].endswith("/")

    # ── Readonly role tests ──────────────────────────────────────────────────

    def test_readonly_cannot_add(self):
        """Readonly users cannot add wines."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.post("/add", data={"name": "Test Wine"})
        assert resp.status_code in (302, 403)

    def test_readonly_cannot_delete(self):
        """Readonly users cannot delete wines."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.post("/delete/1")
        assert resp.status_code in (302, 403)

    def test_readonly_cannot_edit(self):
        """Readonly users cannot edit wines."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.post("/edit/1", data={"name": "Hacked"}, headers=AJAX)
        assert resp.status_code == 403
        data = json.loads(resp.data)
        assert data["error"] == "readonly"

    def test_readonly_cannot_duplicate(self):
        """Readonly users cannot duplicate wines."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.post("/duplicate/1", data={}, headers=AJAX)
        assert resp.status_code == 403

    def test_readonly_can_view(self):
        """Readonly users can view the wine list."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.get("/")
        assert resp.status_code == 200

    def test_readonly_can_view_stats(self):
        """Readonly users can view the stats page."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.get("/stats")
        assert resp.status_code == 200

    def test_readonly_can_chat(self):
        """Readonly users can use the chat API."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        with patch("app.load_options") as mock_opts, patch("app._call_chat") as mock_chat:
            mock_opts.return_value = {
                "currency": "CHF", "language": "en",
                "ai_provider": "anthropic", "anthropic_api_key": "sk-test",
                "anthropic_model": "claude-sonnet-4-20250514",
                "openai_api_key": "", "openrouter_api_key": "",
                "ollama_host": "", "ollama_model": "",
            }
            mock_chat.return_value = "Nice wine!"
            resp = client.post(
                "/api/chat",
                data=json.dumps({"message": "hi", "history": []}),
                content_type="application/json",
            )
            assert resp.status_code == 200

    def test_readonly_hides_fab(self):
        """Readonly users should not see the FAB (add wine) button."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.get("/")
        assert b'class="fab"' not in resp.data

    def test_readonly_hides_card_actions(self):
        """Readonly users should not see card action buttons in server-rendered cards."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        # Login as admin first to add a wine
        client.post("/login", data={"username": "admin", "password": "secret"})
        client.post("/add", data={"name": "Visible Wine", "quantity": "2"}, headers=AJAX)
        client.get("/logout")
        # Login as readonly
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.get("/")
        html = resp.data.decode()
        # The server-rendered card divs should not have card-actions
        # (the JS renderCard function string still exists in source but is
        # guarded by AUTH_READONLY, so we check the actual HTML cards only)
        # Count card-actions outside of <script> tags
        import re
        # Remove all script blocks from HTML
        html_no_script = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL)
        assert 'class="card-actions"' not in html_no_script

    def test_admin_can_add(self):
        """Admin users can add wines normally."""
        client = self._make_auth_app()
        client.post("/login", data={"username": "admin", "password": "secret"})
        resp = client.post("/add", data={"name": "Admin Wine"}, headers=AJAX)
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data["ok"] is True

    def test_readonly_blocks_api_write(self):
        """Readonly users cannot use write API endpoints."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.post(
            "/api/vivino-image",
            data=json.dumps({"url": "https://example.com/img.jpg"}),
            content_type="application/json",
        )
        assert resp.status_code == 403

    def test_login_sets_role_in_session(self):
        """Login should store the user role in the session."""
        client = self._make_auth_app(extra_users={
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        })
        client.post("/login", data={"username": "viewer", "password": "pass"})
        # Verify by checking auth_readonly in template context
        resp = client.get("/")
        assert resp.status_code == 200
        assert b"AUTH_READONLY = true" in resp.data


# ── DEV_AUTH ─────────────────────────────────────────────────────────────────

class TestDevAuth:
    """Tests for the DEV_AUTH environment variable shortcut."""

    def _make_dev_auth_app(self, dev_auth_str):
        """Simulate DEV_AUTH by parsing it and setting module globals."""
        import app as wine_app

        users = wine_app.parse_user_string(dev_auth_str)
        wine_app.AUTH_ENABLED = True
        wine_app._USERS = users
        wine_app.app.config["TESTING"] = True
        wine_app.app.secret_key = "test-secret"
        wine_app.init_db()
        return wine_app.app.test_client()

    def teardown_method(self):
        import app as wine_app
        wine_app.AUTH_ENABLED = False
        wine_app._USERS = {}

    def test_dev_auth_single_user_login(self):
        """DEV_AUTH with single user should allow login."""
        client = self._make_dev_auth_app("dev:devpass")
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        resp = client.post("/login", data={"username": "dev", "password": "devpass"})
        assert resp.status_code == 302
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dev_auth_with_role(self):
        """DEV_AUTH user with readonly role should be restricted."""
        client = self._make_dev_auth_app("viewer:pass:readonly")
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.post(
            "/add",
            data={"name": "Test"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 403

    def test_dev_auth_multiple_users(self):
        """DEV_AUTH with multiple users should allow each to login."""
        client = self._make_dev_auth_app("admin:pass1:admin,viewer:pass2:readonly")
        # Admin can login
        client.post("/login", data={"username": "admin", "password": "pass1"})
        resp = client.get("/")
        assert resp.status_code == 200
        client.get("/logout")
        # Viewer can login
        client.post("/login", data={"username": "viewer", "password": "pass2"})
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dev_auth_wrong_password_rejected(self):
        """DEV_AUTH should reject wrong passwords."""
        client = self._make_dev_auth_app("admin:secret")
        resp = client.post("/login", data={"username": "admin", "password": "wrong"})
        assert resp.status_code == 200  # Re-renders login page
        resp = client.get("/")
        assert resp.status_code == 302  # Still redirects to login

    def test_dev_auth_logout(self):
        """Logout should work with DEV_AUTH users."""
        client = self._make_dev_auth_app("admin:pass")
        client.post("/login", data={"username": "admin", "password": "pass"})
        resp = client.get("/")
        assert resp.status_code == 200
        client.get("/logout")
        resp = client.get("/", follow_redirects=False)
        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]


class TestAiRationale:
    """AI rationale ("Quellen") stored on wines (ai_rationale)."""

    def test_add_stores_ai_rationale(self, client):
        resp = client.post("/add", data={"name": "R", "quantity": "1",
                            "ai_rationale": "Erkannt anhand Label."}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["ok"] is True
        assert data["wine"]["ai_rationale"] == "Erkannt anhand Label."

    def test_edit_updates_ai_rationale(self, client, sample_wine):
        wine_id = sample_wine["wine"]["id"]
        resp = client.post(f"/edit/{wine_id}", data={"name": "X", "quantity": "1",
                            "ai_rationale": "Neue Basis."}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["wine"]["ai_rationale"] == "Neue Basis."

    def test_duplicate_copies_ai_rationale(self, client):
        created = json.loads(client.post("/add", data={"name": "Dup", "quantity": "1",
                             "ai_rationale": "Basis."}, headers=AJAX).data)
        wid = created["wine"]["id"]
        resp = client.post(f"/duplicate/{wid}", data={"year": "2021"}, headers=AJAX)
        data = json.loads(resp.data)
        assert data["wine"]["ai_rationale"] == "Basis."

    def test_api_wine_returns_ai_rationale(self, client):
        created = json.loads(client.post("/add", data={"name": "C2", "quantity": "1",
                             "ai_rationale": "Weinführer-Wissen."}, headers=AJAX).data)
        wid = created["wine"]["id"]
        data = json.loads(client.get(f"/api/wine/{wid}").data)
        assert data["wine"]["ai_rationale"] == "Weinführer-Wissen."


class TestImageSync:
    """BP1: wines.image is mirrored into the wine_images table."""

    def test_add_creates_scan_default_row(self, client, db):
        import io
        data = {"name": "Img", "quantity": "1",
                "image": (io.BytesIO(b"\xff\xd8\xff\xe0fakejpeg"), "x.jpg")}
        wid = json.loads(client.post("/add", data=data, headers=AJAX,
                          content_type="multipart/form-data").data)["wine"]["id"]
        rows = db.execute("SELECT category, is_default FROM wine_images WHERE wine_id=?", (wid,)).fetchall()
        assert len(rows) == 1
        assert rows[0]["category"] == "scan" and rows[0]["is_default"] == 1

    def test_wine_json_includes_images(self, client):
        import io
        data = {"name": "Img2", "quantity": "1",
                "image": (io.BytesIO(b"\xff\xd8\xff\xe0fakejpeg"), "y.jpg")}
        wid = json.loads(client.post("/add", data=data, headers=AJAX,
                          content_type="multipart/form-data").data)["wine"]["id"]
        wine = json.loads(client.get(f"/api/wine/{wid}").data)["wine"]
        assert "images" in wine and len(wine["images"]) == 1
        assert wine["image"] == wine["images"][0]["filename"]  # default mirrored

    def test_add_without_image_has_no_rows(self, client, db):
        wid = json.loads(client.post("/add", data={"name": "NoImg", "quantity": "1"},
                          headers=AJAX).data)["wine"]["id"]
        rows = db.execute("SELECT * FROM wine_images WHERE wine_id=?", (wid,)).fetchall()
        assert rows == []

    def test_migrate_legacy_backfills(self, client, db):
        import app as wine_app
        db.execute("INSERT INTO wines (name, quantity, image) VALUES ('Legacy', 1, 'leg.jpg')")
        db.commit()
        wid = db.execute("SELECT id FROM wines WHERE name='Legacy'").fetchone()[0]
        db.execute("DELETE FROM wine_images WHERE wine_id=?", (wid,))
        db.commit()
        wine_app.images.migrate_legacy_images(db)
        db.commit()
        rows = db.execute("SELECT category, is_default FROM wine_images WHERE wine_id=?", (wid,)).fetchall()
        assert len(rows) == 1 and rows[0]["category"] == "scan" and rows[0]["is_default"] == 1


# ── grape varieties (1-n + pct) ───────────────────────────────────────────────

def test_add_wine_with_grapes_json(client, db):
    resp = client.post("/add", data={
        "name": "Blend Test", "type": "red", "region": "Bordeaux", "quantity": "1",
        "grapes": json.dumps([{"name": "Merlot", "pct": 70},
                              {"name": "Cabernet Franc", "pct": 30}]),
    }, follow_redirects=True)
    assert resp.status_code == 200
    wid = db.execute("SELECT id FROM wines WHERE name='Blend Test'").fetchone()[0]
    import grapes
    rows = grapes.list_wine_grapes(db, wid)
    assert [(r["name"], r["pct"]) for r in rows] == [("Merlot", 70), ("Cabernet Franc", 30)]
    assert db.execute("SELECT grape FROM wines WHERE id=?", (wid,)).fetchone()[0] \
        == "Merlot, Cabernet Franc"


def test_add_wine_legacy_grape_fallback(client, db):
    resp = client.post("/add", data={
        "name": "Legacy Grape", "type": "red", "region": "Rioja", "quantity": "1",
        "grape": "Tempranillo, Garnacha",
    }, follow_redirects=True)
    assert resp.status_code == 200
    wid = db.execute("SELECT id FROM wines WHERE name='Legacy Grape'").fetchone()[0]
    import grapes
    assert [r["name"] for r in grapes.list_wine_grapes(db, wid)] == ["Tempranillo", "Garnacha"]


# ── spirits: category, details, casks ─────────────────────────────────────────

def test_add_whisky_stores_details_and_casks(client, db):
    resp = client.post("/add", data={
        "name": "Lagavulin 16", "category": "whisky", "type": "Single Malt",
        "region": "Islay", "quantity": "2", "alcohol_pct": "43", "age_years": "16",
        "bottler": "Original", "batch_number": "Batch 003", "peat_ppm": "35",
        "casks": json.dumps([{"name": "Ex-Bourbon", "years": 14},
                             {"name": "PX Sherry", "years": 2}]),
    }, follow_redirects=True)
    assert resp.status_code == 200
    wid = db.execute("SELECT id FROM wines WHERE name='Lagavulin 16'").fetchone()[0]
    assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "whisky"

    import spirits
    d = spirits.get_details(db, wid)
    assert d["age_years"] == 16 and d["batch_number"] == "Batch 003"
    assert db.execute("SELECT alcohol_pct FROM wines WHERE id=?", (wid,)).fetchone()[0] == 43
    assert [c["name"] for c in spirits.list_casks(db, wid)] == ["Ex-Bourbon", "PX Sherry"]
    assert d["cask_summary"] == "Ex-Bourbon → PX Sherry"


def test_add_wine_stays_wine_and_has_no_spirit_row(client, db):
    client.post("/add", data={"name": "Barolo Cat", "type": "red", "quantity": "1"},
                follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Barolo Cat'").fetchone()[0]
    assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "wine"
    assert db.execute("SELECT COUNT(*) FROM spirit_details WHERE wine_id=?",
                      (wid,)).fetchone()[0] == 0


def test_edit_without_spirit_fields_keeps_them(client, db):
    """A quantity-only edit must not wipe the whisky details."""
    client.post("/add", data={
        "name": "Keep Details", "category": "whisky", "type": "Single Malt",
        "quantity": "1", "alcohol_pct": "46", "age_years": "12",
    }, follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Keep Details'").fetchone()[0]
    client.post(f"/edit/{wid}", data={
        "name": "Keep Details", "type": "Single Malt", "quantity": "3", "rating": "0",
    }, follow_redirects=True)
    import spirits
    assert spirits.get_details(db, wid)["age_years"] == 12
    assert db.execute("SELECT alcohol_pct FROM wines WHERE id=?", (wid,)).fetchone()[0] == 46
    assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "whisky"


def test_unknown_category_falls_back_to_wine(client, db):
    client.post("/add", data={"name": "Weird Cat", "type": "red", "quantity": "1",
                              "category": "bogus"}, follow_redirects=True)
    wid = db.execute("SELECT id FROM wines WHERE name='Weird Cat'").fetchone()[0]
    assert db.execute("SELECT category FROM wines WHERE id=?", (wid,)).fetchone()[0] == "wine"


# ── description vs. notes ─────────────────────────────────────────────────────

class TestDescriptionAndNotes:
    """`notes` is the user's own field. Everything the AI writes about a bottle
    goes to `description` instead."""

    def test_both_fields_are_saved_independently(self, client, db):
        client.post("/add", data={
            "name": "Zwei Felder", "quantity": "1",
            "description": "Kraeftiger Rotwein mit dunklen Beeren.",
            "notes": "Vom Winzer persoenlich gekauft.",
        }, headers=AJAX)
        row = db.execute(
            "SELECT notes, description FROM wines WHERE name='Zwei Felder'").fetchone()
        assert row["description"] == "Kraeftiger Rotwein mit dunklen Beeren."
        assert row["notes"] == "Vom Winzer persoenlich gekauft."

    def test_edit_keeps_them_apart(self, client, db):
        client.post("/add", data={"name": "Trennung", "quantity": "1",
                                  "description": "A", "notes": "B"}, headers=AJAX)
        wid = db.execute("SELECT id FROM wines WHERE name='Trennung'").fetchone()[0]
        client.post(f"/edit/{wid}", data={"name": "Trennung", "quantity": "1",
                                          "description": "A2", "notes": "B2"}, headers=AJAX)
        row = db.execute("SELECT notes, description FROM wines WHERE id=?", (wid,)).fetchone()
        assert (row["description"], row["notes"]) == ("A2", "B2")

    def test_partial_edit_preserves_the_description(self, client, db):
        """A quantity-only update must not blank a field it does not carry."""
        client.post("/add", data={"name": "Teilupdate", "quantity": "1",
                                  "description": "Bleibt stehen"}, headers=AJAX)
        wid = db.execute("SELECT id FROM wines WHERE name='Teilupdate'").fetchone()[0]
        client.post(f"/edit/{wid}", data={"name": "Teilupdate", "quantity": "5"}, headers=AJAX)
        row = db.execute("SELECT quantity, description FROM wines WHERE id=?", (wid,)).fetchone()
        assert row["quantity"] == 5
        assert row["description"] == "Bleibt stehen"

    def test_duplicate_carries_the_description(self, client, db):
        client.post("/add", data={"name": "Dupli", "quantity": "1",
                                  "description": "Kopiert mich", "notes": "Auch ich"},
                    headers=AJAX)
        wid = db.execute("SELECT id FROM wines WHERE name='Dupli'").fetchone()[0]
        client.post(f"/duplicate/{wid}", data={"quantity": "1"}, headers=AJAX)
        rows = db.execute("SELECT description FROM wines WHERE name='Dupli'").fetchall()
        assert len(rows) == 2
        assert all(r["description"] == "Kopiert mich" for r in rows)

    def test_form_offers_both_fields(self, client):
        html = client.get("/").data.decode()
        assert 'id="wine_description"' in html
        assert 'id="wine_notes"' in html
        assert 'name="description"' in html


class TestNotesToDescriptionMigration:
    def test_moves_notes_and_clears_them(self, client, db):
        import app as wine_app
        db.execute("INSERT INTO wines (name, quantity, notes, category) "
                   "VALUES ('Alt', 1, 'KI-Text von damals', 'wine')")
        db.execute("DELETE FROM app_meta WHERE key='notes_to_description'")
        moved = wine_app.migrate_notes_to_description(db)
        assert moved >= 1
        row = db.execute("SELECT notes, description FROM wines WHERE name='Alt'").fetchone()
        assert row["description"] == "KI-Text von damals"
        assert row["notes"] == ""

    def test_never_runs_twice(self, client, db):
        """The decisive property: a second run would sweep up the personal notes
        the user has typed since."""
        import app as wine_app
        db.execute("DELETE FROM app_meta WHERE key='notes_to_description'")
        wine_app.migrate_notes_to_description(db)

        db.execute("INSERT INTO wines (name, quantity, notes, category) "
                   "VALUES ('Neu', 1, 'Meine private Notiz', 'wine')")
        assert wine_app.migrate_notes_to_description(db) == 0
        row = db.execute("SELECT notes, description FROM wines WHERE name='Neu'").fetchone()
        assert row["notes"] == "Meine private Notiz"
        assert not row["description"]

    def test_does_not_overwrite_an_existing_description(self, client, db):
        import app as wine_app
        db.execute("INSERT INTO wines (name, quantity, notes, description, category) "
                   "VALUES ('Beides', 1, 'Notiz', 'Schon da', 'wine')")
        db.execute("DELETE FROM app_meta WHERE key='notes_to_description'")
        wine_app.migrate_notes_to_description(db)
        row = db.execute("SELECT notes, description FROM wines WHERE name='Beides'").fetchone()
        assert row["description"] == "Schon da"
        assert row["notes"] == "Notiz"      # left alone, nothing to move into


class TestCardDatasetPriceFields:
    """The table view reads card.dataset, so the price trio must live there."""

    @staticmethod
    def _card(html, name):
        return [chunk for chunk in html.split('<div class="card') if name in chunk][0]

    def test_own_price_wins(self, client, db):
        # /add no longer takes a "price" field directly - the own price is
        # cached from purchase lots (see purchases.recompute_wine_price), so
        # it is set here the same way a purchase lot would set it.
        client.post("/add", data={"name": "Beide Preise", "quantity": "1",
                                  "ai_price": "65"}, headers=AJAX)
        db.execute("UPDATE wines SET price=60 WHERE name='Beide Preise'")
        db.commit()
        card = self._card(client.get("/").data.decode(), "Beide Preise")
        assert 'data-price_effective="60' in card
        assert 'data-ai_price="65' in card

    def test_ai_price_fills_in(self, client, db):
        client.post("/add", data={"name": "Nur KI", "quantity": "1",
                                  "ai_price": "42"}, headers=AJAX)
        card = self._card(client.get("/").data.decode(), "Nur KI")
        assert 'data-price_effective="42' in card

    def test_empty_when_neither(self, client, db):
        client.post("/add", data={"name": "Kein Preis", "quantity": "1"}, headers=AJAX)
        card = self._card(client.get("/").data.decode(), "Kein Preis")
        assert 'data-price_effective=""' in card

    def test_structured_grapes_are_exposed(self, client, db):
        import json as J
        client.post("/add", data={
            "name": "Cuvee Dataset", "quantity": "1",
            "grapes": J.dumps([{"name": "Merlot", "pct": 70},
                               {"name": "Syrah", "pct": 30}]),
        }, headers=AJAX)
        card = self._card(client.get("/").data.decode(), "Cuvee Dataset")
        assert "data-grapes=" in card
        assert "Merlot" in card and "Syrah" in card


# ── alcohol content on the bottle (wine and spirits) ──────────────────────────

def _alc(db, name):
    return db.execute("SELECT alcohol_pct FROM wines WHERE name=?", (name,)).fetchone()[0]


def test_add_and_edit_store_alcohol_pct(client, db):
    client.post("/add", data={"name": "Riesling Alk", "quantity": "1",
                              "alcohol_pct": "12.5"}, headers=AJAX)
    client.post("/add", data={"name": "Whisky Alk", "category": "whisky", "quantity": "1",
                              "alcohol_pct": "46"}, headers=AJAX)
    assert _alc(db, "Riesling Alk") == 12.5
    assert _alc(db, "Whisky Alk") == 46.0
    wid = db.execute("SELECT id FROM wines WHERE name='Riesling Alk'").fetchone()[0]
    client.post(f"/edit/{wid}", data={"name": "Riesling Alk", "quantity": "1",
                                      "alcohol_pct": "13"}, headers=AJAX)
    assert _alc(db, "Riesling Alk") == 13.0
    client.post(f"/edit/{wid}", data={"name": "Riesling Alk", "quantity": "1",
                                      "alcohol_pct": ""}, headers=AJAX)
    assert _alc(db, "Riesling Alk") is None


def test_partial_edit_keeps_alcohol_pct(client, db):
    client.post("/add", data={"name": "Teil Alk", "category": "whisky", "quantity": "1",
                              "alcohol_pct": "57.1"}, headers=AJAX)
    wid = db.execute("SELECT id FROM wines WHERE name='Teil Alk'").fetchone()[0]
    client.post(f"/edit/{wid}", data={"name": "Teil Alk", "quantity": "2"}, headers=AJAX)
    assert _alc(db, "Teil Alk") == 57.1


def test_duplicate_copies_alcohol_pct(client, db):
    client.post("/add", data={"name": "Dupli Alk", "quantity": "1", "year": "2019",
                              "alcohol_pct": "14"}, headers=AJAX)
    wid = db.execute("SELECT id FROM wines WHERE name='Dupli Alk'").fetchone()[0]
    client.post(f"/duplicate/{wid}", data={"new_year": "2020", "quantity": "1"}, headers=AJAX)
    vals = [r[0] for r in db.execute("SELECT alcohol_pct FROM wines WHERE name='Dupli Alk'")]
    assert vals == [14.0, 14.0]


def test_wine_json_carries_alcohol_pct(client):
    w = json.loads(client.post("/add", data={"name": "Json Alk", "quantity": "1",
                                             "alcohol_pct": "13.5"}, headers=AJAX).data)["wine"]
    assert w["alcohol_pct"] == 13.5
    assert "abv" not in (w.get("spirit_details") or {})


def test_form_has_one_alcohol_field(client):
    html = client.get("/").data.decode()
    assert html.count('name="alcohol_pct"') == 1
    assert 'name="abv"' not in html


def test_card_carries_alcohol_pct(client):
    client.post("/add", data={"name": "Talisker", "category": "whisky", "quantity": "1",
                              "alcohol_pct": "45.8"}, headers=AJAX)
    html = client.get("/?area=bar").data.decode()
    assert 'data-alcohol_pct="45.8"' in html and "data-abv" not in html
    assert "45.8 %" in html     # the spirit card keeps showing it


def test_wine_card_carries_alcohol_pct(client):
    client.post("/add", data={"name": "Pinot Alk", "quantity": "1",
                              "alcohol_pct": "13.5"}, headers=AJAX)
    assert 'data-alcohol_pct="13.5"' in client.get("/").data.decode()


# ── alcohol content in the sommelier chat and server-side parsing ────────────

def test_parse_alcohol_accepts_only_sane_values():
    import app as wine_app
    assert wine_app._parse_alcohol("13,5") == 13.5
    assert wine_app._parse_alcohol(46) == 46.0
    for bad in ("inf", "nan", "-5", "250", "abc", None, ""):
        assert wine_app._parse_alcohol(bad) is None, bad


def test_chat_edit_sets_alcohol_pct(client, db):
    import app as wine_app
    client.post("/add", data={"name": "Chat Alk", "quantity": "1"}, headers=AJAX)
    wid = db.execute("SELECT id FROM wines WHERE name='Chat Alk'").fetchone()[0]
    res = wine_app._process_chat_edit_wine(
        '[EDIT_WINE]{"id": %d, "alcohol_pct": "13,5"}[/EDIT_WINE]' % wid, db)
    assert res and "alcohol_pct" in res["fields"]
    assert _alc(db, "Chat Alk") == 13.5
    # garbage must not clear a good value
    wine_app._process_chat_edit_wine('[EDIT_WINE]{"id": %d, "alcohol_pct": "viel"}[/EDIT_WINE]' % wid, db)
    assert _alc(db, "Chat Alk") == 13.5


def test_chat_add_stores_alcohol_pct(client, db):
    import app as wine_app
    wine_app._process_chat_add_wine(
        '[ADD_WINE]{"name": "Chat Neu", "wine_type": "Weisswein", "alcohol_pct": 12}[/ADD_WINE]',
        None, [], db)
    assert _alc(db, "Chat Neu") == 12.0


def test_cellar_context_mentions_alcohol(app, client):
    import app as wine_app
    client.post("/add", data={"name": "Kontext Alk", "quantity": "1",
                              "alcohol_pct": "14.5"}, headers=AJAX)
    with app.test_request_context("/"):
        text, _ = wine_app._build_wine_cellar_context()
    line = next(l for l in text.splitlines() if "Kontext Alk" in l)
    assert "14.5 % vol" in line


# ── reading alcohol content from AI answers ──────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    (46.3, 46.3), ("13,5 % vol", 13.5), ("Alc. 12.5% vol.", 12.5), ("14%", 14.0),
    ("12.5 vol.-%", 12.5), ("ABV 43", 43.0), ("86 proof", 43.0),
    ("100% Merlot", None), ("40% new oak", None), (250, None), ("viel", None),
])
def test_parse_alcohol_reads_label_notations(raw, expected):
    import app as wine_app
    assert wine_app._parse_alcohol(raw) == expected


def test_ai_answer_alcohol_is_cleaned(app):
    import app as wine_app
    with app.app_context():
        db = wine_app.get_db()
        assert wine_app._canonicalize_ai_fields(db, {"alcohol_pct": "13,5 % vol"}, "wine")["alcohol_pct"] == 13.5
        assert wine_app._canonicalize_ai_fields(db, {"alcohol_pct": "100% Merlot"}, "wine")["alcohol_pct"] is None
        assert wine_app._canonicalize_ai_fields(db, {"alcohol_pct": "86 proof"}, "whisky")["alcohol_pct"] == 43.0
        assert "alcohol_pct" not in wine_app._canonicalize_ai_fields(db, {"name": "X"}, "wine")


# ── settings modal tabs (P3) ──────────────────────────────────────────────────

def _settings_tabs(html):
    import re
    return re.findall(r'class="settings-tab" data-tab="(\w+)"', html)


def test_settings_modal_has_tabs(client):
    html = client.get("/").data.decode()
    tabs = _settings_tabs(html)
    assert tabs == ["appearance", "ai", "data", "about"]      # no AI configured
    for t in tabs:
        assert f'data-settings-tab="{t}"' in html


def test_sommelier_tab_only_with_ai(client, monkeypatch):
    import app as wine_app
    monkeypatch.setattr(wine_app, "load_options", lambda: {
        **wine_app.HA_OPTIONS, "ai_provider": "anthropic", "anthropic_api_key": "sk-test"})
    assert _settings_tabs(client.get("/").data.decode()) == [
        "appearance", "ai", "sommelier", "data", "about"]


def test_no_settings_footer_without_login(client):
    assert 'class="settings-footer"' not in client.get("/").data.decode()


def test_settings_footer_shows_the_logged_in_user(client, monkeypatch):
    import app as wine_app
    monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
    with client.session_transaction() as s:
        s["user"] = "dominik"
        s["role"] = "admin"
    html = client.get("/").data.decode()
    footer = html.split('class="settings-footer"', 1)[1].split("</div>", 1)[0]
    assert "dominik" in footer and "/logout" in footer


# ── in-app AI settings (P4) ───────────────────────────────────────────────────

class TestAiSettings:
    """Tests for in-app AI settings (/api/ai-settings)."""

    XHR = {"X-Requested-With": "XMLHttpRequest"}

    def test_save_and_overlay(self, client):
        resp = client.post("/api/ai-settings", json={
            "ai_provider": "anthropic", "anthropic_api_key": "sk-test-123",
            "anthropic_model": "claude-x", "chat_model": "claude-chat",
        })
        assert resp.get_json()["ok"] is True
        import app as wine_app
        opts = wine_app.load_options()
        assert opts["ai_provider"] == "anthropic"
        assert opts["anthropic_api_key"] == "sk-test-123"
        assert opts["anthropic_model"] == "claude-x"
        assert opts["chat_model"] == "claude-chat"

    def test_get_masks_key_values(self, client):
        client.post("/api/ai-settings", json={"anthropic_api_key": "sk-secret-456"})
        data = client.get("/api/ai-settings").get_json()
        assert data["ok"] is True
        assert data["keys"]["anthropic_api_key"] is True
        assert "sk-secret-456" not in json.dumps(data)

    def test_empty_key_keeps_stored_value(self, client):
        client.post("/api/ai-settings", json={"anthropic_api_key": "sk-keep"})
        client.post("/api/ai-settings", json={"anthropic_api_key": "", "anthropic_model": "m2"})
        import app as wine_app
        opts = wine_app.load_options()
        assert opts["anthropic_api_key"] == "sk-keep"
        assert opts["anthropic_model"] == "m2"

    def test_null_deletes_override(self, client):
        client.post("/api/ai-settings", json={"anthropic_api_key": "sk-x"})
        client.post("/api/ai-settings", json={"anthropic_api_key": None})
        import app as wine_app
        assert wine_app.load_options()["anthropic_api_key"] == ""

    def test_unknown_keys_ignored(self, client, db):
        client.post("/api/ai-settings", json={"currency": "EUR", "evil": "x"})
        assert db.execute("SELECT COUNT(*) AS c FROM app_settings").fetchone()["c"] == 0

    def test_missing_json_body_is_rejected(self, client):
        assert client.post("/api/ai-settings", data="x").status_code == 400

    def test_web_search_flag_is_a_bool(self, client):
        import app as wine_app
        client.post("/api/ai-settings", json={"openai_web_search": "false"})
        assert wine_app.load_options()["openai_web_search"] is False
        assert client.get("/api/ai-settings").get_json()["settings"]["openai_web_search"] is False
        client.post("/api/ai-settings", json={"openai_web_search": "true"})
        assert wine_app.load_options()["openai_web_search"] is True

    def test_overrides_are_listed(self, client):
        client.post("/api/ai-settings", json={"ai_provider": "openai", "openai_model": "gpt-x"})
        assert client.get("/api/ai-settings").get_json()["overrides"] == ["ai_provider", "openai_model"]

    def test_keys_never_leave_the_server(self, client):
        client.post("/api/ai-settings", json={"openai_api_key": "sk-geheim-789"})
        assert "sk-geheim-789" not in client.get("/api/ai-settings").data.decode()
        assert "sk-geheim-789" not in client.get("/").data.decode()
        # The ZIP is deflated - look inside every member, not at the raw bytes.
        import io, zipfile
        zf = zipfile.ZipFile(io.BytesIO(client.get("/export").data))
        for name in zf.namelist():
            assert b"sk-geheim-789" not in zf.read(name), name

    def test_connection_test_uses_form_values_without_saving(self, client, db):
        """Trying another provider must not overwrite a working setup."""
        client.post("/api/ai-settings", json={"ai_provider": "openai", "openai_api_key": "sk-good",
                                              "openai_model": "gpt-good"})
        with patch("app._call_chat_anthropic", return_value="OK") as mock_call:
            resp = client.post("/api/ai-settings/test", headers=self.XHR, json={
                "ai_provider": "anthropic", "anthropic_api_key": "sk-try", "anthropic_model": "claude-try"})
        assert resp.get_json()["ok"] is True
        used = mock_call.call_args[0][2]
        assert used["anthropic_api_key"] == "sk-try" and used["anthropic_model"] == "claude-try"
        import app as wine_app
        opts = wine_app.load_options()
        assert opts["ai_provider"] == "openai" and opts["openai_model"] == "gpt-good"
        assert opts["anthropic_api_key"] == ""

    def test_connection_test_keeps_stored_key_when_field_is_empty(self, client):
        client.post("/api/ai-settings", json={"ai_provider": "anthropic", "anthropic_api_key": "sk-stored"})
        with patch("app._call_chat_anthropic", return_value="OK") as mock_call:
            client.post("/api/ai-settings/test", headers=self.XHR,
                        json={"ai_provider": "anthropic", "anthropic_api_key": "", "anthropic_model": "m"})
        assert mock_call.call_args[0][2]["anthropic_api_key"] == "sk-stored"

    def test_connection_test_honours_a_cleared_chat_model(self, client):
        client.post("/api/ai-settings", json={"ai_provider": "anthropic", "anthropic_api_key": "sk",
                                              "anthropic_model": "label-m", "chat_model": "old-chat"})
        with patch("app._call_chat_anthropic", return_value="OK") as mock_call:
            client.post("/api/ai-settings/test", headers=self.XHR,
                        json={"ai_provider": "anthropic", "chat_model": "", "anthropic_model": "label-m"})
        assert mock_call.call_args[0][2]["anthropic_model"] == "label-m"

    def test_readonly_cannot_test_or_list_models(self, client, monkeypatch):
        import app as wine_app
        monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
        with client.session_transaction() as s:
            s["user"] = "viewer"
            s["role"] = "readonly"
        assert client.get("/api/ai-settings/models?provider=openrouter").status_code == 403
        assert client.post("/api/ai-settings/test", headers=self.XHR, json={}).status_code == 403

    def test_test_endpoint_uses_chat_call(self, client):
        client.post("/api/ai-settings", json={
            "ai_provider": "anthropic", "anthropic_api_key": "sk-t", "chat_model": "chat-m",
        })
        with patch("app._call_chat_anthropic", return_value="OK") as mock_call:
            resp = client.post("/api/ai-settings/test", headers=self.XHR)
        assert resp.get_json()["ok"] is True
        assert resp.get_json()["reply"] == "OK"
        assert mock_call.call_args[0][2]["anthropic_model"] == "chat-m"

    def test_test_endpoint_reports_error(self, client):
        client.post("/api/ai-settings", json={"ai_provider": "anthropic", "anthropic_api_key": "sk-t"})
        with patch("app._call_chat_anthropic", side_effect=RuntimeError("bad key")):
            resp = client.post("/api/ai-settings/test", headers=self.XHR)
        assert resp.status_code == 502
        assert "bad key" in resp.get_json()["error"]

    def test_test_endpoint_unconfigured(self, client):
        assert client.post("/api/ai-settings/test", headers=self.XHR).status_code == 400

    def test_chat_uses_chat_model(self, client):
        client.post("/api/ai-settings", json={
            "ai_provider": "anthropic", "anthropic_api_key": "sk-t",
            "anthropic_model": "label-m", "chat_model": "chat-m"})
        with patch("app._call_chat_anthropic", return_value="Prost") as mock_call:
            client.post("/api/chat", json={"message": "Hallo", "history": []}, headers=self.XHR)
        assert mock_call.called
        assert mock_call.call_args[0][2]["anthropic_model"] == "chat-m"


class TestAiSettingsAuth:
    """Readonly users must not read or change AI settings."""

    def _make_auth_app(self):
        import app as wine_app
        wine_app.AUTH_ENABLED = True
        wine_app._USERS = {
            "admin": {"hash": generate_password_hash("secret", method="pbkdf2:sha256"), "role": "admin"},
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        }
        wine_app.app.config["TESTING"] = True
        wine_app.app.secret_key = "test-secret"
        wine_app.init_db()
        return wine_app.app.test_client()

    def teardown_method(self):
        import app as wine_app
        wine_app.AUTH_ENABLED = False
        wine_app._USERS = {}

    def test_readonly_cannot_read_or_write(self):
        client = self._make_auth_app()
        client.post("/login", data={"username": "viewer", "password": "pass"})
        assert client.get("/api/ai-settings").status_code == 403
        resp = client.post("/api/ai-settings", json={"ai_provider": "openai"},
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 403

    def test_admin_can_save(self):
        client = self._make_auth_app()
        client.post("/login", data={"username": "admin", "password": "secret"})
        resp = client.post("/api/ai-settings", json={"ai_provider": "openai"},
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.get_json()["ok"] is True


def test_readonly_sees_no_ai_tab(client, monkeypatch):
    import app as wine_app
    monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
    with client.session_transaction() as s:
        s["user"] = "viewer"
        s["role"] = "readonly"
    html = client.get("/").data.decode()
    assert "ai" not in _settings_tabs(html)
    assert 'id="aiProviderSelect"' not in html


def test_ai_tab_offers_every_provider_and_web_search(client):
    html = client.get("/").data.decode()
    section = html.split('data-settings-tab="ai"', 1)[1].split('data-settings-tab=', 1)[0]
    for p in ("none", "anthropic", "openai", "openrouter", "ollama", "minimax", "mistral"):
        assert f'<option value="{p}"' in section, p
    assert 'id="aiWebSearchToggle"' in section and 'id="aiOverridesHint"' in section
    assert 'id="aiModelDd"' in html


# ── user preferences on the server (P5) ──────────────────────────────────────

def _stored_prefs(db, user="default"):
    return {r["key"]: r["value"]
            for r in db.execute("SELECT key, value FROM user_prefs WHERE user=?", (user,))}


class TestUserPrefs:
    """Tests for server-side persistence of UI preferences (/api/prefs)."""

    def test_save_and_seed_prefs(self, client, db):
        resp = client.post("/api/prefs", json={"set": {"wine-theme": "dark", "wineViewMode": "table"}})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert _stored_prefs(db) == {"wine-theme": "dark", "wineViewMode": "table"}
        assert b'"wine-theme": "dark"' in client.get("/").data

    def test_unknown_keys_ignored(self, client, db):
        client.post("/api/prefs", json={"set": {"evil-key": "x", "wine-theme": "light"}})
        assert list(_stored_prefs(db)) == ["wine-theme"]

    def test_non_string_values_ignored(self, client, db):
        client.post("/api/prefs", json={"set": {"wine-theme": {"nested": True}, "wineViewMode": "cards"}})
        assert _stored_prefs(db) == {"wineViewMode": "cards"}

    def test_missing_json_body_keeps_prefs(self, client, db):
        client.post("/api/prefs", json={"set": {"wine-theme": "dark"}})
        resp = client.post("/api/prefs", data="kein json")
        assert resp.status_code == 400
        assert _stored_prefs(db) == {"wine-theme": "dark"}

    def test_prefix_keys_and_our_keys_are_stored(self, client, db):
        cols = '["winery","alcohol_pct","quantity"]'
        client.post("/api/prefs", json={"set": {"wineTableCols.bar": cols, "wt_area": "bar",
                                        "statsPriceBasis": "ai", "wineSettingsTab": "data",
                                        "wineTableColsX": "nope"}})
        assert _stored_prefs(db) == {"wineTableCols.bar": cols, "wt_area": "bar",
                                     "statsPriceBasis": "ai", "wineSettingsTab": "data"}

    def test_active_filter_is_not_synced(self, client, db):
        """A filter is working state - following you to another device it would
        hide bottles there for no visible reason."""
        client.post("/api/prefs", json={"set": {"wine-advanced-filter": '{"rules":{}}', "wine-theme": "dark"}})
        assert _stored_prefs(db) == {"wine-theme": "dark"}

    def test_overlong_values_are_dropped_not_cut(self, client, db):
        client.post("/api/prefs", json={"set": {"wineTableCols.cellar": "[" + '"x",' * 2000 + '"y"]',
                                        "wine-theme": "dark"}})
        assert _stored_prefs(db) == {"wine-theme": "dark"}

    @pytest.mark.parametrize("path", ["/", "/stats", "/timeline", "/reference"])
    def test_every_page_seeds_prefs(self, client, path):
        client.post("/api/prefs", json={"set": {"wine-theme-name": "burgundy"}})
        head = client.get(path).data.decode().split("</head>", 1)[0]
        assert '"wine-theme-name": "burgundy"' in head


class TestUserPrefsAuth:
    """Per-user separation and readonly access for /api/prefs."""

    def _make_auth_app(self):
        import app as wine_app
        wine_app.AUTH_ENABLED = True
        wine_app._USERS = {
            "admin": {"hash": generate_password_hash("secret", method="pbkdf2:sha256"), "role": "admin"},
            "viewer": {"hash": generate_password_hash("pass", method="pbkdf2:sha256"), "role": "readonly"},
        }
        wine_app.app.config["TESTING"] = True
        wine_app.app.secret_key = "test-secret"
        wine_app.init_db()
        return wine_app.app.test_client()

    def teardown_method(self):
        import app as wine_app
        wine_app.AUTH_ENABLED = False
        wine_app._USERS = {}

    def test_prefs_are_per_user(self, db):
        client = self._make_auth_app()
        client.post("/login", data={"username": "admin", "password": "secret"})
        client.post("/api/prefs", json={"set": {"wine-theme": "dark"}})
        client.get("/logout")
        client.post("/login", data={"username": "viewer", "password": "pass"})
        client.post("/api/prefs", json={"set": {"wine-theme": "light"}},
                    headers={"X-Requested-With": "XMLHttpRequest"})
        rows = {r["user"]: r["value"]
                for r in db.execute("SELECT user, value FROM user_prefs WHERE key='wine-theme'")}
        assert rows == {"admin": "dark", "viewer": "light"}

    def test_readonly_can_save_prefs(self, db):
        client = self._make_auth_app()
        client.post("/login", data={"username": "viewer", "password": "pass"})
        resp = client.post("/api/prefs", json={"set": {"wineViewMode": "list"}},
                           headers={"X-Requested-With": "XMLHttpRequest"})
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_prefs_require_login(self):
        client = self._make_auth_app()
        resp = client.post("/api/prefs", json={"set": {"wine-theme": "dark"}})
        assert resp.status_code == 401



# ── Quantity undo ─────────────────────────────────────────────────────────────

class TestQtyUndo:
    """Undo of a quantity change removes the reverted timeline entry."""

    XHR = {"X-Requested-With": "XMLHttpRequest"}

    def _timeline_actions(self, db, wine_id):
        rows = db.execute(
            "SELECT action, quantity FROM timeline WHERE wine_id=? ORDER BY id",
            (wine_id,),
        ).fetchall()
        return [(r["action"], r["quantity"]) for r in rows]

    def test_undo_consumed_removes_timeline_entry(self, client, db, sample_wine):
        """Undoing a minus click deletes the consumed entry instead of logging restocked."""
        wine_id = sample_wine["wine"]["id"]
        name = sample_wine["wine"]["name"]
        client.post(f"/edit/{wine_id}", data={"name": name, "quantity": "2"}, headers=self.XHR)
        assert ("consumed", 1) in self._timeline_actions(db, wine_id)
        resp = client.post(
            f"/edit/{wine_id}",
            data={"name": name, "quantity": "3", "qty_undo": "1"},
            headers=self.XHR,
        )
        assert resp.get_json()["wine"]["quantity"] == 3
        actions = self._timeline_actions(db, wine_id)
        assert ("consumed", 1) not in actions
        assert ("restocked", 1) not in actions

    def test_undo_restocked_removes_timeline_entry(self, client, db, sample_wine):
        """Undoing a plus click deletes the restocked entry instead of logging consumed."""
        wine_id = sample_wine["wine"]["id"]
        name = sample_wine["wine"]["name"]
        client.post(f"/edit/{wine_id}", data={"name": name, "quantity": "4"}, headers=self.XHR)
        assert ("restocked", 1) in self._timeline_actions(db, wine_id)
        client.post(
            f"/edit/{wine_id}",
            data={"name": name, "quantity": "3", "qty_undo": "1"},
            headers=self.XHR,
        )
        actions = self._timeline_actions(db, wine_id)
        assert ("restocked", 1) not in actions
        assert ("consumed", 1) not in actions

    def test_undo_without_matching_entry_logs_normally(self, client, db, sample_wine):
        """qty_undo without a matching entry falls back to normal logging."""
        wine_id = sample_wine["wine"]["id"]
        name = sample_wine["wine"]["name"]
        client.post(
            f"/edit/{wine_id}",
            data={"name": name, "quantity": "5", "qty_undo": "1"},
            headers=self.XHR,
        )
        assert ("restocked", 2) in self._timeline_actions(db, wine_id)


def test_qty_controls_hidden_for_readonly(client, sample_wine, monkeypatch):
    import app as wine_app
    monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
    with client.session_transaction() as s:
        s["user"] = "viewer"
        s["role"] = "readonly"
    html = client.get("/").data.decode()
    import re
    assert not re.search(r'<div class="qty-badge[^"]*" onclick=', html)
    assert 'id="qtyPopover"' not in html and 'id="undoToast"' not in html


def test_qty_badge_opens_the_popover(client, sample_wine):
    html = client.get("/").data.decode()
    assert 'onclick="openQtyPopover(this, event)"' in html
    assert 'id="qtyPopover"' in html and 'id="undoToast"' in html


# ── undo deleting a wine (P7) ─────────────────────────────────────────────────

_CHILD_TABLES = ("wine_grapes", "wine_purchases", "wine_images", "spirit_details", "spirit_casks")


def _make_full_whisky(client, db, upload_dir):
    """A whisky with everything that hangs off a bottle: details, casks,
    grapes rows, a purchase and three image files."""
    import images
    w = json.loads(client.post("/add", data={
        "name": "Voll Whisky", "category": "whisky", "type": "Single Malt", "quantity": "2",
        "alcohol_pct": "46", "age_years": "12", "bottler": "Original",
        "casks": json.dumps([{"name": "Ex-Bourbon", "years": 10}, {"name": "PX Sherry", "years": 2}]),
    }, headers=AJAX).data)["wine"]
    wid = w["id"]
    client.post(f"/api/wine/{wid}/purchases", json={"quantity": 2, "unit_price": 80})
    db.execute("INSERT INTO wine_grapes (wine_id, name, pct, position) VALUES (?, 'Gerste', NULL, 0)", (wid,))
    for i, cat in enumerate(("scan", "vivino", "scan")):
        fname = f"full{i}.jpg"
        with open(os.path.join(upload_dir, fname), "wb") as f:
            f.write(b"\xff\xd8img")
        images.add_image(db, wid, cat, fname)
    db.commit()
    return wid


def _snapshot(db, wid):
    snap = {"wines": [dict(r) for r in db.execute("SELECT * FROM wines WHERE id=?", (wid,))]}
    for t in _CHILD_TABLES:
        snap[t] = sorted((dict(r) for r in db.execute(f"SELECT * FROM {t} WHERE wine_id=?", (wid,))),
                         key=lambda r: json.dumps(r, sort_keys=True, default=str))
    return snap


def test_delete_offers_restore_and_keeps_files(client, db, upload_dir):
    wid = _make_full_whisky(client, db, upload_dir)
    resp = client.post(f"/delete/{wid}", headers=AJAX).get_json()
    assert resp["ok"] is True and resp["restorable"] is True
    for i in range(3):
        assert os.path.exists(os.path.join(upload_dir, f"full{i}.jpg"))


def test_restore_brings_back_everything(client, db, upload_dir):
    wid = _make_full_whisky(client, db, upload_dir)
    before = _snapshot(db, wid)
    assert all(before[t] for t in _CHILD_TABLES)          # the fixture really has all of them
    client.post(f"/delete/{wid}", headers=AJAX)
    assert db.execute("SELECT COUNT(*) FROM wines WHERE id=?", (wid,)).fetchone()[0] == 0
    resp = client.post(f"/api/wine/{wid}/restore", headers=AJAX).get_json()
    assert resp["ok"] is True and resp["wine"]["id"] == wid
    assert _snapshot(db, wid) == before
    actions = [r[0] for r in db.execute("SELECT action FROM timeline WHERE wine_id=?", (wid,))]
    assert "removed" not in actions


def test_restore_unknown_is_404(client):
    assert client.post("/api/wine/987654/restore", headers=AJAX).status_code == 404


def test_restore_twice_is_404(client, db, upload_dir):
    wid = _make_full_whisky(client, db, upload_dir)
    client.post(f"/delete/{wid}", headers=AJAX)
    assert client.post(f"/api/wine/{wid}/restore", headers=AJAX).status_code == 200
    assert client.post(f"/api/wine/{wid}/restore", headers=AJAX).status_code == 404


def test_readonly_cannot_restore(client, db, upload_dir, monkeypatch):
    import app as wine_app
    wid = _make_full_whisky(client, db, upload_dir)
    client.post(f"/delete/{wid}", headers=AJAX)
    monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
    with client.session_transaction() as s:
        s["user"] = "viewer"
        s["role"] = "readonly"
    assert client.post(f"/api/wine/{wid}/restore", headers=AJAX).status_code == 403


# ── review fixes P5-P7 ────────────────────────────────────────────────────────

def test_quantity_only_edit_keeps_the_grape_text(client, db):
    w = json.loads(client.post("/add", data={
        "name": "Traube", "quantity": "2",
        "grapes": json.dumps([{"name": "Merlot", "pct": 60}, {"name": "Cabernet Franc", "pct": 40}]),
    }, headers=AJAX).data)["wine"]
    client.post(f"/edit/{w['id']}", data={"name": "Traube", "quantity": "3"}, headers=AJAX)
    row = db.execute("SELECT grape FROM wines WHERE id=?", (w["id"],)).fetchone()
    assert row["grape"] == "Merlot, Cabernet Franc"


class TestQuantityEndpoint:
    """POST /api/wine/<id>/quantity applies a delta on the server, so quick
    clicks cannot overtake each other and no other field is touched."""

    def _wine(self, client, qty=3, **extra):
        data = {"name": "Mengenwein", "quantity": str(qty), "notes": "Meine Notiz",
                "grapes": json.dumps([{"name": "Syrah", "pct": 100}])}
        data.update(extra)
        return json.loads(client.post("/add", data=data, headers=AJAX).data)["wine"]["id"]

    def _post(self, client, wid, **payload):
        return client.post(f"/api/wine/{wid}/quantity", json=payload, headers=AJAX)

    def _timeline(self, db, wid):
        return [(r[0], r[1]) for r in db.execute(
            "SELECT action, quantity FROM timeline WHERE wine_id=? ORDER BY id", (wid,))]

    def test_delta_changes_only_the_quantity(self, client, db):
        wid = self._wine(client)
        resp = self._post(client, wid, delta=-1).get_json()
        assert resp["ok"] is True and resp["wine"]["quantity"] == 2
        row = db.execute("SELECT notes, grape FROM wines WHERE id=?", (wid,)).fetchone()
        assert row["notes"] == "Meine Notiz" and row["grape"] == "Syrah"
        assert self._timeline(db, wid)[-1] == ("consumed", 1)

    def test_never_below_zero(self, client, db):
        wid = self._wine(client, qty=1)
        assert self._post(client, wid, delta=-5).get_json()["wine"]["quantity"] == 0
        assert self._timeline(db, wid)[-1] == ("consumed", 1)
        self._post(client, wid, delta=-1)
        assert self._timeline(db, wid)[-1] == ("consumed", 1)      # nothing new logged

    def test_undo_removes_the_entry(self, client, db):
        wid = self._wine(client)
        self._post(client, wid, delta=-1)
        self._post(client, wid, delta=1, undo=True)
        assert self._timeline(db, wid) == [("added", 3)]

    def test_unknown_wine_is_404(self, client):
        assert self._post(client, 987654, delta=1).status_code == 404

    def test_bad_delta_is_400(self, client):
        wid = self._wine(client)
        assert self._post(client, wid, delta="viel").status_code == 400
        assert self._post(client, wid).status_code == 400

    def test_readonly_cannot_change(self, client, monkeypatch):
        import app as wine_app
        wid = self._wine(client)
        monkeypatch.setattr(wine_app, "AUTH_ENABLED", True)
        with client.session_transaction() as s:
            s["user"] = "viewer"
            s["role"] = "readonly"
        assert self._post(client, wid, delta=1).status_code == 403

    def test_concurrent_clicks_all_count(self, app, client, db):
        """Eight parallel +1 must end at +8 - the server reads and writes the
        quantity in one locked transaction."""
        import threading
        wid = self._wine(client, qty=3)
        errors = []

        def click():
            try:
                c = app.test_client()
                r = c.post(f"/api/wine/{wid}/quantity", json={"delta": 1}, headers=AJAX)
                if r.status_code != 200:
                    errors.append(r.status_code)
            except Exception as e:          # pragma: no cover - surfaced below
                errors.append(repr(e))

        threads = [threading.Thread(target=click) for _ in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert errors == []
        assert db.execute("SELECT quantity FROM wines WHERE id=?", (wid,)).fetchone()[0] == 11
        restocked = [q for a, q in self._timeline(db, wid) if a == "restocked"]
        assert sum(restocked) == 8


class TestPrefsDelta:
    """The browser sends what changed; other devices' settings survive."""

    def test_set_keeps_other_keys(self, client, db):
        client.post("/api/prefs", json={"set": {"wine-theme": "dark", "wineViewMode": "table"}})
        client.post("/api/prefs", json={"set": {"wine-theme": "light"}})
        assert _stored_prefs(db) == {"wine-theme": "light", "wineViewMode": "table"}

    def test_remove_deletes_only_those_keys(self, client, db):
        client.post("/api/prefs", json={"set": {"wine-show-empty": "1", "wine-theme": "dark"}})
        client.post("/api/prefs", json={"remove": ["wine-show-empty"]})
        assert _stored_prefs(db) == {"wine-theme": "dark"}

    def test_table_column_keys_are_limited_to_the_areas(self, client, db):
        client.post("/api/prefs", json={"set": {"wineTableCols.cellar": "[]", "wineTableCols.bar": "[]",
                                                "wineTableCols.x1": "[]"}})
        assert sorted(_stored_prefs(db)) == ["wineTableCols.bar", "wineTableCols.cellar"]

    def test_unknown_and_invalid_entries_ignored(self, client, db):
        client.post("/api/prefs", json={"set": {"evil": "x", "wine-theme": {"a": 1},
                                                "wineViewMode": "list"},
                                        "remove": ["evil", 5]})
        assert _stored_prefs(db) == {"wineViewMode": "list"}


def test_stats_drink_window_chart_with_outliers(client):
    """An old dessert wine and a very long-lived red must not stretch the axis,
    and their bars must render with a label instead of a year."""
    from datetime import date
    cur = date.today().year
    client.post("/add", data={"name": "Alter Suesswein", "quantity": "1", "type": "Dessertwein",
                              "drink_from": str(cur - 14), "drink_until": str(cur - 8)}, headers=AJAX)
    client.post("/add", data={"name": "Ewiger Roter", "quantity": "2", "type": "Rotwein",
                              "drink_from": str(cur + 20), "drink_until": str(cur + 30)}, headers=AJAX)
    client.post("/add", data={"name": "Jetzt Trinken", "quantity": "3", "type": "Weisswein",
                              "drink_from": str(cur), "drink_until": str(cur + 2)}, headers=AJAX)
    resp = client.get("/stats")
    assert resp.status_code == 200
    html = resp.data.decode()
    chart = html.split('class="dw-chart"', 1)[1].split('class="dw-legend"', 1)[0]
    assert chart.count('class="dw-bar-col') == 6          # older, cur..cur+2, later (+ phone edge bar)
    assert chart.count("dw-only-phone") == 1 and chart.count("dw-only-desktop") == 1
    import html as _html
    import re as _re
    # edge bars carry a full and a short label (phones): "< 2023" / "<23"
    labels = [" ".join(_html.unescape(_re.sub(r"<[^>]+>", " ", part.split("</div>", 1)[0])).split())
              for part in chart.split('class="dw-bar-label">')[1:]]
    yy = lambda y: f"{y % 100:02d}"
    assert labels[0] == f"< {cur - 3} <{yy(cur - 3)}"
    assert labels[-2:] == [f"{cur + 10}+ {yy(cur + 10)}+", f"{cur + 15}+ {yy(cur + 15)}+"]
    assert str(cur - 14) not in chart and str(cur + 30) not in chart


# ── stats polish ──────────────────────────────────────────────────────────────

def test_drink_window_bars_show_the_bottle_total(client):
    """Each bar carries its total bottle count, summed over the wine types."""
    import re
    from datetime import date
    cur = date.today().year
    client.post("/add", data={"name": "Rot A", "type": "Rotwein", "quantity": "2",
                              "drink_from": str(cur), "drink_until": str(cur + 1)}, headers=AJAX)
    client.post("/add", data={"name": "Weiss B", "type": "Weisswein", "quantity": "3",
                              "drink_from": str(cur), "drink_until": str(cur)}, headers=AJAX)
    html = client.get("/stats").data.decode()
    chart = html.split('class="dw-chart"', 1)[1].split('class="dw-legend"', 1)[0]
    totals = re.findall(r'class="dw-bar-total">(\d+)<', chart)
    assert totals == ["5", "2"]


class TestPriceTop5:
    """The price card offers overview, top 5 most expensive and top 5 cheapest,
    for recorded prices and for the AI estimate alike."""

    def _seed(self, client):
        for i, price in enumerate([10, 25, 40, 55, 70, 85, 99]):
            w = json.loads(client.post("/add", data={"name": f"Preis{price}", "quantity": "1"},
                                       headers=AJAX).data)["wine"]
            client.post(f"/api/wine/{w['id']}/purchases", json={"quantity": 1, "unit_price": price})
        # one bottle known only by its AI estimate
        client.post("/add", data={"name": "NurKI", "quantity": "1", "ai_price": "500"}, headers=AJAX)

    def _list(self, html, basis, view):
        import re
        block = html.split(f'data-price-basis="{basis}" data-price-view="{view}"', 1)[1]
        block = block.split("</div>\n  </div>", 1)[0] if view == "overview" else block.split('data-price-', 1)[0]
        return re.findall(r'class="wine-name">([^<]+)<', block)

    def test_top5_lists_for_recorded_prices(self, client):
        self._seed(client)
        html = client.get("/stats").data.decode()
        assert self._list(html, "own", "top_exp") == ["Preis99", "Preis85", "Preis70", "Preis55", "Preis40"]
        assert self._list(html, "own", "top_cheap") == ["Preis10", "Preis25", "Preis40", "Preis55", "Preis70"]

    def test_top5_with_estimate_includes_estimated_bottles(self, client):
        self._seed(client)
        html = client.get("/stats").data.decode()
        assert self._list(html, "est", "top_exp")[0] == "NurKI"

    def test_view_switch_is_rendered(self, client):
        self._seed(client)
        html = client.get("/stats").data.decode()
        assert 'id="priceViewSwitch"' in html
        for view in ("overview", "top_exp", "top_cheap"):
            assert f'data-view="{view}"' in html


def test_globe_regions_are_clickable_and_list_can_be_hidden(client):
    import re
    client.post("/add", data={"name": "Barolo", "quantity": "2", "region": "Piemont",
                              "country": "Italien"}, headers=AJAX)
    html = client.get("/stats").data.decode()
    if 'id="globeCanvas"' not in html:
        pytest.skip("no map coordinates for the test region in this reference set")
    assert 'id="globeListToggle"' in html
    items = re.findall(r'<button type="button" class="globe-legend-item"[^>]*data-lat="[-\d.]+"[^>]*data-lon="[-\d.]+"', html)
    assert items, "legend entries must be buttons carrying their coordinates"
