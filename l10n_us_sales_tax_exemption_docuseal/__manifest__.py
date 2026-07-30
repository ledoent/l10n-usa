# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax - Exemption Certificates via DocuSeal",
    "summary": "Collect exemption certificates with DocuSeal e-signature",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Localization",
    "maintainers": ["dnplkndll"],
    "development_status": "Alpha",
    "depends": ["l10n_us_sales_tax_exemption_renewal"],
    "data": [
        "views/res_config_settings_views.xml",
        "views/us_tax_exemption_views.xml",
    ],
    "installable": True,
}
