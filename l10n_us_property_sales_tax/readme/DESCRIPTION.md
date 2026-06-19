Bridges [property_data_base](https://github.com/OCA/l10n-usa) into the US sales
tax engine so a transaction's tax jurisdiction is resolved from the **rooftop
address**, not just the ZIP.

A ZIP can straddle two tax jurisdictions, and ZIP-level data can only guess
(e.g. ZIP 15717 spans Indiana and Westmoreland counties). This module overrides
the engine's `_geocode_jurisdiction` hook: it geocodes the address with the
free property-data geocoder (US Census), gets the **county FIPS**, and matches
the county tax jurisdiction by FIPS. The engine then **learns** the result, so
the same address resolves to the correct county thereafter — **without a paid
tax-API call**.

Install it alongside `l10n_us_property_census` (the free geocoder) and the tax
engine; no configuration is required. County tax jurisdictions must carry their
FIPS codes for the match to land.
