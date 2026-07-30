# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
from datetime import date

from odoo.tests import TransactionCase, tagged
from odoo.tools import misc


@tagged("post_install", "-at_install")
class TestSignOcaBridge(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.company.us_tax_exemption_signature_backend = "sign_oca"
        cls.data = base64.b64encode(
            open(misc.file_path("sign_oca/tests/empty.pdf"), "rb").read()
        )
        cls.role = cls.env.ref("sign_oca.sign_role_customer")
        cls.template = cls.env["sign.oca.template"].create(
            {"data": cls.data, "name": "Exemption Certificate", "filename": "empty.pdf"}
        )
        cls.company.us_tax_exemption_sign_template_id = cls.template

        cls.us = cls.env.ref("base.us")
        cls.wy = cls.env["res.country.state"].search(
            [("code", "=", "WY"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.ga = cls.env["res.country.state"].search(
            [("code", "=", "GA"), ("country_id", "=", cls.us.id)], limit=1
        )
        cls.resale = cls.env.ref("l10n_us_sales_tax_exemption.reason_resale")
        cls.partner = cls.env["res.partner"].create(
            {
                "name": "Reseller LLC",
                "email": "ap@reseller.test",
                "state_id": cls.wy.id,
                "country_id": cls.us.id,
                "zip": "82001",
            }
        )
        cls.cert = cls.env["us.tax.exemption"].create(
            {
                "partner_id": cls.partner.id,
                "reason_id": cls.resale.id,
                "state_ids": [(6, 0, cls.wy.ids)],
                "certificate_number": "WY-OLD-1",
                "effective_date": date(2022, 1, 1),
                "expiry_date": date(2025, 1, 1),
                "state": "valid",
            }
        )

    def _request(self, values, record=None):
        """A sent request whose signers have all signed."""
        request = self.env["sign.oca.request"].create(
            {
                "data": self.data,
                "name": "Exemption Certificate",
                "record_ref": f"us.tax.exemption,{(record or self.cert).id}",
                "signer_ids": [
                    (0, 0, {"partner_id": self.partner.id, "role_id": self.role.id})
                ],
            }
        )
        request.signatory_data = {
            str(index): {"id": index, "name": name, "value": value}
            for index, (name, value) in enumerate(values.items(), start=1)
        }
        request.state = "sent"
        request.signer_ids.signed_on = "2026-07-29 10:00:00"
        return request

    def _captured(self, number="WY-NEW-1"):
        return self.env["us.tax.exemption"].search(
            [("partner_id", "=", self.partner.id), ("certificate_number", "=", number)]
        )

    # ── capture ──────────────────────────────────────────────────────────────

    def test_signing_populates_the_certificate(self):
        """The answers on the form become data, not just a filed PDF."""
        self._request(
            {
                "State": "WY, GA",
                "Exemption Type": "resale",
                "Exemption Number": "WY-NEW-1",
            }
        )._check_signed()
        cert = self._captured()
        self.assertEqual(len(cert), 1)
        self.assertEqual(cert.reason_id, self.resale)
        self.assertEqual(set(cert.state_ids.ids), set((self.wy + self.ga).ids))

    def test_a_captured_certificate_is_not_yet_effective(self):
        """Same guarantee as the DocuSeal path: signed is not approved."""
        self._request(
            {
                "State": "WY",
                "Exemption Type": "resale",
                "Exemption Number": "WY-NEW-1",
            }
        )._check_signed()
        self.assertEqual(self._captured().state, "signed")

    def test_capture_happens_once(self):
        """_check_signed is called on every signature, not only the last."""
        request = self._request(
            {
                "State": "WY",
                "Exemption Type": "resale",
                "Exemption Number": "WY-NEW-1",
            }
        )
        request._check_signed()
        request._check_signed()
        self.assertEqual(len(self._captured()), 1)

    def test_a_request_for_something_else_is_left_alone(self):
        """sign_oca signs all sorts of documents; only ours is our business."""
        request = self._request({"State": "WY"})
        request.record_ref = f"res.partner,{self.partner.id}"
        request._check_signed()
        self.assertFalse(self._captured())

    def test_an_unreadable_answer_is_kept_as_a_draft(self):
        self._request(
            {
                "State": "WY",
                "Exemption Type": "not-a-known-reason",
                "Exemption Number": "WY-NEW-1",
            }
        )._check_signed()
        self.assertEqual(self._captured().state, "draft")

    def test_values_are_read_by_field_name(self):
        request = self._request({"State": "WY", "Exemption Number": "N-1"})
        self.assertEqual(
            request._us_tax_signed_values(),
            {"State": "WY", "Exemption Number": "N-1"},
        )

    # ── request ──────────────────────────────────────────────────────────────

    def test_requesting_a_renewal_sends_a_signature_request(self):
        self.cert._request_renewal()
        request = self.cert.sign_request_id
        self.assertTrue(request)
        self.assertEqual(request.state, "sent")
        self.assertEqual(request.record_ref, self.cert)

    def test_a_company_with_no_template_is_skipped_not_crashed(self):
        """One misconfigured company must not stop the renewal cron."""
        self.company.us_tax_exemption_sign_template_id = False
        self.cert._request_renewal()
        self.assertFalse(self.cert.sign_request_id)

    def test_another_backend_is_passed_through(self):
        """The routing that lets two bridges coexist.

        With a different backend selected this module must decline the record
        rather than handle it, or whichever bridge loaded last would silently
        own every company.
        """
        self.company.us_tax_exemption_signature_backend = "none"
        self.cert._request_renewal()
        self.assertFalse(self.cert.sign_request_id)
