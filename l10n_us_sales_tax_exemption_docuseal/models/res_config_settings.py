# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models

from .docuseal_client import PARAM_SECRET, PARAM_TEMPLATE, PARAM_TOKEN, PARAM_URL


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    docuseal_url = fields.Char(
        string="DocuSeal URL",
        config_parameter=PARAM_URL,
        help="Base URL of the DocuSeal instance, e.g. https://sign.example.com",
    )
    docuseal_api_token = fields.Char(
        string="DocuSeal API Token", config_parameter=PARAM_TOKEN
    )
    docuseal_template_id = fields.Char(
        string="Exemption Template ID",
        config_parameter=PARAM_TEMPLATE,
        help="Template sent when an exemption certificate is requested.",
    )
    docuseal_webhook_secret = fields.Char(
        string="Webhook Secret",
        config_parameter=PARAM_SECRET,
        help="Shared secret DocuSeal signs webhook deliveries with. Leave "
        "empty only on a trusted network — deliveries are then unverified.",
    )
