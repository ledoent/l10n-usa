# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from datetime import timedelta
from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase
from odoo.tools import mute_logger

_REC_LOG = "odoo.addons.property_data_base.models.property_record"


class TestPropertyRecord(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.us = cls.env.ref("base.us")
        cls.state_pa = cls.env["res.country.state"].search(
            [("code", "=", "PA"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.source = cls.env["property.data.source"].create(
            {"name": "Manual", "provider": "manual", "cache_ttl_days": 10}
        )
        cls.record = cls.env["property.record"].create(
            {"street": "123 Main St", "city": "Erie", "zip": "16501"}
        )

    def test_apply_fills_and_maps_aliases(self):
        self.record._apply(
            {
                "lat": 42.1,
                "lon": -80.08,
                "formatted": "123 Main St, Erie, PA 16501",
                "state_code": "PA",
                "apn": "12-345",
                "raw": {"ok": True},
            },
            self.source,
        )
        self.assertEqual(self.record.latitude, 42.1)
        self.assertEqual(self.record.longitude, -80.08)
        self.assertEqual(self.record.formatted_address, "123 Main St, Erie, PA 16501")
        self.assertEqual(self.record.state_id, self.state_pa)
        self.assertEqual(self.record.apn, "12-345")
        self.assertIn(self.source, self.record.source_ids)
        self.assertTrue(self.record.fetched_on)
        self.assertEqual(self.record.raw_response["manual"], {"ok": True})

    def test_apply_never_overwrites(self):
        self.record.apn = "ORIGINAL"
        self.record._apply({"apn": "NEW"}, self.source)
        self.assertEqual(self.record.apn, "ORIGINAL")

    def test_is_stale(self):
        self.assertTrue(self.record.is_stale)  # never fetched
        self.record.write(
            {
                "fetched_on": fields.Datetime.now(),
                "source_ids": [(4, self.source.id)],
            }
        )
        self.assertFalse(self.record.is_stale)
        self.record.fetched_on = fields.Datetime.now() - timedelta(days=20)
        self.record.invalidate_recordset(["is_stale"])
        self.assertTrue(self.record.is_stale)

    def test_resolve_respects_cache(self):
        # A fresh record with fetched_on is skipped (no source provides data
        # here, but the guard must short-circuit before iterating).
        self.record.write(
            {
                "fetched_on": fields.Datetime.now(),
                "source_ids": [(4, self.source.id)],
            }
        )
        self.assertFalse(self.record.is_stale)
        # Fresh record -> skipped, no source calls, no errors.
        self.assertEqual(self.record._resolve(), [])

    def test_action_resolve_requires_source(self):
        self.source.active = False
        with self.assertRaises(UserError):
            self.record.action_resolve()

    def test_manual_source_has_no_capabilities(self):
        self.assertEqual(self.source._get_capabilities(), [])
        self.assertFalse(self.source.provides("geocode"))

    def test_sync_constraints_idempotent(self):
        items = [{"code": "c1", "name": "C1", "severity": "warning", "applies": True}]
        self.record._sync_constraints(items, self.source)
        self.assertEqual(len(self.record.constraint_ids), 1)
        # Re-sync replaces the source's rows, no duplicates.
        self.record._sync_constraints(items, self.source)
        self.assertEqual(len(self.record.constraint_ids), 1)
        self.assertEqual(self.record.constraint_count, 1)
        self.assertFalse(self.record.has_blocking_constraint)

    def test_derived_and_source_constraints_coexist(self):
        self.record._sync_constraints(
            [{"code": "src", "name": "S", "applies": True}], self.source
        )
        self.record._sync_constraints(
            [{"code": "der", "name": "D", "severity": "blocking", "applies": True}],
            source=None,
        )
        self.assertEqual(len(self.record.constraint_ids), 2)
        self.assertTrue(self.record.has_blocking_constraint)
        # Re-syncing the derived bucket leaves the source bucket untouched.
        self.record._sync_constraints([], source=None)
        self.assertEqual(self.record.constraint_ids.mapped("code"), ["src"])

    def test_base_derives_no_constraints(self):
        self.assertEqual(self.record._derive_constraints(), [])

    @mute_logger(_REC_LOG)
    def test_call_source_isolates_failure(self):
        errors = []
        with patch.object(type(self.source), "geocode", side_effect=ValueError("boom")):
            result = self.record._call_source(errors, self.source, "geocode", {})
        self.assertEqual(result, {})
        self.assertEqual(len(errors), 1)
        self.assertEqual(errors[0][0], self.source)

    def test_action_resolve_partial_posts_message(self):
        self.record.fetched_on = fields.Datetime.now()
        with patch.object(
            type(self.record),
            "_resolve",
            return_value=[(self.source, "boom")],
        ):
            self.assertTrue(self.record.action_resolve())
        self.assertTrue(
            any("skipped" in (m.body or "") for m in self.record.message_ids)
        )

    def test_action_resolve_total_failure_raises(self):
        self.record.fetched_on = False
        with patch.object(
            type(self.record),
            "_resolve",
            return_value=[(self.source, "boom")],
        ):
            with self.assertRaises(UserError):
                self.record.action_resolve()

    def test_non_applicable_blocker_excluded_from_stats(self):
        self.record._sync_constraints(
            [{"code": "x", "name": "X", "severity": "blocking", "applies": False}],
            self.source,
        )
        self.assertEqual(self.record.constraint_count, 0)
        self.assertFalse(self.record.has_blocking_constraint)

    def test_ttl_zero_means_always_stale(self):
        # cache_ttl_days 0 disables caching -> the record is never "fresh".
        self.source.cache_ttl_days = 0
        self.record.write(
            {
                "fetched_on": fields.Datetime.now(),
                "source_ids": [(4, self.source.id)],
            }
        )
        self.assertTrue(self.record.is_stale)

    def test_apply_noop_does_not_stamp_fetched_on(self):
        # A raw-only payload that fills no field must not mark the record fresh.
        self.record._apply({"raw": {"x": 1}}, self.source)
        self.assertFalse(self.record.fetched_on)
        self.assertFalse(self.record.source_ids)

    def test_apply_keeps_zero_values(self):
        self.record._apply({"beds": 0, "year_built": 0}, self.source)
        # 0 is a legitimate value, written; year_built 0 is also kept.
        self.assertEqual(self.record.beds, 0)
        self.assertTrue(self.record.fetched_on)

    def test_geometry_summary_polygon_and_multipolygon(self):
        self.record.geometry = {
            "type": "Polygon",
            "coordinates": [[[0, 0], [1, 0], [0, 0]]],
        }
        self.assertEqual(self.record.geometry_summary, "Polygon, 1 ring(s)")
        self.record.geometry = {
            "type": "MultiPolygon",
            "coordinates": [
                [[[0, 0], [1, 0], [0, 0]]],
                [[[2, 2], [3, 2], [2, 2]]],
            ],
        }
        self.assertEqual(self.record.geometry_summary, "MultiPolygon, 2 ring(s)")
        self.record.geometry = False
        self.assertFalse(self.record.geometry_summary)

    def test_partner_property_record_count(self):
        p_a = self.env["res.partner"].create({"name": "A"})
        p_b = self.env["res.partner"].create({"name": "B"})
        self.env["property.record"].create({"partner_id": p_a.id})
        self.env["property.record"].create({"partner_id": p_a.id})
        self.assertEqual(p_a.property_record_count, 2)
        self.assertEqual(p_b.property_record_count, 0)

    def test_partner_button_requires_address(self):
        partner = self.env["res.partner"].create({"name": "No Address"})
        with self.assertRaises(UserError):
            partner.action_fetch_property_data()

    def test_partner_button_creates_and_reuses_record(self):
        partner = self.env["res.partner"].create(
            {"name": "Has Address", "street": "5 Elm St", "zip": "16501"}
        )
        action = partner.action_fetch_property_data()
        self.assertEqual(action["res_model"], "property.record")
        self.assertEqual(len(partner.property_record_ids), 1)
        # Second call reuses the same record (no source data here, but no dup).
        partner.action_fetch_property_data()
        self.assertEqual(len(partner.property_record_ids), 1)

    def test_address_vals_prefers_partner(self):
        partner = self.env["res.partner"].create(
            {
                "name": "Acme",
                "street": "9 Oak Ave",
                "city": "Pittsburgh",
                "state_id": self.state_pa.id,
                "zip": "15201",
                "country_id": self.us.id,
            }
        )
        rec = self.env["property.record"].create({"partner_id": partner.id})
        vals = rec._address_vals()
        self.assertEqual(vals["street"], "9 Oak Ave")
        self.assertEqual(vals["state_code"], "PA")
        self.assertEqual(vals["country_code"], "US")
