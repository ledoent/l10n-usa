# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
from odoo import models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    def action_open_property_sources(self):
        return self.env["ir.actions.actions"]._for_xml_id(
            "property_data_base.action_property_data_source"
        )
