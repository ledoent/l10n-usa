# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

# DocuSeal completion events that should attach the signed document.
_COMPLETED_EVENTS = ("form.completed", "submission.completed")
_DECLINED_EVENTS = ("form.declined", "submission.expired")


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

        event = payload.get("event_type")
        data = payload.get("data") or {}
        submission_id = str(data.get("submission_id") or data.get("id") or "")
        if not submission_id:
            return request.make_response("ignored", status=200)

        cert = (
            request.env["l10n.us.tax.exemption.certificate"]
            .sudo()
            .search([("docuseal_submission_id", "=", submission_id)], limit=1)
        )
        if not cert:
            _logger.info(
                "DocuSeal webhook for unknown submission %s", submission_id
            )
            return request.make_response("unknown submission", status=200)

        if event in _COMPLETED_EVENTS:
            self._handle_completed(client, cert, data)
        elif event in _DECLINED_EVENTS:
            cert.action_mark_rejected()

        return request.make_response("ok", status=200)

    def _handle_completed(self, client, cert, data):
        documents = data.get("documents") or []
        url = None
        filename = None
        if documents:
            url = documents[0].get("url")
            filename = documents[0].get("name")
        if not url:
            # Fall back to fetching the combined document from the API.
            submission = client.docuseal_get_submission(
                cert.docuseal_submission_id
            )
            url = submission.get("combined_document_url") or (
                (submission.get("documents") or [{}])[0].get("url")
            )
        if not url:
            _logger.warning(
                "DocuSeal completion for %s carried no document url", cert.name
            )
            return
        content = client.docuseal_download(url)
        if filename and not filename.lower().endswith(".pdf"):
            filename = "%s.pdf" % filename
        cert._register_signed_document(content, filename=filename)
