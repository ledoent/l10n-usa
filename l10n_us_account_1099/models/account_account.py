# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import api, fields, models


class AccountAccount(models.Model):
    _inherit = "account.account"

    us_1099_box_id = fields.Many2one(
        "l10n.us.1099.box",
        string="1099 Box",
        help="Payments booked to this account are reported in this 1099 box "
        "(this account represents the payment category, e.g. rent, services).",
    )
    us_1099_corporate_reportable = fields.Boolean(
        string="1099 Reportable to Corporations",
        help="Report payments on this account even when the payee is a "
        "corporation (e.g. legal/attorney fees, medical & health-care).",
    )

    @api.onchange("us_1099_box_id")
    def _onchange_us_1099_box_id(self):
        if self.us_1099_box_id:
            self.us_1099_corporate_reportable = (
                self.us_1099_box_id.applies_to_corporations
            )
