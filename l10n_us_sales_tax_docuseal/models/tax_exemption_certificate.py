# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
import logging

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .docuseal_client import PARAM_TEMPLATE, PARAM_URL

_logger = logging.getLogger(__name__)


class L10nUsTaxExemptionCertificate(models.Model):
    _name = "l10n.us.tax.exemption.certificate"
    _description = "US Sales Tax Exemption Certificate"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "expiration_date desc, id desc"
    _rec_name = "name"

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default=lambda self: _("New"),
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        ondelete="cascade",
        tracking=True,
    )
    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
    )
    state_id = fields.Many2one(
        "res.country.state",
        string="Jurisdiction (State)",
        domain="[('country_id.code', '=', 'US')]",
        tracking=True,
        help="US state whose sales tax this certificate exempts.",
    )
    certificate_type = fields.Selection(
        [
            ("resale", "Resale"),
            ("exempt_org", "Exempt Organization"),
            ("government", "Government"),
            ("manufacturing", "Manufacturing"),
            ("agricultural", "Agricultural"),
            ("other", "Other"),
        ],
        default="resale",
        required=True,
        tracking=True,
    )
    exemption_number = fields.Char(
        help="Permit / exemption number printed on the certificate.",
        tracking=True,
    )
    issue_date = fields.Date(tracking=True)
    expiration_date = fields.Date(
        tracking=True,
        help="Leave empty for certificates that do not expire.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("sent", "Sent for Signature"),
            ("signed", "Signed"),
            ("expired", "Expired"),
            ("rejected", "Rejected"),
            ("cancelled", "Cancelled"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    signer_email = fields.Char(tracking=True)
    signer_name = fields.Char()

    # DocuSeal linkage
    docuseal_template_id = fields.Char(
        string="DocuSeal Template",
        help="DocuSeal template id used to generate the signing request. "
        "Defaults to the company-wide template when empty.",
    )
    docuseal_submission_id = fields.Char(
        string="DocuSeal Submission", readonly=True, copy=False, index=True
    )
    docuseal_slug = fields.Char(readonly=True, copy=False)
    docuseal_sign_url = fields.Char(
        string="Signing Link", readonly=True, copy=False
    )

    signed_document = fields.Binary(
        string="Signed Certificate", readonly=True, copy=False, attachment=True
    )
    signed_document_filename = fields.Char(readonly=True, copy=False)

    is_valid = fields.Boolean(
        compute="_compute_is_valid",
        store=True,
        help="Signed and not past its expiration date.",
    )

    @api.depends("state", "expiration_date")
    def _compute_is_valid(self):
        today = fields.Date.context_today(self)
        for cert in self:
            cert.is_valid = cert.state == "signed" and (
                not cert.expiration_date or cert.expiration_date >= today
            )

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("name") or vals["name"] == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code(
                    "l10n.us.tax.exemption.certificate"
                ) or _("New")
        return super().create(vals_list)

    def _docuseal_template(self):
        self.ensure_one()
        template = self.docuseal_template_id or self.env[
            "ir.config_parameter"
        ].sudo().get_param(PARAM_TEMPLATE)
        if not template:
            raise UserError(
                _(
                    "No DocuSeal template configured. Set a default template in "
                    "Settings or pick one on the certificate."
                )
            )
        return template

    def _docuseal_submitter_values(self):
        """Build the submitter payload. Prefills common certificate fields by
        name; unknown field names are simply ignored by DocuSeal."""
        self.ensure_one()
        partner = self.partner_id
        email = self.signer_email or partner.email
        if not email:
            raise UserError(
                _("Customer %s has no email to send the certificate to.")
                % partner.display_name
            )
        prefill = {
            "Company": partner.commercial_company_name or partner.name,
            "Name": self.signer_name or partner.name,
            "Email": email,
            "State": self.state_id.name or "",
            "Exemption Number": self.exemption_number or "",
        }
        return [
            {
                "role": "Signer",
                "email": email,
                "name": self.signer_name or partner.name,
                "fields": [
                    {"name": key, "default_value": value}
                    for key, value in prefill.items()
                    if value
                ],
            }
        ]

    def action_send_for_signature(self):
        client = self.env["docuseal.client"]
        for cert in self:
            if cert.state not in ("draft", "rejected", "expired"):
                raise UserError(
                    _("Only draft certificates can be sent for signature.")
                )
            response = client.docuseal_create_submission(
                cert._docuseal_template(),
                cert._docuseal_submitter_values(),
                send_email=True,
            )
            submitter = response[0] if isinstance(response, list) else response
            base_url = self.env["ir.config_parameter"].sudo().get_param(
                PARAM_URL
            )
            slug = submitter.get("slug")
            cert.write(
                {
                    "state": "sent",
                    "docuseal_submission_id": str(
                        submitter.get("submission_id") or ""
                    ),
                    "docuseal_slug": slug,
                    "docuseal_sign_url": slug
                    and "%s/s/%s" % (base_url.rstrip("/"), slug),
                    "signer_email": submitter.get("email") or cert.signer_email,
                }
            )
            cert.message_post(
                body=_("Exemption certificate sent for signature via DocuSeal.")
            )
        return True

    def _register_signed_document(self, content, filename=None):
        """Called from the webhook controller once the document is signed."""
        self.ensure_one()
        self.write(
            {
                "state": "signed",
                "signed_document": base64.b64encode(content),
                "signed_document_filename": filename
                or ("%s.pdf" % self.name),
                "issue_date": self.issue_date
                or fields.Date.context_today(self),
            }
        )
        self.message_post(
            body=_("Signed certificate received from DocuSeal."),
            attachments=[
                (filename or ("%s.pdf" % self.name), content)
            ],
        )

    def action_mark_rejected(self):
        self.write({"state": "rejected"})

    def action_cancel(self):
        client = self.env["docuseal.client"]
        for cert in self:
            if cert.docuseal_submission_id and cert.state == "sent":
                try:
                    client.docuseal_archive_submission(
                        cert.docuseal_submission_id
                    )
                except UserError:
                    _logger.warning(
                        "Could not archive DocuSeal submission %s",
                        cert.docuseal_submission_id,
                    )
        self.write({"state": "cancelled"})

    def action_reset_to_draft(self):
        self.write({"state": "draft"})

    def action_open_sign_url(self):
        self.ensure_one()
        if not self.docuseal_sign_url:
            raise UserError(_("This certificate has no DocuSeal signing link."))
        return {
            "type": "ir.actions.act_url",
            "url": self.docuseal_sign_url,
            "target": "new",
        }

    @api.model
    def _cron_expire_certificates(self):
        today = fields.Date.context_today(self)
        expired = self.search(
            [
                ("state", "=", "signed"),
                ("expiration_date", "!=", False),
                ("expiration_date", "<", today),
            ]
        )
        expired.write({"state": "expired"})
        return True
