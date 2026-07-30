# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import hashlib
import hmac
import logging
import time
from urllib.parse import urlparse

import requests

from odoo import _, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

TIMEOUT = 30
# DocuSeal signs webhooks as "<timestamp>.<hmac>" and rejects stale ones.
SIGNATURE_TOLERANCE = 5 * 60
PARAM_URL = "l10n_us_sales_tax_exemption_docuseal.url"
PARAM_TOKEN = "l10n_us_sales_tax_exemption_docuseal.api_token"
PARAM_TEMPLATE = "l10n_us_sales_tax_exemption_docuseal.template_id"
PARAM_SECRET = "l10n_us_sales_tax_exemption_docuseal.webhook_secret"


class DocusealClient(models.AbstractModel):
    """Thin wrapper around the DocuSeal REST API.

    Configuration lives in ir.config_parameter so the connector is generic and
    holds no Avatax/Kencove-specific coupling.
    """

    _name = "docuseal.client"
    _description = "DocuSeal API Client"

    def _docuseal_param(self, key, required=True):
        value = self.env["ir.config_parameter"].sudo().get_param(key)
        if required and not value:
            raise UserError(
                _(
                    "DocuSeal is not configured. Set the server URL and API "
                    "token in Settings > Accounting > Tax Exemption (DocuSeal)."
                )
            )
        return value and value.strip()

    def _docuseal_base_url(self):
        return self._docuseal_param(PARAM_URL).rstrip("/")

    def _docuseal_headers(self):
        return {
            "X-Auth-Token": self._docuseal_param(PARAM_TOKEN),
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _docuseal_request(self, method, path, payload=None):
        url = f'{self._docuseal_base_url()}/{path.lstrip("/")}'
        try:
            response = requests.request(
                method,
                url,
                headers=self._docuseal_headers(),
                json=payload,
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _logger.exception("DocuSeal request to %s failed", url)
            raise UserError(_("DocuSeal request failed: %s") % err) from err
        return response.json() if response.content else {}

    def docuseal_create_submission(self, template_id, submitters, send_email=True):
        """Create a submission from a template. Returns the API response list."""
        payload = {
            "template_id": int(template_id),
            "send_email": send_email,
            "submitters": submitters,
        }
        return self._docuseal_request("POST", "/api/submissions", payload)

    def docuseal_get_submission(self, submission_id):
        return self._docuseal_request("GET", f"/api/submissions/{submission_id}")

    def docuseal_archive_submission(self, submission_id):
        return self._docuseal_request("DELETE", f"/api/submissions/{submission_id}")

    def docuseal_download(self, url):
        """Download a (signed) document. Uses the auth token in case the URL
        is a proxied/authenticated DocuSeal link.

        The URL originates from the (potentially attacker-supplied) webhook
        payload, so it is restricted to the configured DocuSeal host to avoid
        server-side request forgery.
        """
        base = urlparse(self._docuseal_base_url())
        target = urlparse(url or "")
        if (target.scheme, target.netloc) != (base.scheme, base.netloc):
            raise UserError(
                _("Refusing to download a document from an unexpected host: %s")
                % (target.netloc or url)
            )
        try:
            response = requests.get(
                url,
                headers={"X-Auth-Token": self._docuseal_param(PARAM_TOKEN)},
                timeout=TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            _logger.exception("DocuSeal document download failed: %s", url)
            raise UserError(_("DocuSeal download failed: %s") % err) from err
        return response.content

    def docuseal_verify_signature(self, raw_body, signature):
        """Verify the ``X-Docuseal-Signature`` header against the configured
        webhook secret.

        DocuSeal sends ``"<timestamp>.<hexdigest>"`` where the digest is
        ``HMAC-SHA256(secret, "<timestamp>.<body>")``. Returns True when no
        secret is configured (verification disabled) or when the signature is
        valid and within the freshness tolerance.
        """
        secret = self._docuseal_param(PARAM_SECRET, required=False)
        if not secret:
            return True
        timestamp, separator, digest = (signature or "").strip().partition(".")
        if not separator or not digest:
            return False
        try:
            timestamp_int = int(timestamp)
        except (TypeError, ValueError):
            return False
        if abs(int(time.time()) - timestamp_int) > SIGNATURE_TOLERANCE:
            return False
        signed_payload = f"{timestamp}.".encode() + (raw_body or b"")
        expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, digest)
