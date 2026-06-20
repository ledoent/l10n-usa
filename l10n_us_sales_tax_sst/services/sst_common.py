# Copyright 2026 Binhex - Carlos R. Rodriguez.
# License LGPL-3.0 or later (https://www.gnu.org/licenses/lgpl).
"""Shared constants and helpers for the SST Rate & Boundary integration."""

# Re-exported from the engine so the importer and the taxability-matrix wizard
# parse dates (incl. open-ended sentinels) identically.
from odoo.addons.l10n_us_sales_tax_engine.tools import (  # noqa: F401
    OPEN_ENDED,
    parse_sst_date,
)

# X12 Data Element 1721 "Jurisdiction Type" → engine us.tax.jurisdiction.type
# (which drives us_tax_level on the booked tax). Anything not listed is treated
# as a special district.
JTYPE_TO_LEVEL = {
    "45": "state",
    "00": "county",
    "01": "city",
    "02": "city",
    "03": "city",
    "05": "city",
}

# Engine product-category codes that take the SST reduced food/drug rate.
FOOD_DRUG_CATEGORIES = {"FOOD", "MEDICINE"}


def jtype_to_level(jurisdiction_type):
    """Map an X12 DE1721 jurisdiction-type code to an engine level."""
    return JTYPE_TO_LEVEL.get((jurisdiction_type or "").strip(), "district")


def parse_sst_rate(value):
    """Parse an SST decimal-fraction rate string (e.g. '0.04875') to float."""
    value = (value or "").strip()
    if not value:
        return 0.0
    try:
        return float(value)
    except ValueError:
        return 0.0
