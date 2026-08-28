# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US Sales Tax - Exemption Certificate Verification",
    "summary": "Verify exemption certificates against state systems, or on the record",
    "version": "18.0.1.0.0",
    "license": "LGPL-3",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Localization",
    "maintainers": ["dnplkndll"],
    "development_status": "Alpha",
    "depends": ["l10n_us_sales_tax_exemption"],
    "data": [
        "security/ir.model.access.csv",
        "data/us_tax_exemption_verifier.xml",
        "views/us_tax_exemption_verification_views.xml",
        "views/us_tax_exemption_verifier_views.xml",
        "views/us_tax_exemption_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
