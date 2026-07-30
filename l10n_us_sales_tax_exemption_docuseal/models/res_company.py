# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class ResCompany(models.Model):
    _inherit = "res.company"

    us_tax_exemption_signature_backend = fields.Selection(
        selection_add=[("docuseal", "DocuSeal")],
        ondelete={"docuseal": "set default"},
    )
