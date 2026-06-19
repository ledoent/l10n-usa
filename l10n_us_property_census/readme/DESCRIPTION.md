Adds the **US Census Geocoder** as a `property.data.source` for
[property_data_base](https://github.com/OCA/l10n-usa).

The Census geocoder is **free and requires no API key**. It resolves a US
address to a latitude/longitude and the 5-digit county FIPS code, which is the
starting point for parcel and footprint lookups by the other connectors.

It is seeded as a high-priority (low sequence) source on install, so it runs
ahead of any paid geocoder. Note that Census geocoding is range-interpolated and
is weaker on rural and new-construction addresses; pair it with a commercial or
OSM fallback when accuracy matters.
