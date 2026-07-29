# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from unittest.mock import patch

import requests

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

_TX_MODULE = "odoo.addons.l10n_us_sales_tax_exemption_verify.services.verifier_texas"


class _Response:
    """Minimal stand-in for requests.Response."""

    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")


@tagged("post_install", "-at_install")
class TestExemptionVerification(TransactionCase):
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
        cls.manual = cls.env.ref("l10n_us_sales_tax_exemption_verify.verifier_manual")
        cls.texas = cls.env.ref("l10n_us_sales_tax_exemption_verify.verifier_us_tx_cpa")
        cls.partner = cls.env["res.partner"].create(
            {"name": "Lone Star Resale", "country_id": cls.us.id}
        )

    def _certificate(self, state, number="12345678901"):
        return self.env["us.tax.exemption"].create(
            {
                "partner_id": self.partner.id,
                "reason_id": self.resale.id,
                "state_ids": [(6, 0, [state.id])],
                "certificate_number": number,
                "effective_date": "2020-01-01",
                "state": "valid",
            }
        )

    # ── seed data + routing ──────────────────────────────────────────────────

    def test_texas_xmlid_really_is_texas(self):
        """The base.state_us_N ids are not alphabetical — pin the assumption."""
        self.assertEqual(self.tx.code, "TX")
        self.assertEqual(self.texas.state_ids, self.tx)

    def test_state_specific_verifier_outranks_manual(self):
        chosen = self.env["us.tax.exemption.verifier"]._for_state(self.tx)
        self.assertEqual(chosen, self.texas)

    def test_state_without_a_service_falls_back_to_manual(self):
        """Georgia's GATE portal has no service behind it, so manual it is."""
        chosen = self.env["us.tax.exemption.verifier"]._for_state(self.ga)
        self.assertEqual(chosen, self.manual)

    def test_registry_resolves_every_seeded_verifier(self):
        for verifier in self.env["us.tax.exemption.verifier"].search([]):
            service = verifier._get_service()
            self.assertEqual(service.CODE, verifier.code)

    def test_unknown_code_raises(self):
        broken = self.env["us.tax.exemption.verifier"].create(
            {"name": "Nowhere", "code": "nowhere", "mode": "api"}
        )
        with self.assertRaises(UserError):
            broken._get_service()

    def test_verifier_refuses_a_state_it_does_not_cover(self):
        certificate = self._certificate(self.ga)
        with self.assertRaises(UserError):
            certificate.action_verify(state=self.ga, verifier=self.texas)

    # ── manual ───────────────────────────────────────────────────────────────

    def test_manual_verification_is_recorded(self):
        certificate = self._certificate(self.ga)
        verification = certificate.action_verify(detail="GATE portal: active")
        self.assertEqual(verification.result, "verified")
        self.assertEqual(verification.mode, "manual")
        self.assertEqual(verification.verified_by, self.env.user)
        self.assertEqual(verification.state_id, self.ga)
        self.assertEqual(verification.detail, "GATE portal: active")
        self.assertEqual(certificate.verification_result, "verified")
        self.assertEqual(certificate.verification_count, 1)

    def test_manual_can_record_a_negative_result(self):
        """The trail is what was checked, not only the good news."""
        certificate = self._certificate(self.ga)
        verification = certificate.action_verify(
            result="not_found", detail="Card suspended"
        )
        self.assertEqual(verification.result, "not_found")
        self.assertEqual(certificate.verification_result, "not_found")

    def test_latest_verification_wins(self):
        certificate = self._certificate(self.ga)
        certificate.action_verify(result="verified")
        second = certificate.action_verify(result="not_found")
        self.assertEqual(certificate.verification_count, 2)
        self.assertEqual(certificate.last_verification_id, second)

    # ── Texas ────────────────────────────────────────────────────────────────

    def test_texas_active_permit_verifies(self):
        certificate = self._certificate(self.tx)
        payload = [
            {"taxpayer_number": "12345678901", "taxpayer_name": "LONE STAR RESALE INC"}
        ]
        with patch(f"{_TX_MODULE}.requests.get", return_value=_Response(payload)):
            verification = certificate.action_verify(state=self.tx)
        self.assertEqual(verification.result, "verified")
        self.assertEqual(verification.mode, "api")
        self.assertEqual(verification.reference, "12345678901")
        self.assertIn("LONE STAR RESALE INC", verification.detail)
        self.assertIn("taxpayer_number", verification.payload)

    def test_texas_unknown_number_is_not_found(self):
        certificate = self._certificate(self.tx)
        with patch(f"{_TX_MODULE}.requests.get", return_value=_Response([])):
            verification = certificate.action_verify(state=self.tx)
        self.assertEqual(verification.result, "not_found")

    def test_texas_normalizes_a_formatted_number(self):
        certificate = self._certificate(self.tx, number="1-2345-67890-1")
        payload = [{"taxpayer_number": "12345678901", "taxpayer_name": "X"}]
        with patch(
            f"{_TX_MODULE}.requests.get", return_value=_Response(payload)
        ) as mocked:
            verification = certificate.action_verify(state=self.tx)
        self.assertEqual(
            mocked.call_args.kwargs["params"]["taxpayer_number"], "12345678901"
        )
        self.assertEqual(verification.result, "verified")

    def test_texas_rejects_a_wrong_length_number(self):
        certificate = self._certificate(self.tx, number="123")
        with patch(f"{_TX_MODULE}.requests.get") as mocked:
            verification = certificate.action_verify(state=self.tx)
        mocked.assert_not_called()
        self.assertEqual(verification.result, "inconclusive")

    def test_unreachable_service_is_inconclusive_not_invalid(self):
        """A network failure must never read as a bad certificate."""
        certificate = self._certificate(self.tx)
        with (
            patch(
                f"{_TX_MODULE}.requests.get",
                side_effect=requests.ConnectionError("boom"),
            ),
            self.assertLogs(_TX_MODULE, level="WARNING"),
        ):
            # The warning is the point of the branch; swallow it so the OCA
            # checklog gate doesn't read an expected log line as a failure.
            verification = certificate.action_verify(state=self.tx)
        self.assertEqual(verification.result, "inconclusive")
        self.assertNotEqual(verification.result, "not_found")
        self.assertEqual(certificate.state, "valid")

    def test_api_key_switches_to_the_comptroller_endpoint(self):
        certificate = self._certificate(self.tx)
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.tx_cpa_api_key", "secret"
        )
        payload = [{"taxpayerNumber": "12345678901", "taxpayerName": "Y"}]
        with patch(
            f"{_TX_MODULE}.requests.get", return_value=_Response(payload)
        ) as mocked:
            certificate.action_verify(state=self.tx)
        called_url = mocked.call_args.args[0]
        self.assertIn("api.comptroller.texas.gov", called_url)
        self.assertEqual(mocked.call_args.kwargs["headers"]["api-key"], "secret")

    def test_comptroller_404_is_not_found(self):
        certificate = self._certificate(self.tx)
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_tax.tx_cpa_api_key", "secret"
        )
        with patch(
            f"{_TX_MODULE}.requests.get", return_value=_Response(None, status_code=404)
        ):
            verification = certificate.action_verify(state=self.tx)
        self.assertEqual(verification.result, "not_found")

    # ── blanket certificates ─────────────────────────────────────────────────

    def test_blanket_certificate_needs_an_explicit_state(self):
        """Several states covered means no single authority to ask."""
        certificate = self._certificate(self.tx)
        certificate.state_ids = [(4, self.ga.id)]
        self.assertFalse(certificate._verification_state())
        verification = certificate.action_verify(state=self.ga)
        self.assertEqual(verification.state_id, self.ga)
