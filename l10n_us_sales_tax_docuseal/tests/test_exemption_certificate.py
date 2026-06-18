# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import timedelta
from unittest import mock

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

CLIENT_PATH = "odoo.addons.l10n_us_sales_tax_docuseal.models.docuseal_client"


class TestExemptionCertificate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Acme Reseller", "email": "buyer@acme.test"}
        )
        params = cls.env["ir.config_parameter"].sudo()
        params.set_param("l10n_us_sales_tax_docuseal.url", "https://ds.test")
        params.set_param("l10n_us_sales_tax_docuseal.api_token", "tok")
        params.set_param("l10n_us_sales_tax_docuseal.template_id", "42")
        cls.cert = cls.env["l10n.us.tax.exemption.certificate"].create(
            {"partner_id": cls.partner.id, "certificate_type": "resale"}
        )

    def test_sequence_assigned(self):
        self.assertNotEqual(self.cert.name, "New")
        self.assertTrue(self.cert.name.startswith("EXEMPT/"))

    def test_send_requires_template(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_sales_tax_docuseal.template_id", ""
        )
        self.cert.docuseal_template_id = False
        with self.assertRaises(UserError):
            self.cert.action_send_for_signature()

    def test_send_for_signature(self):
        response = [
            {
                "submission_id": 1001,
                "slug": "abc123",
                "email": "buyer@acme.test",
            }
        ]
        with mock.patch.object(
            type(self.env["docuseal.client"]),
            "docuseal_create_submission",
            return_value=response,
        ):
            self.cert.action_send_for_signature()
        self.assertEqual(self.cert.state, "sent")
        self.assertEqual(self.cert.docuseal_submission_id, "1001")
        self.assertEqual(
            self.cert.docuseal_sign_url, "https://ds.test/s/abc123"
        )

    def test_register_signed_document(self):
        self.cert._register_signed_document(b"%PDF-1.4 test", "cert.pdf")
        self.assertEqual(self.cert.state, "signed")
        self.assertTrue(self.cert.signed_document)
        self.assertTrue(self.cert.is_valid)

    def test_validity_and_expiry_cron(self):
        self.cert._register_signed_document(b"%PDF-1.4", "c.pdf")
        self.cert.expiration_date = fields.Date.context_today(
            self.cert
        ) - timedelta(days=1)
        self.assertFalse(self.cert.is_valid)
        self.env[
            "l10n.us.tax.exemption.certificate"
        ]._cron_expire_certificates()
        self.assertEqual(self.cert.state, "expired")

    def test_signature_verification(self):
        client = self.env["docuseal.client"]
        # No secret configured -> verification disabled (always True)
        self.assertTrue(client.docuseal_verify_signature(b"body", None))
        self.env["ir.config_parameter"].sudo().set_param(
            "l10n_us_sales_tax_docuseal.webhook_secret", "s3cr3t"
        )
        import hashlib
        import hmac

        sig = hmac.new(b"s3cr3t", b"body", hashlib.sha256).hexdigest()
        self.assertTrue(client.docuseal_verify_signature(b"body", sig))
        self.assertFalse(client.docuseal_verify_signature(b"body", "deadbeef"))

    def test_has_valid_exemption_on_partner(self):
        self.cert._register_signed_document(b"%PDF", "c.pdf")
        self.partner.invalidate_recordset()
        self.assertTrue(self.partner.has_valid_exemption)
        found = self.env["res.partner"].search(
            [("has_valid_exemption", "=", True)]
        )
        self.assertIn(self.partner, found)
