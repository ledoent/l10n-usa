# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from unittest.mock import patch

from odoo.tests.common import TransactionCase

_HTTP = "odoo.addons.property_data_base.models.property_data_source.requests.get"

FEMA = {
    "features": [
        {"attributes": {"FLD_ZONE": "AE", "ZONE_SUBTY": "FLOODWAY", "SFHA_TF": "T"}}
    ]
}
FEMA_X = {
    "features": [{"attributes": {"FLD_ZONE": "X", "ZONE_SUBTY": "", "SFHA_TF": "F"}}]
}
NRHP = {"features": [{"attributes": {"RESNAME": "Old Town Historic District"}}]}
EMPTY = {"features": []}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _router(fema=None, nrhp=None):
    fema = FEMA if fema is None else fema
    nrhp = NRHP if nrhp is None else nrhp

    def _get(url, params=None, headers=None, timeout=None):
        if "NFHL" in url:
            return _Resp(fema)
        if "nrhp" in url:
            return _Resp(nrhp)
        raise AssertionError(f"Unexpected URL {url}")

    return _get


class TestOverlays(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.fema = cls.env.ref("l10n_us_property_gis_overlays.source_fema_flood")
        cls.nrhp = cls.env.ref("l10n_us_property_gis_overlays.source_nrhp")

    def _record(self):
        return self.env["property.record"].create(
            {"street": "1 Test St", "latitude": 38.84, "longitude": -76.92}
        )

    def test_capabilities(self):
        self.assertEqual(self.fema._get_capabilities(), ["constraints"])
        self.assertEqual(self.nrhp._get_capabilities(), ["constraints"])

    def test_fema_sfha_is_applicable_warning(self):
        with patch(_HTTP, side_effect=_router()):
            vals = self.fema.fetch_data(["constraints"], lat=38.84, lon=-76.92)
        c = vals["constraints"][0]
        self.assertEqual(c["code"], "fema_flood_zone")
        self.assertTrue(c["applies"])
        self.assertEqual(c["severity"], "warning")

    def test_fema_zone_x_not_applicable(self):
        with patch(_HTTP, side_effect=_router(fema=FEMA_X)):
            vals = self.fema.fetch_data(["constraints"], lat=38.84, lon=-76.92)
        self.assertFalse(vals["constraints"][0]["applies"])

    def test_both_overlays_aggregate_on_record(self):
        rec = self._record()
        with patch(_HTTP, side_effect=_router()):
            rec._resolve(capabilities=["constraints"], force=True)
        codes = set(rec.constraint_ids.mapped("code"))
        self.assertEqual(codes, {"fema_flood_zone", "nrhp_historic_district"})
        # Both flood (SFHA) and historic district apply here.
        self.assertEqual(rec.constraint_count, 2)

    def test_nrhp_absent_yields_no_constraint(self):
        rec = self._record()
        with patch(_HTTP, side_effect=_router(nrhp=EMPTY)):
            rec._resolve(capabilities=["constraints"], force=True)
        self.assertNotIn("nrhp_historic_district", rec.constraint_ids.mapped("code"))

    def test_fema_multiple_features_skips_blank_zone(self):
        multi = {
            "features": [
                {"attributes": {"FLD_ZONE": "", "SFHA_TF": "F"}},
                {"attributes": {"FLD_ZONE": "AE", "SFHA_TF": "T"}},
            ]
        }
        with patch(_HTTP, side_effect=_router(fema=multi)):
            vals = self.fema.fetch_data(["constraints"], lat=38.84, lon=-76.92)
        self.assertEqual(len(vals["constraints"]), 1)
        self.assertEqual(vals["constraints"][0]["applies"], True)

    def test_nrhp_resname_fallbacks(self):
        with patch(
            _HTTP,
            side_effect=_router(
                nrhp={"features": [{"attributes": {"NAME": "Foo District"}}]}
            ),
        ):
            vals = self.nrhp.fetch_data(["constraints"], lat=38.84, lon=-76.92)
        self.assertIn("Foo District", vals["constraints"][0]["name"])
        with patch(_HTTP, side_effect=_router(nrhp={"features": [{"attributes": {}}]})):
            vals = self.nrhp.fetch_data(["constraints"], lat=38.84, lon=-76.92)
        self.assertIn("Listed district", vals["constraints"][0]["name"])

    def test_overlay_url_config_override(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "property_data.fema_flood.url", "https://sentinel/NFHL/query"
        )
        seen = {}

        def _capture(url, params=None, headers=None, timeout=None):
            seen["url"] = url
            return _Resp(FEMA)

        with patch(_HTTP, side_effect=_capture):
            self.fema.fetch_data(["constraints"], lat=38.84, lon=-76.92)
        self.assertEqual(seen["url"], "https://sentinel/NFHL/query")

    def test_no_point_skips_query(self):
        with patch(_HTTP, side_effect=_router()) as mocked:
            self.assertEqual(self.fema.fetch_data(["constraints"]), {})
            mocked.assert_not_called()

    def test_stale_constraint_cleared_on_empty_reresolve(self):
        rec = self._record()
        with patch(_HTTP, side_effect=_router()):
            rec._resolve(capabilities=["constraints"], force=True)
        self.assertIn("fema_flood_zone", rec.constraint_ids.mapped("code"))
        # Point now matches no FEMA feature -> the stale row must be removed.
        with patch(_HTTP, side_effect=_router(fema=EMPTY)):
            rec._resolve(capabilities=["constraints"], force=True)
        self.assertNotIn("fema_flood_zone", rec.constraint_ids.mapped("code"))
