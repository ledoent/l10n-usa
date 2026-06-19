# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    property_data_realie_api_key = fields.Char(
        string="Realie API Key",
        config_parameter="property_data.realie.api_key",
    )
