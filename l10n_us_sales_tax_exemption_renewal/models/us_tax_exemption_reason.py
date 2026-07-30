# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class UsTaxExemptionReason(models.Model):
    _inherit = "us.tax.exemption.reason"

    validity_years = fields.Integer(
        help="Default term for certificates issued under this reason. A rule "
        "for a specific state overrides it; left at zero, the company default "
        "applies.",
    )
    never_expires = fields.Boolean(
        help="Certificates for this reason are issued without an expiry date "
        "and are never picked up for renewal. Government and direct-pay "
        "authorities are often open-ended.",
    )
