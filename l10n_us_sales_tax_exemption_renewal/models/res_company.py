# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    us_tax_exemption_validity_years = fields.Integer(
        string="Exemption Validity (years)",
        default=3,
        help="Term applied to a certificate when neither the state nor the "
        "reason carries its own rule. Two to four years is typical.",
    )
    us_tax_exemption_renewal_lead_days = fields.Integer(
        string="Renewal Lead Time (days)",
        default=60,
        help="How long before expiry a renewal is requested. The point is to "
        "hold a signed replacement before the old certificate lapses, rather "
        "than after a sale has already been taxed wrongly.",
    )
    us_tax_exemption_signature_backend = fields.Selection(
        [("none", "None")],
        string="Certificate Signature Backend",
        default="none",
        required=True,
        help="Which e-signature service is asked for a certificate. Each "
        "bridge module adds itself here; with none selected a renewal is "
        "flagged in the log and nothing is sent.",
    )
