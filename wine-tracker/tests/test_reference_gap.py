"""Unit test for the Vivino coverage-gap diff logic (pure, no network)."""
import os
import sys

APP_DIR = os.path.join(os.path.dirname(__file__), "..", "app")
SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "scripts")
sys.path.insert(0, APP_DIR)
sys.path.insert(0, SCRIPTS_DIR)

import reference
import vivino_gap


def test_compute_gaps_identifies_missing():
    bundle_countries = [{"code": "FR"}, {"code": "IT"}]
    bundle_regions = [{"name": "Bordeaux", "country_code": "FR", "aliases": []}]
    bundle_grapes = [
        {"name": "Syrah", "aliases": ["Shiraz"]},
        {"name": "Merlot", "aliases": []},
    ]
    vivino_grapes = ["Shiraz", "Merlot", "Assyrtiko"]        # Assyrtiko is new
    vivino_regions = [
        {"name": "Bordeaux", "country_code": "FR"},          # matched
        {"name": "Chianti", "country_code": "IT"},           # missing (IT known, region not)
        {"name": "Santorini", "country_code": "GR"},         # missing + country GR unknown
    ]

    gaps = vivino_gap.compute_gaps(
        vivino_grapes, vivino_regions, bundle_countries, bundle_regions,
        bundle_grapes, reference.normalize_name,
    )

    # Grapes: alias (Shiraz→Syrah) and Merlot match; only Assyrtiko is missing
    assert gaps["missing_grapes"] == ["Assyrtiko"]
    # Regions: Bordeaux matched, Chianti + Santorini missing
    assert "Chianti" in gaps["missing_regions"]["IT"]
    assert "Santorini" in gaps["missing_regions"]["GR"]
    assert "FR" not in gaps["missing_regions"]
    # Countries: GR not in the bundle
    assert gaps["missing_countries"] == ["GR"]
    assert gaps["stats"]["grapes_matched"] == 2
