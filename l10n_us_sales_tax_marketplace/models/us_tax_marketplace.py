# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxMarketplace(models.Model):
    _name = "us.tax.marketplace"
    _description = "US Sales Tax Marketplace Facilitator"
    _order = "name"

    name = fields.Char(required=True, translate=True)
    code = fields.Char(
        required=True, help="Stable code recorded on marketplace-collected sales."
    )
    active = fields.Boolean(default=True)
    notes = fields.Text()

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "The marketplace code must be unique."),
    ]
