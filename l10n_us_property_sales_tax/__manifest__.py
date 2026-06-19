# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "US Property Geocode -> Sales Tax Jurisdiction",
    "summary": "Resolve the correct tax jurisdiction from an address via a free "
    "geocode (county FIPS), feeding the engine's learned cache",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Localization",
    "maintainers": ["dnplkndll"],
    "development_status": "Alpha",
    "depends": [
        "l10n_us_sales_tax_engine",
        "property_data_base",
        "l10n_us_property_census",
    ],
    "installable": True,
}
