# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import _, fields, models
from odoo.exceptions import UserError


class ResPartner(models.Model):
    _inherit = "res.partner"

    property_record_ids = fields.One2many(
        "property.record", "partner_id", string="Properties"
    )
    property_record_count = fields.Integer(compute="_compute_property_record_count")

    def _compute_property_record_count(self):
        data = self.env["property.record"]._read_group(
            [("partner_id", "in", self.ids)],
            groupby=["partner_id"],
            aggregates=["__count"],
        )
        counts = {partner.id: count for partner, count in data}
        for partner in self:
            partner.property_record_count = counts.get(partner.id, 0)

    def action_fetch_property_data(self):
        """Create/refresh a property record for this partner's address."""
        self.ensure_one()
        if not (self.street or self.zip or self.city):
            raise UserError(_("This contact has no address to look up a property for."))
        record = self.property_record_ids[:1]
        if not record:
            record = self.env["property.record"].create({"partner_id": self.id})
        # Reuse action_resolve so the partner button inherits the same
        # no-source / skipped-source feedback as the record's own button.
        record.action_resolve()
        return {
            "type": "ir.actions.act_window",
            "res_model": "property.record",
            "res_id": record.id,
            "view_mode": "form",
            "target": "current",
        }

    def action_view_property_records(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Properties"),
            "res_model": "property.record",
            "domain": [("partner_id", "=", self.id)],
            "view_mode": "list,form",
            "context": {"default_partner_id": self.id},
        }
