# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax Exemption Certificates (DocuSeal)",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Collect and manage US sales-tax exemption certificates from customers "
        "via DocuSeal e-signature, with validity tracking and signed-document "
        "archival."
    ),
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "maintainers": ["dnplkndll"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "depends": [
        "account",
    ],
    "external_dependencies": {"python": ["requests"]},
    "data": [
        "security/ir.model.access.csv",
        "security/security.xml",
        "data/ir_sequence_data.xml",
        "data/ir_cron_data.xml",
        "views/res_config_settings_views.xml",
        "views/tax_exemption_certificate_views.xml",
        "views/res_partner_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
