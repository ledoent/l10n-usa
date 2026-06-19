# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    exemption_certificate_ids = fields.One2many(
        "l10n.us.tax.exemption.certificate",
        "partner_id",
        string="Exemption Certificates",
    )
    exemption_certificate_count = fields.Integer(
        compute="_compute_exemption_certificate_count"
    )
    has_valid_exemption = fields.Boolean(
        compute="_compute_has_valid_exemption",
        search="_search_has_valid_exemption",
        string="Has Valid Exemption",
    )

    @api.depends("exemption_certificate_ids")
    def _compute_exemption_certificate_count(self):
        data = self.env["l10n.us.tax.exemption.certificate"]._read_group(
            [("partner_id", "in", self.ids)],
            groupby=["partner_id"],
            aggregates=["__count"],
        )
        mapped = {partner.id: count for partner, count in data}
        for partner in self:
            partner.exemption_certificate_count = mapped.get(partner.id, 0)

    @api.depends("exemption_certificate_ids.is_valid")
    def _compute_has_valid_exemption(self):
        for partner in self:
            partner.has_valid_exemption = any(
                partner.exemption_certificate_ids.mapped("is_valid")
            )

    def _search_has_valid_exemption(self, operator, value):
        valid = self.env["l10n.us.tax.exemption.certificate"].search(
            [("is_valid", "=", True)]
        )
        partner_ids = valid.mapped("partner_id").ids
        positive = (operator == "=" and value) or (
            operator == "!=" and not value
        )
        return [("id", "in" if positive else "not in", partner_ids)]

    def action_view_exemption_certificates(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Exemption Certificates"),
            "res_model": "l10n.us.tax.exemption.certificate",
            "view_mode": "list,form",
            "domain": [("partner_id", "=", self.id)],
            "context": {"default_partner_id": self.id},
        }
