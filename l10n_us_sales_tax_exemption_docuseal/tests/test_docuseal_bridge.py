# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib
import hmac
import json
import time
from datetime import date
from unittest.mock import patch

from odoo.tests import HttpCase, tagged

SECRET = "test-webhook-secret"
CLIENT = "odoo.addons.l10n_us_sales_tax_exemption_docuseal.models.docuseal_client"


@tagged("post_install", "-at_install")
class TestDocusealBridge(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env.company.us_tax_exemption_signature_backend = "docuseal"
        ICP = cls.env["ir.config_parameter"].sudo()
        ICP.set_param("l10n_us_sales_tax_exemption_docuseal.url", "https://sign.test")
        ICP.set_param("l10n_us_sales_tax_exemption_docuseal.api_token", "tok")
        ICP.set_param("l10n_us_sales_tax_exemption_docuseal.template_id", "7")
        ICP.set_param("l10n_us_sales_tax_exemption_docuseal.webhook_secret", SECRET)

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
                "zip": "82001",
                "state_id": cls.wy.id,
                "country_id": cls.us.id,
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

    # ── helpers ──────────────────────────────────────────────────────────────

    def _payload(self, number="WY-NEW-1", states="WY, GA", kind="resale"):
        """A form.completed delivery shaped like DocuSeal's.

        Note ``values`` entries key on ``field``, not ``name`` — the ``fields``
        array used when creating a submission uses ``name``, and conflating the
        two is how the answers get silently dropped.
        """
        return {
            "event_type": "form.completed",
            "timestamp": "2026-07-29T12:00:00Z",
            "data": {
                "id": 4242,
                "submission_id": 99,
                "external_id": str(self.cert.id),
                "email": self.partner.email,
                "status": "completed",
                "values": [
                    {"field": "State", "value": states},
                    {"field": "Exemption Type", "value": kind},
                    {"field": "Exemption Number", "value": number},
                ],
                "documents": [],
            },
        }

    def _post(self, payload, sign=True, stamp=None):
        raw = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json"}
        if sign:
            stamp = stamp or int(time.time())
            digest = hmac.new(
                SECRET.encode(), f"{stamp}.".encode() + raw, hashlib.sha256
            ).hexdigest()
            headers["X-Docuseal-Signature"] = f"{stamp}.{digest}"
        return self.url_open("/docuseal/webhook", data=raw, headers=headers)

    def _captured(self, number="WY-NEW-1"):
        return self.env["us.tax.exemption"].search(
            [("partner_id", "=", self.partner.id), ("certificate_number", "=", number)]
        )

    # ── the gap this bridge closes ───────────────────────────────────────────

    def test_a_completed_form_populates_the_certificate(self):
        """The point of the bridge: the answers become data, not just a PDF."""
        self.assertEqual(self._post(self._payload()).status_code, 200)
        cert = self._captured()
        self.assertEqual(len(cert), 1)
        self.assertEqual(cert.reason_id, self.resale)
        self.assertEqual(set(cert.state_ids.ids), set((self.wy + self.ga).ids))
        self.assertEqual(cert.certificate_number, "WY-NEW-1")

    def test_a_captured_certificate_is_not_yet_effective(self):
        """A signature is not an approval — somebody still has to accept it."""
        self._post(self._payload())
        self.assertEqual(self._captured().state, "signed")

    def test_a_retried_delivery_does_not_duplicate(self):
        """DocuSeal retries a failed delivery twelve times, over ~5 days."""
        payload = self._payload()
        for _attempt in range(3):
            self.assertEqual(self._post(payload).status_code, 200)
        self.assertEqual(len(self._captured()), 1)

    def test_an_unsigned_delivery_is_refused(self):
        self.assertEqual(self._post(self._payload(), sign=False).status_code, 401)
        self.assertFalse(self._captured())

    def test_a_replayed_old_signature_is_refused(self):
        """A valid signature stays valid forever without the timestamp check."""
        stale = int(time.time()) - 3600
        self.assertEqual(self._post(self._payload(), stamp=stale).status_code, 401)
        self.assertFalse(self._captured())

    def test_an_unreadable_answer_is_kept_as_a_draft(self):
        """Better a visible draft than a silently discarded certificate."""
        self._post(self._payload(kind="not-a-known-reason"))
        cert = self._captured()
        self.assertEqual(len(cert), 1)
        self.assertEqual(cert.state, "draft")
        self.assertFalse(cert.reason_id)

    def test_an_unmatched_submission_is_acknowledged_not_retried(self):
        """A 500 here would put DocuSeal into a days-long retry loop."""
        payload = self._payload()
        payload["data"]["external_id"] = "999999"
        payload["data"]["submission_id"] = "no-such"
        self.assertEqual(self._post(payload).status_code, 200)

    def test_a_foreign_external_id_does_not_crash(self):
        """A submission created outside Odoo can carry anything here."""
        payload = self._payload()
        payload["data"]["external_id"] = "crm-lead-8842"
        payload["data"]["submission_id"] = "no-such"
        self.assertEqual(self._post(payload).status_code, 200)
        self.assertFalse(self._captured())

    def test_other_events_are_ignored(self):
        payload = self._payload()
        payload["event_type"] = "form.viewed"
        self.assertEqual(self._post(payload).status_code, 200)
        self.assertFalse(self._captured())

    # ── the outbound half ────────────────────────────────────────────────────

    def test_requesting_a_renewal_correlates_by_external_id(self):
        """external_id carries the record id, so completion needs no lookup."""
        sent = {}

        def _fake(self_client, method, path, payload=None):
            sent.update({"method": method, "path": path, "payload": payload})
            return [{"id": 1, "submission_id": 500, "slug": "abc123"}]

        with patch(f"{CLIENT}.DocusealClient._docuseal_request", _fake):
            self.cert._request_renewal()

        self.assertEqual(sent["path"], "/api/submissions")
        submitter = sent["payload"]["submitters"][0]
        self.assertEqual(submitter["external_id"], str(self.cert.id))
        self.assertEqual(submitter["email"], self.partner.email)
        self.assertEqual(self.cert.docuseal_submission_id, "500")
        self.assertEqual(self.cert.docuseal_sign_url, "https://sign.test/s/abc123")

    def test_another_backend_is_passed_through(self):
        """The routing that lets two bridges coexist.

        With a different backend selected this module must decline the record
        rather than handle it, or whichever bridge loaded last would silently
        own every company.
        """
        self.env.company.us_tax_exemption_signature_backend = "none"
        with patch(f"{CLIENT}.DocusealClient._docuseal_request") as called:
            self.assertFalse(self.cert._request_renewal())
        called.assert_not_called()

    def test_a_customer_without_an_email_is_skipped_not_crashed(self):
        """One unreachable customer must not stop the renewal cron."""
        self.partner.email = False
        with patch(f"{CLIENT}.DocusealClient._docuseal_request") as called:
            self.cert._request_renewal()
        called.assert_not_called()

    # ── parsing ──────────────────────────────────────────────────────────────

    def test_state_field_accepts_what_people_actually_type(self):
        parse = self.env["us.tax.exemption"]._docuseal_state_codes
        for raw in ("TX, GA", "TX/GA", "TX GA", "TX;GA"):
            self.assertEqual(parse(raw), ["TX", "GA"], raw)
        self.assertEqual(parse(""), [])
        self.assertEqual(parse(None), [])
