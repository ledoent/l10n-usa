# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import json
import logging

from odoo import http
from odoo.http import request

from ..models.us_tax_exemption import FIELD_NUMBER, FIELD_STATE, FIELD_TYPE

_logger = logging.getLogger(__name__)

_COMPLETED_EVENTS = ("form.completed", "submission.completed")


class DocusealWebhookController(http.Controller):
    @http.route(
        "/docuseal/webhook",
        type="http",
        auth="public",
        methods=["POST"],
        csrf=False,
    )
    def docuseal_webhook(self, **kwargs):
        raw = request.httprequest.get_data()
        signature = request.httprequest.headers.get("X-Docuseal-Signature")
        client = request.env["docuseal.client"].sudo()

        if not client.docuseal_verify_signature(raw, signature):
            _logger.warning("DocuSeal webhook signature verification failed")
            return request.make_response("invalid signature", status=401)

        try:
            payload = json.loads(raw or b"{}")
        except ValueError:
            return request.make_response("bad json", status=400)

        if payload.get("event_type") not in _COMPLETED_EVENTS:
            return request.make_response("ignored", status=200)

        data = payload.get("data") or {}
        exemptions = request.env["us.tax.exemption"].sudo()
        requested = self._resolve_request(exemptions, data)
        if not requested:
            _logger.info("DocuSeal completion could not be matched to a request.")
            return request.make_response("unknown submission", status=200)

        self._record(client, requested, data)
        return request.make_response("ok", status=200)

    @staticmethod
    def _resolve_request(exemptions, data):
        """The certificate this completed form was sent for.

        ``external_id`` is stamped on the submitter when the request goes out,
        so the common path needs no API round-trip. The submission id is the
        fallback for a form started outside Odoo.
        """
        external_id = data.get("external_id")
        if external_id:
            # Not necessarily ours — a submission created outside Odoo can
            # carry anything here, and raising would answer 500 and start a
            # days-long retry of a payload that will never match.
            try:
                record = exemptions.browse(int(external_id)).exists()
            except (TypeError, ValueError):
                record = exemptions
            if record:
                return record
        submission_id = str(data.get("submission_id") or data.get("id") or "")
        if submission_id:
            return exemptions.search(
                [("docuseal_submission_id", "=", submission_id)], limit=1
            )
        return exemptions

    def _record(self, client, requested, data):
        """Turn a completed form into a certificate on file."""
        values = request.env["us.tax.exemption"]._docuseal_values(data)
        document, filename = self._fetch_document(client, data)

        certificate = (
            request.env["us.tax.exemption"]
            .sudo()
            .with_company(requested.company_id)
            ._record_signed_certificate(
                partner=requested.partner_id,
                state_codes=request.env["us.tax.exemption"]._docuseal_state_codes(
                    values.get(FIELD_STATE)
                ),
                reason_code=values.get(FIELD_TYPE),
                certificate_number=values.get(FIELD_NUMBER),
                document=document,
                document_filename=filename,
                company=requested.company_id,
            )
        )
        # Carry the correlation onto whatever record ended up holding the
        # certificate, so a retry of this webhook finds it even if the
        # requested record was superseded in between.
        if certificate and not certificate.docuseal_submission_id:
            certificate.docuseal_submission_id = requested.docuseal_submission_id
        return certificate

    @staticmethod
    def _fetch_document(client, data):
        """The signed PDF, if the payload points at one."""
        documents = data.get("documents") or []
        url = documents[0].get("url") if documents else None
        filename = documents[0].get("name") if documents else None
        if not url:
            return None, None
        try:
            content = client.docuseal_download(url)
        except Exception:  # pragma: no cover - network failure path
            _logger.exception("DocuSeal: could not download the signed document.")
            return None, None
        if filename and not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"
        return content, filename
