# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "US Property Data - Realie",
    "summary": "Realie.ai parcel geometry, attributes and ownership source",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Localization",
    "maintainers": ["dnplkndll"],
    "development_status": "Alpha",
    "depends": ["property_data_base"],
    "data": [
        "data/property_data_source.xml",
        "views/res_config_settings_views.xml",
    ],
    "installable": True,
}
