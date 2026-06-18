# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models


class L10nUs1099Export(models.TransientModel):
    _name = "l10n.us.1099.export"
    _description = "1099 CSV Export"

    filename = fields.Char()
    data = fields.Binary(string="File", readonly=True)
