# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    us_tax_exemption_validity_years = fields.Integer(
        related="company_id.us_tax_exemption_validity_years", readonly=False
    )
    us_tax_exemption_renewal_lead_days = fields.Integer(
        related="company_id.us_tax_exemption_renewal_lead_days", readonly=False
    )
    us_tax_exemption_signature_backend = fields.Selection(
        related="company_id.us_tax_exemption_signature_backend", readonly=False
    )
