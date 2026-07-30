# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    us_tax_exemption_signature_backend = fields.Selection(
        selection_add=[("sign_oca", "Sign Oca")],
        ondelete={"sign_oca": "set default"},
    )
    us_tax_exemption_sign_template_id = fields.Many2one(
        "sign.oca.template",
        string="Exemption Certificate Template",
        help="Template sent when an exemption certificate is requested.",
    )
