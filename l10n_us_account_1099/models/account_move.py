# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class AccountMove(models.Model):
    _inherit = "account.move"

    us_1099_excluded = fields.Boolean(
        string="Exclude from 1099",
        tracking=True,
        help="Exclude this bill from 1099 totals -- e.g. paid by credit card "
        "or a third-party network (PayPal/Stripe), which the processor reports "
        "on Form 1099-K.",
    )
