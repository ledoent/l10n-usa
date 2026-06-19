# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from datetime import date

from odoo import fields, models


class L10nUs1099Generate(models.TransientModel):
    _name = "l10n.us.1099.generate"
    _description = "Generate 1099 Report"

    year = fields.Integer(
        required=True, default=lambda self: date.today().year - 1
    )
    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )

    def action_generate(self):
        self.ensure_one()
        Line = self.env["l10n.us.1099.line"]
        Box = self.env["l10n.us.1099.box"]
        Line.search(
            [("company_id", "=", self.company_id.id), ("year", "=", self.year)]
        ).unlink()
        buckets = self.env["l10n.us.1099.engine"]._collect(
            self.company_id, self.year
        )
        vals_list = []
        for (partner_id, box_id), amount in buckets.items():
            threshold = Box.browse(box_id)._threshold_for_year(self.year)
            vals_list.append(
                {
                    "company_id": self.company_id.id,
                    "year": self.year,
                    "partner_id": partner_id,
                    "box_id": box_id,
                    "amount": amount,
                    "threshold": threshold,
                    "reportable": amount > 0 and amount >= threshold,
                }
            )
        Line.create(vals_list)
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("1099 Report %s", self.year),
            "res_model": "l10n.us.1099.line",
            "view_mode": "list,form",
            "domain": [
                ("company_id", "=", self.company_id.id),
                ("year", "=", self.year),
            ],
            "context": {"search_default_reportable": 1},
        }
