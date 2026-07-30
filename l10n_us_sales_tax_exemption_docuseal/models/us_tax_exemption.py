# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import logging

from odoo import fields, models

from .docuseal_client import PARAM_TEMPLATE

_logger = logging.getLogger(__name__)

# Field names on the DocuSeal template. The same three names are read by the
# sign_oca bridge, so one form design serves either signature stack.
FIELD_STATE = "State"
FIELD_TYPE = "Exemption Type"
FIELD_NUMBER = "Exemption Number"


class UsTaxExemption(models.Model):
    _inherit = "us.tax.exemption"

    docuseal_submission_id = fields.Char(
        readonly=True,
        copy=False,
        index=True,
        help="Submission this certificate was requested through.",
    )
    docuseal_sign_url = fields.Char(readonly=True, copy=False)

    def _request_renewal(self):
        """Send the customer a DocuSeal form to sign.

        Only for companies that selected this backend; anything else is passed
        on, so several bridges can be installed at once without one silently
        winning the override.
        """
        mine = self.filtered(
            lambda r: r.company_id.us_tax_exemption_signature_backend == "docuseal"
        )
        rest = self - mine
        requested = bool(rest) and super(UsTaxExemption, rest)._request_renewal()
        if not mine:
            return requested
        client = self.env["docuseal.client"]
        template_id = client._docuseal_param(PARAM_TEMPLATE)
        for rec in mine:
            partner = rec.partner_id
            if not partner.email:
                _logger.warning(
                    "US Tax: %s has no email address; cannot request a "
                    "certificate renewal.",
                    partner.display_name,
                )
                continue
            response = client.docuseal_create_submission(
                template_id=int(template_id),
                submitters=[
                    {
                        "role": "Signer",
                        "email": partner.email,
                        "name": partner.name,
                        # Correlates the completed form back to this record
                        # without a second API call to resolve the submission.
                        "external_id": str(rec.id),
                        "fields": [
                            {"name": "Company", "default_value": partner.name},
                            {"name": "Email", "default_value": partner.email},
                        ],
                    }
                ],
            )
            submitter = response[0] if isinstance(response, list) else response
            rec.write(
                {
                    "docuseal_submission_id": str(
                        submitter.get("submission_id") or submitter.get("id") or ""
                    ),
                    "docuseal_sign_url": (
                        f"{client._docuseal_base_url()}/s/{submitter.get('slug')}"
                        if submitter.get("slug")
                        else False
                    ),
                }
            )
            requested = True
        return requested

    @staticmethod
    def _docuseal_values(data):
        """Flatten a completed submission's answers to ``{field: value}``.

        DocuSeal returns ``values`` as ``[{"field": ..., "value": ...}]`` —
        the key is ``field``, not ``name``, which the ``fields`` array uses.
        """
        return {
            entry.get("field"): entry.get("value")
            for entry in (data.get("values") or [])
            if entry.get("field")
        }

    @classmethod
    def _docuseal_state_codes(cls, raw):
        """Split whatever the signer typed into the State field.

        Free text on a form: "TX, GA" and "TX/GA" both mean two states.
        """
        if not raw:
            return []
        for sep in (",", ";", "/", "|"):
            raw = raw.replace(sep, " ")
        return [part for part in raw.split() if part]
