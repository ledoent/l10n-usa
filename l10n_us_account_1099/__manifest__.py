# Copyright 2026 Ledo Enterprises
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
{
    "name": "US 1099 Information Returns",
    "version": "18.0.1.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Determine, aggregate and export US 1099-NEC / 1099-MISC information "
        "returns from vendor bills, with W-9 classification, payment-category "
        "box mapping and effective-dated thresholds."
    ),
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "maintainers": ["dnplkndll"],
    "website": "https://github.com/OCA/l10n-usa",
    "license": "LGPL-3",
    "development_status": "Alpha",
    "depends": [
        "account",
    ],
    "data": [
        "security/ir.model.access.csv",
        "data/l10n_us_1099_box_data.xml",
        "data/l10n_us_1099_threshold_data.xml",
        "views/l10n_us_1099_box_views.xml",
        "views/res_partner_views.xml",
        "views/account_account_views.xml",
        "views/account_move_views.xml",
        "views/l10n_us_1099_line_views.xml",
        "wizards/l10n_us_1099_generate_views.xml",
        "wizards/l10n_us_1099_export_views.xml",
        "views/menus.xml",
    ],
    "installable": True,
}
