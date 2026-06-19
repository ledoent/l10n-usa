# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models
from odoo.exceptions import ValidationError


class UsTaxExemption(models.Model):
    _name = "us.tax.exemption"
    _description = "US Sales Tax Exemption Certificate"
    _inherit = ["mail.thread"]
    _order = "partner_id, effective_date desc"

    name = fields.Char(compute="_compute_name", store=True)
    partner_id = fields.Many2one(
        "res.partner",
        string="Customer",
        required=True,
        index=True,
        tracking=True,
        help="Commercial entity the certificate is held for.",
    )
    reason_id = fields.Many2one(
        "us.tax.exemption.reason",
        string="Exemption Reason",
        required=True,
        tracking=True,
    )
    state_ids = fields.Many2many(
        "res.country.state",
        string="Covered States",
        required=True,
        domain=[("country_id.code", "=", "US")],
        help="States the certificate exempts the customer in. A blanket "
        "certificate covers several states.",
    )
    certificate_number = fields.Char(tracking=True)
    effective_date = fields.Date(default=fields.Date.context_today, required=True)
    expiry_date = fields.Date(
        help="Leave empty if the certificate does not expire.",
    )
    state = fields.Selection(
        [
            ("draft", "Draft"),
            ("valid", "Valid"),
            ("expired", "Expired"),
            ("revoked", "Revoked"),
        ],
        default="draft",
        required=True,
        tracking=True,
    )
    is_blanket = fields.Boolean(
        string="Blanket Certificate",
        default=True,
        help="Covers ongoing/future purchases (vs a single transaction). "
        "Advisory metadata in this version — exemption applies whenever the "
        "certificate is valid regardless of this flag.",
    )
    document = fields.Binary(string="Signed Certificate", attachment=True)
    document_filename = fields.Char()
    company_id = fields.Many2one("res.company", default=lambda s: s.env.company)
    notes = fields.Text()

    @api.depends("partner_id", "reason_id", "effective_date")
    def _compute_name(self):
        for rec in self:
            parts = [rec.partner_id.display_name or "", rec.reason_id.name or ""]
            rec.name = " — ".join(p for p in parts if p) or self.env._("New Exemption")

    @api.constrains("effective_date", "expiry_date")
    def _check_dates(self):
        for rec in self:
            if (
                rec.expiry_date
                and rec.effective_date
                and rec.effective_date > rec.expiry_date
            ):
                raise ValidationError(
                    self.env._("Effective date must be on or before the expiry date.")
                )

    # ── Actions ─────────────────────────────────────────────────────────────---

    def action_validate(self):
        self.write({"state": "valid"})

    def action_revoke(self):
        self.write({"state": "revoked"})

    def action_reset_draft(self):
        self.write({"state": "draft"})

    @api.model
    def _cron_expire_certificates(self):
        """Flip valid certificates whose expiry has passed to 'expired'."""
        today = fields.Date.context_today(self)
        expired = self.search(
            [
                ("state", "=", "valid"),
                ("expiry_date", "!=", False),
                ("expiry_date", "<", today),
            ]
        )
        expired.write({"state": "expired"})
        return len(expired)
