# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.tests.common import TransactionCase

_HTTP = "odoo.addons.property_data_base.models.property_data_source.requests.get"

CENSUS_PAYLOAD = {
    "result": {
        "addressMatches": [
            {
                "coordinates": {"x": -80.085, "y": 42.129},
                "matchedAddress": "123 MAIN ST, ERIE, PA, 16501",
                "geographies": {"Counties": [{"GEOID": "42049"}]},
            }
        ]
    }
}


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestCensus(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.source = cls.env.ref("l10n_us_property_census.source_census")

    def test_capabilities(self):
        self.assertEqual(self.source._get_capabilities(), ["geocode"])
        self.assertTrue(self.source.provides("geocode"))
        self.assertFalse(self.source.provides("parcel_geometry"))

    def test_geocode_maps_point_and_fips(self):
        with patch(_HTTP, return_value=_FakeResponse(CENSUS_PAYLOAD)):
            vals = self.source.geocode(
                {
                    "street": "123 Main St",
                    "city": "Erie",
                    "state_code": "PA",
                    "zip": "16501",
                }
            )
        self.assertAlmostEqual(vals["lat"], 42.129, places=3)
        self.assertAlmostEqual(vals["lon"], -80.085, places=3)
        self.assertEqual(vals["county_fips"], "42049")
        self.assertEqual(vals["formatted"], "123 MAIN ST, ERIE, PA, 16501")

    def test_geocode_no_match_returns_empty(self):
        empty = {"result": {"addressMatches": []}}
        with patch(_HTTP, return_value=_FakeResponse(empty)):
            vals = self.source.geocode({"street": "Nowhere"})
        self.assertEqual(vals, {})
