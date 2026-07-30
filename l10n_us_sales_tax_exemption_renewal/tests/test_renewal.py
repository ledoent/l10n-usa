# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import date, timedelta
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged


def _patch_hook(env):
    """Patch the registry model, not a Python class.

    ``_request_renewal`` is contributed by this module through _inherit, so it
    lives on the assembled registry class — patching the base module's Python
    class would not intercept it.
    """
    return patch.object(type(env["us.tax.exemption"]), "_request_renewal")


@tagged("post_install", "-at_install")
class TestExemptionRenewal(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.user.groups_id |= cls.env.ref(
            "l10n_us_sales_tax_engine.group_us_tax_manager"
        )
        cls.us = cls.env.ref("base.us")
        cls.tx = cls.env.ref("base.state_us_44")
        cls.ga = cls.env.ref("base.state_us_11")
        cls.resale = cls.env.ref("l10n_us_sales_tax_exemption.reason_resale")
        cls.government = cls.env.ref("l10n_us_sales_tax_exemption.reason_government")
        cls.partner = cls.env["res.partner"].create(
            {"name": "Lone Star Resale", "country_id": cls.us.id}
        )
        cls.Exemption = cls.env["us.tax.exemption"]
        cls.Validity = cls.env["us.tax.exemption.validity"]
        cls.env.company.us_tax_exemption_validity_years = 3
        cls.env.company.us_tax_exemption_renewal_lead_days = 60

    # ── the validity ladder ─────────────────────────────────────────────────

    def test_company_default_applies_when_nothing_else_does(self):
        years, never = self.Exemption._resolve_validity(self.tx, self.resale)
        self.assertEqual((years, never), (3, False))

    def test_reason_term_beats_the_company_default(self):
        self.resale.validity_years = 4
        years, never = self.Exemption._resolve_validity(self.tx, self.resale)
        self.assertEqual((years, never), (4, False))

    def test_a_state_and_reason_rule_beats_the_reason(self):
        self.resale.validity_years = 4
        self.Validity.create(
            {"state_id": self.tx.id, "reason_id": self.resale.id, "validity_years": 2}
        )
        self.assertEqual(
            self.Exemption._resolve_validity(self.tx, self.resale), (2, False)
        )
        # …and leaves another state on the reason's term.
        self.assertEqual(
            self.Exemption._resolve_validity(self.ga, self.resale), (4, False)
        )

    def test_never_expires_leaves_no_expiry_date(self):
        self.government.never_expires = True
        self.assertFalse(
            self.Exemption._expiry_for(date(2026, 1, 1), self.tx, self.government)
        )
        self.assertEqual(
            self.Exemption._expiry_for(date(2026, 1, 1), self.tx, self.resale),
            date(2029, 1, 1),
        )

    # ── the renewal cron ────────────────────────────────────────────────────

    def _certificate(self, expiry):
        return self.Exemption.create(
            {
                "partner_id": self.partner.id,
                "reason_id": self.resale.id,
                "state_ids": [(6, 0, [self.tx.id])],
                "certificate_number": "TX-1",
                "effective_date": date.today() - timedelta(days=365),
                "expiry_date": expiry,
                "state": "valid",
            }
        )

    def test_cron_requests_a_renewal_inside_the_lead_window(self):
        due = self._certificate(date.today() + timedelta(days=30))
        with _patch_hook(self.env) as hook:
            self.Exemption._cron_request_renewals()
            hook.assert_called_once()
        self.assertTrue(due.renewal_requested_on)

    def test_cron_ignores_a_certificate_outside_the_window(self):
        self._certificate(date.today() + timedelta(days=200))
        with _patch_hook(self.env) as hook:
            self.Exemption._cron_request_renewals()
            hook.assert_not_called()

    def test_a_certificate_is_only_chased_once(self):
        self._certificate(date.today() + timedelta(days=30))
        with _patch_hook(self.env) as hook:
            self.Exemption._cron_request_renewals()
            self.Exemption._cron_request_renewals()
            hook.assert_called_once()

    def test_open_ended_certificates_are_never_chased(self):
        self._certificate(False)
        with _patch_hook(self.env) as hook:
            self.Exemption._cron_request_renewals()
            hook.assert_not_called()

    # ── capture ─────────────────────────────────────────────────────────────

    def test_recording_a_signed_certificate(self):
        certificate = self.Exemption._record_signed_certificate(
            partner=self.partner,
            state_codes=["TX", "GA"],
            reason_code="resale",
            certificate_number="TX-RESALE-9",
            signed_on=date(2026, 1, 1),
        )
        self.assertEqual(certificate.state, "signed", "captured data skipped review")
        self.assertEqual(certificate.reason_id, self.resale)
        self.assertEqual(set(certificate.state_ids.ids), {self.tx.id, self.ga.id})
        self.assertEqual(certificate.certificate_number, "TX-RESALE-9")
        self.assertEqual(certificate.expiry_date, date(2029, 1, 1))

    def test_recording_the_same_signature_twice_does_not_duplicate(self):
        """DocuSeal retries a failed webhook twelve times over two days."""
        kwargs = {
            "partner": self.partner,
            "state_codes": ["TX"],
            "reason_code": "resale",
            "certificate_number": "TX-RESALE-9",
            "signed_on": date(2026, 1, 1),
        }
        first = self.Exemption._record_signed_certificate(**kwargs)
        second = self.Exemption._record_signed_certificate(**kwargs)
        self.assertEqual(first, second)
        self.assertEqual(
            self.Exemption.search_count([("partner_id", "=", self.partner.id)]), 1
        )

    def test_the_old_certificate_survives_until_the_new_one_is_approved(self):
        """No exemption gap.

        Superseding at capture would drop a live certificate the moment a new
        form arrived, leaving the customer taxable until somebody got round to
        approving the replacement.
        """
        old = self._certificate(date.today() + timedelta(days=30))
        old.renewal_requested_on = "2026-01-01 00:00:00"
        new = self.Exemption._record_signed_certificate(
            partner=self.partner,
            state_codes=["TX"],
            reason_code="resale",
            certificate_number="TX-2",
        )
        self.assertEqual(new.state, "signed")
        self.assertEqual(old.state, "valid", "the live certificate was dropped early")

        new.action_validate()
        self.assertEqual(
            old.state, "expired", "the replaced certificate still reads valid"
        )
        self.assertFalse(new.renewal_requested_on)

    def test_an_unresolvable_payload_is_kept_as_a_draft(self):
        """Relaxing the required fields means an unreadable form can be kept
        for a human instead of discarded."""
        # The refusal logs a warning by design; swallow it so the OCA checklog
        # gate does not read an expected log line as a failure.
        with self.assertLogs(
            "odoo.addons.l10n_us_sales_tax_exemption_renewal.models.us_tax_exemption",
            level="WARNING",
        ):
            certificate = self.Exemption._record_signed_certificate(
                partner=self.partner,
                state_codes=["ZZ"],
                reason_code="not-a-reason",
                certificate_number="?",
            )
        self.assertTrue(certificate, "the form was discarded")
        self.assertEqual(certificate.state, "draft")

    def test_the_hook_is_a_no_op_without_a_bridge(self):
        certificate = self._certificate(date.today() + timedelta(days=30))
        self.assertFalse(certificate._request_renewal())
