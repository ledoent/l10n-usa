# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
from odoo import fields, models

from .docuseal_client import (
    PARAM_SECRET,
    PARAM_TEMPLATE,
    PARAM_TOKEN,
    PARAM_URL,
)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    docuseal_url = fields.Char(
        string="DocuSeal URL",
        config_parameter=PARAM_URL,
        help="Base URL of the DocuSeal instance, e.g. "
        "https://docuseal.example.com",
    )
    docuseal_api_token = fields.Char(
        string="DocuSeal API Token",
        config_parameter=PARAM_TOKEN,
    )
    docuseal_template_id = fields.Char(
        string="Default Exemption Template",
        config_parameter=PARAM_TEMPLATE,
        help="DocuSeal template id used by default for exemption certificates.",
    )
    docuseal_webhook_secret = fields.Char(
        string="Webhook Signing Secret",
        config_parameter=PARAM_SECRET,
        help="Optional. When set, incoming DocuSeal webhooks must carry a "
        "matching X-Docuseal-Signature HMAC-SHA256 header.",
    )
