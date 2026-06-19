# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo.tests.common import TransactionCase


class TestLeadConstraint(TransactionCase):
    def _record(self, year_built):
        return self.env["property.record"].create(
            {"street": "1 Test St", "year_built": year_built}
        )

    def test_pre_1978_flags_epa_rrp(self):
        rec = self._record(1965)
        rec._sync_constraints(rec._derive_constraints(), source=None)
        codes = rec.constraint_ids.mapped("code")
        self.assertIn("epa_rrp_lead", codes)
        self.assertEqual(rec.constraint_count, 1)

    def test_post_1978_has_no_lead_flag(self):
        rec = self._record(1999)
        rec._sync_constraints(rec._derive_constraints(), source=None)
        self.assertNotIn("epa_rrp_lead", rec.constraint_ids.mapped("code"))

    def test_unknown_year_no_flag(self):
        rec = self._record(False)
        self.assertEqual(rec._derive_constraints(), [])

    def test_cutoff_year_boundary(self):
        # 1978 itself is NOT pre-1978; 1977 is.
        codes_1978 = self._record(1978)._derive_constraints()
        self.assertEqual(codes_1978, [])
        codes_1977 = [c["code"] for c in self._record(1977)._derive_constraints()]
        self.assertIn("epa_rrp_lead", codes_1977)
