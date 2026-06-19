# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib
import hmac
import json
import time
from unittest import mock

from odoo.tests.common import HttpCase, tagged

CLIENT_CLS = (
    "odoo.addons.l10n_us_sales_tax_docuseal.models."
    "docuseal_client.DocusealClient"
)


@tagged("post_install", "-at_install")
class TestWebhookController(HttpCase):
    def setUp(self):
        super().setUp()
        self.params = self.env["ir.config_parameter"].sudo()
        self.params.set_param("l10n_us_sales_tax_docuseal.webhook_secret", "")
        self.partner = self.env["res.partner"].create(
            {"name": "Reseller", "email": "r@e.test"}
        )
        self.cert = self.env["l10n.us.tax.exemption.certificate"].create(
            {
                "partner_id": self.partner.id,
                "state": "sent",
                "docuseal_submission_id": "777",
            }
        )
        self.env.flush_all()

    def _post(self, payload, headers=None):
        body = json.dumps(payload)
        return self.url_open(
            "/docuseal/webhook",
            data=body.encode(),
            headers={"Content-Type": "application/json", **(headers or {})},
        )

    def test_completed_files_document(self):
        payload = {
            "event_type": "form.completed",
            "data": {
                "submission_id": 777,
                "documents": [{"name": "cert", "url": "https://ds.test/c.pdf"}],
            },
        }
        with mock.patch(
            "%s.docuseal_download" % CLIENT_CLS, return_value=b"%PDF-1.4"
        ):
            resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)
        self.cert.invalidate_recordset()
        self.assertEqual(self.cert.state, "signed")
        self.assertTrue(self.cert.signed_document)

    def test_completed_fallback_to_api(self):
        # No documents in payload -> controller fetches via the API.
        payload = {
            "event_type": "form.completed",
            "data": {"submission_id": 777},
        }
        with mock.patch(
            "%s.docuseal_get_submission" % CLIENT_CLS,
            return_value={"combined_document_url": "https://ds.test/c.pdf"},
        ), mock.patch(
            "%s.docuseal_download" % CLIENT_CLS, return_value=b"%PDF"
        ):
            resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)
        self.cert.invalidate_recordset()
        self.assertEqual(self.cert.state, "signed")

    def test_bad_json_returns_400(self):
        resp = self.url_open(
            "/docuseal/webhook",
            data=b"not-json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_declined_marks_rejected(self):
        payload = {"event_type": "form.declined", "data": {"submission_id": 777}}
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)
        self.cert.invalidate_recordset()
        self.assertEqual(self.cert.state, "rejected")

    def test_unknown_submission_ignored(self):
        payload = {"event_type": "form.completed", "data": {"submission_id": 0}}
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)

    def test_unknown_certificate_ignored(self):
        # Valid submission id with no matching certificate.
        payload = {
            "event_type": "form.completed",
            "data": {"submission_id": 999999},
        }
        resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)

    def test_completed_without_document_url(self):
        payload = {
            "event_type": "form.completed",
            "data": {"submission_id": 777},
        }
        with mock.patch(
            "%s.docuseal_get_submission" % CLIENT_CLS, return_value={}
        ):
            resp = self._post(payload)
        self.assertEqual(resp.status_code, 200)
        self.cert.invalidate_recordset()
        self.assertEqual(self.cert.state, "sent")

    def test_bad_signature_rejected(self):
        self.params.set_param(
            "l10n_us_sales_tax_docuseal.webhook_secret", "topsecret"
        )
        self.env.flush_all()
        payload = {"event_type": "form.completed", "data": {"submission_id": 777}}
        resp = self._post(payload, headers={"X-Docuseal-Signature": "wrong"})
        self.assertEqual(resp.status_code, 401)

    def test_good_signature_accepted(self):
        self.params.set_param(
            "l10n_us_sales_tax_docuseal.webhook_secret", "topsecret"
        )
        self.env.flush_all()
        payload = {
            "event_type": "form.completed",
            "data": {
                "submission_id": 777,
                "documents": [{"name": "c", "url": "https://ds.test/c.pdf"}],
            },
        }
        body = json.dumps(payload).encode()
        ts = int(time.time())
        digest = hmac.new(
            b"topsecret", ("%d." % ts).encode() + body, hashlib.sha256
        ).hexdigest()
        sig = "%d.%s" % (ts, digest)
        with mock.patch(
            "%s.docuseal_download" % CLIENT_CLS, return_value=b"%PDF"
        ):
            resp = self.url_open(
                "/docuseal/webhook",
                data=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Docuseal-Signature": sig,
                },
            )
        self.assertEqual(resp.status_code, 200)
        self.cert.invalidate_recordset()
        self.assertEqual(self.cert.state, "signed")
