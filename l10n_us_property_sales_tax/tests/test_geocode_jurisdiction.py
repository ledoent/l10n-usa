# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.addons.l10n_us_sales_tax_engine.tests.common import UsTaxBaseTest

_HTTP = "odoo.addons.property_data_base.models.property_data_source.requests.get"

# Census geographies response: Erie County, PA -> GEOID 42049 (state 42, county 049).
CENSUS = {
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


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class TestGeocodeJurisdiction(UsTaxBaseTest):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.ZM = cls.env["us.tax.zip.mapping"]
        cls.pa = cls.env["res.country.state"].search(
            [("code", "=", "PA"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.jur_erie = cls.env["us.tax.jurisdiction"].create(
            {
                "name": "Erie",
                "type": "county",
                "state_id": cls.pa.id,
                "county": "ERIE",
                "fips_state": "42",
                "fips_county": "049",
            }
        )
        cls.addr = {
            "zip": "16501",
            "state": "PA",
            "city": "ERIE",
            "address": "123 Main St, Erie, PA 16501",
        }

    def test_geocode_resolves_county_by_fips_and_learns(self):
        with patch(_HTTP, return_value=_Resp(CENSUS)):
            jur = self.ZM.resolve_jurisdiction(self.addr)
        self.assertEqual(jur, self.jur_erie)
        m = self.ZM.search([("address_key", "=", self.ZM._address_key(self.addr))])
        self.assertEqual(len(m), 1)
        self.assertTrue(m.verified)
        self.assertEqual(m.source, "geocode")

    def test_second_call_uses_cache_not_geocode(self):
        with patch(_HTTP, return_value=_Resp(CENSUS)):
            self.ZM.resolve_jurisdiction(self.addr)  # learns
        # Verified cache wins -> the geocoder must not be called again.
        with patch(_HTTP, side_effect=AssertionError("geocoded again")) as m:
            jur = self.ZM.resolve_jurisdiction(self.addr)
        self.assertEqual(jur, self.jur_erie)
        m.assert_not_called()

    def test_unmatched_fips_returns_empty(self):
        other = {
            "result": {
                "addressMatches": [
                    {
                        "coordinates": {"x": -1, "y": 1},
                        "matchedAddress": "x",
                        "geographies": {"Counties": [{"GEOID": "06037"}]},
                    }
                ]
            }
        }
        with patch(_HTTP, return_value=_Resp(other)):
            self.assertFalse(self.ZM._geocode_jurisdiction(self.addr))

    def test_no_street_skips_geocode(self):
        with patch(_HTTP, side_effect=AssertionError("geocoded")) as m:
            self.assertFalse(
                self.ZM._geocode_jurisdiction(
                    {"zip": "16501", "state": "PA", "address": ", Erie, PA"}
                )
            )
        m.assert_not_called()
