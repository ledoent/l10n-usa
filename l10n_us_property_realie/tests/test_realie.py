# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

_HTTP = "odoo.addons.property_data_base.models.property_data_source.requests.get"

REALIE_PAYLOAD = {
    "properties": [
        {
            "apn": "12-345-678",
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-80.086, 42.128],
                        [-80.084, 42.128],
                        [-80.084, 42.130],
                        [-80.086, 42.130],
                        [-80.086, 42.128],
                    ]
                ],
            },
            "lotSizeSquareFeet": 8000,
            "ownerName": "Jane Q Doe",
            "ownerMailingAddress": "PO Box 9, Erie, PA 16501",
            "yearBuilt": 1995,
            "buildingSquareFeet": 1850,
            "zoning": "R-1",
            "assessedValue": 145000,
        }
    ]
}

_PARCEL_CAPS = ["parcel_geometry", "attributes", "owner"]


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _realie_get(url, params=None, headers=None, timeout=None):
    if "realie" in url:
        return _FakeResponse(REALIE_PAYLOAD)
    raise AssertionError(f"Unexpected URL: {url}")


class TestRealie(TransactionCase):
    """Self-contained: tests Realie in isolation (base + realie only), so the
    suite passes without the Census connector installed. The point is supplied
    directly rather than via a geocoder.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "property_data.realie.api_key", "test-key"
        )
        cls.realie = cls.env.ref("l10n_us_property_realie.source_realie")

    def _record(self):
        return self.env["property.record"].create(
            {"street": "123 Main St", "latitude": 42.129, "longitude": -80.085}
        )

    def test_capabilities(self):
        self.assertEqual(
            self.realie._get_capabilities(),
            ["parcel_geometry", "attributes", "owner"],
        )

    def test_realie_fills_parcel_owner_attributes(self):
        rec = self._record()
        with patch(_HTTP, side_effect=_realie_get):
            rec._resolve(capabilities=_PARCEL_CAPS, force=True)
        self.assertEqual(rec.apn, "12-345-678")
        self.assertEqual(rec.geometry["type"], "Polygon")
        self.assertEqual(rec.lot_area_sqft, 8000)
        self.assertEqual(rec.owner_name, "Jane Q Doe")
        self.assertEqual(rec.year_built, 1995)
        self.assertEqual(rec.zoning, "R-1")
        self.assertIn(self.realie, rec.source_ids)

    def test_cache_prevents_second_fetch(self):
        rec = self._record()
        with patch(_HTTP, side_effect=_realie_get) as mocked:
            rec._resolve(capabilities=_PARCEL_CAPS, force=True)
            first = mocked.call_count
            self.assertTrue(first)
            rec._resolve(capabilities=_PARCEL_CAPS)  # fresh -> no network
            self.assertEqual(mocked.call_count, first)

    @mute_logger("odoo.addons.property_data_base.models.property_record")
    def test_missing_key_is_isolated_not_fatal(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "property_data.realie.api_key", ""
        )
        rec = self._record()
        with patch(_HTTP, side_effect=_realie_get):
            errors = rec._resolve(capabilities=_PARCEL_CAPS, force=True)
        self.assertFalse(rec.apn, "Realie skipped, nothing applied")
        self.assertTrue(errors, "the skipped source is reported, no exception")

    def test_first_property_envelope_shapes(self):
        prop = {"apn": "1"}
        self.assertEqual(self.realie._realie_first_property([prop]), prop)
        self.assertEqual(
            self.realie._realie_first_property({"properties": [prop]}), prop
        )
        self.assertEqual(self.realie._realie_first_property({"results": [prop]}), prop)
        self.assertEqual(self.realie._realie_first_property({"data": prop}), prop)
        self.assertEqual(self.realie._realie_first_property(prop), prop)
        self.assertIsNone(self.realie._realie_first_property({}))

    def test_geometry_unwraps_feature_and_rejects_non_polygon(self):
        poly = {"type": "Polygon", "coordinates": [[[0, 0]]]}
        self.assertEqual(
            self.realie._realie_geometry(
                {"geometry": {"type": "Feature", "geometry": poly}}
            ),
            poly,
        )
        self.assertIsNone(
            self.realie._realie_geometry(
                {"geometry": {"type": "Point", "coordinates": [0, 0]}}
            )
        )
        self.assertIsNone(self.realie._realie_geometry({}))

    def test_fetch_uses_address_when_no_point(self):
        captured = {}

        def _capture(url, params=None, headers=None, timeout=None):
            captured["params"] = params
            return _FakeResponse(REALIE_PAYLOAD)

        with patch(_HTTP, side_effect=_capture):
            self.realie.fetch_data(
                ["attributes"],
                address={
                    "street": "123 Main St",
                    "city": "Erie",
                    "state_code": "PA",
                    "zip": "16501",
                },
            )
        self.assertIn("address", captured["params"])
        self.assertNotIn("latitude", captured["params"])

    def test_fetch_with_no_input_returns_empty(self):
        with patch(_HTTP, side_effect=_realie_get) as mocked:
            self.assertEqual(self.realie.fetch_data(["attributes"]), {})
            mocked.assert_not_called()

    def test_missing_key_raises_on_direct_call(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "property_data.realie.api_key", ""
        )
        with patch(_HTTP, side_effect=_realie_get):
            with self.assertRaises(UserError):
                self.realie.fetch_data(["parcel_geometry"], lat=42.1, lon=-80.0)
