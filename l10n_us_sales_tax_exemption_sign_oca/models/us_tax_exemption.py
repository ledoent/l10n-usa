# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import fields, models

_logger = logging.getLogger(__name__)

# The same three names the DocuSeal bridge reads, so one form design carries
# across either signature stack.
FIELD_STATE = "State"
FIELD_TYPE = "Exemption Type"
FIELD_NUMBER = "Exemption Number"


class UsTaxExemption(models.Model):
    _inherit = "us.tax.exemption"

    sign_request_id = fields.Many2one(
        "sign.oca.request",
        string="Signature Request",
        readonly=True,
        copy=False,
        help="Request this certificate was asked for through.",
    )

    def _request_renewal(self):
        """Send the customer a sign_oca request for a replacement.

        Only for companies that selected this backend; anything else is passed
        on, so several bridges can be installed at once without one silently
        winning the override.
        """
        mine = self.filtered(
            lambda r: r.company_id.us_tax_exemption_signature_backend == "sign_oca"
        )
        rest = self - mine
        requested = bool(rest) and super(UsTaxExemption, rest)._request_renewal()
        for rec in mine:
            template = rec.company_id.us_tax_exemption_sign_template_id
            if not template:
                _logger.warning(
                    "US Tax: %s has no exemption certificate signature "
                    "template configured; cannot request a renewal.",
                    rec.company_id.display_name,
                )
                continue
            request = self.env["sign.oca.request"].create(
                template._prepare_sign_oca_request_vals_from_record(rec)
            )
            request.action_send()
            rec.sign_request_id = request
            requested = True
        return requested

    @staticmethod
    def _sign_oca_state_codes(raw):
        """Split whatever the signer put in the State field.

        Free text on a form: "TX, GA" and "TX/GA" both mean two states.
        """
        if not raw:
            return []
        for sep in (",", ";", "/", "|"):
            raw = raw.replace(sep, " ")
        return [part for part in raw.split() if part]
