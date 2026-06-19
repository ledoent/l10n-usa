# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
import base64
import csv
import io

from odoo import fields, models


class L10nUs1099Line(models.Model):
    _name = "l10n.us.1099.line"
    _description = "1099 Reporting Line"
    _order = "year desc, partner_id, box_id"

    company_id = fields.Many2one(
        "res.company", required=True, default=lambda self: self.env.company
    )
    currency_id = fields.Many2one(related="company_id.currency_id")
    year = fields.Integer(required=True, index=True)
    partner_id = fields.Many2one("res.partner", required=True, ondelete="cascade")
    box_id = fields.Many2one("l10n.us.1099.box", required=True)
    form = fields.Selection(related="box_id.form", store=True)
    amount = fields.Monetary()
    threshold = fields.Float()
    reportable = fields.Boolean(
        help="Aggregate amount meets the box threshold and is reportable."
    )
    tin_type = fields.Selection(related="partner_id.us_1099_tin_type")
    tin = fields.Char(related="partner_id.vat", string="TIN")
    w9_received = fields.Boolean(related="partner_id.us_1099_w9_received")

    def _build_csv(self):
        """Render the reportable lines as an IRIS-style CSV string."""
        forms = dict(self.env["l10n.us.1099.box"]._fields["form"].selection)
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(
            ["Payee", "TIN Type", "TIN", "Form", "Box", "Description", "Amount"]
        )
        reportable = self.filtered("reportable").sorted(
            lambda line: (line.partner_id.display_name, line.form, line.box_id.code)
        )
        for line in reportable:
            writer.writerow(
                [
                    line.partner_id.display_name,
                    (line.tin_type or "").upper(),
                    line.tin or "",
                    forms.get(line.form, line.form or ""),
                    line.box_id.code,
                    line.box_id.name,
                    "%.2f" % line.amount,
                ]
            )
        return buffer.getvalue()

    def action_export_csv(self):
        content = self._build_csv()
        year = self[:1].year or fields.Date.today().year
        export = self.env["l10n.us.1099.export"].create(
            {
                "filename": "1099_%s.csv" % year,
                "data": base64.b64encode(content.encode()),
            }
        )
        return {
            "type": "ir.actions.act_window",
            "name": self.env._("Export 1099 CSV"),
            "res_model": "l10n.us.1099.export",
            "res_id": export.id,
            "view_mode": "form",
            "target": "new",
        }
