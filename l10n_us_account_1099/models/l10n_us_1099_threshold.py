# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class L10nUs1099Threshold(models.Model):
    _name = "l10n.us.1099.threshold"
    _description = "1099 Reporting Threshold"
    _order = "box_id, date_from desc"

    box_id = fields.Many2one(
        "l10n.us.1099.box", required=True, ondelete="cascade"
    )
    date_from = fields.Date(
        required=True,
        help="Threshold applies to payments made on or after this date.",
    )
    amount = fields.Float(
        required=True,
        help="Minimum aggregate payment (per payee per year) that triggers "
        "reporting for this box.",
    )
