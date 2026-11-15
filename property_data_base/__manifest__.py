# Copyright 2026 Ledo Enterprises
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Property Data Base",
    "summary": "Provider-agnostic property/parcel data: geocoding, "
    "parcel boundaries, attributes, owner and footprints",
    "version": "18.0.1.0.0",
    "license": "AGPL-3",
    "author": "Ledo Enterprises, Odoo Community Association (OCA)",
    "website": "https://github.com/OCA/l10n-usa",
    "category": "Tools",
    "maintainers": ["dnplkndll"],
    "development_status": "Alpha",
    "depends": ["base", "mail"],
    "data": [
        "security/property_data_security.xml",
        "security/ir.model.access.csv",
        "views/property_data_source_views.xml",
        "views/property_record_views.xml",
        "views/res_partner_views.xml",
        "views/res_config_settings_views.xml",
        "views/property_data_menu.xml",
    ],
    "installable": True,
    "application": False,
}
