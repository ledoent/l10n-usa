# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib
import hmac
from datetime import timedelta
from unittest import mock

import requests

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase

CLIENT_MOD = "odoo.addons.l10n_us_sales_tax_docuseal.models.docuseal_client"


class TestExemptionCertificate(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env["res.partner"].create(
            {"name": "Acme Reseller", "email": "buyer@acme.test"}
        )
        cls.params = cls.env["ir.config_parameter"].sudo()
        cls.params.set_param("l10n_us_sales_tax_docuseal.url", "https://ds.test")
        cls.params.set_param("l10n_us_sales_tax_docuseal.api_token", "tok")
        cls.params.set_param("l10n_us_sales_tax_docuseal.template_id", "42")
        cls.cert = cls.env["l10n.us.tax.exemption.certificate"].create(
            {"partner_id": cls.partner.id, "certificate_type": "resale"}
        )

    # ----- model basics -----
    def test_sequence_assigned(self):
        self.assertTrue(self.cert.name.startswith("EXEMPT/"))

    def test_template_required(self):
        self.params.set_param("l10n_us_sales_tax_docuseal.template_id", "")
        self.cert.docuseal_template_id = False
        with self.assertRaises(UserError):
            self.cert._docuseal_template()

    def test_template_override_on_record(self):
        self.cert.docuseal_template_id = "99"
        self.assertEqual(self.cert._docuseal_template(), "99")

    def test_submitter_requires_email(self):
        self.partner.email = False
        self.cert.signer_email = False
        with self.assertRaises(UserError):
            self.cert._docuseal_submitter_values()

    def test_submitter_prefill(self):
        self.cert.exemption_number = "RS-1"
        values = self.cert._docuseal_submitter_values()[0]
        names = {f["name"] for f in values["fields"]}
        self.assertEqual(values["email"], "buyer@acme.test")
        self.assertIn("Exemption Number", names)

    # ----- send flow -----
    def test_send_for_signature(self):
        response = [
            {"submission_id": 1001, "slug": "abc123", "email": "buyer@acme.test"}
        ]
        with mock.patch.object(
            type(self.env["docuseal.client"]),
            "docuseal_create_submission",
            return_value=response,
        ):
            self.cert.action_send_for_signature()
        self.assertEqual(self.cert.state, "sent")
        self.assertEqual(self.cert.docuseal_submission_id, "1001")
        self.assertEqual(self.cert.docuseal_sign_url, "https://ds.test/s/abc123")

    def test_send_wrong_state(self):
        self.cert.state = "signed"
        with self.assertRaises(UserError):
            self.cert.action_send_for_signature()

    # ----- lifecycle actions -----
    def test_register_signed_document(self):
        self.cert._register_signed_document(b"%PDF-1.4 test", "cert.pdf")
        self.assertEqual(self.cert.state, "signed")
        self.assertTrue(self.cert.signed_document)
        self.assertTrue(self.cert.is_valid)

    def test_mark_rejected_and_reset(self):
        self.cert.action_mark_rejected()
        self.assertEqual(self.cert.state, "rejected")
        self.cert.action_reset_to_draft()
        self.assertEqual(self.cert.state, "draft")

    def test_action_cancel_archives_submission(self):
        self.cert.write({"state": "sent", "docuseal_submission_id": "55"})
        with mock.patch.object(
            type(self.env["docuseal.client"]),
            "docuseal_archive_submission",
            return_value={},
        ) as archive:
            self.cert.action_cancel()
        archive.assert_called_once()
        self.assertEqual(self.cert.state, "cancelled")

    def test_action_cancel_survives_archive_failure(self):
        self.cert.write({"state": "sent", "docuseal_submission_id": "66"})
        with mock.patch.object(
            type(self.env["docuseal.client"]),
            "docuseal_archive_submission",
            side_effect=UserError("nope"),
        ):
            self.cert.action_cancel()
        self.assertEqual(self.cert.state, "cancelled")

    def test_open_sign_url(self):
        with self.assertRaises(UserError):
            self.cert.action_open_sign_url()
        self.cert.docuseal_sign_url = "https://ds.test/s/x"
        action = self.cert.action_open_sign_url()
        self.assertEqual(action["type"], "ir.actions.act_url")

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

    # ----- partner helpers -----
    def test_partner_count_and_action(self):
        self.partner.invalidate_recordset()
        self.assertEqual(self.partner.exemption_certificate_count, 1)
        action = self.partner.action_view_exemption_certificates()
        self.assertEqual(action["res_model"], "l10n.us.tax.exemption.certificate")

    def test_has_valid_exemption_on_partner(self):
        self.cert._register_signed_document(b"%PDF", "c.pdf")
        self.partner.invalidate_recordset()
        self.assertTrue(self.partner.has_valid_exemption)
        found = self.env["res.partner"].search(
            [("has_valid_exemption", "=", True)]
        )
        self.assertIn(self.partner, found)
        missing = self.env["res.partner"].search(
            [("has_valid_exemption", "!=", True)]
        )
        self.assertNotIn(self.partner, missing)


class TestDocusealClient(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.client = cls.env["docuseal.client"]
        cls.params = cls.env["ir.config_parameter"].sudo()
        cls.params.set_param("l10n_us_sales_tax_docuseal.url", "https://ds.test/")
        cls.params.set_param("l10n_us_sales_tax_docuseal.api_token", "tok")

    def test_missing_config_raises(self):
        self.params.set_param("l10n_us_sales_tax_docuseal.url", "")
        with self.assertRaises(UserError):
            self.client.docuseal_get_submission(1)

    def test_create_submission_builds_request(self):
        fake = mock.Mock(status_code=200, content=b"[{}]")
        fake.json.return_value = [{"submission_id": 1}]
        with mock.patch("%s.requests.request" % CLIENT_MOD, return_value=fake) as rq:
            out = self.client.docuseal_create_submission(
                7, [{"role": "Signer", "email": "a@b.c"}], send_email=False
            )
        self.assertEqual(out, [{"submission_id": 1}])
        args, kwargs = rq.call_args
        self.assertEqual(args[0], "POST")
        self.assertEqual(args[1], "https://ds.test/api/submissions")
        self.assertEqual(kwargs["json"]["template_id"], 7)
        self.assertEqual(kwargs["headers"]["X-Auth-Token"], "tok")

    def test_request_error_raises_usererror(self):
        with mock.patch(
            "%s.requests.request" % CLIENT_MOD,
            side_effect=requests.exceptions.ConnectionError("boom"),
        ):
            with self.assertRaises(UserError):
                self.client.docuseal_get_submission(1)

    def test_archive_submission(self):
        fake = mock.Mock(status_code=200, content=b"{}")
        fake.json.return_value = {}
        with mock.patch("%s.requests.request" % CLIENT_MOD, return_value=fake) as rq:
            self.client.docuseal_archive_submission(9)
        self.assertEqual(rq.call_args[0][0], "DELETE")

    def test_download_ok_and_error(self):
        fake = mock.Mock(status_code=200, content=b"PDFDATA")
        with mock.patch("%s.requests.get" % CLIENT_MOD, return_value=fake):
            self.assertEqual(
                self.client.docuseal_download("https://ds.test/x.pdf"), b"PDFDATA"
            )
        with mock.patch(
            "%s.requests.get" % CLIENT_MOD,
            side_effect=requests.exceptions.Timeout("t"),
        ):
            with self.assertRaises(UserError):
                self.client.docuseal_download("https://ds.test/x.pdf")

    def test_signature_verification(self):
        # No secret -> disabled (always True)
        self.params.set_param("l10n_us_sales_tax_docuseal.webhook_secret", "")
        self.assertTrue(self.client.docuseal_verify_signature(b"body", None))
        self.params.set_param(
            "l10n_us_sales_tax_docuseal.webhook_secret", "s3cr3t"
        )
        sig = hmac.new(b"s3cr3t", b"body", hashlib.sha256).hexdigest()
        self.assertTrue(self.client.docuseal_verify_signature(b"body", sig))
        self.assertFalse(self.client.docuseal_verify_signature(b"body", "bad"))
        self.assertFalse(self.client.docuseal_verify_signature(b"body", None))
